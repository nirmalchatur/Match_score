"""
Normalises skill spellings onto TailorUp's canonical vocabulary.

The vocabulary itself lives in :mod:`apps.resumes.services.skill_catalog`,
which is the single file to edit when adding or removing skills. This module
only handles the spelling problem ("ReactJS" -> "react").
"""

import re

from apps.resumes.services import skill_catalog


class SkillNormalizer:

    @classmethod
    def normalize(cls, skill: str) -> str:
        """Fold a raw skill string onto its canonical form."""
        skill = skill.strip().lower()

        skill = re.sub(r"\s+", " ", skill)

        return skill_catalog.get_aliases().get(skill, skill)

    @classmethod
    def normalize_many(cls, skills: list[str]) -> list[str]:
        """Normalise a collection and return a sorted, de-duplicated list."""
        normalized = {
            cls.normalize(skill)
            for skill in skills
            if skill and skill.strip()
        }

        return sorted(normalized)

    @classmethod
    def extract_known_skills(cls, text: str) -> list[str]:
        """
        Find every catalog skill mentioned in ``text``.

        A thin convenience wrapper over the catalog, kept for callers that
        already depend on the normaliser.
        """
        return skill_catalog.extract_skills(text)
