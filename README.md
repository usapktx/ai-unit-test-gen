# .NET Unit Test Generator — GPT-5 Powered

A Python desktop application that analyses a .NET Framework solution (up to 4.8), generates comprehensive unit tests targeting 100% code coverage using OpenAI GPT-5, and integrates them directly into your solution — creating a test project if one does not already exist.

---

## Features

- Browse to any folder containing a `.sln` file
- Automatically detects source projects and existing test projects
- Shows current code coverage (line % and branch %) before generation
- Sends each class to GPT-5 to generate complete, idiomatic unit tests
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

Check your version:

```bash
python3 --version
```

Download from https://www.python.org/downloads/ if not installed.

### 2. .NET SDK

The .NET SDK (version 6 or later recommended) is required to create test projects, restore packages, and run tests.

Check your version:

```bash
dotnet --version
```

Download from https://dotnet.microsoft.com/download if not installed.

### 3. OpenAI API Key

You need an OpenAI account with access to GPT-5 (or GPT-4o as fallback).

- Sign in at https://platform.openai.com
- Go to API Keys and create a new secret key
- Keep it handy — you will enter it in the app or set it as an environment variable

### 4. A modern web browser

The UI runs in your default browser (Chrome, Safari, Firefox, Edge). No additional installation needed.

---

## Installation

### Step 1 — Clone or download the project

```bash
git clone <repository-url> AIUnitTest
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

This installs `openai` and `flask`.

### Step 4 — (Optional) Set your OpenAI API key as an environment variable

This avoids having to paste the key into the UI every time.

```bash
# macOS / Linux
export OPENAI_API_KEY="sk-..."

# Windows (Command Prompt)
set OPENAI_API_KEY=sk-...

# Windows (PowerShell)
$env:OPENAI_API_KEY = "sk-..."
```

To make it permanent, add the export line to your `~/.zshrc`, `~/.bashrc`, or Windows System Environment Variables.

---

## Running the Application

```bash
python3 main.py
```

This starts a local web server on port 5000 and automatically opens the UI in your default browser at `http://127.0.0.1:5000`.

To stop the app, press **Ctrl+C** in the terminal.

> **Note:** The UI runs in your browser — no tkinter or desktop GUI framework is required. This avoids compatibility issues with system Python on macOS.

---

## Using the Application

### 1. Select a Solution Folder

Click **Browse...** and navigate to the root folder of your .NET solution — the folder that contains the `.sln` file.

### 2. Configure Settings

| Field | Description |
|-------|-------------|
| **OpenAI API Key** | Paste your key here if not set via environment variable. Tick **Show** to reveal it. |
| **Model** | Defaults to `gpt-5`. Change to `gpt-4o` if GPT-5 is not available on your account. |
| **Framework** | Choose `xunit`, `nunit`, or `mstest`. The app auto-detects this from existing test projects; this setting applies when creating a new test project. |

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

For each class in each source project, the app will:
1. Read the full C# source
2. Send it to GPT-5 with a prompt targeting 100% branch and line coverage
3. Write the generated `<ClassName>Tests.cs` file to the test project directory
4. If a test file already exists, merge new test methods into it without overwriting existing tests
5. If no test project exists, create one (using `dotnet new xunit/nunit/mstest`), add required NuGet packages, reference the source project, and add it to the solution

After generation, the app runs `dotnet test` again and shows:
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
├── main.py                    # Application entry point
├── config.py                  # Default model, framework, and API key settings
├── requirements.txt           # Python dependencies
├── analyzer/
│   ├── solution_analyzer.py   # Parses .sln and .csproj files
│   └── csharp_parser.py       # Regex-based C# class/method extractor
├── generator/
│   ├── test_generator.py      # OpenAI GPT-5 integration
│   ├── project_manager.py     # Test project creation and file writing
│   └── orchestrator.py        # End-to-end workflow coordinator
├── coverage/
│   └── coverage_runner.py     # dotnet test + coverlet runner; static fallback
└── ui/
    └── main_window.py         # tkinter dark-themed desktop UI
```

---

## Configuration

Edit `config.py` to change defaults permanently:

```python
# The primary model to use — change if your account has a different GPT-5 ID
OPENAI_MODEL = "gpt-5"

# Fallback if the primary model is unavailable
OPENAI_MODEL_FALLBACK = "gpt-4o"

# Default test framework when creating a new test project
DEFAULT_TEST_FRAMEWORK = "xunit"  # "xunit" | "nunit" | "mstest"
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

**"No .sln file found"**
Make sure you select the folder that directly contains the `.sln` file, not a subfolder.

**"dotnet CLI not found"**
Install the .NET SDK from https://dotnet.microsoft.com/download and ensure `dotnet` is on your PATH.

**"Model 'gpt-5' not found"**
Your OpenAI account may not have access to GPT-5 yet. Change the **Model** field to `gpt-4o` in the UI, or update `OPENAI_MODEL` in `config.py`.

**"No coverage XML files generated"**
Ensure the test project references `coverlet.collector` and `Microsoft.NET.Test.Sdk`. The app adds these automatically when creating a new test project; for existing projects you may need to add them manually:
```bash
dotnet add <TestProject>.csproj package coverlet.collector
dotnet add <TestProject>.csproj package Microsoft.NET.Test.Sdk
```

**Tests do not compile after generation**
GPT-5 output is occasionally imperfect for complex classes with many generic constraints or internal types. Open the failing `.cs` file and correct any compilation errors. Re-running generation will add to existing test files rather than overwrite them.

**tkinter not found**
See the Prerequisites section above for platform-specific install instructions.
