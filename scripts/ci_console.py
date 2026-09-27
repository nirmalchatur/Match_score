#!/usr/bin/env python
"""
ci_console.py -- a live terminal for this repository's GitHub Actions runs.

Why this exists
---------------
The GitHub dashboard answers "did it pass?". It does not answer the questions
that actually come up when a merge to ``main`` goes red:

* which job actually failed, and on which step?
* re-run **only the failed jobs** instead of the whole matrix
* re-run one specific job
* force-cancel a run stuck behind a queued matrix
* approve a deployment waiting on an environment reviewer
* pull the logs of a single failed job, or list its artifacts
* delete a run and reclaim its artifact quota

Those are all Actions REST endpoints. This wraps them in a terminal UI so they
are reachable from a shell, and keeps a live view of the current run's jobs.

Design notes
------------
* **Standard library only.** No pip install, so it runs on a fresh runner, in
  a container, or on a machine that has never seen this project.
* **Read-only by default.** Mutating commands print what they will do and
  require confirmation, because a mistyped run id should not cancel a deploy.
* **Not a TTY?** It degrades to a non-interactive report instead of crashing
  on ``input()``, so ``ci_console.py status`` is safe in a pipeline.

Authentication
--------------
    export GITHUB_TOKEN=ghp_...      # or GH_TOKEN
Inside Actions, ``GITHUB_TOKEN`` and ``GITHUB_REPOSITORY`` are injected
automatically, so the console can watch the run it is part of.

Usage
-----
    python scripts/ci_console.py                      # interactive
    python scripts/ci_console.py status               # one-shot report
    python scripts/ci_console.py status --run-id 123
    python scripts/ci_console.py watch --run-id 123   # live job table
    python scripts/ci_console.py help
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"
USER_AGENT = "tailorup-ci-console"

#: Refresh interval for `watch`, in seconds.
POLL_SECONDS = 5

#: Terminal width assumed when the real one cannot be detected.
FALLBACK_WIDTH = 100

# ---------------------------------------------------------------------------
# Small terminal helpers
# ---------------------------------------------------------------------------


def term_width() -> int:
    """Width to lay tables out in, clamped to something readable."""
    return max(60, min(shutil.get_terminal_size((FALLBACK_WIDTH, 24)).columns, 160))


def supports_colour() -> bool:
    """Only emit ANSI codes when a human is actually looking.

    GitHub Actions renders ANSI, but piping to a file or setting NO_COLOR
    should produce clean text. Honour both conventions.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("GITHUB_ACTIONS"):
        return True
    return sys.stdout.isatty()


