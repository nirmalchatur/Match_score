#!/usr/bin/env python
"""
Run the Postman collection against a real Django server and report the result.

This is the entry point used by CI. It:

1. applies migrations to a throwaway SQLite database (``config.settings_test``)
2. starts ``manage.py runserver`` on a free port
3. waits for the server to actually answer before running anything
4. executes the Postman collection with Newman
5. writes a JUnit report, an HTML report, and a console summary
6. tears the server down and exits non-zero if any assertion failed

Why Newman is invoked as a subprocess
------------------------------------
The PyPI ``newman`` package is a thin, unmaintained wrapper that does
``from argument import Argument`` at import time, while every published release
of ``argument`` (0.2.2 ... 1.4.0) exports ``Arguments``. It therefore cannot be
installed at all:

    ModuleNotFoundError: No module named 'argument'
    ImportError: cannot import name 'Argument' from 'argument'

Newman is a Node program; the npm distribution is the supported install path and
is what this script drives. Everything around it -- server lifecycle, database
setup, report summarising, exit codes -- stays in Python.

Usage
-----
    python scripts/run_api_tests.py
    python scripts/run_api_tests.py --port 8123
    python scripts/run_api_tests.py --folder "Auth lifecycle"
    python scripts/run_api_tests.py --keep-server
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND = REPO_ROOT / "backend"
COLLECTION = REPO_ROOT / "postman" / "tailorup-api.postman_collection.json"
ENVIRONMENT = REPO_ROOT / "postman" / "local.postman_environment.json"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports"

# How long to wait for runserver to bind and answer before giving up. A cold
# Django start with migrations is a few seconds; 60 leaves room on a cold CI box
# without letting a genuinely broken boot hang the job.
STARTUP_TIMEOUT = 60.0
POLL_INTERVAL = 0.4


class HarnessError(RuntimeError):
    """Raised for setup problems that should abort before Newman runs."""


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def log(message: str) -> None:
    print(f"[api-tests] {message}", flush=True)


def make_console_utf8() -> None:
    """Reconfigure stdout/stderr to UTF-8.

    Newman's CLI reporter draws box characters (U+25A1 and friends) and the
    Windows console defaults to cp1252, so echoing Newman's output raises
    UnicodeEncodeError *inside this script*, hiding the very report the
    developer needs. Errors are replaced rather than raised so one stray glyph
    can never turn a green run into a crash.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (ValueError, OSError):
            # A stream that cannot be reconfigured (a pipe under capture) is
            # fine; print() falls back to the default encoding.
            pass


