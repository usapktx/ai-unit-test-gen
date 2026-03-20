"""Run dotnet test with coverlet and parse Cobertura XML coverage reports."""

import os
import re
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable


@dataclass
class ClassCoverage:
    name: str
    line_rate: float        # 0.0 – 1.0
    branch_rate: float
    lines_covered: int
    lines_valid: int
    branches_covered: int
    branches_valid: int

    @property
    def line_pct(self):
        return round(self.line_rate * 100, 1)

    @property
    def branch_pct(self):
        return round(self.branch_rate * 100, 1)


@dataclass
class PackageCoverage:
    name: str
    line_rate: float
    branch_rate: float
    classes: List[ClassCoverage] = field(default_factory=list)

    @property
    def line_pct(self):
        return round(self.line_rate * 100, 1)

    @property
    def branch_pct(self):
        return round(self.branch_rate * 100, 1)


@dataclass
class CoverageReport:
    line_rate: float
    branch_rate: float
    packages: List[PackageCoverage] = field(default_factory=list)
    error: str = ""

    @property
    def line_pct(self):
        return round(self.line_rate * 100, 1)

    @property
    def branch_pct(self):
        return round(self.branch_rate * 100, 1)

    @property
    def ok(self):
        return not self.error


def run_coverage(
    solution_path: str,
    test_project_paths: List[str],
    progress_cb: Optional[Callable[[str], None]] = None,
) -> CoverageReport:
    """
    Run `dotnet test` with XPlat Code Coverage on each test project.
    Returns a merged CoverageReport.
    """
    if not test_project_paths:
        return CoverageReport(0.0, 0.0, error="No test projects found.")

    results_dir = os.path.join(os.path.dirname(solution_path), ".test_results")
    os.makedirs(results_dir, exist_ok=True)

    # First restore / build
    if progress_cb:
        progress_cb("Running dotnet restore...")
    _run(["dotnet", "restore", solution_path], progress_cb)

    xml_files = []
    for tp in test_project_paths:
        if progress_cb:
            progress_cb(f"Running tests: {os.path.basename(tp)}")
        proj_results = os.path.join(results_dir, os.path.splitext(os.path.basename(tp))[0])
        os.makedirs(proj_results, exist_ok=True)

        cmd = [
            "dotnet", "test", tp,
            "--no-restore",
            "--collect:XPlat Code Coverage",
            f"--results-directory={proj_results}",
            "--",
            "DataCollectionRunSettings.DataCollectors.DataCollector"
            ".Configuration.Format=cobertura",
        ]
        out, err, rc = _run(cmd, progress_cb)

        if rc != 0 and progress_cb:
            progress_cb(f"  Warning: test run exited with code {rc}")
            if err:
                progress_cb(f"  {err[:400]}")

        # Find generated coverage XML
        for root, _, files in os.walk(proj_results):
            for fname in files:
                if fname.endswith(".cobertura.xml") or fname == "coverage.cobertura.xml":
                    xml_files.append(os.path.join(root, fname))

    if not xml_files:
        return CoverageReport(
            0.0, 0.0,
            error=(
                "No coverage XML files generated. "
                "Ensure test projects reference coverlet.collector and "
                "Microsoft.NET.Test.Sdk. On macOS, .NET Framework 4.x targets "
                "require Mono to run."
            ),
        )

    return _merge_reports(xml_files)


def _run(cmd, progress_cb):
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if progress_cb and proc.stdout:
            for line in proc.stdout.splitlines():
                if line.strip():
                    progress_cb(f"  {line.strip()}")
        return proc.stdout, proc.stderr, proc.returncode
    except FileNotFoundError:
        msg = "dotnet CLI not found. Please install the .NET SDK."
        if progress_cb:
            progress_cb(f"  Error: {msg}")
        return "", msg, -1
    except subprocess.TimeoutExpired:
        msg = "dotnet test timed out after 5 minutes."
        if progress_cb:
            progress_cb(f"  Error: {msg}")
        return "", msg, -1


