"""
The audit record for one AI operation.

Why this exists
---------------
``ResumeTailor`` returns everything the review UI needs and throws away the
rest. When a run fails, or produces something surprising, the only surviving
evidence is a log line that scrolled away: which provider answered, which model
it used, whether the factual validator approved the output, and how long it
took are all gone by the time anyone asks. "What happened when this AI result
was generated?" is a question the repository could not answer.

Two constraints shape what is stored here.

**No secrets, no payloads.** Nothing in this table is a credential, a prompt or
a provider response. The provider name and the model *name* are recorded
because they explain a result; the base URL and the key are configuration, and
a stored raw response would be a second copy of the user's resume sitting in an
audit table.

**It is not the business logic.** This is written by the orchestrator *around*
the provider call. It cannot change a match score, decide a skill, or mark an
artifact approved -- the deterministic layer owns all three, which is what
``apps.common.tests.test_architecture`` asserts.

A fuller discussion, including why this is one table rather than a job queue,
is in ``docs/adr/ADR-005-ai-run-audit.md``.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone


class AIRun(models.Model):
    """
    One AI operation, from request to verdict.

    Deliberately a *record*, not a worker: it is written synchronously by the
    code that made the call. The state machine is here so that introducing a
    real worker later is a change of driver rather than a change of contract --
    ``docs/adr/ADR-003-long-running-job-boundary.md`` states that boundary.
    """

    OPERATION_RESUME_TAILORING = "RESUME_TAILORING"

    #: A closed set. The operations this phase actually performs are listed;
    #: cover letters, interview preparation and the rest are named in ADR-003
    #: as future values rather than pre-declared here, because a choice with no
    #: producer is a claim the code does not support.
    OPERATION_CHOICES = [
        (OPERATION_RESUME_TAILORING, "Resume tailoring"),
    ]

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (RUNNING, "Running"),
        (SUCCEEDED, "Succeeded"),
        (FAILED, "Failed"),
        (CANCELLED, "Cancelled"),
    ]

    #: The states a run never leaves. A terminal row is immutable: a retry is a
    #: new row, so the history of a flaky provider stays visible instead of
    #: being overwritten by the attempt that worked.
    TERMINAL_STATUSES = frozenset({SUCCEEDED, FAILED, CANCELLED})

    #: The only legal moves. PENDING -> FAILED is allowed on purpose: a run that
    #: dies before it starts (no provider configured, no key, no master resume)
    #: never reaches RUNNING, and recording it as "still pending" forever would
    #: hide a configuration problem behind a spinner.
    VALID_TRANSITIONS = {
        PENDING: frozenset({RUNNING, FAILED, CANCELLED}),
        RUNNING: frozenset({SUCCEEDED, FAILED, CANCELLED}),
        SUCCEEDED: frozenset(),
        FAILED: frozenset(),
        CANCELLED: frozenset(),
    }

    #: Coarse buckets, so "why did AI fail last week" is answerable without
    #: reading messages. A category is not a message: it is chosen from this
    #: list, and anything unrecognised becomes INTERNAL rather than free text.
    FAILURE_CONFIGURATION = "CONFIGURATION"
    FAILURE_PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    FAILURE_PROVIDER_TIMEOUT = "PROVIDER_TIMEOUT"
    FAILURE_INVALID_RESPONSE = "INVALID_RESPONSE"
    FAILURE_VALIDATION_FAILED = "VALIDATION_FAILED"
    FAILURE_INTERNAL = "INTERNAL"

    FAILURE_CATEGORY_CHOICES = [
        (FAILURE_CONFIGURATION, "Misconfiguration"),
        (FAILURE_PROVIDER_UNAVAILABLE, "Provider unavailable"),
        (FAILURE_PROVIDER_TIMEOUT, "Provider timed out"),
        (FAILURE_INVALID_RESPONSE, "Unreadable model response"),
        (FAILURE_VALIDATION_FAILED, "Factual validation rejected the output"),
        (FAILURE_INTERNAL, "Unexpected failure"),
    ]

    #: Tenant boundary: an AI run is only ever visible to its owner.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ai_runs",
    )

    operation = models.CharField(max_length=48, choices=OPERATION_CHOICES)

    #: Non-secret identification only: "ollama", "gemini", "fake". Never a URL
    #: and never a key.
    provider = models.CharField(max_length=50, blank=True, default="")
    model = models.CharField(max_length=100, blank=True, default="")

    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default=PENDING)

    #: Set only when ``status`` is FAILED. Empty for every other state, so a
    #: filter on it cannot accidentally include a run that is still going.
    failure_category = models.CharField(
        max_length=32,
        choices=FAILURE_CATEGORY_CHOICES,
        blank=True,
        default="",
    )

    #: The machine-readable code the API layer returned ("ai_timeout",
    #: "ai_validation_failed"). A code, never a message: messages carry base
    #: URLs and provider bodies, and those belong in the log.
    error_code = models.CharField(max_length=48, blank=True, default="")

    #: Which prompt/template produced this. A tailoring result from an older
    #: prompt is not comparable with a newer one, and without this there is no
    #: way to tell them apart after the fact.
    prompt_version = models.CharField(max_length=32, blank=True, default="")

    #: The factual-validator verdict: "valid", "warning", "rejected", or empty
    #: when the run never got as far as validating anything.
    validation_status = models.CharField(max_length=16, blank=True, default="")

    #: What it read and what it wrote. All nullable because deleting a resume
    #: must not delete the record that a run happened.
    source_resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_runs",
    )
    source_job = models.ForeignKey(
        "jobs.Job",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ai_runs",
    )
    result_resume = models.ForeignKey(
        "resumes.Resume",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="produced_by_ai_runs",
        help_text="The artifact this run produced, once the user saved it.",
    )

    #: How many attempts this row represents. Always 1 in this phase, because
    #: nothing retries yet; the field exists so a retry loop can be added
    #: without a migration, and so a reader can tell a first attempt from a
    #: tenth when it is.
    attempts = models.PositiveSmallIntegerField(default=0)

    #: Non-sensitive counters only (token counts, model-reported usage). Never
    #: a prompt and never a response body.
    usage = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    duration_ms = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]

        indexes = [
            models.Index(fields=["user", "-created_at"], name="airun_user_time_idx"),
            models.Index(fields=["user", "operation"], name="airun_user_op_idx"),
            models.Index(fields=["status"], name="airun_status_idx"),
        ]

    def __str__(self):
        return "%s %s %s" % (self.operation, self.status, self.user_id)

    # -- state machine ---------------------------------------------------

    @property
    def is_terminal(self) -> bool:
        return self.status in self.TERMINAL_STATUSES

    def can_transition_to(self, status: str) -> bool:
        """
        Whether ``status`` is reachable from the current one.

        A self-transition is refused even where it looks harmless: writing
        RUNNING over RUNNING would reset ``started_at`` and quietly lose the
        real start time of a run that is still going.
        """
        return status in self.VALID_TRANSITIONS.get(self.status, frozenset())

    def transition_to(self, status: str, **fields):
        """
        Move the run to ``status``, or raise ``ValueError``.

        Raising is right here, unlike almost everything else in the audit path:
        the only way to reach this with an illegal move is a bug in the caller,
        and a state machine that silently accepts anything is not a state
        machine. The persister (:mod:`apps.ai.runs`) is where the "never break
        the operation" rule lives, and it checks ``can_transition_to`` first.
        """
        if not self.can_transition_to(status):
            raise ValueError(
                "Cannot move an AI run from %s to %s." % (self.status, status)
            )

        self.status = status

        now = timezone.now()

        if status == self.RUNNING and self.started_at is None:
            self.started_at = now
        if status in self.TERMINAL_STATUSES:
            self.completed_at = now
            if self.started_at is not None:
                self.duration_ms = int(
                    (self.completed_at - self.started_at).total_seconds() * 1000
                )

        for name, value in fields.items():
            setattr(self, name, value)

        return self

    def mark_running(self):
        """Started: the provider is about to be called."""
        return self.transition_to(self.RUNNING)

    def mark_succeeded(self, *, validation_status: str = "", usage: dict | None = None):
        """Finished and the result was produced."""
        fields = {}
        if validation_status:
            fields["validation_status"] = validation_status[:16]
        if usage:
            fields["usage"] = usage
        return self.transition_to(self.SUCCEEDED, **fields)

    def mark_failed(self, category: str, *, error_code: str = ""):
        """
        Finished badly, with a bucket and a code.

        An unknown category becomes INTERNAL rather than being stored as given,
        so a caller cannot turn this column back into free text -- and so a
        filter for "misconfiguration" is a filter that actually means it.
        """
        known = {value for value, _label in self.FAILURE_CATEGORY_CHOICES}
        if category not in known:
            category = self.FAILURE_INTERNAL

        return self.transition_to(
            self.FAILED,
            failure_category=category,
            error_code=str(error_code or "")[:48],
        )

    def mark_cancelled(self):
        """Abandoned, which is not a failure: nothing went wrong."""
        return self.transition_to(self.CANCELLED)

    # -- exposure --------------------------------------------------------

    #: The only shape any future endpoint may return. Written down here rather
    #: than improvised at a call site, because the question "could this response
    #: carry a credential?" has one answer per model, not one per endpoint.
    def public_dict(self) -> dict:
        return {
            "id": self.id,
            "operation": self.operation,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "validation_status": self.validation_status,
            "failure_category": self.failure_category,
            "error_code": self.error_code,
            "prompt_version": self.prompt_version,
            "duration_ms": self.duration_ms,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
