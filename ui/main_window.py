"""Main application window — tkinter UI for .NET Unit Test Generator."""

import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from typing import Optional

import config
from generator.orchestrator import analyze_only, generate_all_tests, OrchestrationResult
from coverage.coverage_runner import CoverageReport

# ---------- colour palette ----------
BG         = "#1e1e2e"
SURFACE    = "#2a2a3e"
ACCENT     = "#7c3aed"      # violet
ACCENT2    = "#06b6d4"      # cyan
SUCCESS    = "#22c55e"
WARNING    = "#f59e0b"
ERROR_COL  = "#ef4444"
TEXT       = "#e2e8f0"
TEXT_DIM   = "#94a3b8"
TEXT_DARK  = "#1e1e2e"
BORDER     = "#3f3f5c"

FONT_BODY  = ("Segoe UI", 10)
FONT_BOLD  = ("Segoe UI", 10, "bold")
FONT_MONO  = ("Courier New", 9)
FONT_HEAD  = ("Segoe UI", 13, "bold")
FONT_TITLE = ("Segoe UI", 16, "bold")


class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(".NET Unit Test Generator — GPT-5 Powered")
        self.root.geometry("1280x860")
        self.root.minsize(1000, 700)
        self.root.configure(bg=BG)

        self._queue: queue.Queue = queue.Queue()
        self._solution = None
        self._coverage_before = None  # type: Optional[CoverageReport]

        self._folder_var = tk.StringVar()
        self._api_key_var = tk.StringVar(value=config.OPENAI_API_KEY)
        self._model_var = tk.StringVar(value=config.OPENAI_MODEL)
        self._framework_var = tk.StringVar(value=config.DEFAULT_TEST_FRAMEWORK)
        self._status_var = tk.StringVar(value="Ready")
        self._show_key_var = tk.BooleanVar(value=False)

        self._build_ui()
        self._poll_queue()

    # =========================================================
    #  UI construction
    # =========================================================
    def _build_ui(self):
        self._apply_styles()

        # ---- title bar ----
        title_bar = tk.Frame(self.root, bg=ACCENT, height=48)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)
        tk.Label(
            title_bar,
            text="  .NET Unit Test Generator",
            font=FONT_TITLE, fg="white", bg=ACCENT, anchor="w",
        ).pack(side="left", padx=12, pady=8)
        tk.Label(
            title_bar,
            text="Powered by GPT-5",
            font=FONT_BODY, fg="#c4b5fd", bg=ACCENT, anchor="e",
        ).pack(side="right", padx=12)

        # ---- main content ----
        main = tk.Frame(self.root, bg=BG)
        main.pack(fill="both", expand=True, padx=16, pady=12)

        # top section: folder + settings
        self._build_top_section(main)

        # middle: two columns (structure | coverage-before)
        self._build_analysis_section(main)

        # generate button
        self._build_generate_section(main)

        # progress log
        self._build_log_section(main)

        # bottom: two columns (new tests | coverage-after)
        self._build_results_section(main)

        # status bar
        sb = tk.Frame(self.root, bg=SURFACE, height=28)
        sb.pack(fill="x", side="bottom")
        sb.pack_propagate(False)
        tk.Label(
            sb, textvariable=self._status_var,
            font=("Segoe UI", 9), fg=TEXT_DIM, bg=SURFACE, anchor="w",
        ).pack(side="left", padx=12, pady=4)

    def _apply_styles(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("TButton", font=FONT_BOLD, padding=6)
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=FONT_BOLD, padding=8)
        style.map("Accent.TButton",
                  background=[("active", "#6d28d9"), ("pressed", "#5b21b6")])
        style.configure("Gen.TButton", background=SUCCESS, foreground=TEXT_DARK,
                        font=("Segoe UI", 11, "bold"), padding=10)
        style.map("Gen.TButton",
                  background=[("active", "#16a34a"), ("pressed", "#15803d")])
        style.configure("TLabelframe", background=SURFACE, bordercolor=BORDER)
        style.configure("TLabelframe.Label", background=SURFACE, foreground=ACCENT2,
                        font=FONT_BOLD)
        style.configure("Treeview", background=SURFACE, foreground=TEXT,
                        fieldbackground=SURFACE, rowheight=22, font=FONT_BODY)
        style.configure("Treeview.Heading", background=BORDER, foreground=TEXT,
                        font=FONT_BOLD)
        style.map("Treeview", background=[("selected", ACCENT)])
        style.configure("TEntry", fieldbackground=SURFACE, foreground=TEXT,
                        insertcolor=TEXT)
        style.configure("TCombobox", fieldbackground=SURFACE, foreground=TEXT)
        style.configure("TProgressbar", troughcolor=SURFACE, background=ACCENT2)

    # ---------- TOP SECTION ----------
    def _build_top_section(self, parent):
        frame = tk.Frame(parent, bg=SURFACE, relief="flat", bd=0)
        frame.pack(fill="x", pady=(0, 10))
        _inner = tk.Frame(frame, bg=SURFACE)
        _inner.pack(fill="x", padx=14, pady=10)

        # Row 1: folder
        row1 = tk.Frame(_inner, bg=SURFACE)
        row1.pack(fill="x", pady=(0, 6))
        tk.Label(row1, text="Solution Folder:", font=FONT_BOLD,
                 fg=TEXT, bg=SURFACE, width=15, anchor="w").pack(side="left")
        ttk.Entry(row1, textvariable=self._folder_var,
                  font=FONT_BODY, width=60).pack(side="left", padx=(0, 6), fill="x", expand=True)
        ttk.Button(row1, text="Browse...", style="Accent.TButton",
                   command=self._browse_folder).pack(side="left", padx=(0, 6))
        self._analyze_btn = ttk.Button(row1, text="Analyze Solution",
                                       style="Accent.TButton",
                                       command=self._start_analyze)
        self._analyze_btn.pack(side="left")

        # Row 2: API key + model + framework
        row2 = tk.Frame(_inner, bg=SURFACE)
        row2.pack(fill="x")
        tk.Label(row2, text="OpenAI API Key:", font=FONT_BOLD,
                 fg=TEXT, bg=SURFACE, width=15, anchor="w").pack(side="left")

        self._key_entry = ttk.Entry(row2, textvariable=self._api_key_var,
                                    show="*", font=FONT_BODY, width=36)
        self._key_entry.pack(side="left", padx=(0, 4))
        ttk.Checkbutton(row2, text="Show",
                        variable=self._show_key_var,
                        command=self._toggle_key_visibility).pack(side="left", padx=(0, 12))

        tk.Label(row2, text="Model:", font=FONT_BOLD,
                 fg=TEXT, bg=SURFACE).pack(side="left")
        ttk.Entry(row2, textvariable=self._model_var,
                  font=FONT_BODY, width=18).pack(side="left", padx=(4, 12))

        tk.Label(row2, text="Framework:", font=FONT_BOLD,
                 fg=TEXT, bg=SURFACE).pack(side="left")
        fw_combo = ttk.Combobox(row2, textvariable=self._framework_var,
                                values=["xunit", "nunit", "mstest"],
                                state="readonly", width=10, font=FONT_BODY)
        fw_combo.pack(side="left", padx=4)

    # ---------- ANALYSIS SECTION ----------
    def _build_analysis_section(self, parent):
        pane = tk.Frame(parent, bg=BG)
        pane.pack(fill="both", expand=False, pady=(0, 8))
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)
        pane.rowconfigure(0, weight=1)

        # Left: solution tree
        lf_tree = ttk.LabelFrame(pane, text="Solution Structure", padding=6)
        lf_tree.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._sol_tree = ttk.Treeview(lf_tree, show="tree headings",
                                      columns=("type", "framework"),
                                      height=8)
        self._sol_tree.heading("#0", text="Name")
        self._sol_tree.heading("type", text="Type")
        self._sol_tree.heading("framework", text="Framework")
        self._sol_tree.column("#0", width=200)
        self._sol_tree.column("type", width=80)
        self._sol_tree.column("framework", width=90)
        self._sol_tree.pack(fill="both", expand=True)
        _scrollbar(lf_tree, self._sol_tree)

        # Right: coverage before
        lf_cov = ttk.LabelFrame(pane, text="Coverage Before Generation", padding=6)
        lf_cov.grid(row=0, column=1, sticky="nsew")
        self._cov_before_tree = self._make_coverage_tree(lf_cov)

    # ---------- GENERATE SECTION ----------
    def _build_generate_section(self, parent):
        frame = tk.Frame(parent, bg=BG)
        frame.pack(fill="x", pady=6)
        self._gen_btn = ttk.Button(
            frame,
            text="⚡  Generate Unit Tests with GPT-5",
            style="Gen.TButton",
            command=self._start_generate,
            state="disabled",
        )
        self._gen_btn.pack(expand=True)

        self._progress_bar = ttk.Progressbar(
            frame, mode="indeterminate", style="TProgressbar", length=400
        )
        self._progress_bar.pack(expand=True, pady=(4, 0))

    # ---------- LOG SECTION ----------
    def _build_log_section(self, parent):
        lf = ttk.LabelFrame(parent, text="Progress Log", padding=4)
        lf.pack(fill="both", expand=True, pady=(0, 8))
        self._log = tk.Text(
            lf, bg="#0f0f1a", fg=TEXT, font=FONT_MONO,
            height=10, wrap="word", state="disabled",
            insertbackground=TEXT, relief="flat",
        )
        self._log.pack(fill="both", expand=True)
        sb = ttk.Scrollbar(lf, orient="vertical", command=self._log.yview)
        self._log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        # Tag styles
        self._log.tag_configure("info",    foreground=TEXT)
        self._log.tag_configure("success", foreground=SUCCESS)
        self._log.tag_configure("warn",    foreground=WARNING)
        self._log.tag_configure("error",   foreground=ERROR_COL)
        self._log.tag_configure("section", foreground=ACCENT2, font=FONT_BOLD)

    # ---------- RESULTS SECTION ----------
    def _build_results_section(self, parent):
        pane = tk.Frame(parent, bg=BG)
        pane.pack(fill="both", expand=False)
        pane.columnconfigure(0, weight=1)
        pane.columnconfigure(1, weight=1)

        # Left: new tests added
        lf_new = ttk.LabelFrame(pane, text="New Tests Added", padding=6)
        lf_new.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self._new_tests_tree = ttk.Treeview(
            lf_new, show="tree headings",
            columns=("project", "methods"),
            height=8,
        )
        self._new_tests_tree.heading("#0", text="Test Class")
        self._new_tests_tree.heading("project", text="Test Project")
        self._new_tests_tree.heading("methods", text="Methods")
        self._new_tests_tree.column("#0", width=200)
        self._new_tests_tree.column("project", width=180)
        self._new_tests_tree.column("methods", width=70, anchor="center")
        self._new_tests_tree.pack(fill="both", expand=True)
        _scrollbar(lf_new, self._new_tests_tree)

        # Right: coverage after
        lf_cov2 = ttk.LabelFrame(pane, text="Coverage After Generation", padding=6)
        lf_cov2.grid(row=0, column=1, sticky="nsew")
        self._cov_after_tree = self._make_coverage_tree(lf_cov2)

    def _make_coverage_tree(self, parent) -> ttk.Treeview:
        tree = ttk.Treeview(
            parent, show="tree headings",
            columns=("lines", "branches"),
            height=8,
        )
        tree.heading("#0", text="Class / Package")
        tree.heading("lines", text="Line %")
        tree.heading("branches", text="Branch %")
        tree.column("#0", width=220)
        tree.column("lines", width=80, anchor="center")
        tree.column("branches", width=90, anchor="center")
        tree.pack(fill="both", expand=True)
        _scrollbar(parent, tree)
        return tree

    # =========================================================
    #  Actions
    # =========================================================
    def _browse_folder(self):
        path = filedialog.askdirectory(title="Select .NET Solution Folder")
        if path:
            self._folder_var.set(path)

    def _toggle_key_visibility(self):
        self._key_entry.configure(show="" if self._show_key_var.get() else "*")

    def _start_analyze(self):
        folder = self._folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("No Folder", "Please select a valid solution folder.")
            return
        self._set_busy(True)
        self._log_clear()
        self._log_line("=== Analyzing solution ===", "section")
        self._clear_analysis_ui()
        threading.Thread(target=self._analyze_thread, args=(folder,), daemon=True).start()

    def _analyze_thread(self, folder):
        try:
            solution, coverage = analyze_only(folder, self._log_queue)
            self._queue.put(("analyze_done", solution, coverage))
        except Exception as e:
            self._queue.put(("error", str(e)))

    def _start_generate(self):
        api_key = self._api_key_var.get().strip()
        if not api_key:
            messagebox.showwarning("API Key Missing",
                                   "Enter your OpenAI API key before generating tests.")
            return
        if not self._solution:
            messagebox.showwarning("No Solution", "Analyze a solution first.")
            return
        # Update config with current UI values
        config.OPENAI_MODEL = self._model_var.get().strip() or config.OPENAI_MODEL
        config.OPENAI_API_KEY = api_key

        self._set_busy(True)
        self._log_line("\n=== Generating unit tests ===", "section")
        self._clear_results_ui()
        threading.Thread(target=self._generate_thread, args=(api_key,), daemon=True).start()

    def _generate_thread(self, api_key):
        try:
            result = generate_all_tests(
                solution=self._solution,
                api_key=api_key,
                test_framework=self._framework_var.get(),
                progress_cb=self._log_queue,
            )
            self._queue.put(("generate_done", result))
        except Exception as e:
            import traceback
            self._queue.put(("error", traceback.format_exc()))

    # =========================================================
    #  Queue / threading helpers
    # =========================================================
    def _log_queue(self, msg: str):
        """Called from background threads."""
        self._queue.put(("log", msg))

    def _poll_queue(self):
        try:
            while True:
                item = self._queue.get_nowait()
                kind = item[0]
                if kind == "log":
                    self._log_line(item[1])
                elif kind == "analyze_done":
                    self._on_analyze_done(item[1], item[2])
                elif kind == "generate_done":
                    self._on_generate_done(item[1])
                elif kind == "error":
                    self._log_line(f"ERROR: {item[1]}", "error")
                    self._set_busy(False)
        except queue.Empty:
            pass
        self.root.after(80, self._poll_queue)

    # =========================================================
    #  Callbacks
    # =========================================================
    def _on_analyze_done(self, solution, coverage):
        self._solution = solution
        self._coverage_before = coverage

        if not solution:
            self._log_line("No .sln file found in the selected folder.", "error")
            self._set_busy(False)
            self._status_var.set("Analysis failed — no .sln found.")
            return

        self._populate_solution_tree(solution)
        self._populate_coverage_tree(self._cov_before_tree, coverage)

        n_src  = len(solution.source_projects)
        n_test = len(solution.test_projects)
        self._log_line(
            f"Analysis complete: {n_src} source project(s), {n_test} test project(s).",
            "success",
        )
        if coverage.ok:
            self._log_line(
                f"Current coverage — Lines: {coverage.line_pct}%  Branches: {coverage.branch_pct}%",
                "success",
            )
        else:
            self._log_line(f"Coverage note: {coverage.error}", "warn")

        self._gen_btn.configure(state="normal")
        self._set_busy(False)
        self._status_var.set(
            f"Ready — {n_src} source project(s) | Coverage: {coverage.line_pct}% lines"
        )

    def _on_generate_done(self, result: OrchestrationResult):
        # Populate new tests tree
        self._populate_new_tests_tree(result)
        # Populate coverage after
        if result.coverage_after:
            self._populate_coverage_tree(self._cov_after_tree, result.coverage_after)

        total = len(result.generated_tests)
        total_methods = sum(t.method_count for t in result.generated_tests)
        self._log_line(
            f"\nDone! Generated tests for {total} class(es), "
            f"{total_methods} test method(s) total.",
            "success",
        )
        if result.errors:
            for e in result.errors:
                self._log_line(f"Warning: {e}", "warn")
        if result.coverage_after:
            ca = result.coverage_after
            cb = result.coverage_before
            before_l = cb.line_pct if cb else 0.0
            self._log_line(
                f"Coverage: {before_l}% → {ca.line_pct}% lines  |  "
                f"Branches: {ca.branch_pct}%",
                "success",
            )
        self._set_busy(False)
        self._status_var.set("Generation complete.")

    # =========================================================
    #  Tree population helpers
    # =========================================================
    def _populate_solution_tree(self, solution):
        t = self._sol_tree
        for item in t.get_children():
            t.delete(item)

        src_node = t.insert("", "end", text="Source Projects",
                            values=("", ""), open=True)
        for p in solution.source_projects:
            t.insert(src_node, "end", text=p.name,
                     values=("Source", p.target_framework or "?"))

        tst_node = t.insert("", "end", text="Test Projects",
                            values=("", ""), open=True)
        for p in solution.test_projects:
            t.insert(tst_node, "end", text=p.name,
                     values=(f"Test/{p.test_framework}", p.target_framework or "?"))

    def _populate_coverage_tree(self, tree: ttk.Treeview, report: CoverageReport):
        for item in tree.get_children():
            tree.delete(item)

        tag = "ok" if report.line_pct >= 80 else ("warn" if report.line_pct >= 50 else "low")
        tree.tag_configure("ok",   foreground=SUCCESS)
        tree.tag_configure("warn", foreground=WARNING)
        tree.tag_configure("low",  foreground=ERROR_COL)

        overall = tree.insert(
            "", "end",
            text=f"Overall ({report.line_pct}%)",
            values=(f"{report.line_pct}%", f"{report.branch_pct}%"),
            open=True, tags=(tag,),
        )

        if report.error and not report.packages:
            tree.insert(overall, "end", text=report.error,
                        values=("—", "—"), tags=("warn",))
            return

        for pkg in report.packages:
            ptag = "ok" if pkg.line_pct >= 80 else ("warn" if pkg.line_pct >= 50 else "low")
            pkg_node = tree.insert(
                overall, "end",
                text=pkg.name,
                values=(f"{pkg.line_pct}%", f"{pkg.branch_pct}%"),
                open=False, tags=(ptag,),
            )
            for cls in sorted(pkg.classes, key=lambda c: c.line_rate):
                ctag = "ok" if cls.line_pct >= 80 else ("warn" if cls.line_pct >= 50 else "low")
                tree.insert(
                    pkg_node, "end",
                    text=cls.name,
                    values=(f"{cls.line_pct}%", f"{cls.branch_pct}%"),
                    tags=(ctag,),
                )

    def _populate_new_tests_tree(self, result: OrchestrationResult):
        t = self._new_tests_tree
        for item in t.get_children():
            t.delete(item)
        for info in result.generated_tests:
            t.insert(
                "", "end",
                text=f"{info.class_name}Tests.cs",
                values=(info.test_project, str(info.method_count)),
            )

    # =========================================================
    #  UI state helpers
    # =========================================================
    def _set_busy(self, busy: bool):
        state = "disabled" if busy else "normal"
        self._analyze_btn.configure(state=state)
        if not busy and self._solution:
            self._gen_btn.configure(state="normal")
        elif busy:
            self._gen_btn.configure(state="disabled")

        if busy:
            self._progress_bar.start(12)
            self._status_var.set("Working…")
        else:
            self._progress_bar.stop()
            self._progress_bar["value"] = 0

    def _log_clear(self):
        self._log.configure(state="normal")
        self._log.delete("1.0", "end")
        self._log.configure(state="disabled")

    def _log_line(self, msg: str, tag: str = "info"):
        self._log.configure(state="normal")
        if "error" in msg.lower() or "failed" in msg.lower():
            tag = "error"
        elif msg.startswith("===") or msg.startswith("\n==="):
            tag = "section"
        elif "warning" in msg.lower() or "warn" in msg.lower():
            tag = "warn"
        elif "done" in msg.lower() or "complete" in msg.lower() or "success" in msg.lower():
            tag = "success"
        self._log.insert("end", msg + "\n", tag)
        self._log.see("end")
        self._log.configure(state="disabled")

    def _clear_analysis_ui(self):
        for item in self._sol_tree.get_children():
            self._sol_tree.delete(item)
        for item in self._cov_before_tree.get_children():
            self._cov_before_tree.delete(item)

    def _clear_results_ui(self):
        for item in self._new_tests_tree.get_children():
            self._new_tests_tree.delete(item)
        for item in self._cov_after_tree.get_children():
            self._cov_after_tree.delete(item)


# ---- helper ----
def _scrollbar(parent, widget):
    sb = ttk.Scrollbar(parent, orient="vertical", command=widget.yview)
    widget.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
