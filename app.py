"""Flask web application — replaces the crashed tkinter UI."""

import json
import os
import queue
import subprocess
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
#  Routes
# =========================================================

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/config-status")
def config_status():
    """Tells the UI whether server-side credentials are configured — no values exposed."""
    configured = bool(
        config.INTERNAL_AI_ENDPOINT
        and config.INTERNAL_AI_KEY
        and config.INTERNAL_AI_SECRET
    )
    return jsonify({"credentials_configured": configured})


@app.route("/browse", methods=["POST"])
def browse():
    """Open a native folder picker dialog — cross-platform."""
    import sys
    try:
        if sys.platform == "darwin":
            # macOS — osascript
            result = subprocess.run(
                ["osascript", "-e", "set f to choose folder\nPOSIX path of f"],
                capture_output=True, text=True, timeout=60,
            )
            if result.returncode == 0:
                return jsonify({"path": result.stdout.strip()})
            return jsonify({"error": "Dialog cancelled"}), 400

        elif sys.platform == "win32":
            # Windows — PowerShell FolderBrowserDialog
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
            path = result.stdout.strip()
            if result.returncode == 0 and path:
                return jsonify({"path": path})
            return jsonify({"error": "Dialog cancelled"}), 400

        else:
            # Linux — try zenity, fall back to kdialog
            for cmd in [
                ["zenity", "--file-selection", "--directory", "--title=Select .NET solution folder"],
                ["kdialog", "--getexistingdirectory", os.path.expanduser("~")],
            ]:
                try:
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                    path = result.stdout.strip()
                    if result.returncode == 0 and path:
                        return jsonify({"path": path})
                except FileNotFoundError:
                    continue
            return jsonify({"error": "No folder dialog available. Please paste the path manually."}), 400

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/analyze", methods=["POST"])
def analyze():
    data = request.get_json(force=True)
    folder = (data.get("folder") or "").strip()

    if not folder or not os.path.isdir(folder):
        return jsonify({"error": "Invalid or missing folder path"}), 400

    progress: list[str] = []

    from generator.orchestrator import analyze_only
    solution, coverage = analyze_only(folder, progress.append)

    if not solution:
        return jsonify({"error": "No .sln file found in selected folder",
                        "progress": progress}), 404

    _state["solution"] = solution

    return jsonify({
        "progress": progress,
        "solution": _ser_solution(solution),
        "coverage": _ser_coverage(coverage),
    })


@app.route("/generate", methods=["POST"])
def generate():
    data = request.get_json(force=True)
    framework = (data.get("framework") or config.DEFAULT_TEST_FRAMEWORK).strip()
    # Model is server-side config only — never from the client
    model = config.AI_MODEL

    # Credentials are loaded from server-side env / .env only — never from the client
    if not (config.INTERNAL_AI_ENDPOINT and config.INTERNAL_AI_KEY and config.INTERNAL_AI_SECRET):
        return jsonify({"error": "AI API credentials are not configured on this server. "
                                 "Set INTERNAL_AI_ENDPOINT, INTERNAL_AI_KEY, and "
                                 "INTERNAL_AI_SECRET in .env or environment variables."}), 503
    if not _state["solution"]:
        return jsonify({"error": "Analyze a solution first"}), 400

    credentials = AICredentials(
        endpoint=config.INTERNAL_AI_ENDPOINT,
        api_key=config.INTERNAL_AI_KEY,
        api_secret=config.INTERNAL_AI_SECRET,
        model=model,
    )

    # Flush stale queue entries
    while not _state["progress_queue"].empty():
        try:
            _state["progress_queue"].get_nowait()
        except queue.Empty:
            break

    def run():
        from generator.orchestrator import generate_all_tests

        def cb(msg):
            _state["progress_queue"].put({"type": "log", "msg": msg})

        try:
            result = generate_all_tests(
                solution=_state["solution"],
                credentials=credentials,
                test_framework=framework,
                progress_cb=cb,
            )
            _state["progress_queue"].put({"type": "done", "result": _ser_result(result)})
        except Exception:
            import traceback
            _state["progress_queue"].put({"type": "error", "msg": traceback.format_exc()})

    threading.Thread(target=run, daemon=True).start()
    return jsonify({"status": "started"})


@app.route("/generate-stream")
def generate_stream():
    """SSE endpoint — streams progress messages to the browser."""
    def event_gen():
        while True:
            try:
                msg = _state["progress_queue"].get(timeout=30)
                yield f"data: {json.dumps(msg)}\n\n"
                if msg["type"] in ("done", "error"):
                    break
            except queue.Empty:
                yield "data: {\"type\":\"ping\"}\n\n"

    return Response(
        stream_with_context(event_gen()),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
        "line_pct": cov.line_pct,
        "branch_pct": cov.branch_pct,
        "error": cov.error,
        "packages": [
            {
                "name": pkg.name,
                "line_pct": pkg.line_pct,
                "branch_pct": pkg.branch_pct,
                "classes": [
                    {"name": c.name, "line_pct": c.line_pct, "branch_pct": c.branch_pct}
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
                "class_name": t.class_name,
                "test_file": os.path.basename(t.test_file_path),
                "source_project": t.source_project,
                "test_project": t.test_project,
                "method_count": t.method_count,
            }
            for t in result.generated_tests
        ],
        "coverage_before": _ser_coverage(result.coverage_before),
        "coverage_after":  _ser_coverage(result.coverage_after),
        "errors": result.errors,
    }
