from django.test import TestCase

from apps.jobs.services.jd_profile import JDProfile


class JDProfileTest(TestCase):

    def test_multiline_jd_parsing(self):

        jd = """
        Python Backend Engineer

        Requirements
        - 2+ years of experience in Python
        - Experience with Django and REST APIs
        - Knowledge of AWS and Docker
        - Bachelor degree in Computer Science

        Responsibilities
        - Build backend services
        - Develop REST APIs
        - Deploy applications on AWS
        """

        profile = JDProfile.build(jd)

        self.assertEqual(
            profile["experience_years"],
            2.0,
        )

        self.assertIn(
            "python",
            profile["skills"],
        )

        self.assertIn(
            "django",
            profile["skills"],
        )

        self.assertEqual(
            len(profile["requirements"]),
            4,
        )

        self.assertEqual(
            len(profile["responsibilities"]),
            3,
        )

    def test_singleline_jd_parsing(self):

        jd = (
            "Python Backend Engineer "
            "Requirements "
            "- 2+ years of experience in Python "
            "- Experience with Django and REST APIs "
            "- Knowledge of AWS and Docker "
            "- Bachelor degree in Computer Science "
            "Responsibilities "
            "- Build backend services "
            "- Develop REST APIs "
            "- Deploy applications on AWS"
        )

        profile = JDProfile.build(jd)

        self.assertEqual(
            profile["experience_years"],
            2.0,
        )

        self.assertIn(
            "aws",
            profile["skills"],
        )

        self.assertIn(
            "rest api",
            profile["skills"],
        )

        self.assertEqual(
            len(profile["requirements"]),
            4,
        )

    def test_empty_jd(self):

        with self.assertRaises(ValueError):
            JDProfile.build("")