def find_free_port() -> int:
    """Ask the OS for a port, then release it.

    There is an unavoidable race between closing this socket and runserver
    binding it, but in practice it is far better than hardcoding 8000, which
    collides with a developer's own dev server.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_server(base_url: str, timeout: float = STARTUP_TIMEOUT) -> None:
    """Poll a cheap endpoint until the server responds or the timeout expires.

    ``/api/auth/me/`` is used deliberately: it is AllowAny and returns 200 with
    ``{"authenticated": false}``, so it proves the URLconf, middleware stack and
    database connection are all live. Hitting ``/admin/`` instead would succeed
    even with a broken API.
    """
    deadline = time.monotonic() + timeout
    url = base_url + "/api/auth/me/"
    last_error: Exception | None = None

    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    log(f"server is up at {base_url}")
                    return
                last_error = HarnessError(f"unexpected status {response.status}")
        except urllib.error.HTTPError as exc:
            # A 4xx/5xx still means the socket is accepting connections and
            # Django is routing, which is the thing we are actually waiting for.
            last_error = exc
        except (urllib.error.URLError, ConnectionError, socket.timeout, OSError) as exc:
            last_error = exc

        time.sleep(POLL_INTERVAL)

    raise HarnessError(
        f"server did not become ready within {timeout:.0f}s "
        f"({last_error}). Last server output is printed above."
    )


def django_env() -> dict[str, str]:
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "config.settings_test"
    # Fail loudly instead of masking a traceback behind a generic 500.
    env["PYTHONUNBUFFERED"] = "1"


def run_django(*args: str) -> None:
    result = subprocess.run(
        [sys.executable, "manage.py", *args],
        cwd=BACKEND,
        env=django_env(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HarnessError(
            f"`manage.py {' '.join(args)}` failed with exit {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------


#: runserver writes here instead of a pipe. See start_server for why.
SERVER_LOG = Path(tempfile.gettempdir()) / "tailorup_apitest_server.log"


def start_server(port: int) -> subprocess.Popen:
    """Start runserver and return the process.

    ``--noreload`` is essential: without it runserver spawns a child process,
    and killing the parent on teardown leaves an orphan holding the port, which
    makes the next local run fail to bind.

    Output goes to a **file**, not a PIPE. Django logs a line per request (and a
    full traceback for every 404/500 under DEBUG=False), and a pipe holds only
    ~64 KB before the writer blocks. The server would then stop answering
    mid-run, every Newman request would fail to connect, and the harness would
    either hang on teardown or report a wall of confusing connection errors. A
    file has no such limit.
    """
    log(f"starting Django on 127.0.0.1:{port}")

    SERVER_LOG.parent.mkdir(parents=True, exist_ok=True)
    handle = SERVER_LOG.open("w", encoding="utf-8", errors="replace")

    process = subprocess.Popen(
        [
            sys.executable,
            "manage.py",
            "runserver",
            f"127.0.0.1:{port}",
            "--noreload",
        ],
        cwd=BACKEND,
        env=django_env(),
        stdout=handle,
        stderr=subprocess.STDOUT,
    )
    # Keep a reference so the handle is not garbage-collected and closed while
    # the child is still writing to it.
    process._log_handle = handle  # type: ignore[attr-defined]

    # Surface an immediate crash (bad settings, failed import) instead of waiting
    # the full timeout for a server that will never start.
    time.sleep(1.0)
    if process.poll() is not None:
        handle.close()
        raise HarnessError(
            f"runserver exited immediately with code {process.returncode}\n"
            f"{read_server_log()}"
        )

    return process


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        _close_log(process)
        return

    log("stopping Django")

    # terminate() sends SIGTERM on POSIX and TerminateProcess on Windows, which
    # runserver handles. kill() is the backstop if it is still alive after 5s.
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        log("runserver ignored terminate, killing")
        process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log("could not kill runserver; it may need manual cleanup")

    _close_log(process)


def _close_log(process: subprocess.Popen) -> None:
    handle = getattr(process, "_log_handle", None)
    if handle is not None and not handle.closed:
        handle.close()


def read_server_log(limit: int = 4000) -> str:
    """Return the tail of the server log, for failure diagnostics."""
    try:
        text = SERVER_LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "(no server log)"
    return text[-limit:] if len(text) > limit else text


def drain_server_output(process: subprocess.Popen) -> str:
    """Deprecated shim: server output now lives in a file, not a pipe.

    Kept so the failure path in main() reads naturally, but the log handle is
    flushed by the OS on every write, so reading the file is always safe even
    while the server is still running.
    """
    return read_server_log()


# ---------------------------------------------------------------------------
# Newman
# ---------------------------------------------------------------------------


def resolve_newman() -> list[str]:
    """Return the argv prefix that invokes Newman.

    Prefers a local ``node_modules/.bin/newman`` (what CI installs) and falls
    back to whatever is on PATH. Keeping this in one place means the rest of
    the script never has to care which one is used.
    """
    local = REPO_ROOT.parent / "node_modules" / ".bin"
    for name in ("newman.cmd", "newman"):
        candidate = local / name
        if candidate.exists():
            log(f"using local newman at {candidate}")
            return [str(candidate)]

    log("local newman not found, falling back to PATH")
    return ["newman"]


def run_newman(
    base_url: str,
    report_dir: Path,
    folder: str | None,
    bail: bool,
) -> dict:
    """Run the collection and return the parsed JSON summary."""
    report_dir.mkdir(parents=True, exist_ok=True)

    json_report = report_dir / "newman-report.json"
    junit_report = report_dir / "newman-junit.xml"
    html_report = report_dir / "newman-report.html"

    command = [
        *resolve_newman(),
        "run",
        str(COLLECTION),
        "--environment",
        str(ENVIRONMENT),
        # Collection variables win over environment values, so baseUrl is set
        # here to point at the ephemeral port chosen above.
        "--env-var",
        f"baseUrl={base_url}",
        "--reporters",
        "cli,json,junit,html",
        "--reporter-json-export",
        str(json_report),
        "--reporter-junit-export",
        str(junit_report),
        "--reporter-html-export",
        str(html_report),
        "--timeout-request",
        "20000",
        "--timeout-script",
        "10000",
        # Colour codes make the GitHub log hard to read.
        "--color",
        "off",
    ]

    if folder:
        command += ["--folder", folder]
    if bail:
        command.append("--bail")

    log("running newman")
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        capture_output=True,
        # Newman emits UTF-8 (the CLI reporter draws box characters) while the
        # Windows default here is cp1252, which raises UnicodeDecodeError
        # mid-stream and truncates exactly the output needed on failure.
        encoding="utf-8",
        errors="replace",
    )

    # Always echo Newman's own output: on failure its CLI reporter has the
    # request/response detail that explains what broke.
    print(result.stdout, flush=True)
    if result.stderr.strip():
        print(result.stderr, file=sys.stderr, flush=True)

    if not json_report.exists():
        raise HarnessError(
            "newman produced no JSON report, so the run cannot be summarised.\n"
            "This usually means an external reporter is missing -- the HTML\n"
            "reporter ships separately:\n"
            "    npm install newman-reporter-html\n"
            f"command: {' '.join(command)}\n"
            f"exit code: {result.returncode}"
        )

    # Note: newman exits 1 when assertions fail. That is a normal test failure,
    # not a harness error, so it is deliberately NOT raised here -- the assertion
    # counts below decide the exit status and print the per-failure breakdown.
    return {
        "exit_code": result.returncode,
        "summary": json.loads(json_report.read_text(encoding="utf-8")),
        "json_report": json_report,
        "junit_report": junit_report,
        "html_report": html_report,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def iter_assertions(summary: dict):
    """Yield (request_name, assertion) pairs from a Newman summary.

    Newman 6 emits a **flat** ``run.executions`` array -- one entry per request,
    in execution order -- rather than the nested folder/items shape Newman 3 and
    4 used. The ``cursor.position`` field gives the original ordering.
    """
    for execution in summary.get("run", {}).get("executions", []):
        request_name = execution.get("item", {}).get("name", "?")
        error = execution.get("error")

        if error:
            # The request never completed (connection refused, script crash).
            # Surfacing it as a synthetic failure keeps it visible in the
            # per-failure breakdown below.
            yield request_name, {
                "assertion": "request completed",
                "error": error.get("message", "unknown request error"),
            }
            continue

        for assertion in execution.get("assertions") or []:
            yield request_name, assertion


def print_summary(summary: dict) -> tuple[int, int, int]:
    """Print a per-failure breakdown and return (passed, failed, total)."""
    stats = summary.get("run", {}).get("stats", {})
    total = int(stats.get("assertions", {}).get("total", 0))
    failed = int(stats.get("assertions", {}).get("failed", 0))
    passed = total - failed

    failures = [
        (request_name, assertion)
        for request_name, assertion in iter_assertions(summary)
        if assertion.get("error")
    ]

    if failures:
        print()
        print("=" * 72)
        print(f"FAILURES ({len(failures)})")
        print("=" * 72)
        for request_name, assertion in failures:
            error = assertion.get("error") or "failed"
            print(f"\n  {request_name}")
            print(f"    assertion : {assertion.get('assertion', '?')}")
            print(f"    error     : {error}")
    return passed, failed, total


def main() -> int:
    make_console_utf8()

    parser = argparse.ArgumentParser(
        description="Run the TailorUp Postman collection against a live Django server."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Port to bind. 0 (default) picks a free one automatically.",
    )
    parser.add_argument(
        "--folder",
        default=None,
        help="Run only this collection folder, e.g. 'Auth lifecycle'.",
    )
    parser.add_argument(
        "--bail",
        action="store_true",
        help="Stop at the first failing request instead of running them all.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=DEFAULT_REPORT_DIR,
        help=f"Where to write reports (default: {DEFAULT_REPORT_DIR}).",
    )
    parser.add_argument(
        "--keep-server",
        action="store_true",
        help="Leave the server running after the run (for debugging).",
    )
    args = parser.parse_args()

    if not COLLECTION.exists():
        raise HarnessError(
            f"collection not found at {COLLECTION}\n"
            "Regenerate it with: python scripts/build_postman_collection.py"
        )

    port = args.port or find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    server: subprocess.Popen | None = None

    try:
        # Migrations first: runserver with --noreload does not migrate, and a
        # missing table surfaces as a 500 that looks like an API bug.
        log("applying migrations to the test database")
        run_django("migrate", "--noinput")

        server = start_server(port)
        wait_for_server(base_url)

        result = run_newman(base_url, args.report_dir, args.folder, args.bail)
        passed, failed, total = print_summary(result["summary"])

        # Belt and braces with the exit-code check: if the collection ever runs
        # but executes zero assertions (an emptied folder, a broken generator),
        # that is a harness fault, not a pass. Reporting success there would let
        # a misconfigured suite sit green indefinitely.
        if total == 0:
            log("ERROR: newman completed but executed zero assertions.")
            log("The collection is empty, or the reporters are misconfigured.")
            return 2

        print()
        print("=" * 72)
        print(f"  assertions : {total}")
        print(f"  passed     : {passed}")
        print(f"  failed     : {failed}")
        print(f"  html       : {result['html_report']}")
        print(f"  junit      : {result['junit_report']}")
        print("=" * 72)

        if failed:
            log(f"FAILED: {failed} of {total} assertions did not pass")
            return 1

        log(f"PASSED: all {total} assertions")
        return 0

    except HarnessError as exc:
        print(f"\n[api-tests] ERROR: {exc}", file=sys.stderr, flush=True)
        if server is not None:
            output = drain_server_output(server)
            if output.strip():
                print("\n--- server output ---", file=sys.stderr)
                print(output, file=sys.stderr)
        return 2

    finally:
        if server is not None:
            if args.keep_server:
                log(f"--keep-server set, leaving Django running at {base_url}")
            else:
                stop_server(server)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HarnessError as error:  # raised before the try block, e.g. bad args
        print(f"[api-tests] ERROR: {error}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n[api-tests] interrupted", file=sys.stderr)
        sys.exit(130)

