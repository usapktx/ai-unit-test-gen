"""
Top-level orchestration: analyze solution → gather coverage → generate tests → run coverage again.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from analyzer.solution_analyzer import SolutionInfo, DotNetProject, analyze_solution
from analyzer.csharp_parser import parse_file, CSharpClass
from coverage.coverage_runner import CoverageReport, run_coverage, estimate_coverage_static
from generator.test_generator import generate_tests_for_class, generate_missing_tests
from generator.project_manager import ensure_test_project, write_test_file
from config import AICredentials
import config


@dataclass
class GeneratedTestInfo:
    class_name: str
    test_file_path: str
    source_project: str
    test_project: str
    method_count: int = 0


@dataclass
class OrchestrationResult:
    solution: Optional[SolutionInfo]
    coverage_before: Optional[CoverageReport]
    coverage_after: Optional[CoverageReport]
    generated_tests: List[GeneratedTestInfo] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    used_static_estimate: bool = False


def analyze_only(
    folder_path: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> tuple:
    """
    Parse the solution and compute current coverage.
    Returns (SolutionInfo, CoverageReport).
    """
    if progress_cb:
        progress_cb("Scanning for .sln file...")

    solution = analyze_solution(folder_path, progress_cb=progress_cb)
    if not solution:
        return None, CoverageReport(0.0, 0.0, error="No .sln file found in folder.")

    coverage = _run_or_estimate_coverage(solution, progress_cb)
    return solution, coverage


def generate_all_tests(
    solution: SolutionInfo,
    credentials: AICredentials,
    test_framework: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> OrchestrationResult:
    """
    For every source project, generate unit tests and return the result.
    """
    result = OrchestrationResult(
        solution=solution,
        coverage_before=None,
        coverage_after=None,
    )

    if progress_cb:
        progress_cb("=== Measuring coverage BEFORE generation (static analysis) ===")
    result.coverage_before = _static_coverage(solution, progress_cb)

    for src_proj in solution.source_projects:
        if progress_cb:
            progress_cb(f"\n--- Processing: {src_proj.name} ---")

        # Determine test framework for this project
        tf = test_framework
        for tp in solution.test_projects:
            if tp.test_framework:
                tf = tp.test_framework
                break

        test_proj = ensure_test_project(solution, src_proj, tf, progress_cb)
        if not test_proj:
            result.errors.append(f"Could not find or create test project for {src_proj.name}")
            continue

        # Process each source file
        for sf in src_proj.source_files:
            _process_source_file(
                sf, src_proj, test_proj, credentials, tf, result, progress_cb
            )

    if progress_cb:
        progress_cb("\n=== Measuring coverage AFTER generation (static analysis) ===")
    result.coverage_after = _static_coverage(solution, progress_cb)

    return result


METHODS_PER_BATCH = 5


def _process_source_file(
    source_file: str,
    src_proj: DotNetProject,
    test_proj: DotNetProject,
    credentials: AICredentials,
    test_framework: str,
    result: OrchestrationResult,
    progress_cb,
):
    import re
    parsed = parse_file(source_file)
    if not parsed:
        return

    for cls in parsed.classes:
        if cls.is_interface:
            continue
        if not cls.public_methods and not cls.constructors and not cls.properties:
            continue
        if "generated" in cls.name.lower() or cls.name.endswith("Designer"):
            continue

        try:
            with open(source_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                source_code = f.read()
        except OSError:
            continue

        existing_test_file = os.path.join(test_proj.abs_path, f"{cls.name}Tests.cs")
        existing_test_code = ""
        if os.path.isfile(existing_test_file):
            try:
                with open(existing_test_file, "r", encoding="utf-8-sig", errors="ignore") as f:
                    existing_test_code = f.read()
            except OSError:
                pass

        # Build full method list for batching
        all_methods = [m.name for m in cls.public_methods]
        if not all_methods:
            all_methods = [cls.name]  # at least constructors/properties

        # Split into batches to avoid token limits
        batches = [all_methods[i:i+METHODS_PER_BATCH]
                   for i in range(0, len(all_methods), METHODS_PER_BATCH)]
        total_batches = len(batches)

        if progress_cb:
            progress_cb(f"  Generating tests for: {cls.name} "
                        f"({len(all_methods)} methods, {total_batches} batch(es))")

        accumulated_code = existing_test_code
        total_methods_written = 0

        for batch_idx, batch in enumerate(batches, 1):
            if progress_cb and total_batches > 1:
                progress_cb(f"    Batch {batch_idx}/{total_batches}: {', '.join(batch)}")

            if not accumulated_code:
                # First batch — generate full test class
                test_code = generate_tests_for_class(
                    source_code=source_code,
                    class_name=cls.name,
                    namespace=parsed.namespace,
                    test_framework=test_framework,
                    source_project_name=src_proj.name,
                    credentials=credentials,
                    method_names=batch,
                    progress_cb=progress_cb,
                )
            else:
                # Subsequent batches — append to what we already have
                test_code = generate_missing_tests(
                    source_code=source_code,
                    class_name=cls.name,
                    namespace=parsed.namespace,
                    existing_test_code=accumulated_code,
                    test_framework=test_framework,
                    source_project_name=src_proj.name,
                    credentials=credentials,
                    method_names=batch,
                    progress_cb=progress_cb,
                )

            if not test_code:
                result.errors.append(
                    f"No test code generated for {cls.name} batch {batch_idx}")
                continue

            method_count = len(re.findall(
                r'\[(?:Fact|Test|TestMethod|Theory|TestCase|DataTestMethod)\]',
                test_code
            ))
            if method_count == 0:
                if progress_cb:
                    progress_cb(f"    No test methods in AI response — skipping batch")
                continue

            total_methods_written += method_count
            written_path = write_test_file(test_proj, cls.name, test_code, progress_cb)

            # Update accumulated_code with the merged file for next batch
            try:
                with open(written_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    accumulated_code = f.read()
            except OSError:
                accumulated_code = test_code

        if total_methods_written > 0:
            written_path = os.path.join(test_proj.abs_path, f"{cls.name}Tests.cs")
            result.generated_tests.append(GeneratedTestInfo(
                class_name=cls.name,
                test_file_path=written_path,
                source_project=src_proj.name,
                test_project=test_proj.name,
                method_count=total_methods_written,
            ))
        else:
            result.errors.append(f"AI returned no test methods for {cls.name}")


def _static_coverage(solution: SolutionInfo, progress_cb) -> CoverageReport:
    """Static coverage: check which source methods are referenced in test files."""
    all_source = [sf for p in solution.source_projects for sf in p.source_files]
    all_test   = [sf for p in solution.test_projects   for sf in p.source_files]
    return estimate_coverage_static(all_source, all_test)


def _run_or_estimate_coverage(
    solution: SolutionInfo,
    progress_cb,
) -> CoverageReport:
    test_csproj_paths = [p.csproj_path for p in solution.test_projects if os.path.isfile(p.csproj_path)]

    if not test_csproj_paths:
        # No test projects yet — return zero coverage
        return CoverageReport(0.0, 0.0, error="No test projects found yet.")

    report = run_coverage(solution.sln_path, test_csproj_paths, progress_cb)

    if not report.ok:
        if progress_cb:
            progress_cb(f"  dotnet test failed: {report.error}")
            progress_cb("  Falling back to static code analysis estimate...")

        all_source = []
        all_test = []
        for p in solution.source_projects:
            all_source.extend(p.source_files)
        for p in solution.test_projects:
            all_test.extend(p.source_files)

        report = estimate_coverage_static(all_source, all_test)

    return report
