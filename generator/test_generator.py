"""Generate C# unit tests via the internal AI API (GPT-5)."""

import re
from typing import Optional, Callable

from config import AICredentials
from generator.ai_client import InternalAIClient


def _client(creds: AICredentials) -> InternalAIClient:
    return InternalAIClient(creds.endpoint, creds.api_key, creds.api_secret)


def generate_tests_for_class(
    source_code: str,
    class_name: str,
    namespace: str,
    test_framework: str,
    source_project_name: str,
    credentials: AICredentials,
    method_names: Optional[list] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Send the C# class source to the internal AI API and get back a complete
    unit test class. Returns the generated C# content, or None on failure.
    """
    if progress_cb:
        scope = f" [{', '.join(method_names)}]" if method_names else ""
        progress_cb(f"  Sending {class_name}{scope} to AI API...")

    framework_hints = {
        "xunit":  "xUnit.net (using Xunit; use [Fact] and [Theory]/[InlineData])",
        "nunit":  "NUnit (using NUnit.Framework; use [TestFixture], [Test], [TestCase])",
        "mstest": (
            "MSTest (using Microsoft.VisualStudio.TestTools.UnitTesting; "
            "use [TestClass], [TestMethod], [DataTestMethod])"
        ),
    }
    fw_hint = framework_hints.get(test_framework, framework_hints["xunit"])

    system_prompt = (
        "You are an expert C# developer specialising in unit testing and TDD. "
        "Your task is to write comprehensive unit tests that achieve 100% code coverage. "
        "Follow these rules strictly:\n"
        "1. Return ONLY valid C# code — no markdown fences, no explanation text.\n"
        "2. Use the exact test framework specified.\n"
        "3. Use Moq for mocking all constructor-injected dependencies.\n"
        "4. Cover every public method: happy path, edge cases, null inputs, exceptions.\n"
        "5. Cover every branch (if/else, switch, null-coalescing, ternary).\n"
        "6. For async methods use async Task test methods with await.\n"
        "7. Name tests: MethodName_Scenario_ExpectedResult.\n"
        "8. Add all required using statements at the top.\n"
        "9. Place tests in namespace: {ns}.Tests\n"
        "10. The test class name must be {cls}Tests."
    ).format(ns=namespace or source_project_name, cls=class_name)

    method_scope = (
        f"\nOnly generate tests for these methods: {', '.join(method_names)}."
        if method_names else ""
    )
    user_prompt = (
        f"Test framework: {fw_hint}\n\n"
        f"Source namespace: {namespace}\n"
        f"Source assembly:  {source_project_name}\n\n"
        f"Generate complete unit tests for the class below. "
        f"Aim for 100% branch and line coverage.{method_scope}\n\n"
        f"```csharp\n{source_code}\n```"
    )

    try:
        client = _client(creds=credentials)
        content = _strip_fences(client.chat(
            model=credentials.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=4096,
        ))

        # If the response was truncated, ask the AI to complete it
        if not _is_complete(content):
            if progress_cb:
                progress_cb(f"  Response truncated for {class_name} — requesting completion...")
            continuation = _strip_fences(client.chat(
                model=credentials.model,
                messages=[
                    {"role": "system", "content": "You are a C# developer. Complete the truncated C# code below. Return ONLY the missing code needed to finish it — no explanation, no repetition of existing code."},
                    {"role": "user",   "content": f"Complete this truncated C# code:\n\n{content}"},
                ],
                temperature=0.2,
                max_tokens=4096,
            ))
            content = content + "\n" + continuation

        if progress_cb:
            progress_cb(f"  Tests generated for {class_name}.")
        return content
    except Exception as e:
        if progress_cb:
            progress_cb(f"  AI API error for {class_name}: {e}")
        return None


def generate_missing_tests(
    source_code: str,
    class_name: str,
    namespace: str,
    existing_test_code: str,
    test_framework: str,
    source_project_name: str,
    credentials: AICredentials,
    method_names: Optional[list] = None,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Given existing test code, generate ONLY the additional test methods needed
    to reach 100% coverage. Returns new method bodies only (no class wrapper).
    """
    if progress_cb:
        progress_cb(f"  Generating additional tests for {class_name}...")

    framework_hints = {
        "xunit":  "xUnit.net ([Fact], [Theory]/[InlineData])",
        "nunit":  "NUnit ([Test], [TestCase])",
        "mstest": "MSTest ([TestMethod], [DataTestMethod])",
    }
    fw_hint = framework_hints.get(test_framework, framework_hints["xunit"])

    system_prompt = (
        "You are an expert C# developer. Given a source class and its existing unit tests, "
        "add ONLY the missing test methods needed to achieve 100% code coverage.\n"
        "Rules:\n"
        "1. Return ONLY new test method bodies — no class declaration, no using statements.\n"
        "2. Do not duplicate existing tests.\n"
        "3. Match the test framework and naming conventions already in use.\n"
        "4. Use Moq for mocking where needed.\n"
        "5. Return only valid C# method code."
    )

    method_scope = (
        f" Only add tests for these methods: {', '.join(method_names)}."
        if method_names else ""
    )
    user_prompt = (
        f"Test framework: {fw_hint}\n\n"
        f"SOURCE CLASS:\n```csharp\n{source_code}\n```\n\n"
        f"EXISTING TESTS:\n```csharp\n{existing_test_code}\n```\n\n"
        f"Write ONLY the additional test methods to cover untested code paths.{method_scope} "
        "No class wrapper, no using statements."
    )

    try:
        client = _client(creds=credentials)
        content = _strip_fences(client.chat(
            model=credentials.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            temperature=0.2,
            max_tokens=3000,
        ))

        if not _is_complete(content):
            if progress_cb:
                progress_cb(f"  Response truncated for {class_name} — requesting completion...")
            continuation = _strip_fences(client.chat(
                model=credentials.model,
                messages=[
                    {"role": "system", "content": "You are a C# developer. Complete the truncated C# code below. Return ONLY the missing code needed to finish it — no explanation, no repetition of existing code."},
                    {"role": "user",   "content": f"Complete this truncated C# code:\n\n{content}"},
                ],
                temperature=0.2,
                max_tokens=3000,
            ))
            content = content + "\n" + continuation

        return content
    except Exception as e:
        if progress_cb:
            progress_cb(f"  AI API error for {class_name}: {e}")
        return None


def _strip_fences(text: str) -> str:
    """Remove markdown code fences the model may have included."""
    text = text.strip()
    text = re.sub(r"^```(?:csharp|cs)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def _is_complete(code: str) -> bool:
    """Return True if the C# code has balanced curly braces (not truncated)."""
    depth = 0
    in_string = False
    in_char = False
    prev = ""
    for ch in code:
        if ch == '"' and not in_char and prev != "\\":
            in_string = not in_string
        elif ch == "'" and not in_string and prev != "\\":
            in_char = not in_char
        elif not in_string and not in_char:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
        prev = ch
    return depth == 0 and code.strip().endswith("}")
