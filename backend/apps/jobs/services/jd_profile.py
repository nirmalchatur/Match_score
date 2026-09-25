"""
Job Description Profile Builder.

Parses raw job description text and extracts:

- Skills (matched against known list)
- Experience (years)
- Education (dedicated section or keywords)
- Responsibilities (section-based)
- Requirements (section-based)

Handles both multi-line and cleaned single-line JD formats.
"""

import re

from apps.resumes.services.skill_normalizer import SkillNormalizer


class JDProfile:
    """
    Extracts structured profile data from raw job description text.
    """

    SECTION_ALIASES = {
        "requirements": [
            "requirements",
            "qualifications",
            "required skills",
            "must have",
            "what we're looking for",
            "what we are looking for",
            "you should have",
            "you'll have",
            "you will have",
            "your qualifications",
        ],
        "responsibilities": [
            "responsibilities",
            "responsibilities include",
            "what you'll do",
            "what you will do",
            "your role",
            "role responsibilities",
            "what you'll be doing",
            "what you will be doing",
        ],
        "education": [
            "education",
            "educational qualifications",
            "academic qualifications",
            "educational background",
        ],
    }

    # Headings that are not extracted sections,
    # but should stop section extraction.
    BOUNDARY_HEADINGS = [
        "who will love this job",
        "who we are",
        "about us",
        "about the company",
        "about the team",
        "our culture",
        "our values",
        "our mission",
        "our story",
        "why work here",
        "why join us",
        "what we offer",
        "equal employment opportunity",
        "equal opportunity employer",
        "diversity & inclusion",
        "diversity and inclusion",
        "diversity statement",
    ]

    @staticmethod
    def build(text: str) -> dict:
        """
        Build a structured profile dict from raw JD text.
        """

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
        """
        Extract skills by matching against a known list.
        """

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

        return sorted(
            {
                skill
                for skill in known_skills
                if skill.lower() in text_lower
            }
        )

    @staticmethod
    def _extract_experience(text: str):
        """
        Extract years of experience.

        Handles:
        - X years of experience
        - X yrs experience
        - minimum X years
        - at least X years
        """

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
        """
        Extract education requirements from the JD.
        """

        # Normalize curly apostrophes.
        text = (
            text
            .replace("\u2019", "'")
            .replace("\u2018", "'")
        )

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

        # First try dedicated education section.
        education_section = (
            JDProfile._extract_section(
                text,
                "education",
            )
        )

        if education_section:
            return education_section

        # Normalize whitespace.
        normalized_text = re.sub(
            r"\s+",
            " ",
            text.strip(),
        )

        # Check hyphen-separated content.
        lines = re.split(
            r"\s+[-\u2013\u2014]\s+",
            normalized_text,
        )

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

        # Fallback to original lines.
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
    def _normalize_text(text: str) -> str:
        """
        Normalize common Unicode punctuation that can
        interfere with section detection.
        """

        return (
            text
            .replace("\u2019", "'")
            .replace("\u2018", "'")
            .replace("\u201c", '"')
            .replace("\u201d", '"')
        )

    @staticmethod
    def _all_stop_headings() -> list:
        """
        Return all section aliases and boundary headings.
        """

        headings = []

        for values in (
            JDProfile.SECTION_ALIASES.values()
        ):
            headings.extend(values)

        headings.extend(
            JDProfile.BOUNDARY_HEADINGS
        )

        return sorted(
            set(headings),
            key=len,
            reverse=True,
        )

    @staticmethod
    def _is_heading(
        line: str,
        headings: list,
    ) -> bool:
        """
        Determine whether a line represents a section
        or boundary heading.
        """

        normalized = (
            line.strip()
            .lower()
            .rstrip(":")
        )

        for heading in headings:
            if (
                normalized == heading
                or normalized.startswith(
                    heading + " "
                )
                or normalized.endswith(
                    " " + heading
                )
            ):
                return True

        return False

    @staticmethod
    def _extract_section(
        text: str,
        section_name: str,
    ) -> list:
        """
        Extract a named section from the JD.

        Supports:

        1. Normal multiline JDs
        2. Cleaned single-line JDs
        3. ASCII '-' bullets
        4. En-dash '–' bullets
        5. Em-dash '—' bullets

        Inline hyphens such as:
            trade-offs
            full-stack
            user-facing

        are preserved.
        """

        text = JDProfile._normalize_text(text)

        aliases = sorted(
            JDProfile.SECTION_ALIASES[
                section_name
            ],
            key=len,
            reverse=True,
        )

        all_stop_headings = (
            JDProfile._all_stop_headings()
        )

        # =================================================
        # MULTI-LINE FORMAT
        # =================================================

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
                    or normalized.startswith(
                        alias + " "
                    )
                    or normalized.endswith(
                        " " + alias
                    )
                ):
                    start = index + 1
                    break

            if start is not None:
                break

        if start is not None:

            section_lines = []

            for line in lines[start:]:

                normalized = (
                    line.strip()
                    .lower()
                    .rstrip(":")
                )

                # Stop at another section or
                # boundary heading.
                if normalized in all_stop_headings:
                    break

                if JDProfile._is_heading(
                    line,
                    all_stop_headings,
                ):
                    break

                if line.strip():
                    section_lines.append(
                        line.strip()
                    )

            if section_lines:
                return section_lines

        # =================================================
        # SINGLE-LINE FORMAT
        # =================================================

        normalized_text = re.sub(
            r"\s+",
            " ",
            text.strip(),
        )

        # -------------------------------------------------
        # Build the section header pattern.
        # -------------------------------------------------

        alias_pattern = "|".join(
            re.escape(alias)
            for alias in aliases
        )

        section_pattern = (
            r"(?:^|\s)"
            r"(?P<header>"
            + alias_pattern
            + r")"
            r"(?:\s*:\s*|\s+)"
            r"(?P<content>.*?)"
        )

        # -------------------------------------------------
        # Build stop headings.
        #
        # Do NOT include the current section aliases,
        # because we need to capture after them.
        # -------------------------------------------------

        next_sections = []

        for section_type, values in (
            JDProfile.SECTION_ALIASES.items()
        ):
            if section_type == section_name:
                continue

            next_sections.extend(values)

        next_sections.extend(
            JDProfile.BOUNDARY_HEADINGS
        )

        next_sections = sorted(
            set(next_sections),
            key=len,
            reverse=True,
        )

        if next_sections:

            next_section_pattern = "|".join(
                re.escape(heading)
                for heading in next_sections
            )

            section_pattern += (
                r"(?=\s+(?:"
                + next_section_pattern
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

        # =================================================
        # SPLIT SINGLE-LINE BULLETS
        # =================================================

        # Handle:
        #
        # - item one
        # - item two
        #
        # without destroying:
        #
        # trade-offs
        # full-stack
        # user-facing
        #
        # We only split when the dash has whitespace
        # on BOTH sides.
        content = re.sub(
            r"\s+[-\u2013\u2014]\s+",
            "\n",
            content,
        )

        # =================================================
        # CLEAN RESULT
        # =================================================

        items = [
            line.strip()
            for line in content.splitlines()
            if line.strip()
        ]

        if len(items) <= 1:
            sentence_items = [
                item.strip()
                for item in re.split(
                    r"(?<=[.!?])\s+|(?<=[a-z0-9])\s+(?=[A-Z])",
                    content,
                )
                if item.strip()
            ]

            if len(sentence_items) > 1:
                return sentence_items

        return items