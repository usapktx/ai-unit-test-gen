"""Flask web application."""

import json
import os
import queue
import subprocess
import sys
import threading

from flask import Flask, Response, jsonify, render_template, request, stream_with_context

import config
from config import AICredentials

app = Flask(__name__)

# ---------- single-user in-process state ----------
_state: dict = {
    "solution": None,
    "progress_queue": queue.Queue(),
}


# =========================================================
#  Helpers
# =========================================================

def _normalize_path(raw: str) -> str:
    """Strip quotes, whitespace, carriage returns, then normalize separators."""
    path = (raw or "").strip().strip('"').strip("'").strip('\r').strip()
    return os.path.normpath(path) if path else ""


def _flush_queue():
    while not _state["progress_queue"].empty():
        try:
            _state["progress_queue"].get_nowait()
        except queue.Empty:
            break


def _sse_stream():
    """
    Generator that reads from the shared progress queue and yields SSE events.
    Sends a keepalive ping every 25 s of silence. Stops on done/error message.
    """
    while True:
        try:
            msg = _state["progress_queue"].get(timeout=25)
            yield f"data: {json.dumps(msg)}\n\n"
            if msg["type"] in ("done", "error"):
                break
        except queue.Empty:
            yield 'data: {"type":"ping"}\n\n'


def _sse_response():
    """Return a Flask Response that streams _sse_stream() with correct headers."""
    return Response(
        stream_with_context(_sse_stream()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",      # nginx: disable proxy buffering
            "Connection":        "keep-alive",
        },
    )


# =========================================================
#  Routes
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/config-status")
def config_status():
    """Returns whether server-side credentials are configured — no values exposed."""
    configured = bool(
        config.INTERNAL_AI_ENDPOINT
        and config.INTERNAL_AI_KEY
        and config.INTERNAL_AI_SECRET
    )
    return jsonify({"credentials_configured": configured})


# ── Browse ────────────────────────────────────────────────────────────────────

