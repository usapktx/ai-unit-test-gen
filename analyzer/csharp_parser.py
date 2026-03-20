"""Regex-based C# source parser — extracts classes, methods, properties."""

import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------- patterns ----------
_NS_RE = re.compile(r'^\s*namespace\s+([\w.]+)', re.MULTILINE)

_CLASS_RE = re.compile(
    r'^\s*'
    r'((?:(?:public|internal|private|protected|static|abstract|sealed|partial|new)\s+)*)'
    r'(?:class|struct|record)\s+'
    r'(\w+)'
    r'(?:\s*<[^>]*>)?'               # generics
    r'(?:\s*:\s*[^\n{]+)?'           # base / interfaces
    r'\s*\{',
    re.MULTILINE,
)

_INTERFACE_RE = re.compile(
    r'^\s*'
    r'((?:(?:public|internal|private|protected|partial)\s+)*)'
    r'interface\s+(\w+)',
    re.MULTILINE,
)

_METHOD_RE = re.compile(
    r'^\s*'
    r'((?:(?:public|internal|private|protected|static|virtual|override|'
    r'abstract|async|sealed|new|extern)\s+)*)'
    r'([\w<>\[\]?,\s]+?)\s+'        # return type
    r'(\w+)\s*'                      # method name
    r'(?:<[^>]+>)?\s*'              # generic type params
    r'\(([^)]*)\)\s*'               # parameters
    r'(?:where\s+[^\n{]+)?\s*'      # type constraints
    r'(?:\{|=>)',                    # body start or expression body
    re.MULTILINE,
)

_PROP_RE = re.compile(
    r'^\s*'
    r'((?:(?:public|internal|private|protected|static|virtual|override|abstract|new)\s+)*)'
    r'([\w<>\[\]?,\s]+?)\s+'
    r'(\w+)\s*'
    r'\{[^}]*(?:get|set)[^}]*\}',
    re.MULTILINE,
)

_CTOR_RE = re.compile(
    r'^\s*'
    r'((?:(?:public|internal|private|protected)\s+)*)'
    r'(\w+)\s*'
    r'\(([^)]*)\)\s*'
    r'(?::\s*(?:base|this)\s*\([^)]*\))?\s*'
    r'\{',
    re.MULTILINE,
)

# Keywords that appear as method names falsely
_KEYWORDS = {
    "if", "while", "for", "foreach", "switch", "catch", "using", "lock",
    "return", "else", "do", "try", "finally", "namespace", "class",
    "interface", "struct", "enum", "new", "get", "set",
}


@dataclass
class CSharpMethod:
    name: str
    modifiers: str
    return_type: str
    parameters: str
    is_constructor: bool = False
    is_property: bool = False

    @property
    def is_public(self):
        return "public" in self.modifiers

    @property
    def is_static(self):
        return "static" in self.modifiers

    @property
    def is_async(self):
        return "async" in self.modifiers

    @property
    def signature(self):
        if self.is_constructor:
            return f"{self.name}({self.parameters})"
        return f"{self.modifiers}{self.return_type} {self.name}({self.parameters})"


@dataclass
class CSharpClass:
    name: str
    namespace: str
    modifiers: str
    methods: List[CSharpMethod] = field(default_factory=list)
    properties: List[CSharpMethod] = field(default_factory=list)
    constructors: List[CSharpMethod] = field(default_factory=list)
    is_interface: bool = False
    file_path: str = ""

    @property
    def public_methods(self):
        return [m for m in self.methods if m.is_public]

    @property
    def testable_members(self):
        return self.constructors + self.public_methods + self.properties


@dataclass
class ParsedFile:
    file_path: str
    namespace: str
    classes: List[CSharpClass] = field(default_factory=list)


def parse_file(file_path: str) -> Optional[ParsedFile]:
    """Parse a .cs file and return its structure."""
    try:
        with open(file_path, "r", encoding="utf-8-sig", errors="ignore") as f:
            source = f.read()
    except OSError:
        return None

    ns_match = _NS_RE.search(source)
    namespace = ns_match.group(1) if ns_match else ""

    result = ParsedFile(file_path=file_path, namespace=namespace)

    # Interfaces
    for m in _INTERFACE_RE.finditer(source):
        cls = CSharpClass(
            name=m.group(2),
            namespace=namespace,
            modifiers=m.group(1).strip(),
            is_interface=True,
            file_path=file_path,
        )
        result.classes.append(cls)

    # Classes / structs / records
    for m in _CLASS_RE.finditer(source):
        cls = CSharpClass(
            name=m.group(2),
            namespace=namespace,
            modifiers=m.group(1).strip(),
            file_path=file_path,
        )
        # Try to extract the class body
        body_start = m.end()
        body = _extract_block(source, body_start - 1)

        # Constructors
        for cm in _CTOR_RE.finditer(body):
            if cm.group(2) == cls.name:
                cls.constructors.append(CSharpMethod(
                    name=cm.group(2),
                    modifiers=cm.group(1).strip(),
                    return_type="",
                    parameters=cm.group(3).strip(),
                    is_constructor=True,
                ))

        # Properties
        for pm in _PROP_RE.finditer(body):
            prop_name = pm.group(3).strip()
            if prop_name in _KEYWORDS:
                continue
            cls.properties.append(CSharpMethod(
                name=prop_name,
                modifiers=pm.group(1).strip(),
                return_type=pm.group(2).strip(),
                parameters="",
                is_property=True,
            ))

        # Methods
        for mm in _METHOD_RE.finditer(body):
            mname = mm.group(3).strip()
            if mname in _KEYWORDS or mname == cls.name:
                continue
            ret = mm.group(2).strip()
            if ret in _KEYWORDS:
                continue
            cls.methods.append(CSharpMethod(
                name=mname,
                modifiers=mm.group(1).strip(),
                return_type=ret,
                parameters=mm.group(4).strip(),
            ))

        result.classes.append(cls)

    return result


def _extract_block(source: str, open_brace_pos: int) -> str:
    """Extract the content of a { } block starting at open_brace_pos."""
    depth = 0
    in_string = False
    in_char = False
    in_verbatim = False
    in_line_comment = False
    in_block_comment = False
    i = open_brace_pos
    start = -1

    while i < len(source):
        c = source[i]
        nc = source[i + 1] if i + 1 < len(source) else ""

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            i += 1
            continue
        if in_block_comment:
            if c == "*" and nc == "/":
                in_block_comment = False
                i += 2
            else:
                i += 1
            continue
        if in_verbatim:
            if c == '"' and nc == '"':
                i += 2
            elif c == '"':
                in_verbatim = False
                i += 1
            else:
                i += 1
            continue
        if in_string:
            if c == "\\" and nc in ('"', "\\"):
                i += 2
            elif c == '"':
                in_string = False
                i += 1
            else:
                i += 1
            continue
        if in_char:
            if c == "\\" and nc in ("'", "\\"):
                i += 2
            elif c == "'":
                in_char = False
                i += 1
            else:
                i += 1
            continue

        if c == "/" and nc == "/":
            in_line_comment = True
            i += 2
            continue
        if c == "/" and nc == "*":
            in_block_comment = True
            i += 2
            continue
        if c == "@" and nc == '"':
            in_verbatim = True
            i += 2
            continue
        if c == '"':
            in_string = True
            i += 1
            continue
        if c == "'":
            in_char = True
            i += 1
            continue

        if c == "{":
            if start == -1:
                start = i
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1:i]
        i += 1

    return source[start + 1:] if start != -1 else ""
