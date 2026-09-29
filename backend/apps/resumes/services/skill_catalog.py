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
import re
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
    "Go",
    "Rust",
    "PHP",
    "Ruby",
    "Kotlin",
    "Swift",
    "C",
    "C++",
    "C#",
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
    # The plural is a separate entry, not just an alias, because
    # extract_skills() scans the *vocabulary* and only folds through the alias
    # table afterwards -- it is the scan that has to notice the word at all.
    # "REST APIs" is how the term is written far more often than "REST API" in
    # a requirements list.
    #
    # This gap was invisible while matching was plain substring, because "REST"
    # was found inside "REST APIs" by accident. Making matching word-boundary
    # correct therefore *broke* the plural, which is the uncomfortable part of
    # the change worth recording: a stricter matcher exposed a catalog entry
    # that had been passing for the wrong reason.
    "REST APIs",
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
    # Plurals, and the bare noun. "REST APIs" is written far more often than
    # "REST API" in a requirements list, and word-boundary matching is what
    # exposed the gap: the old substring search matched "REST" inside
    # "REST APIs" by accident, so a catalog with no plural silently lost the
    # skill. An entry that cannot match a common spelling is a bug that *reads*
    # as a missing skill, which is the worst way for it to show up.
    "rest apis": "rest api",
    "apis": "rest api",
    "api": "rest api",
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


#: Substrings that are never a standalone mention of the skill.
#:
#: Without this, "Git" is found inside "GitHub", "C" inside "C++", and "Java"
#: inside "JavaScript" -- so a resume listing only "GitHub" reported a "Git"
#: skill it never claimed, and a "JavaScript" resume scored as knowing "Java".
#: Both are wrong in the direction that flatters the candidate, which is the
#: worst direction for a matching tool to be wrong in.
_SUBSTRING_TRAPS: dict[str, tuple[str, ...]] = {
    "git": ("github", "gitlab", "bitbucket"),
    "java": ("javascript", "typescript"),
    "c": ("c++", "c#", "css", "ci/cd"),
    # "Go" is a two-letter English word, so it collides constantly. Without
    # these it matches "going", "Google", "Django", "algorithm" and "good" --
    # which put a phantom language skill on almost every resume.
    "go": ("google", "django", "mongo", "algorithm", "algo", "good", "going",
           "goes", "gone", "category", "categor", "ago", "logo"),
    "r": ("rust",),
    "sql": ("mysql", "postgresql", "sqlite", "nosql", "plsql", "tsql"),
}


def extract_skills(text: str, skills: Iterable[str] | None = None) -> list[str]:
    """
    Return every catalog skill mentioned in ``text``.

    Matching is **word-boundary aware**, not plain substring. That is the single
    change that makes the difference between a useful skill list and a
    confidently wrong one: plain ``"git" in text`` reports "Git" for every
    resume that says "GitHub", and "Java" for every JavaScript developer.

    The trailing boundary also excludes ``+`` and ``#``, which is what stops
    "C" matching inside "C++" while still letting "C++" match on its own.

    Pass ``skills`` to restrict the vocabulary; by default the full catalog.
    """
    if not text:
        return []

    haystack = str(text).lower()
    vocabulary = tuple(skills) if skills is not None else get_skills()

    # Longest first, so "REST API" wins over a hypothetical shorter prefix and
    # a match on the longer phrase is not also reported as its parts.
    ordered = sorted(vocabulary, key=len, reverse=True)

    found: list[str] = []

    for skill in ordered:
        needle = skill.lower()

        pattern = re.compile(
            r"(?<![A-Za-z0-9+#])" + re.escape(needle) + r"(?![A-Za-z0-9+#])"
        )
        if not pattern.search(haystack):
            continue

        # A skill is only suppressed when *every* occurrence in the text sits
        # inside a longer catalog word. One standalone mention anywhere is
        # enough to count, so a document that says both "GitHub Actions" and
        # "Git" honestly reports both.
        if _all_occurrences_are_trapped(needle, haystack, pattern):
            continue

        found.append(skill)

    return found


def _all_occurrences_are_trapped(
    needle: str, haystack: str, pattern: "re.Pattern[str]"
) -> bool:
    """True when every standalone-shaped match is really part of a longer word.

    Needed because the boundary regex above already rejects "Git" inside
    "GitHub" (the trailing ``b`` is a word character). This exists for the
    reverse case: catalog entries that genuinely *are* prefixes of each other
    with a legal trailing boundary, such as "REST" and "REST API", where the
    shorter one would otherwise double-count the longer phrase.
    """
    traps = _SUBSTRING_TRAPS.get(needle)
    if not traps:
        return False

    for match in pattern.finditer(haystack):
        start = match.start()
        for trap in traps:
            trap_start = start - len(trap)
            if trap_start < 0:
                continue
            if haystack[trap_start:start] != trap:
                continue
            # The trap word is immediately before this match, so this mention
            # is the tail of a longer skill rather than a use of its own.
            return True

    return False


def reset_cache() -> None:
    """Clear the cached catalog. Intended for tests."""
    get_catalog.cache_clear()