@app.route("/browse", methods=["POST"])
def browse():
    """Open a native folder picker dialog — cross-platform."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(
                ["osascript", "-e", "set f to choose folder\nPOSIX path of f"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return jsonify({"path": result.stdout.strip()})
            return jsonify({"error": "Dialog cancelled"}), 400

        elif sys.platform == "win32":
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
                "$d.Description = 'Select .NET solution folder';"
                "[void]$d.ShowDialog();"
                "$d.SelectedPath"
            )
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_script],
                capture_output=True, text=True, timeout=60,
            )
            path = result.stdout.strip().strip('\r').strip()
            if result.returncode == 0 and path:
                return jsonify({"path": os.path.normpath(path)})
            return jsonify({"error": "Dialog cancelled"}), 400

        else:
            for cmd in [
                ["zenity", "--file-selection", "--directory",
                 "--title=Select .NET solution folder"],
                ["kdialog", "--getexistingdirectory", os.path.expanduser("~")],
            ]:
                try:
                    result = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=60
                    )
                    path = result.stdout.strip()
                    if result.returncode == 0 and path:
                        return jsonify({"path": path})
                except FileNotFoundError:
                    continue
            return jsonify({
                "error": "No folder dialog available. Please paste the path manually."
            }), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Analyze ───────────────────────────────────────────────────────────────────

@app.route("/analyze", methods=["POST"])
def analyze():
    """Validate path, start background analysis, return immediately."""
    data   = request.get_json(force=True)
    folder = _normalize_path(data.get("folder") or "")

    if not folder or not os.path.isdir(folder):
        return jsonify({
            "error": f"Folder not found: '{folder}'. "
                     "Verify the path exists and the app has permission to read it."
        }), 400

    _flush_queue()

    def run():
        def cb(msg):
            _state["progress_queue"].put({"type": "log", "msg": msg})
        try:
            from generator.orchestrator import analyze_only
            solution, coverage = analyze_only(folder, cb)
            if not solution:
                _state["progress_queue"].put({
                    "type": "error",
                    "msg":  "No .sln file found in the selected folder or its subdirectories."
                })
                return
            _state["solution"] = solution
            _state["progress_queue"].put({
                "type":   "done",
                "result": {
                    "solution": _ser_solution(solution),
                    "coverage": _ser_coverage(coverage),
                },
            })
        except Exception:
            import traceback
            _state["progress_queue"].put({
                "type": "error", "msg": traceback.format_exc()
            })

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/analyze-stream")
def analyze_stream():
    """SSE stream for real-time analyze progress."""
    return _sse_response()


# ── Generate ──────────────────────────────────────────────────────────────────

@app.route("/generate", methods=["POST"])
def generate():
    """Validate credentials, start background generation, return immediately."""
    data      = request.get_json(force=True)
    framework = (data.get("framework") or config.DEFAULT_TEST_FRAMEWORK).strip()
    model     = config.AI_MODEL   # never from the client

    if not (config.INTERNAL_AI_ENDPOINT
            and config.INTERNAL_AI_KEY
            and config.INTERNAL_AI_SECRET):
        return jsonify({
            "error": "AI API credentials are not configured on this server. "
                     "Set INTERNAL_AI_ENDPOINT, INTERNAL_AI_KEY, and "
                     "INTERNAL_AI_SECRET in .env or environment variables."
        }), 503

    if not _state["solution"]:
        return jsonify({"error": "Analyze a solution first."}), 400

    credentials = AICredentials(
        endpoint=config.INTERNAL_AI_ENDPOINT,
        api_key=config.INTERNAL_AI_KEY,
        api_secret=config.INTERNAL_AI_SECRET,
        model=model,
    )

    _flush_queue()

    def run():
        def cb(msg):
            _state["progress_queue"].put({"type": "log", "msg": msg})
        try:
            from generator.orchestrator import generate_all_tests
            result = generate_all_tests(
                solution=_state["solution"],
                credentials=credentials,
                test_framework=framework,
                progress_cb=cb,
            )
            _state["progress_queue"].put({
                "type": "done", "result": _ser_result(result)
            })
        except Exception:
            import traceback
            _state["progress_queue"].put({
                "type": "error", "msg": traceback.format_exc()
            })

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/generate-stream")
def generate_stream():
    """SSE stream for real-time generate progress."""
    return _sse_response()


# =========================================================
#  Serialisation helpers
# =========================================================

def _ser_solution(sol):
    return {
        "name": os.path.basename(sol.sln_path),
        "source_projects": [
            {"name": p.name, "framework": p.target_framework or "?",
             "files": len(p.source_files)}
            for p in sol.source_projects
        ],
        "test_projects": [
            {"name": p.name, "framework": p.target_framework or "?",
             "test_framework": p.test_framework or "?"}
            for p in sol.test_projects
        ],
    }


def _ser_coverage(cov):
    if cov is None:
        return None
    return {
        "line_pct":   cov.line_pct,
        "branch_pct": cov.branch_pct,
        "error":      cov.error,
        "packages": [
            {
                "name":       pkg.name,
                "line_pct":   pkg.line_pct,
                "branch_pct": pkg.branch_pct,
                "classes": [
                    {"name": c.name,
                     "line_pct": c.line_pct,
                     "branch_pct": c.branch_pct}
                    for c in sorted(pkg.classes, key=lambda x: x.line_rate)
                ],
            }
            for pkg in cov.packages
        ],
    }


def _ser_result(result):
    return {
        "generated_tests": [
            {
                "class_name":    t.class_name,
                "test_file":     os.path.basename(t.test_file_path),
                "source_project": t.source_project,
                "test_project":  t.test_project,
                "method_count":  t.method_count,
            }
            for t in result.generated_tests
        ],
        "coverage_before": _ser_coverage(result.coverage_before),
        "coverage_after":  _ser_coverage(result.coverage_after),
        "errors":          result.errors,
    }
