from django.test import TestCase

from apps.jobs.services.jd_profile import JDProfile
from apps.jobs.services.match_engine import MatchEngine


class MatchEngineTest(TestCase):

    def setUp(self):

        self.resume = {
            "skills": [
                "aws",
                "docker",
                "python",
                "react",
                "rest api",
                "git",
            ],
            "experience": {
                "total_years": 0.42,
            },
            "education": (
                "B.Tech Computer Engineering"
            ),
            "projects": "",
            "certifications": "",
        }

    def test_strong_match(self):

        jd = JDProfile.build(
            """
            Python Backend Engineer

            Requirements
            - 0-1 years of experience in Python
            - Experience with Python and REST APIs
            - Knowledge of AWS and Docker
            - Bachelor degree in Computer Engineering
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertGreaterEqual(
            result["score"],
            80,
        )

        self.assertEqual(
            result["decision"],
            "TAILOR",
        )

    def test_medium_match(self):

        jd = JDProfile.build(
            """
            Python Backend Engineer

            Requirements
            - 2+ years of experience in Python
            - Experience with Django and REST APIs
            - Knowledge of AWS and Docker
            - Bachelor degree in Computer Science
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertGreaterEqual(
            result["score"],
            60,
        )

        self.assertLess(
            result["score"],
            70,
        )

        self.assertEqual(
            result["decision"],
            "REVIEW",
        )

    def test_poor_match(self):

        jd = JDProfile.build(
            """
            Java Backend Engineer

            Requirements
            - 5+ years of experience
            - Strong Spring Boot experience
            - Kubernetes
            - Azure
            - Master's degree in Physics
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertLess(
            result["score"],
            30,
        )

        self.assertEqual(
            result["decision"],
            "SKIP",
        )

    def test_missing_skill(self):

        jd = JDProfile.build(
            """
            Backend Engineer

            Requirements
            - Experience with Django
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertIn(
            "django",
            result["skills"]["missing"],
        )

    def test_experience_score(self):

        jd = JDProfile.build(
            """
            Backend Engineer

            Requirements
            - 2+ years of experience
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertEqual(
            result["experience"]["required_years"],
            2.0,
        )

        self.assertAlmostEqual(
            result["experience"]["candidate_years"],
            0.42,
            places=2,
        )

    def test_no_double_counting(self):

        jd = JDProfile.build(
            """
            Backend Engineer

            Requirements
            - 2+ years of experience
            - Bachelor degree in Computer Science
            - Knowledge of AWS and Docker
            """
        )

        result = MatchEngine.calculate(
            self.resume,
            jd,
        )

        self.assertNotIn(
            "- 2+ years of experience",
            result["requirements"]["matched"],
        )

        self.assertNotIn(
            "- Bachelor degree in Computer Science",
            result["requirements"]["matched"],
        )