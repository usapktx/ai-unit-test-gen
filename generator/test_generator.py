"""Generate C# unit tests using OpenAI GPT-5."""

import os
import re
from typing import Optional, Callable
from openai import OpenAI
import config


def _get_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def generate_tests_for_class(
    source_code: str,
    class_name: str,
    namespace: str,
    test_framework: str,
    source_project_name: str,
    api_key: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Send the C# class source to GPT-5 and get back a complete unit test class.
    Returns the generated C# test file content, or None on failure.
    """
    if progress_cb:
        progress_cb(f"  Sending {class_name} to GPT-5 for test generation...")

    framework_hints = {
        "xunit": (
            "xUnit.net (using Xunit; using Xunit.Abstractions; use [Fact] and [Theory]/[InlineData])"
        ),
        "nunit": (
            "NUnit (using NUnit.Framework; use [TestFixture], [Test], [TestCase])"
        ),
        "mstest": (
            "MSTest (using Microsoft.VisualStudio.TestTools.UnitTesting; "
            "use [TestClass], [TestMethod], [DataTestMethod])"
        ),
    }
    fw_hint = framework_hints.get(test_framework, framework_hints["xunit"])

    system_prompt = (
        "You are an expert C# developer specialising in unit testing and test-driven development. "
        "Your task is to write comprehensive unit tests that achieve 100% code coverage. "
        "Follow these rules strictly:\n"
        "1. Return ONLY valid C# code — no markdown fences, no explanation text.\n"
        "2. Use the exact test framework specified.\n"
        "3. Use Moq for mocking all constructor-injected dependencies.\n"
        "4. Cover every public method: happy path, edge cases, null inputs, exceptions.\n"
        "5. Cover every branch (if/else, switch, null-coalescing, ternary).\n"
        "6. For async methods use async Task test methods with await.\n"
        "7. Name tests descriptively: MethodName_Scenario_ExpectedResult.\n"
        "8. Add the correct using statements at the top.\n"
        "9. Place tests in namespace: {ns}.Tests\n"
        "10. The test class name must be {cls}Tests."
    ).format(ns=namespace or source_project_name, cls=class_name)

    user_prompt = (
        f"Test framework to use: {fw_hint}\n\n"
        f"Source project namespace: {namespace}\n"
        f"Source project assembly: {source_project_name}\n\n"
        f"Generate complete unit tests for the following C# class. "
        f"Aim for 100% branch and line coverage.\n\n"
        f"```csharp\n{source_code}\n```"
    )

    client = _get_client(api_key)

    # Try gpt-5 first, fall back to configured fallback model
    for model in [config.OPENAI_MODEL, config.OPENAI_MODEL_FALLBACK]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=4096,
            )
            if progress_cb:
                progress_cb(f"  Model used: {model}")
            content = response.choices[0].message.content or ""
            return _clean_code_fences(content)
        except Exception as e:
            err = str(e)
            if "model" in err.lower() and ("not found" in err.lower() or "does not exist" in err.lower()):
                if progress_cb:
                    progress_cb(f"  Model '{model}' not available, trying fallback...")
                continue
            if progress_cb:
                progress_cb(f"  OpenAI error: {err}")
            return None

    if progress_cb:
        progress_cb("  No suitable model found. Check your OpenAI model names in config.py.")
    return None


def generate_missing_tests(
    source_code: str,
    class_name: str,
    namespace: str,
    existing_test_code: str,
    test_framework: str,
    source_project_name: str,
    api_key: str,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> Optional[str]:
    """
    Given existing test code, generate ONLY the additional test methods needed
    to reach 100% coverage. Returns additional test methods (not a full class).
    """
    if progress_cb:
        progress_cb(f"  Generating additional tests for {class_name}...")

    framework_hints = {
        "xunit": "xUnit.net ([Fact], [Theory]/[InlineData])",
        "nunit": "NUnit ([Test], [TestCase])",
        "mstest": "MSTest ([TestMethod], [DataTestMethod])",
    }
    fw_hint = framework_hints.get(test_framework, framework_hints["xunit"])

    system_prompt = (
        "You are an expert C# developer. You will be given a source class and its existing unit tests. "
        "Your job is to add ONLY the missing test methods needed to achieve 100% code coverage. "
        "Rules:\n"
        "1. Return ONLY the new test method bodies (no class declaration, no using statements).\n"
        "2. Do not duplicate existing tests.\n"
        "3. Use the same test framework and naming conventions as the existing tests.\n"
        "4. Use Moq for mocking where needed.\n"
        "5. Return only valid C# method code."
    )

    user_prompt = (
        f"Test framework: {fw_hint}\n\n"
        f"SOURCE CLASS:\n```csharp\n{source_code}\n```\n\n"
        f"EXISTING TESTS:\n```csharp\n{existing_test_code}\n```\n\n"
        "Write ONLY the additional [Fact]/[Test]/[TestMethod] methods needed "
        "to cover the untested code paths. No class wrapper, no using statements."
    )

    client = _get_client(api_key)

    for model in [config.OPENAI_MODEL, config.OPENAI_MODEL_FALLBACK]:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2,
                max_tokens=3000,
            )
            content = response.choices[0].message.content or ""
            return _clean_code_fences(content)
        except Exception as e:
            err = str(e)
            if "model" in err.lower() and ("not found" in err.lower() or "does not exist" in err.lower()):
                continue
            if progress_cb:
                progress_cb(f"  OpenAI error: {err}")
            return None

    return None


def _clean_code_fences(text: str) -> str:
    """Strip markdown code fences if the model included them."""
    text = text.strip()
    text = re.sub(r'^```(?:csharp|cs)?\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*```\s*$', '', text)
    return text.strip()
