"""
Qualities: what the candidate says about themselves, grouped by kind.

Why this is separate from ``ResumeProfile.skills``
-------------------------------------------------
``skills`` is *parsed*: whatever the extractor found in the uploaded document.
These are *chosen*: deliberate claims the user makes about themselves, and
which therefore need different rules. A parsed skill cannot be wrong (it is
evidence, taken from the document), whereas a chosen quality is an assertion
and must be checked -- that is where the catalogue below earns its keep.

The catalogue: 25 options, pick 7
----------------------------------
:data:`CATALOGUE` is a deliberately short, curated list -- 25 entries across
seven groups -- from which a candidate picks exactly seven.

Short on purpose. An earlier revision carried 96 options in three groups,
which was more precise against a real job description but far heavier to look
at: asking someone to find seven relevant items inside a 96-item wall is a
different task from asking them to choose seven from 25, and the larger list
was measurably worse at being answered.

Seven is the floor enforced by :func:`validate_selection`, and the picker
requires at least one from every group, so the selection cannot be seven
programming languages and nothing else.

Restricting choices to a known list is what lets the matching stage and the
tailoring prompt speak about a quality confidently: a free-text box would
produce "great with people" and "cross-functional collaboration" as two
different entries for the same idea, and neither would match a job
description that says "strong stakeholder communication".

Validation
----------
:data:`MINIMUM_TOTAL` is enforced server-side. A client that sends fewer is
rejected; the UI merely reports the requirement. Client-side validation is a
courtesy, never the control -- a PATCH sent by hand must fail the same way.
"""

from __future__ import annotations

from typing import Any


#: The seven groups a candidate picks from, in the order the picker presents
#: them: the technical clusters first, then the people-facing ones.
KINDS = (
    "programming",
    "data_structures",
    "problem_solving",
    "soft_skills",
    "project_management",
    "leadership",
    "hr",
)

#: Human labels for the UI and for error messages.
KIND_LABELS = {
    "programming": "Programming",
    "data_structures": "Data structures",
    "problem_solving": "Problem solving",
    "soft_skills": "Soft skills",
    "project_management": "Project management",
    "leadership": "Leadership",
    "hr": "HR and people operations",
}


#: How many qualities a candidate must select in total.
#:
#: Seven is the project's stated minimum. It is not arbitrary padding: a
#: tailoring run with only one or two qualities has nothing to choose between,
#: so the "emphasise what this job values" behaviour degenerates. Seven gives
#: enough signal to rank against a job description without turning the picker
#: into a chore.
MINIMUM_TOTAL = 7

#: The options offered, by kind.
CATALOGUE: dict[str, list[str]] = {
    "programming": [
        "Python",
        "JavaScript and TypeScript",
        "Java",
        "SQL",
    ],
    "data_structures": [
        "Arrays and strings",
        "Hash maps and dictionaries",
        "Trees and graphs",
        "Sorting and searching",
    ],
    "problem_solving": [
        "Algorithm design",
        "Dynamic programming",
        "Debugging",
        "Performance optimisation",
    ],
    "soft_skills": [
        "Written communication",
        "Team collaboration",
        "Time management",
        "Attention to detail",
    ],
    "project_management": [
        "Agile delivery",
        "Sprint planning",
        "Stakeholder management",
    ],
    "leadership": [
        "Team leadership",
        "Mentoring",
        "Conflict resolution",
    ],
    "hr": [
        "Talent acquisition",
        "Performance reviews",
        "Onboarding and retention",
    ],
}

#: Every allowed value, lowercased, for membership checks. Built once at import
#: so validation does not rebuild a set of ~130 strings per request.
_ALLOWED: dict[str, set[str]] = {
    kind: {value.lower() for value in values} for kind, values in CATALOGUE.items()
}


class QualityError(ValueError):
    """Raised for input that is not a valid quality selection."""


