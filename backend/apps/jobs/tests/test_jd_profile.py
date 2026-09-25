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

    def test_greenhouse_style_singleline_sections(self):

        jd = (
            "Our mission at Greenhouse is to make hiring work for everyone. "
            "Who will love this job "
            "A collaborative partner \u2013 you share your knowledge and expertise, "
            "work effectively with others, and contribute to successful project outcomes "
            "What you\u2019ll do "
            "Collaborate with Product Managers and Designers to define requirements "
            "and build product experiences from conception through delivery "
            "Build and improve full-stack experiences for Talent Matching, "
            "Talent Rediscovery, and related talent discovery workflows "
            "Design and ship search-backed capabilities using OpenSearch or Elasticsearch, "
            "including indexing, query design, relevance tuning, ranking, and semantic retrieval "
            "Develop matching systems that combine keyword, structured, semantic, "
            "and AI/ML signals to improve match quality "
            "Partner with Applied ML and cross-functional engineering teams "
            "You should have "
            "5+ years of experience writing production code "
            "Experience with Ruby, C#, Java, or Python; Ruby on Rails preferred "
            "Strong JavaScript or TypeScript fundamentals, including React "
            "Full-stack experience across backend systems, APIs, data modeling, "
            "and modern frontend development "
            "Deep experience with OpenSearch or Elasticsearch in production "
            "Who we are "
            "Greenhouse is a remote-first company"
        )

        profile = JDProfile.build(jd)

        self.assertEqual(
            profile["experience_years"],
            5.0,
        )

        self.assertIn(
            "python",
            profile["skills"],
        )

        self.assertIn(
            "react",
            profile["skills"],
        )

        self.assertGreater(
            len(profile["responsibilities"]),
            1,
        )

        self.assertGreater(
            len(profile["requirements"]),
            1,
        )

        requirements_text = " ".join(
            profile["requirements"]
        )

        responsibilities_text = " ".join(
            profile["responsibilities"]
        )

        self.assertIn(
            "5+ years of experience",
            requirements_text,
        )

        self.assertIn(
            "Strong JavaScript or TypeScript",
            requirements_text,
        )

        self.assertIn(
            "Collaborate with Product Managers",
            responsibilities_text,
        )

        self.assertNotIn(
            "You should have",
            responsibilities_text,
        )

        self.assertNotIn(
            "Who we are",
            requirements_text,
        )

        self.assertNotIn(
            "Greenhouse is a remote-first",
            requirements_text,
        )