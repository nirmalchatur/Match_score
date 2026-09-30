"""
The recorder that writes one :class:`~apps.ai.models.AIRun` row around a call.

Why this is a separate module
-----------------------------
``ResumeTailor`` orchestrates: prompt in, validated result out, and it must not
know that an audit table exists -- the same reason it does not know about
SQLite or Postgres. This module owns the persistence side of the run, so the
orchestrator stays a pure function of its inputs and the audit trail can be
extended (retries, a worker, a different table) without touching it.

The rule that shapes every method here: **recording must never break the
operation it is recording.** A user asked to tailor a resume. If the insert
fails, the correct outcome is still a tailored resume and a logged warning, not
a 500 for a bookkeeping row nobody asked for. So every write is guarded, and
:meth:`AIRunRecorder.__exit__` returns ``False`` -- the original exception, if
any, always propagates unchanged.

The mirror of that rule is that this module never decides anything. It does not
validate the output, does not choose a skill, and does not touch a match score.
It observes.
"""

from __future__ import annotations

import logging
import time

from apps.common.observability import log_operation

from .exceptions import (
    AIConfigurationError,
    AIProviderResponseError,
    AIProviderTimeoutError,
    AIProviderUnavailableError,
    AITailoringValidationError,
)
from .models import AIRun

logger = logging.getLogger(__name__)

#: Exception class -> failure bucket. Ordered, and walked with ``isinstance``,
#: so a subclass added later inherits its parent's bucket instead of silently
#: becoming INTERNAL.
FAILURE_CATEGORIES = (
    (AIConfigurationError, AIRun.FAILURE_CONFIGURATION),
    (AIProviderUnavailableError, AIRun.FAILURE_PROVIDER_UNAVAILABLE),
    (AIProviderTimeoutError, AIRun.FAILURE_PROVIDER_TIMEOUT),
    (AIProviderResponseError, AIRun.FAILURE_INVALID_RESPONSE),
    (AITailoringValidationError, AIRun.FAILURE_VALIDATION_FAILED),
)


def failure_category_for(exc: BaseException) -> str:
    """
    Bucket an exception, or return ``INTERNAL`` for anything unrecognised.

    A new exception type added without a bucket shows up as INTERNAL rather
    than as its own category, which is the honest answer: nobody has decided
    what it means yet.
    """
    for cls, category in FAILURE_CATEGORIES:
        if isinstance(exc, cls):
            return category
    return AIRun.FAILURE_INTERNAL


def error_code_for(exc: BaseException) -> str:
    """
    The machine-readable code the API layer will return, or a safe stand-in.

    ``getattr`` rather than a type check because the code lives on the
    exception as a class attribute (``AIError.code``); a non-AI exception has
    none, and inventing one from ``str(exc)`` would put a message where a code
    belongs.
    """
    return str(getattr(exc, "code", "") or "internal_error")


def provider_identity(provider) -> tuple[str, str]:
    """
    ``(name, model)`` for a provider instance, without ever raising.

    Both are non-secret: ``describe()`` is the same method the status endpoint
    already exposes to the browser. A provider that cannot describe itself
    yields empty strings rather than failing an audit write.
    """
    try:
        described = provider.describe() or {}
    except Exception:  # pragma: no cover - defensive
        return "", ""

    name = str(described.get("provider") or getattr(provider, "name", "") or "")
    model = str(described.get("model") or "")
    return name[:50], model[:100]


