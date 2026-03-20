import os

# OpenAI model — change to exact GPT-5 model ID when available in your account
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5")

# Fallback model if gpt-5 is not available
OPENAI_MODEL_FALLBACK = "gpt-4o"

# API key (loaded from env; can also be set in the UI)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Default test framework when creating a new test project
DEFAULT_TEST_FRAMEWORK = "xunit"  # "xunit" | "nunit" | "mstest"

# Packages added to new test projects
TEST_PROJECT_PACKAGES = [
    "coverlet.collector",
    "Microsoft.NET.Test.Sdk",
    "Moq",
]

XUNIT_PACKAGES = ["xunit", "xunit.runner.visualstudio"]
NUNIT_PACKAGES = ["NUnit", "NUnit3TestAdapter"]
MSTEST_PACKAGES = ["MSTest.TestAdapter", "MSTest.TestFramework"]