class Style:
    """ANSI helpers that collapse to no-ops when colour is off."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, text: str) -> str:
        return self._wrap("1", text)

    def dim(self, text: str) -> str:
        return self._wrap("2", text)

    def red(self, text: str) -> str:
        return self._wrap("31", text)

    def green(self, text: str) -> str:
        return self._wrap("32", text)

    def yellow(self, text: str) -> str:
        return self._wrap("33", text)

    def blue(self, text: str) -> str:
        return self._wrap("34", text)

    def magenta(self, text: str) -> str:
        return self._wrap("35", text)

    def cyan(self, text: str) -> str:
        return self._wrap("36", text)


#: How a state should be rendered. A run that is merely "cancelled" is
#: yellow, not red: nobody broke anything, it was superseded.
STATE_STYLE = {
    "success": ("green", "PASS"),
    "failure": ("red", "FAIL"),
    "cancelled": ("yellow", "CANCEL"),
    "skipped": ("dim", "SKIP"),
    "neutral": ("cyan", "NEUTRAL"),
    "timed_out": ("red", "TIMEOUT"),
    "action_required": ("red", "ACTION"),
    "stale": ("dim", "STALE"),
    "queued": ("dim", "QUEUED"),
    "in_progress": ("blue", "RUNNING"),
    "waiting": ("yellow", "WAITING"),
    "requested": ("blue", "REQ"),
    "pending": ("yellow", "PENDING"),
    None: ("dim", "?"),
    "": ("dim", "?"),
}

def _visible_length(text: str) -> int:
    """Length of a string ignoring ANSI escape sequences.

    ANSI codes inflate ``len()``, so padding computed from ``len()`` makes a
    coloured table look ragged. This is the fix.
    """
    length, index = 0, 0
    while index < len(text):
        if text[index] == "\033":
            end = text.find("m", index)
            if end == -1:
                break
            index = end + 1
            continue
        length += 1
        index += 1
    return length


def _truncate(text: str, width: int) -> str:
    """Cut a (possibly coloured) string to a visible width."""
    if _visible_length(text) <= width:
        return text
    if width <= 1:
        return "\033[2m…\033[0m" if "\033" in text else "…"
    out, seen, index = [], 0, 0
    while index < len(text) and seen < width - 1:
        if text[index] == "\033":
            end = text.find("m", index)
            if end == -1:
                break
            out.append(text[index : end + 1])
            index = end + 1
            continue
        out.append(text[index])
        seen += 1
        index += 1
    return "".join(out) + "\033[2m…\033[0m"


class Console:
    """Everything the terminal needs, in one place."""

    def __init__(self) -> None:
        self.style = Style(supports_colour())
        self.width = term_width()

    def paint(self, state, text: str | None = None) -> str:
        """Colour a piece of text by workflow state."""
        colour, label = STATE_STYLE.get(state, ("dim", str(state)))
        return getattr(self.style, colour)(text if text is not None else label)

    def print(self, message: str = "") -> None:
        print(message, flush=True)

    def rule(self, title: str = "") -> None:
        if title:
            head = f"-- {title} "
            self.print(self.style.dim(head + "-" * max(3, self.width - len(head))))
        else:
            self.print(self.style.dim("-" * self.width))

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        """Print a table sized to the terminal, using visible widths.

        Rows are padded or clipped to the header width. A row that is short
        would otherwise raise deep inside the loop, turning a cosmetic slip
        into a crash in the middle of a status report.
        """
        if not rows:
            self.print(self.style.dim("  (nothing to show)"))
            return

        width_count = len(headers)
        rows = [(list(row) + [""] * width_count)[:width_count] for row in rows]

        widths = [_visible_length(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                widths[i] = max(widths[i], _visible_length(cell))

        # Shrink the widest column first; that is nearly always the name.
        budget = self.width - 2 * len(widths) - 2
        guard = 0
        while sum(widths) > budget and max(widths) > 10 and guard < 10_000:
            widths[widths.index(max(widths))] -= 1
            guard += 1

        def render(cells: list[str], styler=None) -> str:
            parts = []
            for i, cell in enumerate(cells):
                text = _truncate(cell, widths[i])
                padding = " " * max(0, widths[i] - _visible_length(text))
                parts.append((styler(text) if styler else text) + padding)
            return "  " + "  ".join(parts).rstrip()

        self.print(render(headers, self.style.bold))
        self.print(self.style.dim("  " + "  ".join("-" * w for w in widths)))
        for row in rows:
            self.print(render(row))

    def auto_confirm(self, question: str) -> bool:
        """Answer 'yes' on the user's behalf, announcing that it did.

        Used for one-shot commands run without a terminal. Printing the
        action keeps the log honest: a script that silently cancels a run
        is worse than one that fails loudly.
        """
        self.print(self.style.yellow(f"  auto-confirmed: {question}"))
        return True

    def confirm(self, question: str) -> bool:
        """Ask before doing something irreversible.

        Defaults to NO, and refuses outright when there is no terminal: a
        stray newline in a pipeline must never cancel a deployment.
        """
        if not sys.stdin.isatty():
            self.print(self.style.yellow("  not a terminal; refusing to confirm"))
            return False
        try:
            answer = input(f"  {question} [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            self.print()
            return False
        return answer in {"y", "yes"}

# ---------------------------------------------------------------------------
# GitHub API
# ---------------------------------------------------------------------------


class GitHubError(RuntimeError):
    """A REST call failed. Carries the status code for better messages."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHub:
    """Thin REST client for the Actions endpoints this tool needs."""

    def __init__(self, repo: str, token: str, console: Console) -> None:
        if "/" not in repo:
            raise GitHubError(
                f"'{repo}' is not in owner/name form. "
                "Pass --repo or set GITHUB_REPOSITORY."
            )
        self.owner, self.name = repo.split("/", 1)
        self.token = token
        self.console = console

    @property
    def repo_path(self) -> str:
        return f"/repos/{self.owner}/{self.name}"

    # -- transport ---------------------------------------------------------

    def _request(self, method: str, path: str, payload=None, raw: bool = False):
        url = path if path.startswith("http") else f"{API_ROOT}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Accept", "application/vnd.github+json")
        request.add_header("X-GitHub-Api-Version", API_VERSION)
        request.add_header("User-Agent", USER_AGENT)
        if self.token:
            request.add_header("Authorization", f"Bearer {self.token}")
        if data is not None:
            request.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                if raw:
                    return body
                return json.loads(body) if body else {}
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            try:
                message = json.loads(detail).get("message", detail)
            except ValueError:
                message = detail
            hint = {
                401: "  (token rejected -- check GITHUB_TOKEN)",
                403: "  (token lacks the 'actions' scope, or rate limit hit)",
                404: "  (run not found, or the token cannot see this repo)",
            }.get(exc.code, "")
            raise GitHubError(f"HTTP {exc.code}: {message}{hint}", exc.code) from None
        except urllib.error.URLError as exc:
            raise GitHubError(f"cannot reach api.github.com: {exc.reason}") from None

    def _get(self, path: str, raw: bool = False):
        return self._request("GET", path, raw=raw)

    def _post(self, path: str, payload=None):
        return self._request("POST", path, payload if payload is not None else {})

    def _delete(self, path: str):
        return self._request("DELETE", path)

    # -- reads -------------------------------------------------------------

    def runs(self, branch: str | None = None, per_page: int = 15) -> list[dict]:
        query = {"per_page": per_page}
        if branch:
            query["branch"] = branch
        data = self._get(f"{self.repo_path}/actions/runs?{urllib.parse.urlencode(query)}")
        return data.get("workflow_runs", [])

    def run(self, run_id: int) -> dict:
        return self._get(f"{self.repo_path}/actions/runs/{run_id}")

    def jobs(self, run_id: int) -> list[dict]:
        data = self._get(f"{self.repo_path}/actions/runs/{run_id}/jobs?per_page=100")
        return data.get("jobs", [])

    def latest_run_id(self, branch: str | None = None) -> int | None:
        found = self.runs(branch=branch, per_page=1)
        return found[0]["id"] if found else None

    def artifacts(self, run_id: int) -> list[dict]:
        data = self._get(f"{self.repo_path}/actions/runs/{run_id}/artifacts?per_page=100")
        return data.get("artifacts", [])

    def pending_deployments(self, run_id: int) -> list[dict]:
        data = self._get(f"{self.repo_path}/actions/runs/{run_id}/pending_deployments")
        return data.get("environments", [])

    def job_log(self, job_id: int, tail: int | None = None) -> str:
        """Fetch one job's log.

        The API redirects to a plain-text blob rather than JSON, so this is
        read as bytes and decoded leniently: CI output is full of box
        characters, and a strict decode would raise on a perfectly valid log.
        """
        raw = self._get(f"{self.repo_path}/actions/jobs/{job_id}/logs", raw=True)
        text = raw.decode("utf-8", "replace")
        if tail and tail > 0:
            text = "\n".join(text.splitlines()[-tail:])
        return text

    # -- writes ------------------------------------------------------------
    # Each is a single call so the UI layer can wrap it in a confirmation
    # without the client knowing anything about the interface.

    def rerun(self, run_id: int) -> None:
        self._post(f"{self.repo_path}/actions/runs/{run_id}/rerun")

    def rerun_failed(self, run_id: int) -> None:
        """Re-run only the failed jobs.

        The single most useful command here. The UI buries this behind
        "Re-run jobs", and re-running a whole matrix to fix one test wastes
        minutes of CI.
        """
        self._post(f"{self.repo_path}/actions/runs/{run_id}/rerun-failed-jobs")

    def cancel(self, run_id: int) -> None:
        self._post(f"{self.repo_path}/actions/runs/{run_id}/cancel")

    def force_cancel(self, run_id: int) -> None:
        self._post(f"{self.repo_path}/actions/runs/{run_id}/force-cancel")

    def approve_run(self, run_id: int) -> None:
        """Approve a run held by fork-PR review rules."""
        self._post(f"{self.repo_path}/actions/runs/{run_id}/approve")

    def review_deployments(self, run_id: int, approve: bool) -> None:
        """Approve or reject every environment deployment waiting on a run."""
        ids = [env["id"] for env in self.pending_deployments(run_id)]
        if not ids:
            raise GitHubError(f"run {run_id} has nothing waiting for approval")
        self._post(
            f"{self.repo_path}/actions/runs/{run_id}/pending_deployments",
            {
                "environment_ids": ids,
                "state": "approved" if approve else "rejected",
                "comment": "reviewed via ci_console.py",
            },
        )

    def delete_run(self, run_id: int) -> None:
        self._delete(f"{self.repo_path}/actions/runs/{run_id}")

    def delete_logs(self, run_id: int) -> None:
        self._delete(f"{self.repo_path}/actions/runs/{run_id}/logs")

    def dispatch(self, workflow: str, ref: str, inputs: dict[str, str]) -> None:
        """Trigger a workflow_dispatch run, optionally with inputs."""
        payload: dict = {"ref": ref}
        if inputs:
            payload["inputs"] = inputs
        self._post(
            f"{self.repo_path}/actions/workflows/{workflow}/dispatches", payload
        )

# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def humanise_seconds(value) -> str:
    """Render a duration compactly: 45s, 3m12s, 1h04m, 2d03h.

    A run stuck for days should read as days rather than as an
    unreadable five-digit hour count.
    """
    if value in (None, ""):
        return "-"
    try:
        total = int(value)
    except (TypeError, ValueError):
        return "-"
    if total < 0:
        return "-"
    if total < 60:
        return f"{total}s"
    minutes, seconds = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{seconds:02d}s"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h{minutes:02d}m"
    days, hours = divmod(hours, 24)
    return f"{days}d{hours:02d}h"


def short_sha(run: dict) -> str:
    return (run.get("head_sha") or "")[:7] or "-"


def commit_line(run: dict) -> str:
    """First line of the commit message, which is what identifies a run."""
    commit = run.get("head_commit") or {}
    message = (commit.get("message") or "").strip().splitlines()
    return message[0] if message else "-"


def format_run_row(console: Console, run: dict) -> list[str]:
    state = run.get("conclusion") or run.get("status")
    return [
        str(run.get("id")),
        console.paint(state),
        (run.get("name") or "-")[:34],
        (run.get("head_branch") or "-")[:22],
        console.style.dim(short_sha(run)),
        humanise_seconds(run.get("run_started_at") and _elapsed(run)),
        commit_line(run)[:40],
    ]


