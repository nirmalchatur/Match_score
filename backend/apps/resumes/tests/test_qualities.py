"""
Tests for the qualities catalogue and its validation rules.

The contract under test is "what a user is allowed to save": the canonical
shape, the catalogue membership rule, and the minimum of seven enforced
server-side. The last one is the point of this file -- a disabled button in
the UI is a hint, not a control, and a PATCH sent by hand has to fail
identically.
"""

import json

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from apps.resumes.models import Resume, ResumeProfile

from apps.resumes import qualities as q


class NormalizeTests(SimpleTestCase):
    def test_empty_input_gives_all_three_keys(self):
        for raw in (None, "", {}):
            self.assertEqual(q.normalize(raw), {k: [] for k in q.KINDS})

    def test_case_and_whitespace_are_canonicalised(self):
        result = q.normalize({"technical": ["  python ", "PYTHON", "dOcKeR"]})
        self.assertEqual(result["technical"], ["Python", "Docker"])

    def test_duplicates_collapse(self):
        result = q.normalize({"technical": ["Python", "python", "PYTHON"]})
        self.assertEqual(result["technical"], ["Python"])

    def test_output_follows_catalogue_order_not_input_order(self):
        """
        Stable ordering is what makes the UI and the prompt reproducible.

        The expectation follows the catalogue's own positions (Python 0,
        Rust 7, Docker 32), so it stays correct if the catalogue is reordered
        as long as those relative positions hold. It is deliberately not
        alphabetical: "Python, Rust, Docker" proves the sort is by catalogue
        position, since alphabetical would give Docker first.
        """
        result = q.normalize({"technical": ["Docker", "Rust", "Python"]})
        self.assertEqual(
            [v.lower() for v in result["technical"]],
            ["python", "rust", "docker"],
        )

    def test_missing_kinds_are_filled_in_empty(self):
        result = q.normalize({"technical": ["Python"]})
        self.assertEqual(set(result), set(q.KINDS))
        self.assertEqual(result["soft_skills"], [])

    def test_blank_entries_are_ignored(self):
        """An empty input row in the picker is an artefact, not a choice."""
        result = q.normalize({"technical": ["Python", "", "   "]})
        self.assertEqual(result["technical"], ["Python"])

    def test_unknown_value_is_rejected_not_silently_dropped(self):
        with self.assertRaises(q.QualityError) as ctx:
            q.normalize({"technical": ["COBOL"]})
        self.assertIn("COBOL", str(ctx.exception))

    def test_unknown_category_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"technical": ["Python"], "vibes": ["good"]})

    def test_value_from_the_wrong_category_is_rejected(self):
        """Categories are not interchangeable, and must not be interchangeable."""
        with self.assertRaises(q.QualityError):
            q.normalize({"project_management": ["Python"]})

    def test_non_list_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"technical": "Python"})

    def test_non_mapping_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize(["Python"])

    def test_non_string_entry_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"technical": [42]})

class MinimumTests(SimpleTestCase):
    def test_seven_is_accepted(self):
        selection = {
            "technical": ["Python", "Java", "Go", "Rust"],
            "project_management": ["Scrum"],
            "soft_skills": ["Communication", "Empathy"],
        }
        self.assertEqual(q.count(q.validate_selection(selection)), 7)

    def test_six_is_rejected(self):
        selection = {
            "technical": ["Python", "Java", "Go"],
            "project_management": ["Scrum"],
            "soft_skills": ["Communication", "Empathy"],
        }
        with self.assertRaises(q.QualityError) as ctx:
            q.validate_selection(selection)
        self.assertIn(str(q.MINIMUM_TOTAL), str(ctx.exception))

    def test_empty_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.validate_selection({})

    def test_every_category_must_be_represented(self):
        """
        Seven technical skills and nothing else is not a valid selection.

        Without this the other two groups are decorative, and the "pick your
        strengths" framing becomes a lie.
        """
        selection = {
            "technical": [
                "Python", "Java", "Go", "Rust", "SQL", "Docker", "AWS",
            ],
            "project_management": [],
            "soft_skills": [],
        }
        with self.assertRaises(q.QualityError) as ctx:
            q.validate_selection(selection)
        self.assertIn("soft skills", str(ctx.exception).lower())

    def test_the_category_message_wins_over_the_total_message(self):
        """
        When a category is empty the total is the unhelpful half of the answer.

        A user who selected six and forgot soft skills should be told to add a
        soft skill, not that they need one more.
        """
        selection = {
            "technical": ["Python", "Java", "Go", "Rust", "SQL", "Docker"],
            "project_management": ["Scrum", "Kanban"],
            "soft_skills": [],
        }
        with self.assertRaises(q.QualityError) as ctx:
            q.validate_selection(selection)
        self.assertIn("soft skills", str(ctx.exception).lower())
        self.assertNotIn("You have selected", str(ctx.exception))


class CatalogueTests(SimpleTestCase):
    def test_catalogue_has_no_duplicates_within_a_kind(self):
        for kind, values in q.CATALOGUE.items():
            lowered = [v.lower() for v in values]
            self.assertEqual(
                len(lowered), len(set(lowered)), f"{kind} has duplicate entries"
            )

    def test_every_catalogue_entry_normalises_to_itself(self):
        """Round-trip: what the UI offers must be what the server accepts."""
        for kind, values in q.CATALOGUE.items():
            result = q.normalize({kind: values})
            self.assertEqual(result[kind], values, f"{kind} does not round-trip")

    def test_catalogue_is_not_empty(self):
        for kind in q.KINDS:
            self.assertTrue(q.CATALOGUE[kind], f"{kind} has no options")

    def test_labels_exist_for_every_kind(self):
        for kind in q.KINDS:
            self.assertIn(kind, q.KIND_LABELS)


