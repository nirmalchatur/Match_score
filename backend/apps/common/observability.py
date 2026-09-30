"""
Structured operational logging for important operations.

Why this exists
---------------
Every module in this project already logs, and each one invented its own shape:
``ai.tailor_start provider=ollama experience=3``, ``resume.render_failed
resume=12 fmt=pdf``, and a dozen variations on the same three fields. That is
readable by a person and useless to a filter: "how long did tailoring take
yesterday" cannot be answered without knowing every spelling of ``duration``.

This module gives the handful of operations worth measuring one line format:

    operation=resume_tailoring outcome=ok duration_ms=14203 provider=ollama
    model=llama3.1 validation=valid user=7

Three properties matter, and each is the reason for a rule below.

**Never log a secret.** A structured logger invites ``log_operation(...,
api_key=key)`` and the field name is the only thing standing between a
credential and a log aggregator that keeps it for a year. So redaction is by
field *name* and by field *value* shape, and it is applied here rather than
left to the call site's discipline. This is asserted by
``apps.common.tests.test_observability``.

**Never break the operation.** A log line is diagnostics attached to real work.
``log_operation`` cannot raise, whatever it is handed, so a caller never has to
wrap it.

**No new platform.** These go to the standard ``logging`` tree, so Render's log
stream (or a local console) already collects them. ``ARCHITECTURE.md`` records
that a hosted observability product is deliberately not part of this phase.

What this is *not*: an audit trail. A log line is disposable and is not what a
user or an operator should be asked to trust. Durable records live in
``apps.ai.models.AIRun`` and ``apps.common.models.ActivityEvent``.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

#: The logger every operation line goes to, regardless of the module that
#: emits it. One name, so one filter is enough to isolate operational traffic
#: from Django's request logs and from the per-module debug lines.
logger = logging.getLogger("tailorup.operations")


#: Field names whose values are never written, whatever they happen to contain.
#: A credential is identified by the name it is passed under far more often
#: than by its shape, and the cost of redacting a benign field is a slightly
#: less informative line -- the cost of the opposite is a leaked key.
_SENSITIVE_NAME_RE = re.compile(
    r"key|secret|token|password|passwd|credential|authorization|cookie|"
    r"session|prompt|bearer",
    re.IGNORECASE,
)

#: Field *values* that are recognisably credentials even under an innocent
#: name. The prefixes are the real ones: Google AI Studio keys start ``AIza``,
#: Groq and OpenAI keys ``gsk_`` / ``sk-``, and a JWT starts with a base64
#: ``eyJ``. A test-created key of some other shape is caught by the name rule
#: instead, which is the case ``test_observability`` exercises.
_SENSITIVE_VALUE_RE = re.compile(
    r"^(?:AIza|gsk_|sk-|xox[baprs]-|eyJ)[A-Za-z0-9_\-\.]{4,}$"
)

_REDACTED = "[redacted]"

#: Longest value kept. A log line that carries a whole resume stops being a log
#: line; truncation makes the failure obvious without copying the document.
_MAX_VALUE = 160


def _coerce(value: Any) -> str:
    """
    Render one field value as a single line of text.

    Deliberately lossy. ``None`` becomes an empty string rather than the word
    "None" so ``completed_at=`` is visibly "absent" instead of looking like a
    timestamp, and a container reports its size rather than its contents --
    a resume dict has no business being printed, and its length is the part
    that is useful in a log.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return re.sub(r"\s+", " ", value).strip()[:_MAX_VALUE]
    if isinstance(value, (list, tuple, set)):
        return "len:%d" % len(value)
    if isinstance(value, dict):
        try:
            return json.dumps(
                sorted(value), default=str, separators=(",", ":")
            )[:_MAX_VALUE]
        except (TypeError, ValueError):  # pragma: no cover - defensive
            return "dict"
    return type(value).__name__


def is_sensitive_name(name: str) -> bool:
    """
    Whether a field name means "this value is a secret".

    Public because the activity record needs the same judgement when it decides
    which metadata keys to store: one module deciding what counts as sensitive
    is the point, and a second copy of the pattern would drift.
    """
    return bool(_SENSITIVE_NAME_RE.search(str(name or "")))


