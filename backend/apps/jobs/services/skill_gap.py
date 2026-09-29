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

from apps.resumes.services import skill_catalog


def _clean(values) -> list:
    """Sorted, de-duplicated, display-ready list."""
    return sorted({str(v).strip() for v in (values or []) if str(v).strip()})


def _skills_in(lines) -> list:
    """
    Reduce raw JD requirement *lines* to the catalog skills they mention.

    This is the fix for a bug that made the "Partial match" panel unreadable.
    It used to show the requirement sentences verbatim, so a job whose JD said
    "Ability to manage and communicate with many people at once" produced a
    partial match *called* "Ability To Manage And Communicate With Many People
    At Once". That is not a skill, it is a sentence, and the panel was titled
    "Skill analysis" -- so it looked like the tool was telling the candidate it
    did not have the ability to talk to people.

    Reducing to catalog skills makes every row a real, nameable technology, and
    makes the three columns homogeneous: all three are drawn from one vocabulary.
    """
    vocabulary = skill_catalog.get_skills()

    found: set[str] = set()
    for line in lines or []:
        for skill in skill_catalog.extract_skills(str(line), vocabulary):
            found.add(skill.lower())

    return sorted(found)


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
    #       The engine records partial credit against the sentence, not the
    #       skill, so the line is reduced to its skills here. Showing the raw
    #       sentence is what put non-skills in this panel.
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

    matched = set(_clean(skills.get("matched")))
    missing = set(_clean(skills.get("missing")))

    partial = set(_skills_in(requirements.get("partially_matched")))

    # Disjointness, and it is a *reassignment*, not a plain subtraction.
    #
    # A skill can be named by a half-matched requirement and also be reported
    # as missing by the skill pass. "Strong Python and Kubernetes experience"
    # against a Python-only resume is exactly that: Python matches, Kubernetes
    # does not, so the sentence earns partial credit AND Kubernetes appears in
    # `missing`.
    #
    # Two earlier versions of this were both wrong:
    #
    #   - subtracting only `matched` left the skill in `partial` and `missing`
    #     at once, which reads as the tool contradicting itself in one row;
    #   - giving `missing` priority by *removing* the overlap deleted the
    #     partial entirely, so a genuine half-matched signal vanished.
    #
    # The resolution is that a partial naming a missing skill is *redundant*
    # rather than wrong: `missing` is the headline fact and already shows it,
    # so the skill is not repeated under `partial`. Nothing is lost -- the
    # panel still reports it, once -- and only `matched` is removed outright,
    # because a skill the resume demonstrably has is never a gap.
    partial -= matched
    partial -= missing

    matched, partial, missing = sorted(matched), sorted(partial), sorted(missing)

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
