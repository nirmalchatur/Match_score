"""
The job list is a compact row; the detail endpoint carries the posting.

Why this is pinned rather than trusted: the list is fetched by the shell on
every dashboard mount and holds *every* job the account owns, and the full shape
measured 2.0 MB at 400 rows. Adding one heavy field back to the list serializer
is a one-line change whose cost lands on the whole dashboard, so the shape and
its size are asserted here.
"""

import json
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.jobs.models import Job
from apps.jobs.serializers import JobListSerializer, JobSerializer

User = get_user_model()

#: A realistically long posting (~8 KB). Real Greenhouse and Workday postings
#: are this size, and the size is the whole reason the payload was split.
LONG_DESCRIPTION = "Requirements: Python, Django, PostgreSQL, Docker. " * 160

ANALYSIS = {
    "score": 61.5,
    "decision": "REVIEW",
    "skills": {"score": 70.0, "matched": ["python", "django"], "missing": ["docker"]},
    "experience": {"score": 40.0, "note": "2 of 5 years"},
    "requirements": {"score": 50.0, "matched": [], "unmatched": ["docker"]},
    "education": {"score": 100.0, "note": "No explicit education requirement"},
    "qualities": {"matched": [], "selected": []},
}

PIPELINE = [{"name": "Resume matched", "status": "complete"}] * 8

#: What a list row has to carry for the UI that renders it: JobRow, the sidebar
#: search, the tracker panel and the resume/job pickers.
SUMMARY_FIELDS = (
    "id",
    "url",
    "company",
    "title",
    "location",
    "source",
    "match_score",
    "decision",
    "status",
    "created_at",
    "updated_at",
)

#: What only the detail view renders.
DETAIL_ONLY_FIELDS = (
    "description",
    "match_result",
    "skill_gap",
    "pipeline_steps",
    "error_message",
)


class JobListTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="payload@example.test",
            email="payload@example.test",
            password="pw-payload-1234",
        )
        self.job = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/1",
            company="Acme",
            title="Senior Backend Engineer",
            location="Remote",
            source="greenhouse",
            description=LONG_DESCRIPTION,
            match_score=61.5,
            match_result=ANALYSIS,
            decision="REVIEW",
            status="READY",
            pipeline_steps=PIPELINE,
            error_message="",
        )

    def list_row(self):
        return JobListSerializer(Job.objects.filter(user=self.user), many=True).data[0]

    def detail_row(self):
        return JobSerializer(self.job).data


class JobListShapeTests(JobListTestCase):
    def test_the_list_row_carries_what_a_list_renders(self):
        row = self.list_row()

        for field in SUMMARY_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, row)

    def test_the_list_row_carries_none_of_the_heavy_fields(self):
        row = self.list_row()

        for field in DETAIL_ONLY_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn(field, row)

    def test_the_detail_row_still_carries_the_posting_and_the_analysis(self):
        row = self.detail_row()

        for field in DETAIL_ONLY_FIELDS:
            with self.subTest(field=field):
                self.assertIn(field, row)

        self.assertEqual(row["description"], LONG_DESCRIPTION)

    def test_a_list_row_is_a_fraction_of_a_detail_row(self):
        """
        The measured problem, as an assertion. A row that carries the posting
        cannot be small, so the ratio between the two shapes is what is worth
        guarding rather than an absolute size that drifts with the fixture.
        """
        list_size = len(json.dumps(self.list_row()))
        detail_size = len(json.dumps(self.detail_row()))

        self.assertLess(list_size * 4, detail_size)

    def test_the_list_does_not_compute_a_skill_gap(self):
        """
        ``skill_gap`` is derived CPU: it is rebuilt from the stored analysis on
        every serialisation. On a list of hundreds of rows that is hundreds of
        rebuilds per request, so the list must not touch it at all.
        """
        with mock.patch("apps.jobs.serializers.analyze_skill_gap") as gap:
            JobListSerializer(Job.objects.filter(user=self.user), many=True).data

        gap.assert_not_called()


class JobEndpointShapeTests(JobListTestCase):
    """The same split, through the endpoints the frontend actually calls."""

    def setUp(self):
        super().setUp()
        self.client.force_login(self.user)

    def test_the_list_endpoint_returns_compact_rows(self):
        response = self.client.get("/api/jobs/")

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(len(body), 1)
        for field in DETAIL_ONLY_FIELDS:
            with self.subTest(field=field):
                self.assertNotIn(field, body[0])

        self.assertEqual(body[0]["title"], "Senior Backend Engineer")

    def test_the_detail_endpoint_returns_the_posting(self):
        response = self.client.get(f"/api/jobs/{self.job.id}/")

        self.assertEqual(response.status_code, 200)
        body = response.json()

        self.assertEqual(body["description"], LONG_DESCRIPTION)
        self.assertIn("skill_gap", body)

    def test_a_list_of_realistic_postings_stays_small(self):
        """
        The guard that matters in production: 25 postings of a realistic size
        must not produce a response measured in megabytes. Before the split this
        single response was the largest thing the app ever sent, and it grew
        linearly with the library.
        """
        Job.objects.filter(user=self.user).delete()
        Job.objects.bulk_create(
            [
                Job(
                    user=self.user,
                    url="https://boards.greenhouse.io/acme/jobs/%d" % index,
                    company="Company %d" % index,
                    title="Backend Engineer %d" % index,
                    description=LONG_DESCRIPTION,
                    source="greenhouse",
                    status="READY",
                    match_score=61.5,
                    match_result=ANALYSIS,
                    decision="REVIEW",
                    pipeline_steps=PIPELINE,
                )
                for index in range(25)
            ]
        )

        response = self.client.get("/api/jobs/")

        self.assertEqual(len(response.json()), 25)
        self.assertLess(len(response.content), 40 * 1024)