def is_sensitive_value(value: Any) -> bool:
    """Whether a value looks like a credential whatever it is called."""
    return isinstance(value, str) and bool(_SENSITIVE_VALUE_RE.match(value.strip()))


def redact_fields(fields: dict) -> dict:
    """
    Drop anything that must not reach a log, keyed on name and on value shape.

    Returns a new dict; the caller's is untouched, because a log call mutating
    its own arguments would be a genuinely surprising side effect.
    """
    safe = {}
    for name, value in (fields or {}).items():
        key = str(name)
        if is_sensitive_name(key) or is_sensitive_value(value):
            safe[key] = _REDACTED
            continue
        safe[key] = _coerce(value)
    return safe


def render_operation(
    operation: str,
    *,
    outcome: str = "ok",
    duration_ms: int | float | None = None,
    **fields: Any,
) -> str:
    """
    Build the log line for one operation, without logging it.

    Split out from :func:`log_operation` so the format is a pure function a
    test can assert on, and so a caller that wants the rendered line (a
    diagnostic script, say) does not have to attach a handler to get it.

    Field order is fixed: operation, outcome, duration, then the caller's
    fields sorted by name. A stable order is what makes these lines greppable
    rather than merely present.
    """
    parts = [
        "operation=%s" % _coerce(operation),
        "outcome=%s" % _coerce(outcome or "ok"),
    ]

    if duration_ms is not None:
        parts.append("duration_ms=%s" % _coerce(int(duration_ms)))

    safe = redact_fields(fields)
    for name in sorted(safe):
        parts.append("%s=%s" % (name, safe[name]))

    return " ".join(parts)


def log_operation(
    operation: str,
    *,
    outcome: str = "ok",
    duration_ms: int | float | None = None,
    level: str = "info",
    log: logging.Logger | None = None,
    **fields: Any,
) -> str:
    """
    Emit one operational line and return what was written.

    Never raises: this is called on the success path of real work, and a
    diagnostics failure must not be able to turn a successful tailoring run
    into a 500. The exception swallowed here is genuinely exceptional -- a
    logger whose handlers are broken -- which is the correct trade rather than
    a convenience.
    """
    try:
        line = render_operation(
            operation, outcome=outcome, duration_ms=duration_ms, **fields
        )
        (log or logger).log(
            getattr(logging, str(level).upper(), logging.INFO), "%s", line
        )
        return line
    except Exception:  # pragma: no cover - defensive by design
        return ""


class OperationTimer:
    """
    Time a block of work and log it once, whatever the outcome.

    Used as a context manager::

        with OperationTimer("resume_tailoring", user=user.pk) as timer:
            timer.add(provider="ollama")
            outcome = do_the_work()

    The failure path is the point. A try/finally in every caller is exactly the
    code that gets forgotten on the branch nobody tests, and the slow, failing
    operation is the one an operator most needs a duration for. The exception
    is never suppressed -- this only observes.

    ``add`` merges fields in, so a value only known part-way through (the
    provider that answered, the row that was written) still lands on the same
    line as everything else.
    """

    def __init__(
        self,
        operation: str,
        *,
        log: logging.Logger | None = None,
        **fields: Any,
    ):
        self.operation = operation
        self.log = log
        self.fields: dict = dict(fields)
        self.duration_ms: int | None = None
        self._started = 0.0

    def add(self, **fields: Any) -> None:
        """Attach fields discovered during the block."""
        self.fields.update(fields)

    def __enter__(self) -> "OperationTimer":
        self._started = time.monotonic()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.duration_ms = int((time.monotonic() - self._started) * 1000)

        if exc_type is None:
            log_operation(
                self.operation,
                outcome="ok",
                duration_ms=self.duration_ms,
                log=self.log,
                **self.fields,
            )
        else:
            # The exception *class* is logged, never its message: a provider
            # error message can carry the base URL and the response body, and
            # those belong in the module that raised it, not here.
            log_operation(
                self.operation,
                outcome="error",
                duration_ms=self.duration_ms,
                level="warning",
                log=self.log,
                error=exc_type.__name__,
                **self.fields,
            )

        # False: never swallow. This class observes, it does not handle.
        return False


__all__ = [
    "OperationTimer",
    "is_sensitive_name",
    "is_sensitive_value",
    "log_operation",
    "redact_fields",
    "render_operation",
]
