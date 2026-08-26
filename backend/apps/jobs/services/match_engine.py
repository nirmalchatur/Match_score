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

        score = (len(matched) / len(jd)) * 100

        return {
            "score": round(score, 2),
            "matched": matched,
            "missing": missing,
        }

    @staticmethod
    def _experience_match(resume_experience, required_years):

        if required_years is None:
            return {
                "score": 100.0,
                "required_years": None,
                "candidate_years": resume_experience.get(
                    "total_years", 0.0
                ) if isinstance(resume_experience, dict) else 0.0,
                "note": "No explicit experience requirement",
            }

        if not isinstance(resume_experience, dict):
            return {
                "score": 0.0,
                "required_years": required_years,
                "candidate_years": 0.0,
                "note": "Resume experience could not be determined",
            }

        candidate_years = resume_experience.get(
            "total_years",
            0.0,
        )

        if required_years <= 0:
            score = 100.0
        else:
            score = min(
                (candidate_years / required_years) * 100,
                100.0,
            )

        return {
            "score": round(score, 2),
            "required_years": required_years,
            "candidate_years": candidate_years,
            "note": "Experience requirement detected",
        }

    @staticmethod
    def _requirement_match(resume_profile, jd_profile):

        requirements = jd_profile.get("requirements", [])

        if not requirements:
            return {
                "score": 100.0,
                "matched": [],
                "partially_matched": [],
                "unmatched": [],
            }

        resume_skills = set(
            resume_profile.get("skills", [])
        )

        jd_skills = set(
            jd_profile.get("skills", [])
        )

        matched = []
        partially_matched = []
        unmatched = []

        for requirement in requirements:

            requirement_lower = requirement.lower()

            relevant_skills = [
                skill
                for skill in jd_skills
                if skill.lower() in requirement_lower
            ]

            if not relevant_skills:
                # No identifiable skill in this requirement.
                # Use conservative text matching.
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

                matches = sum(
                    1
                    for word in words
                    if word in resume_text
                )

                ratio = (
                    matches / len(words)
                    if words
                    else 1
                )

            else:

                matched_skills = [
                    skill
                    for skill in relevant_skills
                    if skill in resume_skills
                ]

                ratio = (
                    len(matched_skills)
                    / len(relevant_skills)
                )

            if ratio >= 0.99:
                matched.append(requirement)

            elif ratio > 0:
                partially_matched.append(requirement)

            else:
                unmatched.append(requirement)

        total = (
            len(matched)
            + len(partially_matched)
            + len(unmatched)
        )

        if total == 0:
            score = 100.0
        else:
            score = (
                len(matched)
                + (0.5 * len(partially_matched))
            ) / total * 100

        return {
            "score": round(score, 2),
            "matched": matched,
            "partially_matched": partially_matched,
            "unmatched": unmatched,
        }
    @staticmethod
    def _education_match(resume_education, jd_education):

        if not jd_education:
            return {
                "score": 100.0,
                "note": "No explicit education requirement",
            }

        if not resume_education:
            return {
                "score": 0.0,
                "note": "Education requirement exists",
            }

        return {
            "score": 100.0,
            "note": "Resume contains education information",
        }

    @staticmethod
    def _decision(score):

        if score >= 95:
            return "USE_MASTER"

        return "TAILOR"