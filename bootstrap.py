"""Set up dn-repurposer on this machine (Windows, macOS or Linux).

Usage: python bootstrap.py [--refresh]

Standard library only, so it runs before anything is installed. It:
  1. checks Python is 3.10 or newer,
  2. creates .venv with this interpreter if it is missing,
  3. installs requirements.txt into .venv,
  4. (--refresh only) rebuilds the blog index and the brand-rules cache,
  5. writes .mcp.json with the .venv Python path for this OS,
  6. checks the cache files exist and parse,
  7. runs the unit tests with the .venv Python,
  8. starts the MCP server over stdio and confirms every tool is listed.
Every failure says what went wrong and what to do, then exits non-zero.
"""

import argparse
import json
import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_DIR = ROOT / ".venv"
REQUIREMENTS = ROOT / "requirements.txt"
MCP_JSON = ROOT / ".mcp.json"
CACHE_DIR = ROOT / "mcp_server" / "cache"
SERVER_NAME = "dn-repurposer"
MIN_PYTHON = (3, 10)
BRAND_RULE_FILES = [
    "anti-slop-catalog.json",
    "logo-usage.json",
    "mechanics.json",
    "say-this-not-that.json",
    "the-gate.json",
    "voice-principles.json",
    "where-the-brand-speaks.json",
]
EXPECTED_TOOLS = ["list_blog_posts", "fetch_blog_post", "get_brand_rule", "lint_draft", "verify_quotes", "validate_handoff", "save_run"]
SERVER_TIMEOUT_SECONDS = 60

# Runs inside .venv (where the mcp SDK is installed); prints the server's tool names as JSON.
PROBE = """
import json, sys
import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

async def main():
    params = StdioServerParameters(command=sys.executable, args=["-m", "mcp_server.server"], cwd=sys.argv[1])
    async with stdio_client(params) as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()
            result = await session.list_tools()
            print(json.dumps([tool.name for tool in result.tools]))

anyio.run(main)
"""


def step(title: str) -> None:
    print(f"\n== {title}", flush=True)


def fail(what: str, todo: str) -> None:
    print(f"\nFAILED: {what}\nWhat to do: {todo}", file=sys.stderr, flush=True)
    sys.exit(1)


def venv_python() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"
    return VENV_DIR / "bin" / "python"


def mcp_command() -> str:
    return ".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python"


def run(cmd: list[str], what: str, todo: str, quiet: bool = False) -> None:
    """Run a command from the project root; on a non-zero exit, show its output and fail."""
    result = subprocess.run(cmd, cwd=ROOT, capture_output=quiet, text=True)
    if result.returncode != 0:
        if quiet:
            print((result.stdout or "") + (result.stderr or ""), file=sys.stderr)
        fail(f"{what} (exit code {result.returncode}).", todo)


def check_python() -> None:
    step("Python version")
    found = sys.version_info[:3]
    if found[:2] < MIN_PYTHON:
        fail(
            f"Python {'.'.join(map(str, found))} is too old; dn-repurposer needs {'.'.join(map(str, MIN_PYTHON))} or newer.",
            "Install Python 3.10+ from https://www.python.org/downloads/ and run this script with it.",
        )
    print(f"Python {'.'.join(map(str, found))} at {sys.executable}")


def ensure_venv() -> Path:
    step("Virtual environment")
    python = venv_python()
    if python.exists():
        print(f"Using existing {VENV_DIR.name} ({python.relative_to(ROOT)})")
        return python
    if VENV_DIR.exists():
        fail(
            f"{VENV_DIR.name} exists but has no {python.relative_to(ROOT)}; it was probably made on another OS.",
            f"Delete the {VENV_DIR.name} folder and run this script again.",
        )
    print(f"Creating {VENV_DIR.name} with {sys.executable}")
    try:
        venv.EnvBuilder(with_pip=True).create(VENV_DIR)
    except Exception as exc:  # venv raises several types (CalledProcessError, OSError, ...)
        fail(
            f"Could not create {VENV_DIR.name}: {exc}",
            "On Debian/Ubuntu install the venv module (sudo apt install python3-venv), delete any partial .venv, and re-run.",
        )
    if not python.exists():
        fail(f"{VENV_DIR.name} was created but {python.relative_to(ROOT)} is missing.", "Delete .venv and run this script again.")
    return python


