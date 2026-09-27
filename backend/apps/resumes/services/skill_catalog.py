"""
Single source of truth for TailorUp's skill vocabulary.

Why this file exists
--------------------
The skill list used to be duplicated inline in ``ResumeProfile`` and
``JDProfile``, which had already drifted apart (the JD list had grown extra
entries such as Kubernetes and TypeScript that the resume list never picked
up). Every consumer now reads from here, so the vocabulary can be changed in
exactly one place.

Configuration
-------------
The built-in catalog below is the default. To override it without touching
code, point an environment variable at a JSON file with the same shape::

    TAILORUP_SKILL_CATALOG=/path/to/skills.json

    {
      "skills": ["Python", "Django", "..."],
      "aliases": {"reactjs": "react"}
    }

The file is read once and cached; tests can call :func:`reset_cache`.
"""

from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Iterable

logger = logging.getLogger(__name__)

#: Environment variable pointing at a JSON override for the catalog.
CATALOG_ENV_VAR = "TAILORUP_SKILL_CATALOG"

#: The canonical vocabulary, grouped by category purely for readability.
#:
#: Matching is case-insensitive substring matching, so entries are written in
#: their most common spelling. "REST API" is listed rather than "REST" so that
#: the phrase is matched, and aliases below map variants onto it.
DEFAULT_SKILL_CATALOG: tuple[str, ...] = (
    # Languages
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "C++",
    "HTML",
    "CSS",
    "SQL",
    # Backend / frameworks
    "Django",
    "FastAPI",
    "Flask",
    "Spring Boot",
    "Node.js",
    "REST API",
    # Frontend
    "React",
    # Databases
    "PostgreSQL",
    "MySQL",
    "SQLite",
    "MongoDB",
    "Redis",
    "Kafka",
    # Cloud / infrastructure
    "AWS",
    "Azure",
    "GCP",
    "Docker",
    "Kubernetes",
    "Terraform",
    "Jenkins",
    "CI/CD",
    # Tooling
    "Git",
    "GitHub",
    "Linux",
    # Data / ML
    "Machine Learning",
    "Artificial Intelligence",
    "Pandas",
    "NumPy",
    "TensorFlow",
    "PyTorch",
)

#: Spellings that should collapse onto a canonical entry.
DEFAULT_SKILL_ALIASES: dict[str, str] = {
    "react.js": "react",
    "reactjs": "react",
    "react js": "react",
    "node.js": "node",
    "nodejs": "node",
    "node js": "node",
    "amazon web services": "aws",
    "python 3": "python",
    "python 3.10": "python",
    "python 3.11": "python",
    "python 3.12": "python",
    "postgres": "postgresql",
    "rest": "rest api",
    "restful api": "rest api",
    "restful apis": "rest api",
    "c/c++": "c++",
    "scikit-learn": "sklearn",
    "scikit learn": "sklearn",
}


def _load_from_file(path: str) -> tuple[tuple[str, ...], dict[str, str]]:
    """Read a JSON override, tolerating a missing or malformed file."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError) as exc:
        logger.warning(
            "skills.catalog_override_unreadable path=%s error=%s; using defaults",
            path,
            exc,
        )
        return DEFAULT_SKILL_CATALOG, DEFAULT_SKILL_ALIASES

    if not isinstance(data, dict):
        logger.warning(
            "skills.catalog_override_invalid path=%s; using defaults", path
        )
        return DEFAULT_SKILL_CATALOG, DEFAULT_SKILL_ALIASES

    skills = data.get("skills")
    aliases = data.get("aliases")

    resolved_skills = (
        tuple(str(item) for item in skills if str(item).strip())
        if isinstance(skills, list) and skills
        else DEFAULT_SKILL_CATALOG
    )
    resolved_aliases = (
        {str(k).lower(): str(v) for k, v in aliases.items()}
        if isinstance(aliases, dict)
        else dict(DEFAULT_SKILL_ALIASES)
    )

    return resolved_skills, resolved_aliases



@lru_cache(maxsize=1)
def get_catalog() -> tuple[tuple[str, ...], dict[str, str]]:
    """Return ``(skills, aliases)``, honouring the environment override."""
    path = (os.environ.get(CATALOG_ENV_VAR) or "").strip()
    if path:
        return _load_from_file(path)
    return DEFAULT_SKILL_CATALOG, dict(DEFAULT_SKILL_ALIASES)


def get_skills() -> tuple[str, ...]:
    """The canonical skill vocabulary."""
    return get_catalog()[0]


def get_aliases() -> dict[str, str]:
    """Variant spellings mapped onto canonical entries."""
    return get_catalog()[1]


def extract_skills(text: str, skills: Iterable[str] | None = None) -> list[str]:
    """
    Return every catalog skill mentioned in ``text``.

    Matching is case-insensitive substring matching, mirroring the historical
    behaviour of the profilers. Pass ``skills`` to restrict the vocabulary;
    by default the full catalog is used.
    """
    if not text:
        return []

    haystack = str(text).lower()
    vocabulary = tuple(skills) if skills is not None else get_skills()

    # Longest first, so "REST API" wins over a hypothetical shorter prefix.
    ordered = sorted(vocabulary, key=len, reverse=True)

    return [skill for skill in ordered if skill.lower() in haystack]


def reset_cache() -> None:
    """Clear the cached catalog. Intended for tests."""
    get_catalog.cache_clear()
