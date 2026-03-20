# .NET Unit Test Generator — GPT-5 Powered

A Python web application that analyses a .NET Framework solution (up to 4.8), generates comprehensive unit tests targeting 100% code coverage using an internal GPT-5 AI API, and integrates them directly into your solution — creating a test project if one does not already exist.

---

## Features

- Browse to any folder containing a `.sln` file
- Automatically detects source projects and existing test projects
- Shows current code coverage (line % and branch %) before generation
- Sends each C# class to the internal GPT-5 API to generate complete, idiomatic unit tests
- Supports xUnit, NUnit, and MSTest frameworks (auto-detected or user-selected)
- Merges new test methods into existing test files without overwriting them
- Creates a new test project (with coverlet, Moq, and SDK packages) if none exists
- Displays newly created test files and method counts after generation
- Shows updated code coverage after tests are written and executed
- Falls back to a static coverage estimate on macOS with .NET Framework 4.x targets (Mono required to run net48 tests natively)

---

## Prerequisites

### 1. Python

Python 3.9 or later is required.

```bash
python3 --version
```

Download from https://www.python.org/downloads/ if not installed.

### 2. .NET SDK

The .NET SDK (version 6 or later recommended) is required to create test projects, restore packages, and run tests.

```bash
dotnet --version
```

Download from https://dotnet.microsoft.com/download if not installed.

### 3. Internal AI API credentials

You need access to the internal GPT-5 AI gateway. Obtain the following three values from your platform/infrastructure team:

| Credential | Description |
|------------|-------------|
| **API Endpoint** | Base URL of the internal AI gateway, e.g. `https://internal-ai.example.com/v1` |
| **API Key** | Your personal or service API key |
| **API Secret** | Your personal or service API secret |

These can be set in a `.env` file, as environment variables, or entered directly in the UI at runtime.

### 4. A modern web browser

The UI runs in your default browser (Chrome, Safari, Firefox, Edge). No additional installation needed.

---

## Installation

### Step 1 — Clone or download the project

```bash
git clone https://github.com/usapktx/ai-unit-test-gen.git AIUnitTest
cd AIUnitTest
```

Or if you downloaded a zip, extract it and open a terminal in the `AIUnitTest` folder.

### Step 2 — (Recommended) Create a virtual environment

```bash
python3 -m venv .venv
```

Activate it:

```bash
# macOS / Linux
source .venv/bin/activate

# Windows (Command Prompt)
.venv\Scripts\activate.bat

# Windows (PowerShell)
.venv\Scripts\Activate.ps1
```

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

This installs `flask` and `requests`.

### Step 4 — Configure API credentials

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```env
INTERNAL_AI_ENDPOINT=https://internal-ai.example.com/v1
INTERNAL_AI_KEY=your-api-key-here
INTERNAL_AI_SECRET=your-api-secret-here
AI_MODEL=gpt-5
```

The app loads `.env` automatically on startup. Values entered in the UI at runtime take priority over `.env` for that session.

Alternatively, set them as real environment variables:

```bash
# macOS / Linux
export INTERNAL_AI_ENDPOINT=https://internal-ai.example.com/v1
export INTERNAL_AI_KEY=your-api-key-here
export INTERNAL_AI_SECRET=your-api-secret-here

# Windows (Command Prompt)
set INTERNAL_AI_ENDPOINT=https://internal-ai.example.com/v1
set INTERNAL_AI_KEY=your-api-key-here
set INTERNAL_AI_SECRET=your-api-secret-here

# Windows (PowerShell)
$env:INTERNAL_AI_ENDPOINT = "https://internal-ai.example.com/v1"
$env:INTERNAL_AI_KEY = "your-api-key-here"
$env:INTERNAL_AI_SECRET = "your-api-secret-here"
```

---

## Running the Application

```bash
python3 main.py
```

This starts a local web server on port 5000 and automatically opens the UI in your default browser at `http://127.0.0.1:5000`.

To stop the app, press **Ctrl+C** in the terminal.

> **Note:** The UI runs in your browser — no desktop GUI framework is required.

---

## Using the Application

### 1. Select a Solution Folder

Click **Browse...** and navigate to the root folder of your .NET solution — the folder that contains the `.sln` file. You can also paste the path directly into the text field.

### 2. Configure Credentials and Settings

| Field | Description |
|-------|-------------|
| **API Endpoint** | Base URL of the internal AI gateway. Pre-filled from `.env` / environment. |
| **Model** | AI model identifier sent in every request. Defaults to `gpt-5`. |
| **Framework** | `xunit`, `nunit`, or `mstest`. Auto-detected from existing test projects; used when creating a new one. |
| **API Key** | Your API key. Pre-filled from `.env` / environment. Click **Show** to reveal. |
| **API Secret** | Your API secret. Click **Show** to reveal. |

### 3. Analyze the Solution

Click **Analyze Solution**.

The app will:
- Parse the `.sln` file and all `.csproj` files
- Identify source projects and test projects
- Run `dotnet test` with coverlet to measure current code coverage
- Display the **Solution Structure** and **Coverage Before Generation** panels

If `dotnet test` cannot run (e.g., macOS with a .NET Framework 4.8 target), the app falls back to a static estimate based on which public methods are referenced in existing test files, and shows a notice in the log.

