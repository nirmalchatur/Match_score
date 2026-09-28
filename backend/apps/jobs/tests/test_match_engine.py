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

class QualityMatchTests(TestCase):
    """
    Qualities are reported by the engine but must not move the score.

    The score is the product's central claim about a candidate, so the
    guarantee that a self-assessment cannot inflate it is worth pinning
    explicitly rather than trusting to the weights staying untouched.
    """

    RESUME = {
        "skills": ["Python", "Django"],
        "experience": {"total_years": 5.0},
        "education": "B.Tech Computer Science",
    }

    JD = {
        "skills": ["Python", "Docker"],
        "requirements": ["Docker experience", "Scrum"],
        "responsibilities": ["Lead delivery"],
        "title": "Backend Engineer",
        "education": [],
    }

    def calculate(self, qualities):
        resume = dict(self.RESUME)
        resume["qualities"] = qualities
        return MatchEngine.calculate(resume, self.JD)

    def test_the_score_is_identical_with_and_without_qualities(self):
        without = self.calculate(None)
        with_seven = self.calculate(
            {
                "technical": ["Python", "Docker", "Go", "Rust"],
                "project_management": ["Scrum"],
                "soft_skills": ["Communication", "Empathy"],
            }
        )
        self.assertEqual(without["score"], with_seven["score"])
        self.assertEqual(without["decision"], with_seven["decision"])

    def test_selecting_everything_cannot_raise_the_score(self):
        """
        The abuse case, stated directly.

        Choosing every catalogue entry is the cheapest way to try to inflate a
        score. It must change nothing, or the number stops meaning anything.
        """
        from apps.resumes.qualities import CATALOGUE

        everything = {kind: list(values) for kind, values in CATALOGUE.items()}
        self.assertEqual(
            self.calculate(None)["score"], self.calculate(everything)["score"]
        )

    def test_a_quality_the_job_mentions_is_reported_as_matched(self):
        result = self.calculate(
            {
                "technical": ["Python", "Docker"],
                "project_management": ["Scrum"],
                "soft_skills": ["Communication"],
            }
        )
        matched = result["qualities"]["matched"]
        self.assertIn("Docker", matched)
        self.assertIn("Scrum", matched)

    def test_a_quality_the_job_never_mentions_is_not_matched(self):
        result = self.calculate(
            {
                "technical": ["Rust"],
                "project_management": ["Kanban"],
                "soft_skills": ["Diplomacy"],
            }
        )
        self.assertEqual(result["qualities"]["matched"], [])

    def test_no_selection_is_distinguishable_from_matching_nothing(self):
        """
        "Chose nothing" and "chose things, none relevant" must not look alike.

        The first is an onboarding state; the second is a real result. The note
        field is what tells them apart.
        """
        empty = self.calculate(None)["qualities"]
        chosen_but_unmatched = self.calculate(
            {
                "technical": ["Rust"],
                "project_management": ["Kanban"],
                "soft_skills": ["Diplomacy"],
            }
        )["qualities"]

        self.assertEqual(empty["matched"], [])
        self.assertEqual(chosen_but_unmatched["matched"], [])
        self.assertNotEqual(empty["note"], chosen_but_unmatched["note"])
        self.assertEqual(empty["selected"], [])

    def test_malformed_qualities_do_not_break_the_engine(self):
        """A bad row must not take the whole analysis down with it."""
        for bad in ("not-a-mapping", {"technical": "Python"}, {"nope": []}):
            result = self.calculate(bad)
            self.assertEqual(result["qualities"]["matched"], [])
            self.assertIn("score", result)

    def test_the_qualities_block_does_not_disturb_the_other_blocks(self):
        """Existing consumers see exactly the keys they saw before."""
        result = self.calculate(
            {
                "technical": ["Python"],
                "project_management": ["Scrum"],
                "soft_skills": ["Communication"],
            }
        )
        for key in ("skills", "experience", "requirements", "education", "decision"):
            self.assertIn(key, result)
