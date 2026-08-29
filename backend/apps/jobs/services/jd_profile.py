import re

from apps.resumes.services.skill_normalizer import SkillNormalizer


class JDProfile:

    SECTION_ALIASES = {
        "requirements": [
            "requirements",
            "qualifications",
            "required skills",
            "must have",
            "what we're looking for",
            "what we are looking for",
        ],
        "responsibilities": [
            "responsibilities",
            "responsibilities include",
            "what you'll do",
            "what you will do",
            "your role",
            "role responsibilities",
        ],
        "education": [
            "education",
            "educational qualifications",
            "academic qualifications",
        ],
    }

    @staticmethod
    def build(text: str) -> dict:

        if not text or not text.strip():
            raise ValueError(
                "Job description is empty"
            )

        return {
            "skills": SkillNormalizer.normalize_many(
                JDProfile._extract_skills(text)
            ),
            "experience_years": (
                JDProfile._extract_experience(text)
            ),
            "education": (
                JDProfile._extract_education(text)
            ),
            "responsibilities": (
                JDProfile._extract_section(
                    text,
                    "responsibilities",
                )
            ),
            "requirements": (
                JDProfile._extract_section(
                    text,
                    "requirements",
                )
            ),
        }

    @staticmethod
    def _extract_skills(text: str) -> list:

        known_skills = [
            "Python",
            "Django",
            "FastAPI",
            "REST API",
            "SQL",
            "PostgreSQL",
            "MySQL",
            "SQLite",
            "Docker",
            "Kubernetes",
            "AWS",
            "Azure",
            "GCP",
            "Git",
            "GitHub",
            "Linux",
            "Java",
            "C++",
            "JavaScript",
            "TypeScript",
            "React",
            "Node.js",
            "HTML",
            "CSS",
            "Machine Learning",
            "Artificial Intelligence",
            "Pandas",
            "NumPy",
            "TensorFlow",
            "PyTorch",
            "Spring Boot",
            "Flask",
            "MongoDB",
            "Redis",
            "Kafka",
            "Terraform",
            "Jenkins",
            "CI/CD",
        ]

        text_lower = text.lower()

        return sorted({
            skill
            for skill in known_skills
            if skill.lower() in text_lower
        })

    @staticmethod
    def _extract_experience(text: str):

        patterns = [
            r"(\d+(?:\.\d+)?)\+?\s*"
            r"(?:years?|yrs?)\s+"
            r"(?:of\s+)?experience",

            r"minimum\s+"
            r"(\d+(?:\.\d+)?)\s*"
            r"(?:years?|yrs?)",

            r"at least\s+"
            r"(\d+(?:\.\d+)?)\s*"
            r"(?:years?|yrs?)",
        ]

        matches = []

        for pattern in patterns:

            matches.extend(
                re.findall(
                    pattern,
                    text,
                    flags=re.IGNORECASE,
                )
            )

        if not matches:
            return None

        return max(
            float(match)
            for match in matches
        )

    @staticmethod
    def _extract_education(text: str) -> list:

        education_keywords = [
            "bachelor",
            "b.tech",
            "btech",
            "master",
            "m.tech",
            "mtech",
            "computer science",
            "computer engineering",
            "information technology",
            "degree",
            "ph.d",
            "phd",
            "doctorate",
        ]

        # First try to extract as a dedicated
        # section (like responsibilities)
        education_section = (
            JDProfile._extract_section(
                text,
                "education",
            )
        )

        if education_section:
            return education_section

        # If no dedicated section, extract from
        # requirements that contain education
        # keywords
        normalized_text = re.sub(
            r"\s+",
            " ",
            text.strip(),
        )

        lines = normalized_text.split(" - ")

        education_lines = [
            line.strip()
            for line in lines
            if any(
                keyword in line.lower()
                for keyword in education_keywords
            )
        ]

        if education_lines:
            return education_lines

        # Fallback: check original splitlines
        # for multi-line JDs
        lines = text.splitlines()

        return [
            line.strip()
            for line in lines
            if any(
                keyword in line.lower()
                for keyword in education_keywords
            )
        ]

    @staticmethod
    def _extract_section(
        text: str,
        section_name: str,
    ) -> list:

        aliases = JDProfile.SECTION_ALIASES[
            section_name
        ]

        # -------------------------------------------------
        # First try the normal multi-line format
        # -------------------------------------------------

        lines = text.splitlines()

        start = None

        for index, line in enumerate(lines):

            normalized = (
                line.strip()
                .lower()
                .rstrip(":")
            )

            for alias in aliases:

                if (
                    normalized == alias
                    or normalized.endswith(
                        " " + alias
                    )
                    or normalized.startswith(
                        alias + " "
                    )
                ):
                    start = index + 1
                    break

            if start is not None:
                break

        if start is not None:

            section_lines = []

            all_aliases = []

            for values in (
                JDProfile.SECTION_ALIASES.values()
            ):
                all_aliases.extend(values)

            for line in lines[start:]:

                normalized = (
                    line.strip()
                    .lower()
                    .rstrip(":")
                )

                # Stop at another section
                if normalized in all_aliases:
                    break

                is_heading = False

                for alias in all_aliases:

                    if (
                        normalized.endswith(
                            " " + alias
                        )
                        or normalized.startswith(
                            alias + " "
                        )
                    ):
                        is_heading = True
                        break

                if is_heading:
                    break

                if line.strip():
                    section_lines.append(
                        line.strip()
                    )

            if section_lines:
                return section_lines

        # -------------------------------------------------
        # Single-line JD support
        # -------------------------------------------------

        normalized_text = re.sub(
            r"\s+",
            " ",
            text.strip(),
        )

        # Find the requested section
        # and the next major section.
        section_pattern = (
            r"(?:^|\s)"
            r"(?P<header>"
            + "|".join(
                re.escape(alias)
                for alias in aliases
            )
            + r")"
            r"(?:\s*:\s*|\s+)"
            r"(?P<content>.*?)"
        )

        next_sections = []

        for section_type, values in (
            JDProfile.SECTION_ALIASES.items()
        ):

            if section_type == section_name:
                continue

            for alias in values:
                next_sections.append(
                    re.escape(alias)
                )

        if next_sections:

            section_pattern += (
                r"(?=\s+(?:"
                + "|".join(next_sections)
                + r")"
                r"(?:\s*:|\s|$))"
            )

        match = re.search(
            section_pattern,
            normalized_text,
            flags=re.IGNORECASE,
        )

        if not match:
            return []

        content = match.group(
            "content"
        ).strip()

        if not content:
            return []

        # Remove bullet formatting
        content = re.sub(
            r"\s*-\s*",
            "\n",
            content,
        )

        return [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]