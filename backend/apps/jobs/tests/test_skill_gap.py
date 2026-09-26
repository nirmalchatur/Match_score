"""
Skill gap analysis tests.

The point of this module is that it is a **projection** of what MatchEngine
already computed, not a second matching system. These tests assert both halves:
that the projection is faithful, and that it is derived from the deterministic
engine rather than anything the model produced.
"""

from django.contrib.auth.models import User
from django.test import TestCase

from apps.jobs.models import Job
from apps.resumes.services import skill_catalog
from apps.jobs.services.match_engine import MatchEngine
from apps.jobs.services.skill_gap import analyze_skill_gap
from apps.resumes.services.skill_normalizer import SkillNormalizer


class SkillGapTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username="gap@example.test", email="gap@example.test", password="pw-12345"
        )
        self.job = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/1",
            company="Acme",
            title="Backend Engineer",
            description=(
                "Requirements:\n"
                "- Strong Python and Django experience\n"
                "- PostgreSQL\n"
                "- Docker\n"
                "- Kubernetes\n"
                "- Terraform\n"
            ),
        )

    def _analysed_job(self, resume_text, description):
        """Run the real pipeline, then project it. No shortcuts."""
        from apps.resumes.services.resume_profile import ResumeProfile

        profile = ResumeProfile.build(resume_text)
        jd = __import__(
            "apps.jobs.services.jd_profile", fromlist=["JDProfile"]
        ).JDProfile.build(description)
        result = MatchEngine.calculate(profile, jd)

        self.job.description = description
        self.job.match_result = result
        self.job.match_score = result["score"]
        self.job.save()
        return result

    def test_projection_reproduces_engine_output(self):
        result = self._analysed_job(
            "Skills: Python, Django, PostgreSQL\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- PostgreSQL\n- Kubernetes\n",
        )
        gap = analyze_skill_gap(self.job)

        self.assertTrue(gap["has_analysis"])
        # Matched/missing are the normalized skill vocabulary; partial comes
        # from the requirement pass, which is the only place the engine records
        # partial credit.
        self.assertEqual(set(gap["matched"]), set(result["skills"]["matched"]))
        self.assertEqual(set(gap["missing"]), set(result["skills"]["missing"]))
        self.assertEqual(
            set(gap["partial"]), set(result["requirements"]["partially_matched"])
        )

    def test_matched_skills_come_from_the_central_catalog(self):
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- Django\n- Kubernetes\n",
        )
        gap = analyze_skill_gap(self.job)

        catalog = {s.lower() for s in skill_catalog.get_skills()}
        for skill in gap["matched"] + gap["partial"] + gap["missing"]:
            self.assertIn(
                SkillNormalizer.normalize(skill),
                catalog,
                "%r is not in the centralized skill catalog" % skill,
            )

    def test_missing_requirement_is_reported_as_not_found(self):
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- Kubernetes\n",
        )
        gap = analyze_skill_gap(self.job)

        self.assertIn("kubernetes", gap["missing"])
        self.assertNotIn("kubernetes", gap["matched"])

    def test_wording_does_not_claim_the_candidate_lacks_a_skill(self):
        """The copy must describe the resume, not judge the person."""
        self._analysed_job(
            "Skills: Python\n\nExperience\nBuilt services.",
            "Requirements:\n- Kubernetes\n",
        )
        summary = analyze_skill_gap(self.job)["summary"]

        # Must state the caveat: absence from the document is not absence of skill.
        self.assertIn("not found", summary.lower())
        self.assertIn("not a judgement about what you can do", summary.lower())

        for forbidden in (
            "you don't know",
            "you lack",
            "you cannot",
            "missing skill",
            "you are weak",
            "skill gap in you",
        ):
            self.assertNotIn(forbidden.lower(), summary.lower())

    def test_summary_reports_a_count_not_a_verdict(self):
        """A number of matches, not a grade of the candidate."""
        self._analysed_job(
            "Skills: Python\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- Kubernetes\n",
        )
        summary = analyze_skill_gap(self.job)["summary"]
        self.assertIn("1 of the 2 skills", summary)

    def test_unanalysed_job_reports_no_analysis_rather_than_an_empty_gap(self):
        gap = analyze_skill_gap(self.job)
        self.assertFalse(gap["has_analysis"])
        self.assertEqual(gap["matched"], [])
        self.assertEqual(gap["summary"], "No job analysis available.")

    def test_empty_requirement_list_does_not_read_as_a_total_mismatch(self):
        self._analysed_job(
            "Skills: Python\n\nExperience\nBuilt services.",
            "A role focused on collaboration and communication.",
        )
        gap = analyze_skill_gap(self.job)
        self.assertTrue(gap["has_analysis"])
        self.assertIn("No skill requirements", gap["summary"])

    def test_gap_is_exposed_on_the_job_serializer(self):
        self.client.force_login(self.user)
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- Kubernetes\n",
        )
        response = self.client.get("/api/jobs/%d/" % self.job.id)

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("skill_gap", body)
        self.assertTrue(body["skill_gap"]["has_analysis"])
        self.assertIn("kubernetes", body["skill_gap"]["missing"])

    def test_skill_gap_needs_no_model(self):
        """Deterministic: identical input always yields identical output."""
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Python\n- Kubernetes\n",
        )
        first = analyze_skill_gap(self.job)
        second = analyze_skill_gap(self.job)
        self.assertEqual(first, second)
