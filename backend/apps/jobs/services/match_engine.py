import re


class MatchEngine:

    SKILL_WEIGHT = 0.50
    EXPERIENCE_WEIGHT = 0.20
    REQUIREMENT_WEIGHT = 0.20
    EDUCATION_WEIGHT = 0.10

    @classmethod
    def calculate(cls, resume_profile: dict, jd_profile: dict) -> dict:

        skill_result = cls._skill_match(
            resume_profile.get("skills", []),
            jd_profile.get("skills", []),
        )

        experience_result = cls._experience_match(
            resume_profile.get("experience", {}),
            jd_profile.get("experience_years"),
        )

        requirement_result = cls._requirement_match(
            resume_profile,
            jd_profile,
        )

        education_result = cls._education_match(
            resume_profile.get("education", ""),
            jd_profile.get("education", []),
        )

        score = (
            skill_result["score"] * cls.SKILL_WEIGHT
            + experience_result["score"] * cls.EXPERIENCE_WEIGHT
            + requirement_result["score"] * cls.REQUIREMENT_WEIGHT
            + education_result["score"] * cls.EDUCATION_WEIGHT
        )

        return {
            "score": round(score, 2),
            "skills": skill_result,
            "experience": experience_result,
            "requirements": requirement_result,
            "education": education_result,
            "decision": cls._decision(score),
        }

    @staticmethod
    def _skill_match(resume_skills, jd_skills):

        resume = set(resume_skills)
        jd = set(jd_skills)

        if not jd:
            return {
                "score": 100.0,
                "matched": [],
                "missing": [],
            }

        matched = sorted(resume & jd)
        missing = sorted(jd - resume)

        score = (
            len(matched)
            / len(jd)
            * 100
        )

        return {
            "score": round(score, 2),
            "matched": matched,
            "missing": missing,
        }

    @staticmethod
    def _experience_match(
        resume_experience,
        required_years,
    ):

        if required_years is None:

            candidate_years = (
                resume_experience.get(
                    "total_years",
                    0.0,
                )
                if isinstance(
                    resume_experience,
                    dict,
                )
                else 0.0
            )

            return {
                "score": 100.0,
                "required_years": None,
                "candidate_years": candidate_years,
                "note": (
                    "No explicit experience "
                    "requirement"
                ),
            }

        if not isinstance(
            resume_experience,
            dict,
        ):

            return {
                "score": 0.0,
                "required_years": required_years,
                "candidate_years": 0.0,
                "note": (
                    "Resume experience could "
                    "not be determined"
                ),
            }

        candidate_years = float(
            resume_experience.get(
                "total_years",
                0.0,
            )
        )

        if required_years <= 0:

            score = 100.0

        else:

            score = min(
                (
                    candidate_years
                    / required_years
                ) * 100,
                100.0,
            )

        return {
            "score": round(score, 2),
            "required_years": required_years,
            "candidate_years": candidate_years,
            "note": (
                "Experience requirement "
                "detected"
            ),
        }

    @staticmethod
    def _requirement_match(
        resume_profile,
        jd_profile,
    ):

        requirements = jd_profile.get(
            "requirements",
            [],
        )

        if not requirements:

            return {
                "score": 100.0,
                "matched": [],
                "partially_matched": [],
                "unmatched": [],
            }

        resume_skills = set(
            resume_profile.get(
                "skills",
                [],
            )
        )

        jd_skills = set(
            jd_profile.get(
                "skills",
                [],
            )
        )

        matched = []
        partially_matched = []
        unmatched = []

        credits = []

        experience_pattern = (
            r"(\d+(?:\.\d+)?)\+?\s*"
            r"(?:years?|yrs?)"
        )

        education_keywords = (
            "bachelor",
            "b.tech",
            "btech",
            "master",
            "m.tech",
            "mtech",
            "degree",
            "undergraduate",
            "graduate",
            "ph.d",
            "phd",
            "doctorate",
        )

        resume_experience = (
            resume_profile.get(
                "experience",
                {},
            )
        )

        candidate_years = float(
            resume_experience.get(
                "total_years",
                0,
            )
        )

        for requirement in requirements:

            requirement_lower = (
                requirement.lower()
            )

            # -----------------------------------------
            # Education is handled separately
            # -----------------------------------------

            if any(
                keyword in requirement_lower
                for keyword in education_keywords
            ):
                continue

            # -----------------------------------------
            # Experience is handled separately
            # -----------------------------------------

            experience_match = re.search(
                experience_pattern,
                requirement_lower,
            )

            if (
                experience_match
                and "experience"
                in requirement_lower
            ):
                # Skip: Experience is scored by
                # _experience_match() separately
                # to avoid double-counting
                continue

            # -----------------------------------------
            # Technical / skill requirements
            # -----------------------------------------

            relevant_skills = [
                skill
                for skill in jd_skills
                if skill.lower()
                in requirement_lower
            ]

            if relevant_skills:

                matched_skills = [
                    skill
                    for skill in relevant_skills
                    if skill in resume_skills
                ]

                ratio = (
                    len(matched_skills)
                    / len(relevant_skills)
                )

                credits.append(ratio)

                if ratio >= 1.0:

                    matched.append(
                        requirement
                    )

                elif ratio > 0:

                    partially_matched.append(
                        requirement
                    )

                else:

                    unmatched.append(
                        requirement
                    )

                continue

            # -----------------------------------------
            # Generic requirement
            # -----------------------------------------

            resume_text = " ".join(
                str(value)
                for value in resume_profile.values()
                if isinstance(value, str)
            ).lower()

            words = [
                word
                for word in requirement_lower.split()
                if len(word) > 3
            ]

            if not words:

                credit = 0.0

            else:

                ratio = (
                    sum(
                        word in resume_text
                        for word in words
                    )
                    / len(words)
                )

                if ratio >= 0.75:

                    credit = 1.0

                elif ratio > 0:

                    credit = 0.5

                else:

                    credit = 0.0

            credits.append(credit)

            if credit >= 1.0:

                matched.append(
                    requirement
                )

            elif credit > 0:

                partially_matched.append(
                    requirement
                )

            else:

                unmatched.append(
                    requirement
                )

        # All requirements were either
        # education or experience requirements.
        if not credits:

            return {
                "score": 100.0,
                "matched": [],
                "partially_matched": [],
                "unmatched": [],
            }

        score = (
            sum(credits)
            / len(credits)
            * 100
        )

        return {
            "score": round(score, 2),
            "matched": matched,
            "partially_matched": partially_matched,
            "unmatched": unmatched,
        }

    @staticmethod
    def _education_requirement_credit(
        requirement,
        education,
    ):

        education_keywords = (
            "bachelor",
            "b.tech",
            "btech",
            "master",
            "m.tech",
            "mtech",
            "degree",
            "undergraduate",
            "graduate",
            "ph.d",
            "phd",
            "doctorate",
        )

        if not any(
            keyword in requirement
            for keyword in education_keywords
        ):

            return None

        if not education:

            return 0.0

        required_level = (
            MatchEngine._education_level(
                requirement
            )
        )

        candidate_level = (
            MatchEngine._education_level(
                education
            )
        )

        if (
            required_level
            and candidate_level < required_level
        ):

            return 0.0

        fields = (
            "computer science",
            "computer engineering",
            "information technology",
            "physics",
            "mathematics",
            "electrical engineering",
            "mechanical engineering",
        )

        required_fields = [
            field
            for field in fields
            if field in requirement
        ]

        if not required_fields:

            return (
                1.0
                if candidate_level
                else 0.0
            )

        if any(
            field in education
            for field in required_fields
        ):

            return 1.0

        if (
            "computer science"
            in required_fields
            and any(
                field in education
                for field in (
                    "computer engineering",
                    "information technology",
                )
            )
        ):

            return 0.5

        return 0.0

    @staticmethod
    def _education_level(text):

        if any(
            term in text
            for term in (
                "ph.d",
                "phd",
                "doctorate",
            )
        ):

            return 3

        if any(
            term in text
            for term in (
                "master",
                "m.tech",
                "mtech",
            )
        ):

            return 2

        if any(
            term in text
            for term in (
                "bachelor",
                "b.tech",
                "btech",
                "undergraduate",
                "degree",
            )
        ):

            return 1

        return 0

    @staticmethod
    def _education_match(
        resume_education,
        jd_education,
    ):

        if not jd_education:

            return {
                "score": 100.0,
                "note": (
                    "No explicit education "
                    "requirement"
                ),
            }

        education = str(
            resume_education or ""
        ).lower()

        requirements = [
            str(item).lower()
            for item in jd_education
        ]

        if not education:

            return {
                "score": 0.0,
                "note": (
                    "Education requirement exists"
                ),
            }

        credits = []

        for requirement in requirements:

            credit = (
                MatchEngine
                ._education_requirement_credit(
                    requirement,
                    education,
                )
            )

            if credit is not None:

                credits.append(credit)

        if not credits:

            return {
                "score": 100.0,
                "note": (
                    "No specific education "
                    "requirement detected"
                ),
            }

        score = (
            sum(credits)
            / len(credits)
            * 100
        )

        return {
            "score": round(score, 2),
            "note": (
                "Education requirement "
                "evaluated"
            ),
        }

    @staticmethod
    def _decision(score):

        if score >= 95:
            return "USE_MASTER"

        if score >= 70:
            return "TAILOR"

        if score >= 50:
            return "REVIEW"

        return "SKIP"