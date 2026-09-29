"""
Job discovery: rank already-collected jobs against a resume.

The existing flow is analyse-one-URL-at-a-time: a user pastes a link, waits
for a model call, sees a score. That answers "how well do I fit this job I
already found" and does not answer "what should I be applying to".

This module answers the second question using the jobs this account has
already collected. It is deliberately not a job-board scraper. Fetching fresh
postings from many providers at search time is a different and much larger
system with rate limits, pagination and a freshness problem; pretending to
solve it here would produce results that silently go stale. What is here ranks
real, stored, already-analysed jobs, and says so.

Why the score is recomputed rather than read from the row
--------------------------------------------------------
``Job.match_score`` is the score of the master resume at the moment that job
was analysed. The user can upload a new master resume, at which point every
stored score is stale, and a search ranked by an old resume would be quietly
wrong. So the search re-scores against the *current* master resume, in memory,
and never writes back. Writing back would turn a read into a bulk mutation of
a user's job list, which a search box should not be able to do.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.db.models import Q, QuerySet

from apps.resumes.models import Resume

from .match_engine import MatchEngine

logger = logging.getLogger(__name__)


#: Hard ceiling on rows pulled from the database for scoring. A user with a
#: long history should get their best matches, not whatever the first few
#: hundred rows happen to be.
MAX_CANDIDATES = 400

#: Ceiling on rows returned to the client.
MAX_RESULTS = 50

#: Jobs below this are not worth showing. A "match" list full of 12% scores
#: reads as a broken feature; the threshold is where a result is actionable.
MIN_USEFUL_SCORE = 25.0


class NoMasterResume(Exception):
    """
    Raised when the user has no master resume to search against.

    A distinct exception rather than an empty result set: "you have no
    resume" and "you have a resume but nothing matches" call for different UI,
    and collapsing them into an empty list produces a blank page that tells
    the user nothing.

    The two class attributes are the whole public contract. A view must
    return :attr:`MESSAGE`, never ``str(exc)``: the text of a live exception
    is an internal detail, and handing it to a response body is how stack and
    internals escape to a browser. Keeping the string here also means the
    wording is reviewed once, next to the condition that produces it.
    """

    #: Discriminator the client switches on. Stable: it is in the API, not in
    #: a sentence a translator may reword.
    CODE = "no_master_resume"

    #: Written to be read by a person, so it says what to do next rather than
    #: what went wrong internally.
    MESSAGE = "Upload a master resume before searching for matching jobs."


@dataclass
class SearchHit:
    """One ranked job.

    A dataclass rather than a model instance: these are computed values, not
    persisted rows, and attaching a transient score to a real ``Job`` risks it
    being saved by accident further up the stack.
    """

    job: object
    score: float
    matched_skills: list = field(default_factory=list)
    missing_skills: list = field(default_factory=list)
    headline: str = ""

    def as_dict(self) -> dict:
        return {
            "job_id": self.job.id,
            "title": self.job.title,
            "company": self.job.company,
            "location": self.job.location,
            "url": self.job.url,
            "source": self.job.source,
            "score": self.score,
            "matched_skills": self.matched_skills,
            "missing_skills": self.missing_skills,
            "headline": self.headline,
            # The stored score is from when this job was analysed, against an
            # older resume. Sending it beside the fresh score would invite the
            # UI to show two different numbers.
            "analysed_at": self.job.created_at,
        }


def _normalise(value: str) -> str:
    return value.strip().lower()


def _prefilter(queryset: QuerySet, terms) -> QuerySet:
    """
    Cheap OR-over-terms narrowing, before any scoring happens.

    The match is a plain ``icontains`` rather than full-text search because the
    vocabulary is skill names and role words, not prose, and because SQLite --
    what tests and local dev run on -- has no equivalent of Postgres
    ``SearchVector`` without a separate dependency.

    An empty term list returns the queryset unfiltered, which is intentional:
    "show me everything, ranked" is a legitimate request.
    """
    usable = [t for t in (_normalise(term) for term in terms) if t]

    if not usable:
        return queryset

    condition = Q()
    for term in usable:
        condition |= Q(title__icontains=term)
        condition |= Q(company__icontains=term)
        condition |= Q(description__icontains=term)

    return queryset.filter(condition)


def get_master_resume(user) -> Resume:
    """
    The user's master resume, or raise.

    ``filter(is_master=True).first()`` rather than ``get()``: the database has
    a conditional unique constraint preventing two masters, but a
    ``MultipleObjectsReturned`` escaping into a view as a 500 would be a poor
    answer to a race the constraint already makes nearly impossible.
    """
    resume = Resume.objects.filter(user=user, is_master=True).first()
    if resume is None:
        raise NoMasterResume(NoMasterResume.MESSAGE)
    return resume


def _build_resume_payload(resume: Resume) -> dict:
    """
    The shape ``MatchEngine.calculate`` expects, read from the profile.

    Uses the stored profile rather than re-parsing the uploaded document:
    re-parsing on every search would mean a model call per search, and the
    profile already holds the extraction.
    """
    profile = getattr(resume, "profile", None)

    if profile is None:
        # A master resume with no profile row has been uploaded but not yet
        # extracted. Empty skills produce a valid "nothing matches" rather than
        # an error, and the empty case is handled explicitly by the caller.
        return {"skills": [], "experience": [], "education": "", "qualities": []}

    return {
        "skills": profile.skills or [],
        "experience": profile.experience or [],
        "education": profile.education or "",
        "qualities": profile.qualities or [],
    }


def _jd_payload(job):
    """
    The job side of ``MatchEngine.calculate``, or ``None`` if unavailable.

    Only a stored ``jd_profile`` counts. This is stricter than it might look:
    ``MatchEngine._skill_match`` returns a perfect 100 when the JD lists no
    skills, so scoring a job we have not actually parsed would rank it at the
    *top* on the strength of an absence. There is no fallback to the raw
    title and description for exactly that reason -- guessing at a JD would
    produce confident-looking scores for jobs nobody has read.

    Returning ``None`` lets the caller skip the job, which is the honest
    outcome: an unparsed job has no place in a "jobs that match you" list.
    """
    stored = getattr(job, "match_result", None)
    if not isinstance(stored, dict):
        return None

    jd = stored.get("jd_profile")
    return jd if isinstance(jd, dict) and jd.get("skills") else None



def _headline(matched: list, missing: list) -> str:
    """
    One short sentence explaining the score.

    This is the part that makes a ranked list useful rather than a number to
    stare at. It names the strongest overlap and, when there is one, the single
    biggest gap -- a list that only ever said "you match 6 skills" leaves the
    user with nothing to act on.
    """
    if not matched:
        return "No skills from your resume appear in this posting yet."

    parts = ["Strong overlap on %s" % ", ".join(matched[:3])]
    if missing:
        parts.append("missing %s" % missing[0])
    return "; ".join(parts) + "."


def search_jobs(user, terms=None, limit: int = MAX_RESULTS) -> dict:
    """
    Rank this account's jobs against the current master resume.

    Returns a dict rather than a list because the caller needs more than
    results: the resume's skill count, whether anything was filtered out, and
    the number actually examined all change what the UI should say. A bare
    list would force that context to be re-derived, incorrectly, on the client.

    Raises :class:`NoMasterResume` when there is nothing to search against.
    """
    resume = get_master_resume(user)
    resume_payload = _build_resume_payload(resume)
    resume_skills = [s for s in resume_payload.get("skills", []) if s]

    base = (
        job_model_objects()
        .filter(user=user)
        # An allowlist rather than an exclude list: see _SEARCHABLE_STATUSES.
        .filter(status__in=_SEARCHABLE_STATUSES)
    )

    total_before = base.count()
    narrowed = _prefilter(base, terms or [])
    matched_by_filter = narrowed.count()

    # The cap is applied in the query. Slicing after fetching would pull every
    # matching row into memory first and only then throw most of them away.
    candidates = list(narrowed.order_by("-created_at")[:MAX_CANDIDATES])

    limit = max(1, min(int(limit or MAX_RESULTS), MAX_RESULTS))

    if not resume_skills:
        # A master resume with no extracted skills cannot be matched against
        # anything. Scoring would return a uniform zero for every job, which
        # looks like a broken search rather than an incomplete resume, so this
        # is reported explicitly.
        return {
            "results": [],
            "resume": {"id": resume.id, "name": resume.name, "skills": 0},
            "examined": 0,
            "total_jobs": total_before,
            "matched_filter": matched_by_filter,
            "reason": "no_skills",
        }

    hits = []
    for job in candidates:
        jd = _jd_payload(job)
        if jd is None:
            # Not scorable: no extracted JD. Counting it as a miss would show a
            # low score for a job we simply never read.
            continue

        try:
            result = MatchEngine.calculate(resume_payload, jd)
        except Exception:
            # One malformed job must not fail the whole search. The user asked
            # "what should I apply to", and losing all results to one bad row
            # is a worse answer than skipping that row.
            logger.exception(
                "job_search.score_failed job=%s user=%s",
                job.pk,
                getattr(user, "pk", None),
            )
            continue

        score = float(result.get("score", 0) or 0)
        if score < MIN_USEFUL_SCORE:
            continue

        skill_block = result.get("skills", {}) or {}
        matched = [s for s in (skill_block.get("matched") or []) if s]
        missing = [s for s in (skill_block.get("missing") or []) if s]

        # Require real skill overlap, not merely a passing overall score.
        #
        # MatchEngine weights skills at 50% and the other three factors at 50%
        # combined, so a job sharing none of the candidate's skills can still
        # reach the 50s on requirements and education alone. That is a
        # defensible general-purpose match score, but it is the wrong answer
        # for a list headed "jobs that match your skills": showing a job with
        # an empty "matched skills" chip under that heading is misleading, and
        # the user cannot tell the number came from the other factors.
        if not matched:
            continue

        hits.append(
            SearchHit(
                job=job,
                score=score,
                matched_skills=matched,
                missing_skills=missing,
                headline=_headline(matched, missing),
            )
        )

    hits.sort(key=lambda hit: hit.score, reverse=True)

    return {
        "results": [hit.as_dict() for hit in hits[:limit]],
        "resume": {
            "id": resume.id,
            "name": resume.name,
            "skills": len(resume_skills),
        },
        "examined": len(candidates),
        "total_jobs": total_before,
        "matched_filter": matched_by_filter,
        # True when the cap actually bit. Without this the UI cannot tell the
        # difference between "these are your ten best matches" and "these are
        # every job you have", which is the difference between a complete
        # answer and a misleading one.
        "truncated": matched_by_filter > MAX_CANDIDATES,
        "reason": "",
    }


def job_model_objects() -> QuerySet:
    """
    The base queryset of searchable jobs.

    A function rather than a module-level ``Job.objects`` binding: ``Job`` is
    imported lazily here to keep this module importable from ``apps.jobs``
    code that itself imports services, without a circular import at module
    load time.
    """
    from apps.jobs.models import Job

    return Job.objects.all()


#: Job states that cannot be meaningfully scored. A job still queued, running
#: or failed has no extracted JD profile, so scoring it would compare a resume
#: against an empty posting and report a confident zero.
#:
#: Derived from the model rather than written out by hand. A hand-written list
#: silently rots the moment someone adds a status, and the failure is invisible:
#: the new status is simply included in results, scoring as a low match. The
#: positive states are named explicitly and everything else is excluded, so a
#: newly added status is excluded by default until someone decides it should
#: be searchable.
_SEARCHABLE_STATUSES = ("COMPLETED", "READY")