def install_requirements(python: Path) -> None:
    step("Install requirements")
    if not REQUIREMENTS.exists():
        fail("requirements.txt is missing.", "Restore it from git (git checkout -- requirements.txt).")
    todo = "Check your internet connection, then re-run. If it keeps failing, delete .venv and re-run."
    run([str(python), "-m", "pip", "install", "--quiet", "--upgrade", "pip"], "Upgrading pip failed", todo, quiet=True)
    run([str(python), "-m", "pip", "install", "--quiet", "-r", str(REQUIREMENTS)], "Installing requirements.txt failed", todo, quiet=True)
    print("Installed requirements.txt into .venv")


def refresh_caches(python: Path) -> None:
    step("Refresh caches (--refresh)")
    todo = "Check your internet connection and that disruptionnow.com and dn-brand-hub.netlify.app load, then re-run."
    for script in ("build_index.py", "build_brand_cache.py"):
        print(f"Running mcp_server/{script}")
        run([str(python), str(ROOT / "mcp_server" / script)], f"mcp_server/{script} failed", todo)


def write_mcp_json() -> None:
    step("Write .mcp.json")
    config = {"mcpServers": {SERVER_NAME: {"type": "stdio", "command": mcp_command(), "args": ["-m", "mcp_server.server"]}}}
    try:
        MCP_JSON.write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        fail(f"Could not write .mcp.json: {exc}", "Check that the project folder is writable.")
    print(f"Wrote .mcp.json (command: {mcp_command()})")


def check_caches() -> None:
    step("Check cache files")
    paths = [CACHE_DIR / "blog-index.json", CACHE_DIR / "lint-rules.json"]
    paths += [CACHE_DIR / "brand-rules" / name for name in BRAND_RULE_FILES]
    problems = []
    for path in paths:
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            problems.append(f"missing: {path.relative_to(ROOT)}")
        except (OSError, ValueError) as exc:
            problems.append(f"unreadable: {path.relative_to(ROOT)} ({exc})")
    if problems:
        fail(
            "Cache files are missing or invalid:\n  " + "\n  ".join(problems),
            "Restore them from git (git checkout -- mcp_server/cache), or run: python bootstrap.py --refresh",
        )
    print(f"All {len(paths)} cache files exist and parse")


def run_tests(python: Path) -> None:
    step("Unit tests")
    run(
        [str(python), "-m", "unittest", "discover", "tests"],
        "Unit tests failed",
        "Read the failing test output above; fix the code or re-run after pulling a working version.",
    )


def check_server(python: Path) -> None:
    step("Start the MCP server and list its tools")
    try:
        result = subprocess.run(
            [str(python), "-c", PROBE, str(ROOT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=SERVER_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        fail(
            f"The MCP server did not answer within {SERVER_TIMEOUT_SECONDS} seconds.",
            f"Run `{mcp_command()} -m mcp_server.server` by hand to see why it hangs or crashes.",
        )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        fail(
            "Could not start the MCP server or list its tools.",
            f"Run `{mcp_command()} -m mcp_server.server` by hand to see the error.",
        )
    try:
        tools = json.loads(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        fail(f"Unexpected output from the server check: {result.stdout!r}", "Re-run; if it repeats, start the server by hand to debug.")
    missing = [name for name in EXPECTED_TOOLS if name not in tools]
    if missing:
        fail(f"The server is missing tools: {', '.join(missing)}", "Check mcp_server/server.py registers every tool.")
    print(f"{SERVER_NAME} is up with {len(tools)} tools:")
    for name in tools:
        print(f"  - {name}")


def next_steps() -> None:
    print(
        "\nSetup complete. Next steps:\n"
        "  1. Open this folder in Claude Code.\n"
        f"  2. Approve the \"{SERVER_NAME}\" MCP server when prompted.\n"
        f"  3. Run /mcp and check {SERVER_NAME} shows as connected.\n"
        "  4. Run /repurpose-post <post URL>, for example:\n"
        "     /repurpose-post https://disruptionnow.com/blog/your-hospital-bill-is-wrong-ai-can-prove-it"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up dn-repurposer on this machine.")
    parser.add_argument("--refresh", action="store_true", help="re-run build_index.py and build_brand_cache.py first")
    args = parser.parse_args()

    check_python()
    python = ensure_venv()
    install_requirements(python)
    if args.refresh:
        refresh_caches(python)
    write_mcp_json()
    check_caches()
    run_tests(python)
    check_server(python)
    next_steps()


if __name__ == "__main__":
    main()