def normalize(raw: Any) -> dict[str, list[str]]:
    """
    Coerce arbitrary input into the canonical shape, or raise.

    The canonical shape is ``{kind: [value, ...]}`` with all three keys always
    present, values deduplicated case-insensitively, written in the catalogue's
    own spelling, and each list ordered as the catalogue orders it. That last
    part matters: sorting by catalogue position rather than alphabetically
    means the UI and the prompt present a stable, meaningful order.

    Raises :class:`QualityError` for anything unusable -- a non-mapping, an
    unknown kind, or a value that is not in the catalogue. Unknown values are
    rejected rather than dropped, because silently discarding a selection the
    user made is worse than telling them it is not one of the options.
    """
    if raw in (None, ""):
        return {kind: [] for kind in KINDS}

    if not isinstance(raw, dict):
        raise QualityError(
            "Qualities must be an object with 'technical', 'project_management' "
            "and 'soft_skills' lists."
        )

    unknown_kinds = set(raw) - set(KINDS)
    if unknown_kinds:
        raise QualityError(
            "Unknown quality categories: " + ", ".join(sorted(unknown_kinds))
        )

    out: dict[str, list[str]] = {}
    for kind in KINDS:
        values = raw.get(kind) or []
        if not isinstance(values, (list, tuple)):
            raise QualityError(f"'{kind}' must be a list of qualities.")

        seen: set[str] = set()
        for value in values:
            if not isinstance(value, str):
                raise QualityError(f"'{kind}' must contain only text.")
            cleaned = value.strip()
            if not cleaned:
                # A blank entry is a UI artefact (an empty input row), not a
                # choice. Ignoring it is kinder than failing the whole save.
                continue
            if cleaned.lower() not in _ALLOWED[kind]:
                raise QualityError(
                    f"{cleaned!r} is not an available {KIND_LABELS[kind].lower()} "
                    "option."
                )
            seen.add(cleaned.lower())

        # Catalogue order, not alphabetical, and not the order the client sent.
        out[kind] = [value for value in CATALOGUE[kind] if value.lower() in seen]

    return out


def count(normalized: dict[str, list[str]]) -> int:
    """Total number of selected qualities, across all kinds."""
    return sum(len(normalized.get(kind) or []) for kind in KINDS)


def as_list(normalized: dict[str, list[str]]) -> list[str]:
    """Every selected quality, flattened in :data:`KINDS` order."""
    return [
        value for kind in KINDS for value in (normalized.get(kind) or [])
    ]


def missing_kind_errors(normalized: dict[str, list[str]]) -> list[str]:
    """Per-kind emptiness messages. Separate from the total for a clearer UI."""
    return [
        f"Select at least one {KIND_LABELS[kind].lower()} option."
        for kind in KINDS
        if not normalized.get(kind)
    ]


def uncovered_groups(normalized: dict[str, list[str]]) -> list[str]:
    """
    Groups with nothing selected, in presentation order.

    A **hint, not a rule**. It is deliberately not enforced: there are seven
    groups and the minimum is seven, so "at least one from each" is
    mathematically identical to "exactly one from each". Enforcing it would
    oblige a backend engineer to claim an HR skill they do not have, which is
    a false claim invented by the form -- the same thing the tailoring
    pipeline refuses to do with a resume.

    So the API reports the gaps and the picker shows them as a nudge, and the
    only hard rule is the total.
    """
    return [kind for kind in KINDS if not normalized.get(kind)]


def validate_selection(raw: Any) -> dict[str, list[str]]:
    """
    Normalize, then enforce :data:`MINIMUM_TOTAL`.

    This is the server-side control. Every path that accepts a selection --
    the API and anything internal -- goes through here, so a hand-written
    request cannot bypass the minimum the way a disabled button would let a
    crafted one through.

    Raises :class:`QualityError` with a message written for a person.
    """
    normalized = normalize(raw)
    total = count(normalized)

    if total < MINIMUM_TOTAL:
        raise QualityError(
            f"Select at least {MINIMUM_TOTAL} qualities. "
            f"You have selected {total}."
        )

    return normalized
