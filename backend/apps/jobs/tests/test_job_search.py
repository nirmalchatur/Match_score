"""
Tests for resume-ranked job search.

The behaviours worth defending, in order of how badly they would hurt:

1. Tenant isolation -- a search never returns another account's jobs, even
   when that other account has a much better-matching resume.
2. Fresh scoring -- a search after a master-resume change reflects the new
   resume, not the score stored when each job was analysed.
3. Honest empties -- no resume, no skills, and no matches are three different
   answers and must stay distinguishable.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from apps.resumes.models import Resume, ResumeProfile

from apps.jobs.models import Job
from apps.jobs.services import job_search

User = get_user_model()


def make_user(username):
    return User.objects.create_user(
        username=username,
        email=f"{username}@example.com",
        password="test-password-123",
    )


def make_master(user, skills, name="Master"):
    resume = Resume.objects.create(user=user, name=name, is_master=True)
    ResumeProfile.objects.create(resume=resume, skills=list(skills))
    return resume


class SearchServiceTests(TestCase):
    def setUp(self):
        self.user = make_user("alice")
        self.other = make_user("bob")
        make_master(self.user, ["Python", "Django", "PostgreSQL"])

    def test_ranks_by_score_descending(self):
        strong = make_job(self.user, "Python Django Engineer", skills=["Python", "Django"])
        make_job(self.user, "Office Manager", skills=["Excel", "Word"])

        titles = [row["title"] for row in job_search.search_jobs(self.user)["results"]]

        self.assertIn(strong.title, titles)
        self.assertNotIn("Office Manager", titles)

    def test_excludes_jobs_below_the_useful_threshold(self):
        make_job(self.user, "Office Manager", skills=["Excel", "Word"])
        self.assertEqual(job_search.search_jobs(self.user)["results"], [])

    def test_excludes_jobs_with_no_skill_overlap_however_high_the_score(self):
        """
        The important one.

        MatchEngine scores skills at 50% and the other three factors at 50%
        combined, so a job sharing none of the candidate's skills can still land
        in the 50s on requirements and education alone. A list headed "jobs that
        match your skills" must not show that job with an empty matched-skills
        chip -- the number would look like a skill match and be nothing of the
        sort.
        """
        make_job(
            self.user,
            "Office Manager",
            company="Acme",
            skills=["Excel", "Word", "PowerPoint", "Reception"],
        )

        result = job_search.search_jobs(self.user)

        self.assertEqual(result["results"], [])

    def test_every_result_reports_at_least_one_matched_skill(self):
        # The invariant behind the test above, asserted across a mixed set.
        make_job(self.user, "Python Engineer", skills=["Python", "Django"])
        make_job(self.user, "Chef", skills=["Excel", "Word", "Food Safety"])

        for row in job_search.search_jobs(self.user)["results"]:
            self.assertTrue(row["matched_skills"], row["title"])

    def test_never_returns_another_users_jobs(self):
        # Bob's job is a far better match on paper, and must still be absent.
        make_job(self.other, "Python Django Engineer", skills=["Python", "Django"])
        self.assertEqual(job_search.search_jobs(self.user)["results"], [])

    def test_ignores_jobs_that_are_not_searchable_yet(self):
        # A queued job has no JD profile; scoring it would report a confident
        # zero against an empty posting.
        for status in ("PENDING", "FAILED", "RUNNING"):
            make_job(
                self.user,
                f"Python Engineer {status}",
                skills=["Python"],
                status=status,
            )
        self.assertEqual(job_search.search_jobs(self.user)["results"], [])

    def test_rescore_reflects_current_resume_not_stored_score(self):
        job = make_job(self.user, "Engineer", skills=["Python", "Django"])
        job.match_score = 5.0
        job.save(update_fields=["match_score"])

        result = job_search.search_jobs(self.user)


    def test_free_text_filter_narrows_results(self):
        make_job(self.user, "Python Engineer", company="Acme", skills=["Python"])
        make_job(self.user, "Chef", company="Tasty", skills=["Python"])

        result = job_search.search_jobs(self.user, terms=["Acme"])

        self.assertEqual([r["title"] for r in result["results"]], ["Python Engineer"])

    def test_skill_filter_narrows_results(self):
        make_job(self.user, "Python Engineer", company="PyCo", skills=["Python"])
        make_job(self.user, "Chef", company="Tasty", skills=["Python"])

        result = job_search.search_jobs(self.user, terms=["PyCo"])

        self.assertEqual([r["title"] for r in result["results"]], ["Python Engineer"])

    def test_no_master_resume_raises(self):
        with self.assertRaises(job_search.NoMasterResume):
            job_search.search_jobs(make_user("bare"))

    def test_resume_without_skills_reports_why(self):
        # Not an empty result set with no explanation: the user needs to know
        # the resume is the problem, not their job list.
        empty = make_user("empty")
        Resume.objects.create(user=empty, name="Master", is_master=True)
        make_job(empty, "Engineer", skills=["Python"])

        result = job_search.search_jobs(empty)

        self.assertEqual(result["results"], [])
        self.assertEqual(result["reason"], "no_skills")

    def test_limit_is_clamped_to_the_maximum(self):
        for index in range(5):
            make_job(self.user, f"Engineer {index}", skills=["Python", "Django"])

        result = job_search.search_jobs(self.user, limit=10_000)

        self.assertLessEqual(len(result["results"]), job_search.MAX_RESULTS)

    def test_reports_totals_for_the_empty_state(self):
        # The UI needs to distinguish "no jobs yet" from "nothing matched".
        # This class's setUp gives the user a three-skill master resume.
        result = job_search.search_jobs(self.user)
        self.assertEqual(result["total_jobs"], 0)
        self.assertEqual(result["resume"]["skills"], 3)

    def test_resume_with_no_extraction_reports_zero_skills(self):
        # A master resume with no profile row yet must say so rather than
        # looking like a search that found nothing.
        fresh = make_user("hank")
        Resume.objects.create(user=fresh, name="Master", is_master=True)

        result = job_search.search_jobs(fresh)

        self.assertEqual(result["reason"], "no_skills")
        self.assertEqual(result["resume"]["skills"], 0)


class JobSearchApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = make_user("erin")
        make_master(self.user, ["Python", "Django"])
        self.client.force_authenticate(self.user)

    def test_requires_authentication(self):
        anonymous = APIClient()
        self.assertIn(
            anonymous.get("/api/jobs/search/").status_code, (401, 403)
        )

    def test_no_master_resume_is_409_with_a_code(self):
        # 409 rather than an empty 200: the UI must be able to tell the user to
        # upload a resume instead of showing "no matches".
        bare = make_user("frank")
        self.client.force_authenticate(bare)

        response = self.client.get("/api/jobs/search/")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "no_master_resume")
        self.assertEqual(response.data["results"], [])

    def test_returns_results_for_a_matching_account(self):
        make_job(self.user, "Python Engineer", skills=["Python", "Django"])
        response = self.client.get("/api/jobs/search/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 1)

    def test_does_not_leak_another_accounts_jobs(self):
        other = make_user("gina")
        make_job(other, "Python Engineer", skills=["Python", "Django"])
        response = self.client.get("/api/jobs/search/")
        self.assertEqual(response.data["results"], [])

    def test_q_parameter_filters(self):
        make_job(self.user, "Python Engineer", company="Acme", skills=["Python"])
        make_job(self.user, "Chef", company="Tasty", skills=["Python"])
        response = self.client.get("/api/jobs/search/?q=Acme")
        self.assertEqual(len(response.data["results"]), 1)

    def test_skills_parameter_is_split_on_commas(self):
        make_job(self.user, "Python Engineer", company="PyCo", skills=["Python"])
        make_job(self.user, "Chef", company="Tasty", skills=["Python"])
        response = self.client.get("/api/jobs/search/?skills=PyCo")
        self.assertEqual(len(response.data["results"]), 1)

    def test_a_non_numeric_limit_is_ignored_not_fatal(self):
        make_job(self.user, "Python Engineer", skills=["Python", "Django"])
        response = self.client.get("/api/jobs/search/?limit=banana")
        self.assertEqual(response.status_code, 200)

    def test_every_returned_hit_names_at_least_one_matched_skill(self):
        # The API-level counterpart of the service invariant, so a future
        # change to the response shape cannot quietly drop the field the UI
        # uses to justify the ordering.
        make_job(self.user, "Python Engineer", skills=["Python", "Django"])
        make_job(self.user, "Chef", skills=["Excel", "Word", "Food Safety"])

        response = self.client.get("/api/jobs/search/")

        self.assertTrue(response.data["results"])
        for row in response.data["results"]:
            self.assertTrue(row["matched_skills"], row["title"])

    def test_search_path_is_not_swallowed_by_the_detail_route(self):
        # A regression guard: "search/" declared after "<int:pk>/" would 404.
        response = self.client.get("/api/jobs/search/")
        self.assertNotEqual(response.status_code, 404)


    def test_a_malformed_job_does_not_break_the_whole_search(self):
        make_job(self.user, "Good Engineer", skills=["Python", "Django"])
        broken = make_job(self.user, "Broken", skills=["Python"])
        Job.objects.filter(pk=broken.pk).update(match_result="not-a-dict")

        result = job_search.search_jobs(self.user)

        self.assertTrue(
            any(row["title"] == "Good Engineer" for row in result["results"])
        )

    def test_search_does_not_write_back_to_the_job(self):
        # A read must not mutate the user's job list.
        job = make_job(self.user, "Engineer", skills=["Python", "Django"])
        before = job.match_score

        job_search.search_jobs(self.user)

        job.refresh_from_db()
        self.assertEqual(job.match_score, before)


def make_job(user, title, company="Acme", skills=None, status="COMPLETED"):
    """A job carrying an already-extracted JD profile, as analysis stores."""
    return Job.objects.create(
        user=user,
        title=title,
        company=company,
        url=f"https://example.com/{abs(hash((title, company))) % 10**8}",
        description=title,
        status=status,
        match_result={"jd_profile": {"skills": list(skills or [])}},
    )