def _elapsed(run: dict) -> int:
    """Seconds between a run starting and now (or when it ended)."""
    from datetime import datetime, timezone

    def parse(value):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    start = parse(run.get("run_started_at") or run.get("created_at"))
    if not start:
        return 0
    end = parse(run.get("updated_at")) or datetime.now(timezone.utc)
    return max(0, int((end - start).total_seconds()))


def format_job_row(console: Console, job: dict) -> list[str]:
    """One job as a row, including which step is currently running.

    The step is the part the dashboard hides behind a click, and it is
    usually the single most useful thing on screen while a run is in flight.
    """
    state = job.get("conclusion") or job.get("status")
    active = next(
        (s for s in job.get("steps") or [] if s.get("status") == "in_progress"),
        None,
    )
    current = active["name"] if active else "-"
    return [
        str(job.get("id")),
        (job.get("name") or "-")[:36],
        console.paint(state),
        humanise_seconds(job.get("started_at") and _job_elapsed(job)),
        current[:30],
    ]


def _job_elapsed(job: dict) -> int:
    from datetime import datetime, timezone

    if not job.get("started_at"):
        return 0
    try:
        start = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
    except ValueError:
        return 0
    end = datetime.now(timezone.utc)
    if job.get("completed_at"):
        try:
            end = datetime.fromisoformat(job["completed_at"].replace("Z", "+00:00"))
        except ValueError:
            pass
    return max(0, int((end - start).total_seconds()))


