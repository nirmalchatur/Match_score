"""
Dashboard statistics, computed from this account's own rows.

Every number here is a real aggregate over the signed-in user's data. There are
no placeholders and no defaults that look like data: an account with nothing
tracked gets zeros, which is the truthful answer.

Aggregated in a fixed number of queries rather than per-widget, and every
queryset is user-scoped, so the dashboard cannot leak another account's totals
and does not issue one query per tile.
"""

from __future__ import annotations

from django.db.models import Avg, Count, Q

from apps.jobs.models import Job
from apps.resumes.models import Resume

from .models import Application

#: Recent applications shown on the dashboard. A small, fixed number: this is a
#: summary, not a second tracker page.
RECENT_LIMIT = 5


def dashboard_stats(user) -> dict:
    """Build the dashboard payload for one account."""
    applications = Application.objects.filter(user=user)

    # One grouped query gives every status count.
    status_rows = (
        applications.values("status")
        .annotate(count=Count("id"))
        .order_by()
    )
    counts = {row["status"]: row["count"] for row in status_rows}

    for value, _label in Application.STATUS_CHOICES:
        counts.setdefault(value, 0)

    jobs = Job.objects.filter(user=user)

    # Averages ignore jobs that have not been scored yet, which is what we
    # want: an unscored job should not drag the average toward zero.
    match_average = jobs.filter(match_score__isnull=False).aggregate(
        value=Avg("match_score")
    )["value"]

    resumes = Resume.objects.filter(user=user)

    return {
        "jobs": {
            "total": jobs.count(),
            "scored": jobs.filter(match_score__isnull=False).count(),
        },
        "applications": {
            "total": applications.count(),
            "by_status": counts,
            # "Active" is the waiting-on-them number a candidate actually
            # cares about, rather than a fourth status nobody tracks.
            "active": applications.filter(
                status__in=list(Application.ACTIVE_STATUSES)
            ).count(),
            "interviews": counts.get("INTERVIEW", 0),
            "offers": counts.get("OFFER", 0),
        },
        "resumes": {
            "total": resumes.count(),
            "tailored": resumes.filter(resume_type="TAILORED").count(),
            "has_master": resumes.filter(is_master=True).exists(),
        },
        "match": {
            "average": round(match_average, 1) if match_average is not None else None,
        },
        "recent_applications": recent_applications(user),
    }


def recent_applications(user) -> list:
    """
    The newest few applications, labelled for direct display.

    ``select_related`` on both foreign keys: every row renders a job label and
    a resume link, so without it this would be two extra queries per row.
    """
    rows = (
        Application.objects.filter(user=user)
        .select_related("job", "tailored_resume")
        .order_by("-updated_at")[:RECENT_LIMIT]
    )

    return [
        {
            "id": row.id,
            "status": row.status,
            "notes": row.notes,
            "updated_at": row.updated_at,
            "job": {
                "id": row.job_id,
                "title": row.job.title,
                "company": row.job.company,
                "location": row.job.location,
                "match_score": row.job.match_score,
            },
            "tailored_resume_id": row.tailored_resume_id,
        }
        for row in rows
    ]