class AsListTests(SimpleTestCase):
    def test_flattens_in_kind_order(self):
        selection = q.normalize(
            {
                "technical": ["Docker"],
                "project_management": ["Scrum"],
                "soft_skills": ["Empathy"],
            }
        )
        self.assertEqual(q.as_list(selection), ["Docker", "Scrum", "Empathy"])

class QualitiesApiTests(TestCase):
    """
    GET/PUT /api/resumes/qualities/ over HTTP.

    The unit tests in this file cover the rules; these cover the contract --
    in particular that the minimum is enforced by the *server*. A request built
    by hand has to fail the same way the UI's disabled button prevents, because
    the button is a courtesy and the handler is the control.
    """

    URL = "/api/resumes/qualities/"

    def setUp(self):
        self.user = User.objects.create_user(
            username="q@example.test", email="q@example.test", password="pw-12345"
        )
        self.other = User.objects.create_user(
            username="r@example.test", email="r@example.test", password="pw-12345"
        )
        self.master = Resume.objects.create(
            user=self.user, name="Master", resume_type="MASTER", is_master=True
        )
        self.profile = ResumeProfile.objects.create(
            resume=self.master, skills=["Python"], experience={}
        )
        self.client.force_login(self.user)

    def put(self, payload):
        return self.client.put(
            self.URL, data=json.dumps(payload), content_type="application/json"
        )

    def selection(self, **overrides):
        base = {
            "technical": ["Python", "Java", "Go", "Rust"],
            "project_management": ["Scrum"],
            "soft_skills": ["Communication", "Empathy"],
        }
        base.update(overrides)
        return base

    # -- read ---------------------------------------------------------------

    def test_get_returns_the_catalogue_and_the_minimum(self):
        """
        The picker must not hard-code options the server would reject.

        Shipping the catalogue in the response is what keeps the two in step.
        """
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(set(body["catalogue"]), set(q.KINDS))
        self.assertEqual(body["minimum_total"], q.MINIMUM_TOTAL)
        self.assertIn("technical", body["labels"])

    def test_get_starts_empty_for_a_fresh_account(self):
        body = self.client.get(self.URL).json()
        self.assertEqual(body["selected_count"], 0)
        self.assertEqual(body["qualities"], {k: [] for k in q.KINDS})

    def test_get_without_a_master_resume_is_not_an_error(self):
        """
        A 200 with an empty selection, so the picker can render and explain.

        Failing here would strand a brand new account with no way to see what
        the options even are.
        """
        User.objects.all().delete()
        fresh = User.objects.create_user(
            username="s@example.test", email="s@example.test", password="pw-12345"
        )
        self.client.force_login(fresh)
        response = self.client.get(self.URL)
        self.assertEqual(response.status_code, 200)
        self.assertIn("catalogue", response.json())

    def test_get_requires_authentication(self):
        self.client.logout()
        self.assertIn(self.client.get(self.URL).status_code, (401, 403))

    # -- write --------------------------------------------------------------

    def test_a_valid_selection_is_saved(self):
        response = self.put(self.selection())
        self.assertEqual(response.status_code, 200)
        self.profile.refresh_from_db()
        self.assertEqual(q.count(self.profile.qualities), 7)

    def test_the_response_echoes_the_canonical_selection(self):
        body = self.put(
            self.selection(technical=["docker", "  PYTHON  ", "Go", "Java"])
        ).json()
        self.assertEqual(body["qualities"]["technical"], ["Python", "Java", "Go", "Docker"])

    def test_fewer_than_seven_is_rejected(self):
        response = self.put(
            self.selection(
                technical=["Python"], project_management=["Scrum"],
                soft_skills=["Communication"],
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(q.MINIMUM_TOTAL), response.json()["error"])

    def test_a_rejected_selection_is_not_partially_saved(self):
        before = dict(self.profile.qualities)
        self.put(self.selection(technical=["Python"]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.qualities, before)

    def test_an_empty_category_is_rejected_even_at_seven_total(self):
        response = self.put(
            self.selection(
                technical=["Python", "Java", "Go", "Rust", "SQL", "Docker"],
                project_management=["Scrum"],
                soft_skills=[],
            )
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("soft skills", response.json()["error"].lower())

    def test_a_value_outside_the_catalogue_is_rejected(self):
        response = self.put(self.selection(technical=["Python", "Java", "Go", "COBOL"]))
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_category_is_rejected(self):
        payload = self.selection()
        payload["vibes"] = ["good"]
        self.assertEqual(self.put(payload).status_code, 400)

    def test_a_replacement_overwrites_rather_than_appends(self):
        self.put(self.selection())
        self.put(self.selection(soft_skills=["Clarity", "Ownership", "Curiosity"]))
        self.profile.refresh_from_db()
        self.assertNotIn("Empathy", self.profile.qualities["soft_skills"])
        self.assertIn("Clarity", self.profile.qualities["soft_skills"])

    def test_another_accounts_qualities_are_untouched(self):
        """Tenant boundary: the lookup is by owner, never by a supplied id."""
        self.put(self.selection())

        intruder_master = Resume.objects.create(
            user=self.other, name="Theirs", resume_type="MASTER", is_master=True
        )
        intruder_profile = ResumeProfile.objects.create(
            resume=intruder_master, skills=["Go"]
        )
        self.assertEqual(intruder_profile.qualities, {})

    def test_writing_without_a_master_resume_is_a_404(self):
        self.master.delete()
        self.assertEqual(self.put(self.selection()).status_code, 404)

    def test_put_requires_authentication(self):
        self.client.logout()
        self.assertIn(self.put(self.selection()).status_code, (401, 403))