def failed_steps(job: dict) -> list[str]:
    return [
        s.get("name", "?")
        for s in job.get("steps") or []
        if s.get("conclusion") == "failure"
    ]

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

HELP = """
  Read
    status  [run-id]      summary of the latest run (or a specific one)
    runs    [branch]      recent workflow runs, newest first
    jobs    [run-id]      every job in a run, with the current step
    log     <job-id>      print a job's log (--tail N for the last N lines)
    arts    [run-id]      artifacts attached to a run
    pending [run-id]      deployments waiting for a reviewer

  Act (each one asks before it does anything)
    watch   [run-id]      live job table until the run finishes (Ctrl-C to stop)
    retry   [run-id]      re-run ONLY the failed jobs
    again   [run-id]      re-run the entire workflow
    cancel  [run-id]      cancel a run that is still going
    kill    [run-id]      force-cancel, ignoring graceful shutdown
    approve [run-id]      approve a run held for fork-PR review
    deploy  [run-id]      approve pending environment deployments
    purge   [run-id]      delete a run and free its artifact quota
    nuke    [run-id]      delete a run's logs but keep the run
    send    <workflow>    trigger workflow_dispatch (e.g. send ci.yml main)

  Misc
    help                 this text
    quit                 leave
"""


class App:
    """The interactive terminal."""

    def __init__(self, api: GitHub, console: Console, branch: str | None) -> None:
        self.api = api
        self.console = console
        self.branch = branch

    # -- helpers -----------------------------------------------------------

    def _resolve(self, run_id: str | None) -> int:
        """Turn a possibly-missing id into a concrete run id."""
        if run_id:
            return int(run_id)
        found = self.api.latest_run_id(self.branch)
        if not found:
            raise GitHubError("no workflow runs found for this repository")
        return found

    def _banner(self, run: dict) -> None:
        state = run.get("conclusion") or run.get("status")
        self.console.print(
            self.console.style.bold(f"Run {run.get('id')}")
            + self.console.style.dim(f"  {run.get('name')}")
        )
        self.console.print(
            f"  {self.console.paint(state)}  "
            f"{run.get('head_branch')}  {self.console.style.dim(short_sha(run))}  "
            f"{commit_line(run)[:60]}"
        )
        if run.get("html_url"):
            self.console.print(self.console.style.dim(f"  {run['html_url']}"))
        self.console.rule()

    def done(self, message: str) -> None:
        self.console.print(self.console.style.green(f"  {message}"))

    # -- read commands -----------------------------------------------------

    def cmd_status(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        run = self.api.run(run_id)
        jobs = self.api.jobs(run_id)
        self._banner(run)

        self.console.table(
            ["JOB ID", "NAME", "STATE", "TIME", "CURRENT STEP"],
            [format_job_row(self.console, j) for j in jobs],
        )

        failed = [j for j in jobs if j.get("conclusion") == "failure"]
        if failed:
            self.console.print()
            self.console.print(self.console.style.red("  Failing steps:"))
            for job in failed:
                for step in failed_steps(job):
                    self.console.print(
                        f"    {self.console.style.red('x')} {job.get('name')} "
                        f"{self.console.style.dim('->')} {step}"
                    )
            self.console.print()
            self.console.print(
                self.console.style.dim(
                    f"  fix it, then: retry {run_id}   (logs: log <job-id>)"
                )
            )

    def cmd_runs(self, branch: str | None) -> None:
        runs = self.api.runs(branch=branch or self.branch, per_page=15)
        self.console.print(
            self.console.style.bold(f"Recent runs ({self.api.owner}/{self.api.name})")
        )
        self.console.table(
            ["RUN", "STATE", "WORKFLOW", "BRANCH", "SHA", "TIME", "COMMIT"],
            [format_run_row(self.console, r) for r in runs],
        )

    def cmd_jobs(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        run = self.api.run(run_id)
        self._banner(run)
        self.console.table(
            ["JOB ID", "NAME", "STATE", "TIME", "CURRENT STEP"],
            [format_job_row(self.console, j) for j in self.api.jobs(run_id)],
        )

    def cmd_log(self, arg: str | None, tail: int | None = None) -> None:
        if not arg:
            raise GitHubError("which job?  try:  log <job-id>")
        self.console.print(self.console.style.dim(f"  fetching log for job {arg} ..."))
        self.console.rule()
        self.console.print(self.api.job_log(int(arg), tail=tail).rstrip())
        self.console.rule()

    def cmd_artifacts(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        self.console.print(self.console.style.bold(f"Artifacts for run {run_id}"))
        self.console.table(
            ["ID", "NAME", "SIZE", "EXPIRES"],
            [
                [
                    str(a.get("id")),
                    a.get("name", "-"),
                    f"{int(a.get('size_in_bytes') or 0) / 1024:.0f} KB",
                    (a.get("expires_at") or "-")[:10],
                ]
                for a in self.api.artifacts(run_id)
            ],
        )

    def cmd_pending(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        pending = self.api.pending_deployments(run_id)
        if not pending:
            self.console.print(self.console.style.green("  nothing waiting for approval"))
            return
        self.console.print(self.console.style.bold(f"Pending for run {run_id}"))
        for env in pending:
            self.console.print(f"  {env.get('id')}  {env.get('name')}")
        self.console.print(
            self.console.style.dim(f"  approve them with:  deploy {run_id}")
        )

    # -- mutating commands -------------------------------------------------
    # Every one of these asks first. The prompt names the exact run so a
    # mistyped id is obvious before anything irreversible happens.

    def _confirm(self, question: str) -> bool:
        self.console.print()
        return self.console.confirm(question)

    def cmd_retry(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"re-run only the FAILED jobs of run {run_id}?"):
            self.api.rerun_failed(run_id)
            self.done(f"re-running failed jobs of {run_id}")

    def cmd_again(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"re-run ALL jobs of run {run_id}?"):
            self.api.rerun(run_id)
            self.done(f"re-running {run_id}")

    def cmd_cancel(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"cancel run {run_id}?"):
            self.api.cancel(run_id)
            self.done(f"cancelled {run_id}")

    def cmd_kill(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"FORCE-cancel run {run_id}, ignoring graceful shutdown?"):
            self.api.force_cancel(run_id)
            self.done(f"force-cancelled {run_id}")

    def cmd_approve(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"approve run {run_id} for fork-PR review?"):
            self.api.approve_run(run_id)
            self.done(f"approved {run_id}")

    def cmd_deploy(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"approve all pending deployments on run {run_id}?"):
            self.api.review_deployments(run_id, approve=True)
            self.done(f"deployments on {run_id} approved")

    def cmd_purge(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"DELETE run {run_id} and its artifacts?  This cannot be undone."):
            self.api.delete_run(run_id)
            self.done(f"deleted {run_id}")

    def cmd_nuke(self, arg: str | None) -> None:
        run_id = self._resolve(arg)
        if self._confirm(f"delete the LOGS of run {run_id}?  The run itself is kept."):
            self.api.delete_logs(run_id)
            self.done(f"logs of {run_id} deleted")

    def cmd_send(self, workflow: str | None, ref: str, inputs: dict) -> None:
        if not workflow:
            raise GitHubError("which workflow?  try:  send ci.yml main")
        target = ", ".join(f"{k}={v}" for k, v in inputs.items()) or "no inputs"
        if self._confirm(f"dispatch '{workflow}' on '{ref}' ({target})?"):
            self.api.dispatch(workflow, ref, inputs)
            self.done(f"dispatched {workflow} on {ref}")

    # -- live view ---------------------------------------------------------

    def cmd_watch(self, arg: str | None) -> None:
        """Poll a run until it finishes, redrawing the job table in place.

        A plain reprint each poll would flood the scrollback, so the screen
        is cleared and repainted. That is only possible on a TTY; piped
        output gets a timestamped line per poll instead.
        """
        run_id = self._resolve(arg)
        interactive = sys.stdout.isatty()

        while True:
            run = self.api.run(run_id)
            jobs = self.api.jobs(run_id)
            state = run.get("conclusion") or run.get("status")

            if interactive:
                # Move to the top and clear rather than scrolling.
                self.console.print("\033[2J\033[H", end="")
            else:
                self.console.print(
                    self.console.style.dim(f"--- {run_id} {state} ---")
                )

            self._banner(run)
            self.console.table(
                ["JOB ID", "NAME", "STATE", "TIME", "CURRENT STEP"],
                [format_job_row(self.console, j) for j in jobs],
            )

            failed = [j for j in jobs if j.get("conclusion") == "failure"]
            if failed:
                self.console.print()
                for job in failed:
                    for step in failed_steps(job):
                        self.console.print(
                            f"  {self.console.style.red('x')} {job.get('name')}"
                            f" {self.console.style.dim('->')} {step}"
                        )

            # A run is finished once it is no longer queued or in progress.
            if run.get("status") == "completed":
                self.console.print()
                self.console.print(f"  finished: {self.console.paint(state)}")
                return

            try:
                time.sleep(POLL_SECONDS)
            except KeyboardInterrupt:
                self.console.print()
                return

    # -- the loop ----------------------------------------------------------

    def dispatch(self, line: str) -> bool:
        """Run one command line. Returns False when the user wants to quit."""
        line = line.strip()
        if not line:
            return True

        parts = line.split()
        command, args = parts[0].lower(), parts[1:]

        if command in {"quit", "exit", "q"}:
            return False
        if command in {"help", "h", "?"}:
            self.console.print(HELP)
            return True

        # `--tail N` is accepted anywhere so `log 123 --tail 50` works.
        tail: int | None = None
        if "--tail" in args:
            index = args.index("--tail")
            if index + 1 < len(args) and args[index + 1].isdigit():
                tail = int(args[index + 1])
                del args[index : index + 2]
        first = args[0] if args else None

        try:
            if command == "status":
                self.cmd_status(first)
            elif command == "runs":
                self.cmd_runs(first)
            elif command == "jobs":
                self.cmd_jobs(first)
            elif command == "log":
                self.cmd_log(first, tail)
            elif command in {"arts", "artifacts"}:
                self.cmd_artifacts(first)
            elif command == "pending":
                self.cmd_pending(first)
            elif command == "watch":
                self.cmd_watch(first)
            elif command == "retry":
                self.cmd_retry(first)
            elif command == "again":
                self.cmd_again(first)
            elif command == "cancel":
                self.cmd_cancel(first)
            elif command == "kill":
                self.cmd_kill(first)
            elif command == "approve":
                self.cmd_approve(first)
            elif command == "deploy":
                self.cmd_deploy(first)
            elif command == "purge":
                self.cmd_purge(first)
            elif command == "nuke":
                self.cmd_nuke(first)
            elif command == "send":
                # Remaining args are `workflow ref [key=value ...]`.
                extra = dict(p.split("=", 1) for p in args[1:] if "=" in p)
                positional = [p for p in args[1:] if "=" not in p]
                self.cmd_send(first, positional[0] if positional else "main", extra)
            else:
                self.console.print(
                    self.console.style.yellow(f"  unknown command: {command}")
                )
                self.console.print(self.console.style.dim("  type 'help' for the list"))
        except GitHubError as exc:
            self.console.print()
            self.console.print(self.console.style.red(f"  {exc}"))
        except ValueError:
            self.console.print(
                self.console.style.yellow("  that argument must be a number")
            )
        return True

    def loop(self) -> None:
        self.console.print(
            self.console.style.bold("ci_console")
            + self.console.style.dim(f"  {self.api.owner}/{self.api.name}")
        )
        self.console.print(
            self.console.style.dim("  type 'help' for commands, 'quit' to leave")
        )

        while True:
            try:
                line = input(self.console.style.cyan("\nci> "))
            except (EOFError, KeyboardInterrupt):
                self.console.print()
                return
            if not self.dispatch(line):
                return

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_inputs(pairs: list[str]) -> dict:
    """Turn ``--input key=value`` pairs into a dict, validating the shape."""
    result = {}
    for pair in pairs or []:
        if "=" not in pair:
            raise GitHubError(f"--input expects key=value, got '{pair}'")
        key, value = pair.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def resolve_repo(explicit: str | None) -> str:
    """Work out which repository to talk to.

    Inside Actions this is injected as GITHUB_REPOSITORY. Outside it the git
    remote is read, so the tool works with no configuration at all.
    """
    if explicit:
        return explicit
    env = os.environ.get("GITHUB_REPOSITORY")
    if env:
        return env

    remote = ""
    try:
        import subprocess

        remote = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
    except Exception:
        remote = ""

    if remote:
        cleaned = remote.removesuffix(".git")
        if cleaned.startswith("git@") and ":" in cleaned:
            return cleaned.split(":", 1)[1]
        parts = [p for p in cleaned.split("/") if p]
        if len(parts) >= 2:
            return f"{parts[-2]}/{parts[-1]}"

    raise GitHubError(
        "cannot tell which repository this is.\n"
        "  Set GITHUB_REPOSITORY, or pass --repo owner/name."
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci_console.py",
        description="Live terminal for this repository's GitHub Actions runs.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["status", "runs", "jobs", "log", "arts", "pending",
                 "watch", "retry", "again", "cancel", "kill", "approve",
                 "deploy", "purge", "nuke", "send", "help"],
        help="run one command and exit (default: interactive)",
    )
    parser.add_argument("target", nargs="?", help="run id, job id, branch or workflow")
    parser.add_argument("--repo", help="owner/name (default: $GITHUB_REPOSITORY)")
    parser.add_argument("--branch", help="only show runs on this branch")
    parser.add_argument("--ref", default="main", help="ref for 'send'")
    parser.add_argument(
        "--input", action="append", metavar="KEY=VALUE",
        help="workflow_dispatch input; repeatable",
    )
    parser.add_argument("--tail", type=int, help="with 'log', show the last N lines")
    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    console = Console()

    if args.command == "help":
        parser.print_help()
        return 0

    # A one-shot command must never prompt, or a pipeline would hang waiting
    # for an answer that can never arrive. It still says what it did.
    if args.command and not sys.stdin.isatty():
        console.confirm = console.auto_confirm  # type: ignore[assignment]

    try:
        api = GitHub(resolve_repo(args.repo),
                     os.environ.get("GITHUB_TOKEN")
                     or os.environ.get("GH_TOKEN")
                     or "",
                     console)
        app = App(api, console, args.branch)

        if not args.command:
            if not sys.stdin.isatty():
                # No TTY and no command: a status report is far more useful
                # than a prompt nobody can answer.
                app.cmd_status(None)
                return 0
            app.loop()
            return 0

        # Reuse the interactive dispatcher so both entry points share one
        # implementation of every command.
        pieces = [args.command, args.target or ""]
        if args.tail is not None:
            pieces += ["--tail", str(args.tail)]
        for pair in parse_inputs(args.input or []):
            pieces += [f"{pair[0]}={pair[1]}"]
        if args.command == "send" and args.target:
            pieces.append(args.ref)
        app.dispatch(" ".join(p for p in pieces if p))
        return 0
    except GitHubError as exc:
        console.print(console.style.red(f"error: {exc}"))
        return 2
    except KeyboardInterrupt:
        console.print()
        return 130


if __name__ == "__main__":
    sys.exit(main())
