"""
The application service behind the tailoring endpoints.

Why this exists
---------------
The tailoring flow used to be written inside ``TailorResumeView.post`` and
``SaveTailoredResumeView.post``: ownership lookups, provider resolution, key
decryption, progress reporting, validation, the AI audit write and the
persistence of the resulting artifact, all interleaved with HTTP status codes.
That is a lot of business decisions in two methods that a test can only reach
through a request.

This module is the missing layer between them:

    View (auth, throttling, error -> HTTP)
        |
    TailoringService                        <- this module
        |
    ResumeTailor  +  validators  +  AIRunRecorder  +  ActivityEvent
        |
    Resume / Job models

What moved out of the views: *which* resume and job are involved, whether the
job is usable, which provider and key apply, what counts as a failure, what is
recorded, and what is persisted. What stayed: authentication, throttling, and
the mapping of a :class:`TailoringError` onto a response.

Deliberately no HTTP here. The service raises :class:`TailoringError` (or an
``AIError``) and knows nothing about status codes -- ``status_code`` on the
exception is a *request* made to the API layer, which is free to disagree.
"""

from __future__ import annotations

import logging
import time

from apps.ai import factory, progress, prompts, selection
from apps.ai.exceptions import AIError, AITailoringValidationError
from apps.ai.models import AIRun
from apps.ai.runs import AIRunRecorder
from apps.ai.schemas import normalise
from apps.ai.tailor import ResumeTailor, build_source_resume
from apps.ai.validators import validate as validate_tailoring
from apps.common.models import ActivityEvent
from apps.common.observability import OperationTimer
from apps.jobs.models import Job
from apps.jobs.services.jd_profile import JDProfile
from apps.resumes import qualities
from apps.resumes.models import Resume, ResumeProfile

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TailoringError(Exception):
    """
    A tailoring request that cannot be satisfied, in API-agnostic terms.

    ``code`` is the same machine-readable token the endpoints have always
    returned, so moving the decision here did not change the contract the
    frontend branches on. ``extra`` is merged into the response body, which is
    how a rejection still carries its ``violations``.
    """

    code = "tailoring_error"
    status_code = 400

    def __init__(self, message: str, *, code: str = "", status_code: int = 0, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code
        self.extra = dict(extra or {})

    def as_dict(self) -> dict:
        """The response body. No detail, no internals, no stack."""
        payload = {"error": self.message, "code": self.code}
        payload.update(self.extra)
        return payload


class ResumeMissing(TailoringError):
    """No master resume on this account."""

    code = "resume_missing"
    status_code = 404


class JobMissing(TailoringError):
    """The job does not exist **or is not owned by this account**."""

    code = "job_missing"
    status_code = 404


class JobDescriptionMissing(TailoringError):
    """The job is stored but carries nothing to tailor against."""

    code = "job_description_missing"
    status_code = 400


class ResultMissing(TailoringError):
    """A save was called without a result payload."""

    code = "result_missing"
    status_code = 400


class TailoringRejected(TailoringError):
    """
    The submitted result claims something the master resume does not support.

    Carries the violations so the review screen can explain the refusal rather
    than just asserting it.
    """

    code = "ai_validation_failed"
    status_code = 422


# ---------------------------------------------------------------------------
# Loading the inputs
# ---------------------------------------------------------------------------


def mastered_resume(user) -> Resume:
    """This account's master resume, or :class:`ResumeMissing`."""
    master = Resume.objects.filter(user=user, is_master=True).first()
    if master is None:
        raise ResumeMissing("No master resume found. Upload one before tailoring.")
    return master


def stored_profile(resume: Resume) -> dict:
    """
    The stored profile dict, in the shape ``build_source_resume`` expects.

    A resume with no profile row yields ``{}`` rather than raising: the profile
    services may have failed on an old upload, and the tailoring pipeline is
    capable of saying "there is nothing to tailor here" more usefully than a
    500 from an import-time assumption.
    """
    try:
        profile = resume.profile
    except ResumeProfile.DoesNotExist:
        return {}

    return {
        "summary": "",
        "skills": profile.skills or [],
        "experience": profile.experience or {},
        "education": profile.education or "",
        "projects": profile.projects or "",
        "certifications": profile.certifications or "",
        # Chosen qualities ride along with the parsed profile so the tailoring
        # prompt and the match analysis can both see them. Normalised on read
        # as well as on write, because a row written before this field existed
        # holds {} rather than the canonical three-key shape.
        "qualities": qualities.normalize(profile.qualities),
    }


def load_job(user, job_id) -> Job:
    """
    Fetch a job **scoped to the requesting account**.

    Scoping by ``user`` in the query itself is what stops User A from tailoring
    against User B's job: there is no id-guessing path here at all. A malformed
    id is the same 404 as a missing one, deliberately -- a 400 would confirm
    that the id was well-formed but someone else's.
    """
    try:
        job_id = int(job_id)
    except (TypeError, ValueError):
        raise JobMissing("Job not found.") from None

    job = Job.objects.filter(user=user, id=job_id).first()
    if job is None:
        raise JobMissing("Job not found.")
    return job


def tailoring_context(user, job_id) -> tuple[Resume, Job, dict]:
    """
    Everything a tailoring needs, or a :class:`TailoringError`.

    The JD profile is re-derived from the stored description rather than looked
    up, so the emphasis the model is asked for agrees with the match score the
    user has already been shown.
    """
    master = mastered_resume(user)
    job = load_job(user, job_id)

    if not (job.description or "").strip():
        raise JobDescriptionMissing(
            "This job has no stored description to tailor against."
        )

    try:
        jd_profile = JDProfile.build(job.description)
    except ValueError:
        raise JobDescriptionMissing(
            "This job has no usable description to tailor against."
        ) from None

    return master, job, jd_profile


def resolve_provider_and_key(user) -> tuple[str, object, str]:
    """
    ``(provider_name, provider, api_key)`` for this account.

    The order matters and is the reason this is one function rather than three
    calls at the call site: the provider is resolved *first*, and the key is
    then resolved *for that provider*. Resolving the key first meant looking up
    a hardcoded provider, which is exactly the bug that made tailoring
    Gemini-only when Groq arrived (see ``apps.ai.selection``).

    Any :class:`~apps.ai.exceptions.AIError` from here -- including the
    ``AIConfigurationError`` an unconfigured deployment raises -- propagates to
    the caller, which turns it into a real response.
    """
    effective, _reason = selection.resolve_provider_name(user)
    provider = factory.get_ai_provider(effective)

    # The key is resolved now, at the single moment it is needed, rather than
    # held for the session. Absent for a keyless provider like Ollama, which
    # ignores it.
    api_key = selection.resolve_api_key(user, effective)

    return effective, provider, api_key


# ---------------------------------------------------------------------------
# The operations
# ---------------------------------------------------------------------------


def generate_tailoring(user, job_id) -> dict:
    """
    Produce a validated tailoring of this account's master resume for review.

    Saves nothing. The user reviews the before/after payload and saving is a
    separate, explicit call -- see :func:`save_tailored_resume`.

    Returns the review payload: the normalised result, the deterministic
    validation verdict, and the *source* resume as it is stored, so the UI
    renders originals from our data rather than from whatever the model echoed
    back.

    :raises TailoringError: the request cannot be satisfied (no master resume,
        unknown job, nothing to tailor against).
    :raises AIError: the provider could not be used, or its output failed
        factual validation. The subclasses carry the HTTP status the API layer
        should use.
    """
    master, job, jd_profile = tailoring_context(user, job_id)

    uid = user.pk
    progress.reset(uid)
    progress.emit(uid, "start", "Request received.")
    started = time.monotonic()

    with OperationTimer("tailoring_request", user=uid, job=job.pk) as timer:
        with AIRunRecorder(
            user=user,
            operation=AIRun.OPERATION_RESUME_TAILORING,
            prompt_version=prompts.PROMPT_VERSION,
            source_resume=master,
            source_job=job,
        ) as run:
            try:
                effective, provider, api_key = resolve_provider_and_key(user)

                progress.emit(
                    uid,
                    "provider",
                    "Provider: %s, model %s."
                    % (
                        effective or "unconfigured",
                        provider.describe().get("model") or "unknown",
                    ),
                )
                progress.emit(
                    uid,
                    "prompt",
                    "Building the tailoring prompt from your resume and this job.",
                )

                # Emitted immediately before the call. The wording matters: on a
                # CPU this is minutes, and saying so up front is the difference
                # between "it is working" and "it has hung".
                progress.emit(
                    uid,
                    "generating",
                    "Waiting for the model. On CPU this can take several minutes. "
                    "The page may look idle; it is not.",
                )

                run.use_provider(provider)
                timer.add(provider=effective or "none")

                outcome = ResumeTailor.tailor_resume(
                    provider=provider,
                    resume=stored_profile(master),
                    job={
                        "title": job.title,
                        "company": job.company,
                        "location": job.location,
                        "description": job.description,
                    },
                    # The match analysis already computed for this job, reused
                    # rather than recomputed.
                    match_analysis=job.match_result or {},
                    jd_profile=jd_profile,
                    api_key=api_key,
                )
            except AITailoringValidationError as exc:
                # Fabricated output is never returned as a suggestion. Recorded
                # as a validation failure, then re-raised so the API can return
                # the violations for the review screen.
                run.attach_validation("rejected")
                timer.add(validation="rejected")
                progress.emit(
                    uid,
                    "error",
                    "The result failed the factual check and was discarded "
                    "(%.0fs)." % (time.monotonic() - started),
                    level="error",
                )
                raise
            except AIError as exc:
                progress.emit(
                    uid,
                    "error",
                    "Failed after %.0fs: %s" % (time.monotonic() - started, exc.message),
                    level="error",
                )
                raise

            progress.emit(
                uid,
                "validating",
                "Checking the result against your original resume for invented facts.",
            )

            validation = outcome.validation
            verdict = getattr(validation, "status", "unknown")
            run.attach_validation(verdict)
            timer.add(validation=verdict)

            progress.emit(
                uid,
                "done",
                "Finished in %.0fs. Factual check: %s."
                % (time.monotonic() - started, verdict),
                level="done",
            )

            payload = outcome.as_dict()
            payload["job"] = {
                "id": job.id,
                "title": job.title,
                "company": job.company,
            }
            payload["master_resume_id"] = master.id

    ActivityEvent.record(
        user,
        ActivityEvent.TAILORING_GENERATED,
        object_type="job",
        object_id=job.id,
        summary=_job_label(job),
        metadata={
            "provider": effective or "",
            "model": str(payload.get("provider", {}).get("model") or ""),
            "validation": verdict,
            "run": run.run_id,
            "match_score": job.match_score,
        },
    )

    return payload


def save_tailored_resume(user, job_id, raw_result, provider_name: str = ""):
    """
    Persist a reviewed tailoring as a **new** resume version.

    The master is never modified. The result is **re-validated** against the
    stored master here rather than trusted, because it arrives from the browser:
    a payload edited in devtools would otherwise be able to persist content the
    validator had already rejected.

    Returns ``(tailored_resume, validation_payload)``.

    :raises ResultMissing: no result payload was sent.
    :raises TailoringRejected: the result claims something the master does not
        support. Nothing is written.
    """
    master, job, _jd_profile = tailoring_context(user, job_id)

    if not isinstance(raw_result, dict):
        raise ResultMissing("A tailoring result is required.")

    # The same normalisation and validation the generate path ran, against our
    # own copy of the master resume.
    parsed = normalise(raw_result)
    source = build_source_resume(stored_profile(master))
    validation = validate_tailoring(parsed, source)

    if validation.rejected:
        raise TailoringRejected(
            "This tailoring claims experience the master resume does not "
            "support, so it was not saved.",
            extra={"violations": [v.as_dict() for v in validation.violations]},
        )

    with OperationTimer("tailoring_save", user=user.pk, job=job.pk) as timer:
        tailored = Resume.objects.create(
            user=user,
            # Company + role reads naturally in the workspace and makes a
            # sensible download filename. The master name is deliberately not
            # folded in: it is already shown as the provenance link, and the
            # download filename strips parentheses anyway, which turned
            # "Acme - BE (Master Resume)" into "... BE Master Resume".
            name="%s - %s" % (job.company or "Job", job.title or "Role"),
            resume_type="TAILORED",
            is_master=False,
            source_resume=master,
            source_job=job,
            # The source view is re-derived from the stored master rather than
            # taken from the request, so a saved version is self-describing and
            # cannot be told to believe a client-supplied "original".
            tailoring_result={
                "result": parsed.to_dict(),
                "validation": validation.as_dict(),
                "source": source,
            },
            ai_provider=str(provider_name or "")[:50],
            # The structured content, so the existing resume endpoints can serve
            # this version without a document generator.
            profile_data=parsed.to_dict(),
        )

        # Mirror the master's profile so a tailored resume is a normal resume to
        # the rest of the app. Deliberately the *full* master skill list, not
        # the emphasised subset: emphasis reorders in build_document, and
        # storing only the subset would silently drop every other skill from the
        # generated document.
        master_profile = stored_profile(master)
        ResumeProfile.objects.update_or_create(
            resume=tailored,
            defaults={
                "skills": master_profile.get("skills") or [],
                "experience": master_profile.get("experience") or {},
                "education": master_profile.get("education") or "",
                "projects": master_profile.get("projects") or "",
                "certifications": master_profile.get("certifications") or "",
            },
        )

        timer.add(resume=tailored.pk, validation=validation.status)

    _link_result_to_run(user, job, tailored)

    ActivityEvent.record(
        user,
        ActivityEvent.TAILORING_SAVED,
        object_type="resume",
        object_id=tailored.id,
        summary=tailored.name,
        metadata={
            "job": job.id,
            "source_resume": master.id,
            "provider": str(provider_name or "")[:50],
            "validation": validation.status,
        },
    )

    return tailored, validation.as_dict()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _job_label(job) -> str:
    """One line naming the job, for an activity summary."""
    return ("%s — %s" % (job.company or "Job", job.title or "Role"))[:200]


def _link_result_to_run(user, job, resume) -> None:
    """
    Point the tailoring run that produced this artifact at the saved row.

    Best effort, and only the most recent unclaimed run is touched: a user can
    generate twice and save the second, and guessing which run an older save
    belonged to would be worse than leaving one run unlinked. Never raises --
    the save has already succeeded, and an audit link is not worth failing it.
    """
    try:
        run = (
            AIRun.objects.filter(
                user=user,
                operation=AIRun.OPERATION_RESUME_TAILORING,
                source_job=job,
                result_resume__isnull=True,
                status=AIRun.SUCCEEDED,
            )
            .order_by("-created_at", "-id")
            .first()
        )
        if run is None:
            return
        run.result_resume = resume
        run.save(update_fields=["result_resume"])
    except Exception:  # pragma: no cover - defensive by design
        logger.warning(
            "tailoring.result_link_failed job=%s resume=%s",
            getattr(job, "pk", None),
            getattr(resume, "pk", None),
        )
