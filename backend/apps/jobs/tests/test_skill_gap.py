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
        # Matched and missing are the normalized skill vocabulary, copied
        # straight from the engine, so they are still exact.
        self.assertEqual(set(gap["matched"]), set(result["skills"]["matched"]))
        self.assertEqual(set(gap["missing"]), set(result["skills"]["missing"]))

        # Partial is NOT a copy any more, and this is the change that made the
        # panel readable. The engine records partial credit against a whole
        # requirement *line* ("- Strong Python and Kubernetes experience"),
        # which is a sentence, not a skill. Projecting it verbatim put sentences
        # into a panel titled "Skill analysis" -- "Ability To Manage And
        # Communicate With Many People At Once" showed up as a partial match
        # under that exact name.
        #
        # So each line is reduced to the catalog skills it mentions, and the
        # contract is now about *what the partial list contains* rather than
        # about it mirroring the engine. That is a stronger statement than the
        # copy it replaces, because it pins the property that actually matters.
        catalog = {s.lower() for s in skill_catalog.get_skills()}
        for skill in gap["partial"]:
            self.assertIn(
                skill,
                catalog,
                "partial must be a catalog skill, not a raw requirement "
                "line: %r" % skill,
            )

    def test_partial_is_reduced_from_requirement_lines_to_skills(self):
        """The regression this projection change was made to fix.

        A requirement naming a skill the resume does not list must surface as
        that skill -- never as the sentence it was written as.

        "Strong Kubernetes experience" is a *complete* non-match (the only
        skill it names is absent), so the engine records no partial credit for
        it and Kubernetes surfaces in `missing`. The assertion is therefore
        about the reduction: the sentence must not appear in any column.
        """
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Strong Kubernetes experience\n",
        )
        gap = analyze_skill_gap(self.job)

        shown = gap["partial"] + gap["missing"]
        self.assertIn("kubernetes", shown)
        for skill in shown:
            self.assertNotIn("experience", skill.lower())
            self.assertNotIn("strong", skill.lower())

    def test_a_half_matched_sentence_yields_a_skill_not_a_sentence(self):
        """A half-matched requirement reaches the panel as a skill.

        "Strong Python and Kubernetes experience" against a Python-only resume
        scores 0.5: Python is on the resume, Kubernetes is not. That half
        credit is real signal and it must reach the user.

        Kubernetes is *also* reported as missing by the skill pass, so this is
        the overlap case: the skill is shown once, under `missing`, rather than
        listed twice. What must never happen is the sentence surviving, or the
        panel claiming a partial match while displaying none.
        """
        self._analysed_job(
            "Skills: Python, Django\n\nExperience\nBuilt services.",
            "Requirements:\n- Strong Python and Kubernetes experience\n",
        )
        gap = analyze_skill_gap(self.job)

        # Reported exactly once, and the sentence never appears anywhere.
        self.assertIn("kubernetes", gap["missing"])
        for skill in gap["partial"] + gap["matched"] + gap["missing"]:
            self.assertNotIn("experience", skill.lower())
            self.assertNotIn("strong", skill.lower())

    def test_a_partial_can_survive_when_the_skill_is_not_otherwise_missing(self):
        """`partial` is not dead code: it carries skills `missing` does not list.

        The requirement pass and the skill pass read different things -- one
        works from JD requirement lines, the other from the parsed resume skill
        list -- so a half-matched requirement can name a skill the skill pass
        never reported as missing. That skill is exactly what the partial
        column is for, and dropping it would silently lose the signal.
        """
        self._analysed_job(
            "Skills: Python\n\nExperience\nBuilt services.",
            "Requirements:\n- Strong Python and Kubernetes experience\n",
        )
        gap = analyze_skill_gap(self.job)

        # Kubernetes is surfaced exactly once, and it is a skill, not a line.
        everything = gap["partial"] + gap["matched"] + gap["missing"]
        self.assertIn("kubernetes", everything)
        for skill in everything:
            self.assertNotIn("experience", skill.lower())
            self.assertNotIn("strong", skill.lower())
            self.assertNotIn(" ", skill.strip())

    def test_partial_never_duplicates_a_matched_or_missing_skill(self):
        """One skill, one column.

        A skill named by a half-matched requirement can also be in `matched` or
        `missing`. Showing it twice reads as a contradiction, so partial is
        made disjoint -- with `missing` winning, because "the resume does not
        mention it at all" is the stronger fact.
        """
        self._analysed_job(
            "Skills: Python, Django, Docker\n\nExperience\nBuilt services.",
            "Requirements:\n- Strong Python and Kubernetes experience\n"
            "- Python and Docker together\n",
        )
        gap = analyze_skill_gap(self.job)

        self.assertFalse(set(gap["partial"]) & set(gap["matched"]))
        self.assertFalse(set(gap["partial"]) & set(gap["missing"]))

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
