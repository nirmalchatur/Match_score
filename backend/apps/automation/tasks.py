"""
Where notifications come from.

Every emitter goes through :func:`emit`, which applies the user's preferences
and the de-duplication key in one place. Call sites pass intent ("this job
finished analysing, here is the id") rather than constructing rows, because the
two rules that keep the list readable -- honour the preference, and never
repeat a pollable event -- are easy to forget and tedious to repeat.

Each emitter is idempotent through ``dedupe_key``, so calling it twice is
harmless. That matters because two of these are called from more than one
place: a job is analysed both from the analyze endpoint and from the task
queue, and a user should see one notification, not two.
"""

from __future__ import annotations

import logging

from .models import Notification, NotificationPreference

logger = logging.getLogger(__name__)


def emit(
    user,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    dedupe_key: str = "",
) -> None:
    """
    Create a notification for ``user`` if their preferences allow it.

    Never raises. A notification is a convenience layered on top of a real
    action the user already performed, so failing to record one must not turn a
    successful analysis into an error response.
    """
    if user is None or not getattr(user, "is_authenticated", False):
        return

    try:
        preferences = NotificationPreference.for_user(user)
        if not preferences.allows(kind):
            logger.debug("notification.suppressed user=%s kind=%s", user.pk, kind)
            return

        created = Notification.notify(
            user=user,
            kind=kind,
            title=title,
            body=body,
            link=link,
            dedupe_key=dedupe_key,
        )

        if created is None and dedupe_key:
            logger.debug("notification.deduped user=%s key=%s", user.pk, dedupe_key)
    except Exception:
        # Broad on purpose: this runs inside other endpoints' happy path, and a
        # notification failure must not mask the real result.
        logger.exception(
            "notification.emit_failed user=%s kind=%s",
            getattr(user, "pk", None),
            kind,
        )


def job_analysed(user, job) -> None:
    """A job finished analysing and has a score."""
    score = getattr(job, "match_score", None)
    detail = (
        f"Match score {round(score)}."
        if score is not None
        else "Analysis finished."
    )
    emit(
        user=user,
        kind=Notification.KIND_SUCCESS,
        title=f"{getattr(job, 'company', 'A job')} — {getattr(job, 'title', 'New role')}",
        body=detail,
        link=f"/app/jobs?job={job.pk}",
        # Keyed by status *and* id: a re-analysis of the same job is a genuinely
        # new event and should be told about, but one analysis observed twice
        # by a poller is not.
        dedupe_key=f"job-analysed:{job.pk}:{getattr(job, 'status', '')}",
    )


def job_analysis_failed(user, job, reason: str = "") -> None:
    """A job could not be analysed."""
    emit(
        user=user,
        kind=Notification.KIND_ERROR,
        title=f"Could not analyse {getattr(job, 'title', 'a job')}",
        body=reason or "The posting could not be read. Open it to see why.",
        link=f"/app/jobs?job={job.pk}",
        dedupe_key=f"job-failed:{job.pk}:{getattr(job, 'error_message', '')[:60]}",
    )


def tailoring_saved(user, job, resume_name: str = "") -> None:
    """A tailoring was saved as a new resume version."""
    emit(
        user=user,
        kind=Notification.KIND_SUCCESS,
        title=f"Saved {resume_name or 'a tailored resume'}",
        body=f"Built for {getattr(job, 'title', 'a role')} at "
             f"{getattr(job, 'company', 'a company')}.",
        link="/app/resumes",
        dedupe_key=f"tailored:{getattr(job, 'pk', 0)}:{resume_name[:40]}",
    )


def application_status_changed(user, application, previous: str, current: str) -> None:
    """An application moved stage.

    Not de-duplicated: each transition is its own event, and a user moving a
    role OFFERED then WITHDRAWN must see both.
    """
    emit(
        user=user,
        kind=Notification.KIND_INFO,
        title=f"{getattr(application.job, 'company', 'Application')} — {current.title()}",
        body=f"Moved from {previous.title()} to {current.title()}.",
        link="/app/applications",
    )

