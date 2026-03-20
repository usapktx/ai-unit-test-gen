"""Create or locate test projects, write generated test files."""

import os
import re
import subprocess
from typing import List, Optional, Callable

import config
from analyzer.solution_analyzer import DotNetProject, SolutionInfo


def ensure_test_project(
    solution: SolutionInfo,
    source_project: DotNetProject,
    test_framework: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[DotNetProject]:
    """
    Return an existing test project that references source_project, or create one.
    """
    # Try to find an existing test project that matches
    for tp in solution.test_projects:
        if _references_project(tp, source_project):
            return tp
        # Also match by name prefix
        if tp.name.startswith(source_project.name):
            return tp

    # None found — create a new one
    return _create_test_project(solution, source_project, test_framework, progress_cb)


def _references_project(test_proj: DotNetProject, source_proj: DotNetProject) -> bool:
    if not os.path.isfile(test_proj.csproj_path):
        return False
    with open(test_proj.csproj_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        content = f.read()
    return source_proj.name in content or os.path.basename(source_proj.csproj_path) in content


def _create_test_project(
    solution: SolutionInfo,
    source_project: DotNetProject,
    test_framework: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[DotNetProject]:
    test_proj_name = f"{source_project.name}.Tests"
    test_proj_dir = os.path.join(solution.solution_dir, test_proj_name)

    if progress_cb:
        progress_cb(f"Creating test project: {test_proj_name}")

    framework = source_project.target_framework or "net48"
    template = {
        "xunit": "xunit",
        "nunit": "nunit",
        "mstest": "mstest",
    }.get(test_framework, "xunit")

    cmd = [
        "dotnet", "new", template,
        "-n", test_proj_name,
        "-o", test_proj_dir,
        "--framework", framework,
        "--force",
    ]
    _run(cmd, progress_cb)

    csproj_path = os.path.join(test_proj_dir, f"{test_proj_name}.csproj")
    if not os.path.isfile(csproj_path):
        if progress_cb:
            progress_cb(f"  Failed to create {csproj_path}")
        return None

    # Add required packages
    packages = list(config.TEST_PROJECT_PACKAGES)
    if test_framework == "xunit":
        packages += config.XUNIT_PACKAGES
    elif test_framework == "nunit":
        packages += config.NUNIT_PACKAGES
    elif test_framework == "mstest":
        packages += config.MSTEST_PACKAGES

    for pkg in packages:
        _run(["dotnet", "add", csproj_path, "package", pkg], progress_cb)

    # Reference source project
    _run(
        ["dotnet", "add", csproj_path, "reference", source_project.csproj_path],
        progress_cb,
    )

    # Add to solution
    _run(["dotnet", "sln", solution.sln_path, "add", csproj_path], progress_cb)

    if progress_cb:
        progress_cb(f"  Test project created: {test_proj_name}")

    from analyzer.solution_analyzer import DotNetProject
    tp = DotNetProject(
        name=test_proj_name,
        path=os.path.relpath(csproj_path, solution.solution_dir),
        guid="",
        abs_path=test_proj_dir,
        csproj_path=csproj_path,
        target_framework=framework,
        is_test_project=True,
        test_framework=test_framework,
    )
    solution.projects.append(tp)
    return tp


def write_test_file(
    test_project: DotNetProject,
    class_name: str,
    test_code: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> str:
    """
    Write generated test code to the test project directory.
    If an existing test file is found, merge new methods into it.
    Returns the path of the written file.
    """
    test_file_name = f"{class_name}Tests.cs"
    test_file_path = os.path.join(test_project.abs_path, test_file_name)

    if os.path.isfile(test_file_path):
        # Merge: insert new methods before the last closing brace
        existing = open(test_file_path, "r", encoding="utf-8-sig", errors="ignore").read()
        merged = _merge_test_methods(existing, test_code)
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(merged)
        if progress_cb:
            progress_cb(f"  Updated: {test_file_name}")
    else:
        with open(test_file_path, "w", encoding="utf-8") as f:
            f.write(test_code)
        if progress_cb:
            progress_cb(f"  Created: {test_file_name}")

    return test_file_path


def _merge_test_methods(existing: str, new_code: str) -> str:
    """
    If new_code is a partial snippet (only methods), inject before the last '}'.
    If new_code is a full class, extract its methods and inject them.
    """
    # Detect if new_code has using statements or class declaration → full class
    if re.search(r'^\s*(?:using\s|namespace\s|\[(?:TestClass|TestFixture))', new_code, re.MULTILINE):
        # Extract method bodies from new_code
        methods = _extract_methods_from_class(new_code)
        if not methods:
            return existing
        # Find last } in existing file
        last_brace = existing.rfind("}")
        if last_brace == -1:
            return existing + "\n\n" + methods
        return existing[:last_brace] + "\n\n" + methods + "\n" + existing[last_brace:]
    else:
        # new_code is already just methods
        last_brace = existing.rfind("}")
        if last_brace == -1:
            return existing + "\n\n" + new_code
        return existing[:last_brace] + "\n\n" + new_code + "\n" + existing[last_brace:]


def _extract_methods_from_class(class_code: str) -> str:
    """Extract method-level content from inside a class body."""
    # Find first { at the class level
    match = re.search(r'\bclass\s+\w+[^{]*\{', class_code)
    if not match:
        return class_code
    start = match.end()
    # Take everything between outer braces (strip last })
    inner = class_code[start:]
    last = inner.rfind("}")
    if last != -1:
        inner = inner[:last]
    return inner.strip()


def _run(cmd: list, progress_cb):
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if progress_cb:
            if proc.stdout and proc.stdout.strip():
                progress_cb(f"  {proc.stdout.strip()[:200]}")
            if proc.returncode != 0 and proc.stderr and proc.stderr.strip():
                progress_cb(f"  Warning: {proc.stderr.strip()[:200]}")
        return proc.returncode
    except FileNotFoundError:
        if progress_cb:
            progress_cb("  dotnet CLI not found.")
        return -1
    except subprocess.TimeoutExpired:
        if progress_cb:
            progress_cb("  Command timed out.")
        return -1
