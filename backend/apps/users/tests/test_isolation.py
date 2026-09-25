"""
Cross-account data isolation.

These are the most important tests in the project: they prove one account
can never read, mutate, or delete another account's data, including by
guessing a primary key.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.jobs.models import Job
from apps.resumes.models import Resume, ResumeProfile

User = get_user_model()


def make_user(email):
    return User.objects.create_user(
        username=email,
        email=email,
        password="isolation-pass-123",
    )


def make_resume(user, name="Master", is_master=True):
    resume = Resume.objects.create(
        user=user,
        name=name,
        resume_type="MASTER" if is_master else "TAILORED",
        is_master=is_master,
        file=f"resumes/{user.id}-{name}.pdf",
    )
    ResumeProfile.objects.create(
        resume=resume,
        skills=["Python"],
        experience={"years": 3},
        education="BSc",
        projects="Projects",
        certifications="None",
    )
    return resume


def make_job(user, url, title="Role"):
    return Job.objects.create(
        user=user,
        url=url,
        company="Acme",
        title=title,
        location="Remote",
        description="Description",
        status="READY",
        match_score=80.0,
    )


class JobIsolationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice@example.com")
        self.bob = make_user("bob@example.com")

        self.alice_job = make_job(self.alice, "https://acme.greenhouse.io/jobs/1")
        self.bob_job = make_job(self.bob, "https://acme.greenhouse.io/jobs/2")

    def test_job_list_requires_authentication(self):
        response = self.client.get("/api/jobs/")

        self.assertIn(response.status_code, [401, 403])

    def test_job_list_only_returns_own_jobs(self):
        self.client.force_login(self.alice)

        response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.alice_job.id)

    def test_job_detail_hides_other_users_job(self):
        self.client.force_login(self.alice)

        response = self.client.get(f"/api/jobs/{self.bob_job.id}/")

        self.assertEqual(response.status_code, 404)

    def test_job_detail_returns_own_job(self):
        self.client.force_login(self.alice)

        response = self.client.get(f"/api/jobs/{self.alice_job.id}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.alice_job.id)

    def test_same_url_can_be_analysed_by_two_accounts(self):
        """URL uniqueness is per account, not global."""
        shared_url = "https://acme.greenhouse.io/jobs/shared"

        first = make_job(self.alice, shared_url)
        second = make_job(self.bob, shared_url)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(Job.objects.filter(url=shared_url).count(), 2)


class ResumeIsolationTests(TestCase):
    def setUp(self):
        self.alice = make_user("alice@example.com")
        self.bob = make_user("bob@example.com")

        self.alice_resume = make_resume(self.alice)
        self.bob_resume = make_resume(self.bob)

    def test_resume_list_requires_authentication(self):
        response = self.client.get("/api/resumes/")

        self.assertIn(response.status_code, [401, 403])

    def test_resume_list_only_returns_own_resumes(self):
        self.client.force_login(self.alice)

        response = self.client.get("/api/resumes/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["id"], self.alice_resume.id)

    def test_resume_detail_hides_other_users_resume(self):
        self.client.force_login(self.alice)

        response = self.client.get(f"/api/resumes/{self.bob_resume.id}/")

        self.assertEqual(response.status_code, 404)

    def test_master_resume_is_per_account(self):
        self.client.force_login(self.bob)

        response = self.client.get("/api/resumes/master/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], self.bob_resume.id)

    def test_cannot_promote_another_users_resume_to_master(self):
        self.client.force_login(self.alice)

        response = self.client.post(
            f"/api/resumes/{self.bob_resume.id}/set-master/",
        )

        self.assertEqual(response.status_code, 404)
        self.bob_resume.refresh_from_db()
        self.assertFalse(
            self.bob_resume.user == self.alice
        )

    def test_cannot_delete_another_users_resume(self):
        self.client.force_login(self.alice)

        response = self.client.delete(
            f"/api/resumes/{self.bob_resume.id}/",
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Resume.objects.filter(pk=self.bob_resume.id).exists())

    def test_promoting_own_resume_demotes_the_previous_master(self):
        second = make_resume(self.alice, name="Second", is_master=False)

        self.client.force_login(self.alice)
        response = self.client.post(
            f"/api/resumes/{second.id}/set-master/",
        )

        self.assertEqual(response.status_code, 200)
        self.alice_resume.refresh_from_db()
        self.assertFalse(self.alice_resume.is_master)
        self.assertEqual(
            Resume.objects.filter(user=self.alice, is_master=True).count(),
            1,
        )