### 4. Generate Unit Tests

Click **Generate Unit Tests with GPT-5**.

For each class in each source project the app will:
1. Read the full C# source
2. Send it to the internal AI API with a prompt targeting 100% branch and line coverage
3. Write the generated `<ClassName>Tests.cs` file to the test project directory
4. If a test file already exists, merge new test methods into it without overwriting existing ones
5. If no test project exists, create one (`dotnet new xunit/nunit/mstest`), add required NuGet packages, reference the source project, and add it to the solution

Progress streams live in the **Progress Log** panel via Server-Sent Events.

After generation the app re-runs `dotnet test` and shows:
- **New Tests Added** — every test file created and number of test methods
- **Coverage After Generation** — updated line and branch percentages

### 5. Review the Results

- The **Progress Log** shows live output from every step
- Coverage percentages are colour-coded: green (≥ 80%), amber (≥ 50%), red (< 50%)
- Generated test files are placed inside the test project directory and are immediately part of the solution

---

## Project Structure

```
AIUnitTest/
├── main.py                      # Entry point — starts Flask, opens browser
├── app.py                       # Flask routes (/analyze, /generate, /browse, SSE)
├── config.py                    # Credentials + settings; loads .env automatically
├── .env.example                 # Template — copy to .env and fill in values
├── requirements.txt             # Python dependencies (flask, requests)
├── analyzer/
│   ├── solution_analyzer.py     # Parses .sln and .csproj files
│   └── csharp_parser.py         # Regex-based C# class/method extractor
├── generator/
│   ├── ai_client.py             # Internal AI API HTTP client (key + secret auth)
│   ├── test_generator.py        # Builds prompts and calls the AI API
│   ├── project_manager.py       # Test project creation and file writing
│   └── orchestrator.py          # End-to-end workflow coordinator
├── coverage/
│   └── coverage_runner.py       # dotnet test + coverlet runner; static fallback
└── templates/
    └── index.html               # Browser UI (dark theme, SSE progress stream)
```

---

## Configuration Reference

All values can be set in `.env`, as environment variables, or overridden in the UI.

| Variable | Default | Description |
|----------|---------|-------------|
| `INTERNAL_AI_ENDPOINT` | _(empty)_ | Base URL of the internal AI gateway |
| `INTERNAL_AI_KEY` | _(empty)_ | API key for authentication |
| `INTERNAL_AI_SECRET` | _(empty)_ | API secret for authentication |
| `AI_MODEL` | `gpt-5` | Model identifier sent in every request |

Other settings in `config.py`:

```python
DEFAULT_TEST_FRAMEWORK = "xunit"   # "xunit" | "nunit" | "mstest"
```

---

## Internal AI API Contract

The app calls `POST {INTERNAL_AI_ENDPOINT}/chat/completions` with:

**Request headers:**
```
Content-Type : application/json
X-API-Key    : <INTERNAL_AI_KEY>
X-API-Secret : <INTERNAL_AI_SECRET>
```

**Request body (OpenAI-compatible):**
```json
{
  "model": "gpt-5",
  "messages": [ { "role": "system", "content": "..." }, { "role": "user", "content": "..." } ],
  "temperature": 0.2,
  "max_tokens": 4096
}
```

**Expected response:**
```json
{
  "choices": [ { "message": { "content": "..." } } ]
}
```

---

## Platform Notes

### macOS

The app runs fully on macOS. However, .NET Framework 4.x assemblies require **Mono** to execute on macOS. If your solution targets `net48` or similar:

- Test files are still **generated and written** to disk
- `dotnet test` will fail to run them natively
- The app falls back to a static coverage estimate and shows a warning
- To get real coverage numbers, run the solution on a Windows machine or install Mono

### Windows

All features work as expected. .NET Framework 4.x tests run natively via the installed .NET SDK.

### Linux

Same as macOS for .NET Framework targets. .NET 5+ targets work fully.

---

## Troubleshooting

**"API Endpoint is required" / "API Key is required" / "API Secret is required"**
Fill in all three credential fields in the UI, or set them in `.env` before starting the app.

**"No .sln file found"**
Select the folder that directly contains the `.sln` file, not a subfolder.

**"dotnet CLI not found"**
Install the .NET SDK from https://dotnet.microsoft.com/download and ensure `dotnet` is on your PATH.

**HTTP 401 / 403 from AI API**
Your API key or secret is incorrect. Verify them with your platform team.

**HTTP 404 from AI API**
The endpoint URL may be wrong, or `/chat/completions` is at a different path. Confirm the full base URL with your platform team.

**"No coverage XML files generated"**
Ensure the test project references `coverlet.collector` and `Microsoft.NET.Test.Sdk`. The app adds these automatically when creating a new test project; for existing projects add them manually:
```bash
dotnet add <TestProject>.csproj package coverlet.collector
dotnet add <TestProject>.csproj package Microsoft.NET.Test.Sdk
```

**Tests do not compile after generation**
AI output is occasionally imperfect for complex classes with many generic constraints or internal types. Open the failing `.cs` file and correct any compilation errors. Re-running generation will add to existing test files rather than overwrite them.
