"""Parse .sln files and identify source vs test projects."""

import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# Test project indicators
TEST_NAME_PATTERNS = re.compile(
    r'(\.Tests?|\.UnitTests?|\.IntegrationTests?|\.Specs?)$', re.IGNORECASE
)
TEST_PACKAGES = {"xunit", "nunit", "mstest", "microsoft.visualstudio.testtools"}

# .sln project line format
SLN_PROJECT_RE = re.compile(
    r'^Project\("\{[A-F0-9-]+\}"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"\{([A-F0-9-]+)\}"',
    re.IGNORECASE
)


@dataclass
class DotNetProject:
    name: str
    path: str          # relative path from solution dir
    guid: str
    abs_path: str = ""
    target_framework: str = ""
    is_test_project: bool = False
    test_framework: str = ""   # xunit / nunit / mstest
    source_files: List[str] = field(default_factory=list)
    csproj_path: str = ""


@dataclass
class SolutionInfo:
    sln_path: str
    solution_dir: str
    projects: List[DotNetProject] = field(default_factory=list)

    @property
    def source_projects(self):
        return [p for p in self.projects if not p.is_test_project]

    @property
    def test_projects(self):
        return [p for p in self.projects if p.is_test_project]


def analyze_solution(folder_path: str) -> Optional[SolutionInfo]:
    """Find and parse the .sln file in folder_path. Returns None if not found."""
    sln_files = [
        f for f in os.listdir(folder_path) if f.endswith(".sln")
    ]
    if not sln_files:
        return None

    sln_path = os.path.join(folder_path, sln_files[0])
    solution_dir = folder_path
    info = SolutionInfo(sln_path=sln_path, solution_dir=solution_dir)

    with open(sln_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        content = f.read()

    for match in SLN_PROJECT_RE.finditer(content):
        name, rel_path, guid = match.group(1), match.group(2), match.group(3)
        # Skip solution folders (no .csproj)
        if not rel_path.endswith(".csproj"):
            continue
        # Normalize path separators
        rel_path = rel_path.replace("\\", os.sep)
        abs_path = os.path.normpath(os.path.join(solution_dir, rel_path))
        proj = DotNetProject(
            name=name, path=rel_path, guid=guid,
            abs_path=os.path.dirname(abs_path),
            csproj_path=abs_path,
        )
        _enrich_project(proj)
        info.projects.append(proj)

    return info


def _enrich_project(proj: DotNetProject):
    """Read .csproj to fill in framework, test flag, source files."""
    if not os.path.isfile(proj.csproj_path):
        return

    with open(proj.csproj_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        xml = f.read()

    # Target framework
    tf_match = re.search(r'<TargetFramework[s]?>(.*?)</TargetFramework[s]?>', xml, re.IGNORECASE)
    if tf_match:
        proj.target_framework = tf_match.group(1).strip().split(";")[0]

    # Detect test packages
    xml_lower = xml.lower()
    if TEST_NAME_PATTERNS.search(proj.name):
        proj.is_test_project = True

    for pkg in TEST_PACKAGES:
        if pkg in xml_lower:
            proj.is_test_project = True
            if "xunit" in xml_lower:
                proj.test_framework = "xunit"
            elif "nunit" in xml_lower:
                proj.test_framework = "nunit"
            elif "mstest" in xml_lower or "visualstudio.testtools" in xml_lower:
                proj.test_framework = "mstest"
            break

    # Also detect by IsTestProject element
    if "<istestproject>true</istestproject>" in xml_lower:
        proj.is_test_project = True

    # Collect .cs source files
    proj_dir = proj.abs_path
    if os.path.isdir(proj_dir):
        for root, _, files in os.walk(proj_dir):
            for fname in files:
                if fname.endswith(".cs"):
                    rel = os.path.relpath(os.path.join(root, fname), proj_dir)
                    # Skip generated / obj files
                    if "obj" + os.sep not in rel and "bin" + os.sep not in rel:
                        proj.source_files.append(os.path.join(root, fname))