class AIRunRecorder:
    """
    Record one AI operation for its whole lifetime.

    ::

        with AIRunRecorder(user=user, operation=AIRun.OPERATION_RESUME_TAILORING,
                           source_resume=master, source_job=job) as run:
            run.use_provider(active_provider)
            raw = active_provider.tailor_resume(request)
            run.attach_validation(outcome.validation.status)

    The row is created PENDING, moved to RUNNING immediately (the call is about
    to happen), and closed on the way out. A caller that never calls
    ``use_provider`` still gets an honest row: an empty provider is a run that
    failed before one was resolved, which is exactly what a misconfigured
    deployment looks like.

    ``enabled=False`` skips the database entirely, so a unit test of the
    orchestrator does not need a user fixture to exercise it.
    """

    def __init__(
        self,
        *,
        user,
        operation: str,
        provider: str = "",
        model: str = "",
        prompt_version: str = "",
        source_resume=None,
        source_job=None,
        enabled: bool = True,
    ):
        self.user = user
        self.operation = operation
        self.provider = provider
        self.model = model
        self.prompt_version = prompt_version
        self.source_resume = source_resume
        self.source_job = source_job
        self.enabled = enabled

        #: The row, or ``None`` when the audit write failed. Public so a test
        #: can assert on it, and so a caller can attach a result id.
        self.run: AIRun | None = None

        self.validation_status = ""
        self._started = 0.0
        self._outcome = "ok"

    # -- setup -----------------------------------------------------------

    def use_provider(self, provider) -> None:
        """
        Adopt the identity of the provider that is about to be called.

        The values are written onto the *row* as well as onto the recorder,
        because the row was created before a provider existed -- that is what
        makes "failed before a provider was resolved" distinguishable from
        "the provider failed".
        """
        self.provider, self.model = provider_identity(provider)

        if self.run is not None:
            self.run.provider = self.provider[:50]
            self.run.model = self.model[:100]

        self._persist("provider", "model")

    def attach_validation(self, status: str) -> None:
        """
        Record the factual validator's verdict for this run.

        Written onto the row immediately as well as held on the recorder: the
        verdict is frequently the *reason* a run failed, and on that path the
        row is closed by ``mark_failed``, which has no verdict argument. Holding
        it only in memory meant a rejected run recorded the bucket and not the
        verdict -- the one detail that explains it.
        """
        self.validation_status = str(status or "")[:16]

        if self.run is not None:
            self.run.validation_status = self.validation_status

    def attach_result(self, resume) -> None:
        """
        Point the run at the artifact it produced.

        Called after a save, so the row answers "which resume did this
        produce?" as well as "did it succeed?". Guarded like every other write:
        failing to link a result must not fail the save that just succeeded.
        """
        if self.run is None or resume is None:
            return
        try:
            self.run.result_resume = resume
            self.run.save(update_fields=["result_resume"])
        except Exception:  # pragma: no cover - defensive
            logger.warning(
                "ai.run_result_link_failed run=%s", getattr(self.run, "pk", None)
            )

    @property
    def run_id(self):
        """The row's id, or ``None``. Convenient for logging and tests."""
        return getattr(self.run, "pk", None)

    # -- persistence -----------------------------------------------------

    def _persist(self, *fields) -> None:
        """Best-effort save of named fields. Never raises."""
        if self.run is None:
            return
        try:
            self.run.save(update_fields=list(fields))
        except Exception:  # pragma: no cover - defensive by design
            logger.exception("ai.run_save_failed run=%s", getattr(self.run, "pk", None))

    def __enter__(self) -> "AIRunRecorder":
        self._started = time.monotonic()

        if not self.enabled:
            return self

        try:
            self.run = AIRun.objects.create(
                user=self.user,
                operation=self.operation,
                provider=self.provider[:50],
                model=self.model[:100],
                prompt_version=self.prompt_version[:32],
                source_resume=self.source_resume,
                source_job=self.source_job,
                # One row is one attempt. A retry gets its own row, so the
                # unsuccessful attempt stays visible; see ADR-003.
                attempts=1,
            )
            self.run.mark_running()
            self._persist("status", "started_at")
        except Exception:  # pragma: no cover - defensive by design
            logger.exception("ai.run_create_failed operation=%s", self.operation)
            self.run = None

        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        duration_ms = int((time.monotonic() - self._started) * 1000)

        if self.run is not None:
            try:
                if exc_type is None:
                    self.run.mark_succeeded(validation_status=self.validation_status)
                    self._outcome = "ok"
                elif not issubclass(exc_type, Exception):
                    # KeyboardInterrupt and friends: the run did not fail, it
                    # was abandoned. Recording that as a provider failure would
                    # blame the provider for an operator's Ctrl-C.
                    self.run.mark_cancelled()
                    self._outcome = "cancelled"
                else:
                    self.run.mark_failed(
                        failure_category_for(exc),
                        error_code=error_code_for(exc),
                    )
                    self._outcome = "error"

                # ``validation_status`` is written in every branch, including
                # the failure one: a run rejected by the factual validator has
                # to record *that* verdict, or the only evidence of why it died
                # is the coarse failure bucket.
                fields = ["status", "completed_at", "duration_ms", "validation_status"]

                if self._outcome == "error":
                    fields += ["failure_category", "error_code"]

                self._persist(*fields)
            except Exception:  # pragma: no cover - defensive by design
                logger.exception(
                    "ai.run_close_failed run=%s", getattr(self.run, "pk", None)
                )

        log_operation(
            "ai_run",
            outcome=self._outcome,
            duration_ms=duration_ms,
            # Named ``ai_operation`` rather than ``operation`` because the
            # first argument above already owns that name; the line then reads
            # `operation=ai_run ai_operation=RESUME_TAILORING`.
            ai_operation=self.operation,
            provider=self.provider or "none",
            model=self.model,
            status=getattr(self.run, "status", "unrecorded"),
            validation=self.validation_status,
            user=getattr(self.user, "pk", None),
        )

        # False: the operation's own exception, if any, is not ours to handle.
        return False
