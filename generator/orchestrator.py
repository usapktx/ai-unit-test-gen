"""
Top-level orchestration: analyze solution → gather coverage → generate tests → run coverage again.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional, Callable

from analyzer.solution_analyzer import SolutionInfo, DotNetProject, analyze_solution
from analyzer.csharp_parser import parse_file, CSharpClass
from coverage.coverage_runner import CoverageReport, run_coverage, estimate_coverage_static
from generator.test_generator import generate_tests_for_class, generate_missing_tests, generate_methods_for_batch
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
        if progress_cb:
            progress_cb(f"  {len(src_proj.source_files)} source file(s) to process")
        for sf in src_proj.source_files:
            _process_source_file(
                sf, src_proj, test_proj, credentials, tf, result, progress_cb
            )

    if progress_cb:
        progress_cb("\n=== Measuring coverage AFTER generation (static analysis) ===")
    result.coverage_after = _static_coverage(solution, progress_cb)

    return result


METHODS_PER_BATCH = 5


def _count_test_methods(code: str) -> int:
    import re
    return len(re.findall(
        r'\[(?:Fact|Test|TestMethod|Theory|TestCase|DataTestMethod)\]', code
    ))


def _process_source_file(
    source_file: str,
    src_proj: DotNetProject,
    test_proj: DotNetProject,
    credentials: AICredentials,
    test_framework: str,
    result: OrchestrationResult,
    progress_cb,
):
    parsed = parse_file(source_file)
    if not parsed:
        return

    if progress_cb:
        progress_cb(f"  Scanning: {os.path.basename(source_file)} "
                    f"({len(parsed.classes)} class(es) found)")

    for cls in parsed.classes:
        if cls.is_interface:
            if progress_cb:
                progress_cb(f"    Skipping interface: {cls.name}")
            continue
        if not cls.public_methods and not cls.constructors and not cls.properties:
            if progress_cb:
                progress_cb(f"    Skipping {cls.name} — no public methods/constructors/properties")
            continue
        if "generated" in cls.name.lower() or cls.name.endswith("Designer"):
            if progress_cb:
                progress_cb(f"    Skipping {cls.name} — name suggests auto-generated class")
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

        all_methods = [m.name for m in cls.public_methods]

        if progress_cb:
            progress_cb(f"  Generating tests for: {cls.name} ({len(all_methods)} method(s))")

        # ── Phase 1: single call — ensures the file is always created ──
        if existing_test_code:
            first_code = generate_missing_tests(
                source_code=source_code,
                class_name=cls.name,
                namespace=parsed.namespace,
                existing_test_code=existing_test_code,
                test_framework=test_framework,
                source_project_name=src_proj.name,
                credentials=credentials,
                progress_cb=progress_cb,
            )
        else:
            first_code = generate_tests_for_class(
                source_code=source_code,
                class_name=cls.name,
                namespace=parsed.namespace,
                test_framework=test_framework,
                source_project_name=src_proj.name,
                credentials=credentials,
                progress_cb=progress_cb,
            )

        if not first_code:
            result.errors.append(f"No test code generated for {cls.name}")
            continue

        mc = _count_test_methods(first_code)
        if mc == 0:
            if progress_cb:
                progress_cb(f"  No test methods in AI response for {cls.name} — skipping")
            result.errors.append(f"AI returned no test methods for {cls.name}")
            continue

        written_path = write_test_file(test_proj, cls.name, first_code, progress_cb)
        total_method_count = mc

        # ── Phase 2: batch top-up for methods not covered in phase 1 ──
        if all_methods:
            try:
                with open(written_path, "r", encoding="utf-8-sig", errors="ignore") as f:
                    written_content = f.read()
            except OSError:
                written_content = first_code

            # Find methods whose names don't appear anywhere in the test file
            uncovered = [m for m in all_methods if m not in written_content]

            if uncovered:
                if progress_cb:
                    progress_cb(f"  {len(uncovered)} method(s) not covered — running batch top-up")

                for i in range(0, len(uncovered), METHODS_PER_BATCH):
                    batch = uncovered[i:i + METHODS_PER_BATCH]
                    if progress_cb:
                        progress_cb(f"    Top-up batch: {', '.join(batch)}")

                    batch_code = generate_methods_for_batch(
                        source_code=source_code,
                        class_name=cls.name,
                        method_names=batch,
                        test_framework=test_framework,
                        source_project_name=src_proj.name,
                        credentials=credentials,
                        progress_cb=progress_cb,
                    )
                    if batch_code:
                        bmc = _count_test_methods(batch_code)
                        if bmc > 0:
                            write_test_file(test_proj, cls.name, batch_code, progress_cb)
                            total_method_count += bmc

        result.generated_tests.append(GeneratedTestInfo(
            class_name=cls.name,
            test_file_path=written_path,
            source_project=src_proj.name,
            test_project=test_proj.name,
            method_count=total_method_count,
        ))


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
