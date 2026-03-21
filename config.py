import os
from typing import NamedTuple


# ── Load .env file (if present) before reading env vars ──────────────────────
def _load_dotenv():
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            # Remove optional surrounding quotes from the value
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)


_load_dotenv()


# ── Internal AI API credentials ───────────────────────────────────────────────
# These can be set in the .env file or as real environment variables.
# Values entered in the UI at runtime take priority over these defaults.

INTERNAL_AI_ENDPOINT = os.environ.get("INTERNAL_AI_ENDPOINT", "")
INTERNAL_AI_KEY      = os.environ.get("INTERNAL_AI_KEY", "")
INTERNAL_AI_SECRET   = os.environ.get("INTERNAL_AI_SECRET", "")
AI_MODEL             = os.environ.get("AI_MODEL", "gpt-5")


class AICredentials(NamedTuple):
    """Bundles the three connection parameters for the internal AI API."""
    endpoint:   str
    api_key:    str
    api_secret: str
    model:      str = "gpt-5"


def credentials_from_env() -> AICredentials:
    """Return an AICredentials instance populated from env / .env values."""
    return AICredentials(
        endpoint=INTERNAL_AI_ENDPOINT,
        api_key=INTERNAL_AI_KEY,
        api_secret=INTERNAL_AI_SECRET,
        model=AI_MODEL,
    )


# ── dotnet / test project settings ────────────────────────────────────────────
DEFAULT_TEST_FRAMEWORK = "mstest"  # "xunit" | "nunit" | "mstest"

TEST_PROJECT_PACKAGES = [
    "coverlet.collector",
    "Microsoft.NET.Test.Sdk",
    "Moq",
]

XUNIT_PACKAGES  = ["xunit", "xunit.runner.visualstudio"]
NUNIT_PACKAGES  = ["NUnit", "NUnit3TestAdapter"]
MSTEST_PACKAGES = ["MSTest.TestAdapter", "MSTest.TestFramework"]