def _merge_reports(xml_files: List[str]) -> CoverageReport:
    """Parse and merge multiple Cobertura XML files into one CoverageReport."""
    all_packages: Dict[str, PackageCoverage] = {}
    total_lines_covered = 0
    total_lines_valid = 0
    total_branches_covered = 0
    total_branches_valid = 0

    for xml_path in xml_files:
        try:
            tree = ET.parse(xml_path)
            root = tree.getroot()
        except ET.ParseError:
            continue

        for pkg_el in root.findall(".//package"):
            pkg_name = pkg_el.get("name", "Unknown")
            pkg_lr = float(pkg_el.get("line-rate", 0))
            pkg_br = float(pkg_el.get("branch-rate", 0))

            if pkg_name not in all_packages:
                all_packages[pkg_name] = PackageCoverage(
                    name=pkg_name, line_rate=pkg_lr, branch_rate=pkg_br
                )

            pkg = all_packages[pkg_name]

            for cls_el in pkg_el.findall(".//class"):
                cls_name = cls_el.get("name", "Unknown")
                lc = int(cls_el.get("lines-covered", 0) or 0)
                lv = int(cls_el.get("lines-valid", 0) or 0)
                bc = int(cls_el.get("branches-covered", 0) or 0)
                bv = int(cls_el.get("branches-valid", 0) or 0)
                lr = float(cls_el.get("line-rate", 0))
                br = float(cls_el.get("branch-rate", 0))

                total_lines_covered += lc
                total_lines_valid += lv
                total_branches_covered += bc
                total_branches_valid += bv

                pkg.classes.append(ClassCoverage(
                    name=cls_name,
                    line_rate=lr, branch_rate=br,
                    lines_covered=lc, lines_valid=lv,
                    branches_covered=bc, branches_valid=bv,
                ))

    overall_line = (
        total_lines_covered / total_lines_valid if total_lines_valid else 0.0
    )
    overall_branch = (
        total_branches_covered / total_branches_valid if total_branches_valid else 0.0
    )

    return CoverageReport(
        line_rate=overall_line,
        branch_rate=overall_branch,
        packages=list(all_packages.values()),
    )


# ---------- static estimation (fallback when dotnet test can't run) ----------

def estimate_coverage_static(
    source_files: List[str],
    test_files: List[str],
) -> CoverageReport:
    """
    Very rough static estimation: checks which public methods in source files
    are referenced by name in test files. Returns a synthetic CoverageReport.
    """
    from analyzer.csharp_parser import parse_file

    test_content = ""
    for tf in test_files:
        try:
            with open(tf, "r", encoding="utf-8-sig", errors="ignore") as f:
                test_content += f.read() + "\n"
        except OSError:
            pass

    packages: Dict[str, PackageCoverage] = {}
    total_methods = 0
    tested_methods = 0

    for sf in source_files:
        parsed = parse_file(sf)
        if not parsed:
            continue
        pkg_name = parsed.namespace or os.path.basename(sf)
        if pkg_name not in packages:
            packages[pkg_name] = PackageCoverage(pkg_name, 0.0, 0.0)

        for cls in parsed.classes:
            if cls.is_interface:
                continue
            cls_total = 0
            cls_tested = 0
            for m in cls.public_methods:
                cls_total += 1
                total_methods += 1
                if m.name in test_content:
                    cls_tested += 1
                    tested_methods += 1
            for c in cls.constructors:
                cls_total += 1
                total_methods += 1
                if cls.name in test_content:
                    cls_tested += 1
                    tested_methods += 1

            lr = cls_tested / cls_total if cls_total else 0.0
            packages[pkg_name].classes.append(ClassCoverage(
                name=cls.name,
                line_rate=lr, branch_rate=lr,
                lines_covered=cls_tested, lines_valid=cls_total,
                branches_covered=cls_tested, branches_valid=cls_total,
            ))

    overall = tested_methods / total_methods if total_methods else 0.0
    for pkg in packages.values():
        if pkg.classes:
            pkg.line_rate = sum(c.line_rate for c in pkg.classes) / len(pkg.classes)
            pkg.branch_rate = pkg.line_rate

    report = CoverageReport(
        line_rate=overall, branch_rate=overall,
        packages=list(packages.values()),
        error="Static estimate only — dotnet test could not run on this platform/framework.",
    )
    return report
