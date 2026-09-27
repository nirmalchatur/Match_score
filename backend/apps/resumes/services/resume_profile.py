from apps.resumes.services.skill_normalizer import SkillNormalizer
from apps.resumes.services import skill_catalog
from apps.resumes.services.experience_parser import ExperienceParser

class ResumeProfile:

    @staticmethod
    def build(text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("Resume text is empty")

        return {
            "skills": SkillNormalizer.normalize_many(
                ResumeProfile._extract_skills(text)
            ),
            "experience": ExperienceParser.parse(
    ResumeProfile._extract_section(
        text,
        ["experience", "work experience", "professional experience"]
    )),
            "education": ResumeProfile._extract_section(
                text,
                [
                    "education",
                    "academic background",
                ],
            ),
            "projects": ResumeProfile._extract_section(
                text,
                [
                    "projects",
                    "personal projects",
                ],
            ),
            "certifications": ResumeProfile._extract_section(
                text,
                [
                    "certifications",
                    "certificates",
                ],
            ),
        }

    @staticmethod
    def _extract_skills(text: str) -> list:
        # Reads the single shared vocabulary (apps.resumes.services
        # .skill_catalog) instead of a private copy.
        return skill_catalog.extract_skills(text)

    @staticmethod
    def _extract_section(text: str, headings: list) -> str:
        lines = text.splitlines()

        start = None

        for i, line in enumerate(lines):
            normalized = line.strip().lower()

            if normalized in headings:
                start = i + 1
                break

        if start is None:
            return ""

        section = []

        section_headings = [
            "skills",
            "technical skills",
            "experience",
            "work experience",
            "professional experience",
            "education",
            "projects",
            "certifications",
            "certificates",
        ]

        for line in lines[start:]:
            normalized = line.strip().lower()

            if normalized in section_headings:
                break

            if line.strip():
                section.append(line.strip())

        return "\n".join(section)