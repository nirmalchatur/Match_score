"""
Qualities: what the candidate says about themselves, grouped by kind.

Why this is separate from ``ResumeProfile.skills``
-------------------------------------------------
``skills`` is *parsed*: whatever the extractor found in the uploaded document.
These are *chosen*: deliberate claims the user makes about themselves, and
which therefore need different rules. A parsed skill cannot be wrong (it is
evidence, taken from the document), whereas a chosen quality is an assertion
and must be checked -- that is where the catalogue below earns its keep.

The catalogue
-------------
:data:`CATALOGUE` is the fixed set of options the UI offers, grouped by kind.
Restricting choices to a known list is what lets the matching stage and the
tailoring prompt speak about a quality confidently: a free-text box would
produce "great with people" and "cross-functional collaboration" as two
different entries for the same idea, and neither would match a job
description that says "strong stakeholder communication".

It is intentionally a reasonable, recognisable set rather than an exhaustive
one. :func:`normalize` is the single gate that enforces membership, so
extending the catalogue later is a one-line change with no other edits.

Validation
----------
:data:`MINIMUM_TOTAL` is enforced server-side. A client that sends fewer is
rejected; the UI merely reports the requirement. Client-side validation is a
courtesy, never the control -- a PATCH sent by hand must fail the same way.
"""

from __future__ import annotations

from typing import Any


#: The three kinds, in the order the UI should present them. Also the order
#: they appear in the prompt, most concrete first.
KINDS = ("technical", "project_management", "soft_skills")

#: Human labels for the UI and for error messages.
KIND_LABELS = {
    "technical": "Technical skills",
    "project_management": "Project management",
    "soft_skills": "Soft skills",
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
    "technical": [
        "Python",
        "JavaScript",
        "TypeScript",
        "Java",
        "C#",
        "C++",
        "Go",
        "Rust",
        "Ruby",
        "PHP",
        "SQL",
        "HTML/CSS",
        "React",
        "Angular",
        "Vue",
        "Next.js",
        "Node.js",
        "Django",
        "Flask",
        "FastAPI",
        "Spring Boot",
        "Express",
        "REST API design",
        "GraphQL",
        "PostgreSQL",
        "MySQL",
        "MongoDB",
        "Redis",
        "SQLite",
        "AWS",
        "Azure",
        "Google Cloud",
        "Docker",
        "Kubernetes",
        "Terraform",
        "CI/CD",
        "Git",
        "Linux",
        "Jenkins",
        "GitHub Actions",
        "Machine learning",
        "Data engineering",
        "Pandas",
        "Spark",
        "ETL pipelines",
        "Data modelling",
        "Tableau",
        "Power BI",
        "Figma",
        "UI design",
        "UX research",
        "Accessibility",
        "Automated testing",
        "Security",
    ],
    "project_management": [
        "Agile delivery",
        "Scrum",
        "Kanban",
        "Sprint planning",
        "Sprint retrospectives",
        "Stakeholder management",
        "Roadmap planning",
        "Prioritisation",
        "Requirements gathering",
        "Sprint estimation",
        "Release management",
        "Risk management",
        "Budget management",
        "Resource planning",
        "Cross-functional collaboration",
        "Team leadership",
        "Mentoring",
        "Performance reviews",
        "Conflict resolution",
        "Vendor management",
        "Change management",
    ],
    "soft_skills": [
        "Communication",
        "Written communication",
        "Presentation skills",
        "Active listening",
        "Problem solving",
        "Critical thinking",
        "Analytical thinking",
        "Attention to detail",
        "Time management",
        "Adaptability",
        "Self-management",
        "Ownership",
        "Curiosity",
        "Collaboration",
        "Empathy",
        "Confidence",
        "Resilience",
        "Reliability",
        "Organisation",
        "Clarity",
        "Diplomacy",
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


def validate_selection(raw: Any) -> dict[str, list[str]]:
    """
    Normalize, then enforce :data:`MINIMUM_TOTAL` and one-per-kind.

    This is the server-side control. Every path that accepts a selection --
    the API and anything internal -- goes through here, so a hand-written
    request cannot bypass the minimum the way a disabled button would let a
    crafted one through.

    Raises :class:`QualityError` with a message written for a person.
    """
    normalized = normalize(raw)
    total = count(normalized)

    empty_kinds = missing_kind_errors(normalized)
    if empty_kinds:
        # Checked before the total: "add a soft skill" is far more useful than
        # "you have selected 7" when the real problem is one empty category.
        raise QualityError(" ".join(empty_kinds))

    if total < MINIMUM_TOTAL:
        raise QualityError(
            f"Select at least {MINIMUM_TOTAL} qualities. "
            f"You have selected {total}."
        )

    return normalized
