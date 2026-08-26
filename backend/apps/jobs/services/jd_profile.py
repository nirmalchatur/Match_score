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
            raise ValueError("Job description is empty")

        return {
            "skills": SkillNormalizer.normalize_many(
    JDProfile._extract_skills(text)),
            "experience_years": JDProfile._extract_experience(text),
            "education": JDProfile._extract_education(text),
            "responsibilities": JDProfile._extract_section(
                text,
                "responsibilities",
            ),
            "requirements": JDProfile._extract_section(
                text,
                "requirements",
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
            r"(\d+(?:\.\d+)?)\+?\s*(?:years?|yrs?)\s+(?:of\s+)?experience",
            r"minimum\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
            r"at least\s+(\d+(?:\.\d+)?)\s*(?:years?|yrs?)",
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

        return max(float(match) for match in matches)

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
        ]

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
    def _extract_section(text: str, section_name: str) -> list:
        lines = text.splitlines()

        aliases = JDProfile.SECTION_ALIASES[section_name]

        start = None

        for index, line in enumerate(lines):
            normalized = line.strip().lower()

            if normalized in aliases:
                start = index + 1
                break

        if start is None:
            return []

        section_lines = []

        all_section_names = []

        for values in JDProfile.SECTION_ALIASES.values():
            all_section_names.extend(values)

        for line in lines[start:]:
            normalized = line.strip().lower()

            # Stop when another major section begins.
            if normalized in all_section_names:
                break

            if line.strip():
                section_lines.append(line.strip())

        return section_lines