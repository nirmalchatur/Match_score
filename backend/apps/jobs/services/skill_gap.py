"""
Skill gap analysis for the job workspace.

This is a **projection**, not a second matching system.

Every value here is read out of the ``match_result`` that
:class:`~apps.jobs.services.match_engine.MatchEngine` already computed when the
job was analysed: the same centralized skill catalog, the same
:class:`~apps.resumes.services.skill_normalizer.SkillNormalizer`, the same
deterministic set arithmetic. Nothing is re-extracted and nothing is sent to a
model, so the gap shown in the UI can never disagree with the match score.

The one thing this module adds is wording. A missing skill is something the
resume does not *mention*; it is not evidence that the candidate cannot do it,
and the copy says so.
"""

from __future__ import annotations


def _clean(values) -> list:
    """Sorted, de-duplicated, display-ready list."""
    return sorted({str(v).strip() for v in (values or []) if str(v).strip()})


def analyze_skill_gap(job) -> dict:
    """
    Build the skill-gap view for one job.

    Returns ``has_analysis=False`` when the job has not been analysed yet, so
    the UI can show an empty state rather than an empty gap that reads as
    "you match nothing".
    """
    match_result = job.match_result or {}

    # The two MatchEngine sub-results carry different things, and conflating
    # them is the easy mistake here:
    #
    #   skills.matched / skills.missing
    #       Normalized catalog vocabulary ("python", "kubernetes"). These are
    #       the actual skills, so they are what the skill view shows.
    #
    #   requirements.partially_matched
    #       Raw requirement *lines* from the JD ("- 3+ years with Docker").
    #       Requirements are not skills, but they are the only place the engine
    #       records a partial credit, so they supply the "partial" list.
    requirements = match_result.get("requirements") or {}
    skills = match_result.get("skills") or {}

    has_analysis = bool(match_result) and bool(
        requirements or skills or match_result.get("score") is not None
    )

    if not has_analysis:
        return {
            "has_analysis": False,
            "matched": [],
            "partial": [],
            "missing": [],
            "summary": "No job analysis available.",
        }

    matched = _clean(skills.get("matched"))
    partial = _clean(requirements.get("partially_matched"))
    missing = _clean(skills.get("missing"))

    return {
        "has_analysis": True,
        "matched": matched,
        "partial": partial,
        "missing": missing,
        "summary": _summarise(matched, partial, missing),
    }


def _summarise(matched: list, partial: list, missing: list) -> str:
    """
    One sentence explaining the gap.

    The wording matters: these are requirements *not found in the current
    resume*. Saying "you don't know Kubernetes" would be both wrong and
    discouraging -- the resume simply does not evidence it.
    """
    if not matched and not partial and not missing:
        return "No skill requirements were extracted from this job description."

    total = len(matched) + len(partial) + len(missing)

    if total:
        headline = "%d of the %d skills this job lists %s" % (
            len(matched),
            total,
            "was found in your current resume" if len(matched) == 1
            else "were found in your current resume",
        )
    else:
        headline = "No skills were extracted from this job description."

    caveat = (
        " A skill marked “not found” is simply absent from your resume as "
        "uploaded — it is not a judgement about what you can do."
    )

    if partial:
        return headline + ", and %d more only partially matched." % len(partial) + caveat
    return headline + "." + caveat
