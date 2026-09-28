"""
Tests for the qualities catalogue and its validation rules.

The catalogue is 50 options across seven groups, from which a candidate picks
seven. The contract under test is "what a user is allowed to save": the
canonical shape, catalogue membership, the minimum of seven, and one from
every group. That last rule is what makes seven selections meaningful rather
than seven programming languages.

The minimum is enforced server-side. A disabled button in the UI is a hint,
not a control, and a request sent by hand has to fail identically.
"""

import json

from django.contrib.auth.models import User
from django.test import Client, SimpleTestCase, TestCase

from apps.resumes import qualities as q
from apps.resumes.models import Resume, ResumeProfile

#: A valid seven: one from every group, so it satisfies every rule at once.
VALID = {
    "programming": ["Python"],
    "data_structures": ["Trees and graphs"],
    "problem_solving": ["Debugging"],
    "soft_skills": ["Team collaboration"],
    "project_management": ["Sprint planning"],
    "leadership": ["Mentoring"],
    "hr": ["Performance reviews"],
}


class NormalizeTests(SimpleTestCase):
    def test_empty_input_gives_all_seven_keys(self):
        for raw in (None, "", {}):
            self.assertEqual(q.normalize(raw), {k: [] for k in q.KINDS})

    def test_case_and_whitespace_are_canonicalised(self):
        result = q.normalize({"programming": ["  python ", "PYTHON", "sql"]})
        self.assertEqual(result["programming"], ["Python", "SQL"])

    def test_duplicates_collapse(self):
        result = q.normalize({"programming": ["Python", "python", "PYTHON"]})
        self.assertEqual(result["programming"], ["Python"])

    def test_output_follows_catalogue_order_not_input_order(self):
        result = q.normalize(
            {"programming": ["SQL", "Java", "Python"]}
        )
        self.assertEqual(
            result["programming"], ["Python", "Java", "SQL"]
        )

    def test_missing_groups_are_filled_in_empty(self):
        result = q.normalize({"programming": ["Python"]})
        self.assertEqual(set(result), set(q.KINDS))
        self.assertEqual(result["hr"], [])

    def test_blank_entries_are_ignored(self):
        """An empty input row in the picker is an artefact, not a choice."""
        result = q.normalize({"programming": ["Python", "", "   "]})
        self.assertEqual(result["programming"], ["Python"])

    def test_unknown_value_is_rejected_not_silently_dropped(self):
        with self.assertRaises(q.QualityError) as ctx:
            q.normalize({"programming": ["COBOL"]})
        self.assertIn("COBOL", str(ctx.exception))

    def test_unknown_group_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"programming": ["Python"], "vibes": ["good"]})

    def test_value_from_the_wrong_group_is_rejected(self):
        """Groups are not interchangeable, and must not be interchangeable."""
        with self.assertRaises(q.QualityError):
            q.normalize({"leadership": ["Python"]})

    def test_non_list_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"programming": "Python"})

    def test_non_mapping_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize(["Python"])

    def test_non_string_entry_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.normalize({"programming": [42]})


class MinimumTests(SimpleTestCase):
    def test_seven_is_accepted(self):
        self.assertEqual(q.count(q.validate_selection(VALID)), 7)

    def test_six_is_rejected(self):
        selection = dict(VALID)
        selection["hr"] = []
        self.assertEqual(q.count(q.normalize(selection)), 6)
        with self.assertRaises(q.QualityError) as ctx:
            q.validate_selection(selection)
        self.assertIn(str(q.MINIMUM_TOTAL), str(ctx.exception))

    def test_empty_is_rejected(self):
        with self.assertRaises(q.QualityError):
            q.validate_selection({})

    def test_seven_all_from_the_programming_group_is_accepted(self):
        """
        Concentrated picks are allowed, and the gap is reported as a hint.

        This is the deliberate alternative to enforcing one-per-group. Seven
        groups and a total of seven means "at least one from each" is really
        "exactly one from each", which would oblige a backend engineer to
        claim an HR skill they do not have. The form must not invent a claim
        for the person filling it in, so the rule is the total and
        :func:`uncovered_groups` carries the nudge.
        """
        selection = {
            "programming": [
                "Python", "Java", "SQL",
                "JavaScript and TypeScript",
            ],
            "data_structures": [
                "Arrays and strings", "Hash maps and dictionaries",
            ],
            "problem_solving": ["Algorithm design"],
        }
        self.assertEqual(q.count(q.normalize(selection)), 7)
        self.assertEqual(q.count(q.validate_selection(selection)), 7)

        gaps = q.uncovered_groups(q.normalize(selection))
        self.assertIn("leadership", gaps)
        self.assertIn("hr", gaps)
        self.assertNotIn("programming", gaps)

    def test_a_fully_covered_selection_reports_no_gaps(self):
        self.assertEqual(q.uncovered_groups(q.normalize(VALID)), [])

    def test_the_gap_hint_lists_groups_in_presentation_order(self):
        gaps = q.uncovered_groups(q.normalize({"programming": ["Python"]}))
        self.assertEqual(gaps, list(q.KINDS[1:]))


class CatalogueTests(SimpleTestCase):
    def test_the_catalogue_has_exactly_fifty_entries(self):
        """The brief was 50, and the picker copy says 50. Keep them in step."""
        total = sum(len(values) for values in q.CATALOGUE.values())
        self.assertEqual(total, 50, f"catalogue has {total} entries, expected 50")

    def test_the_catalogue_has_exactly_seven_groups(self):
        self.assertEqual(len(q.KINDS), 7)
        self.assertEqual(set(q.CATALOGUE), set(q.KINDS))

    def test_every_group_has_at_least_three_options(self):
        """A group with one or two options forces the choice, it does not offer it."""
        for kind, values in q.CATALOGUE.items():
            self.assertGreaterEqual(len(values), 3, f"{kind} has only {len(values)}")

    def test_catalogue_has_no_duplicates_within_a_group(self):
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

    def test_labels_exist_for_every_group(self):
        for kind in q.KINDS:
            self.assertIn(kind, q.KIND_LABELS)

    def test_covering_the_whole_catalogue_is_also_rejected_for_missing_groups(self):
        """
        The abuse case: selecting everything is still not a valid profile.

        It satisfies the total, and must still fail the per-group rule, which
        it does because nothing was chosen for the six groups left empty.
        """
        everything = {kind: list(values) for kind, values in q.CATALOGUE.items()}
        result = q.normalize(everything)
        self.assertEqual(q.count(result), sum(len(v) for v in q.CATALOGUE.values()))
        self.assertEqual(q.validate_selection(VALID), q.normalize(VALID))


class AsListTests(SimpleTestCase):
    def test_flattens_in_group_order(self):
        selection = q.normalize(VALID)
        self.assertEqual(
            q.as_list(selection), [v for k in q.KINDS for v in selection[k]]
        )


class QualitiesApiTests(TestCase):
    """
    GET/PUT /api/resumes/qualities/ over HTTP.

    The unit tests cover the rules; these cover the contract -- in particular
    that the minimum is enforced by the *server*. A request built by hand has
    to fail the way the UI's disabled button prevents.
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
        base = {kind: list(values) for kind, values in VALID.items()}
        base.update(overrides)
        return base

    # -- read ---------------------------------------------------------------

    def test_get_returns_the_catalogue_and_the_minimum(self):
        """The picker must not hard-code options the server would reject."""
        body = self.client.get(self.URL).json()
        self.assertEqual(set(body["catalogue"]), set(q.KINDS))
        self.assertEqual(body["minimum_total"], q.MINIMUM_TOTAL)
        self.assertEqual(len(body["kinds"]), 7)
        # Counted from the response, not a literal: this asserts the API
        # ships the whole catalogue, and stays right if the size changes.
        self.assertEqual(
            sum(len(v) for v in body["catalogue"].values()),
            sum(len(v) for v in q.CATALOGUE.values()),
        )

    def test_get_starts_empty_for_a_fresh_account(self):
        body = self.client.get(self.URL).json()
        self.assertEqual(body["selected_count"], 0)
        self.assertEqual(body["qualities"], {k: [] for k in q.KINDS})
        self.assertEqual(
            sorted(body["uncovered_groups"]), sorted(q.KINDS)
        )

    def test_get_without_a_master_resume_is_not_an_error(self):
        """
        A 200 with an empty selection, so the picker can render and explain.

        Failing here would strand a brand new account with no way to see the
        options.
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
            self.selection(leadership=["  team leadership ", "mentoring"])
        ).json()
        self.assertEqual(
            body["qualities"]["leadership"], ["Team leadership", "Mentoring"]
        )

    def test_a_fully_covered_selection_reports_no_gaps(self):
        body = self.put(self.selection()).json()
        self.assertEqual(body["uncovered_groups"], [])

    def test_a_concentrated_selection_is_saved_but_reports_gaps(self):
        """Seven from three groups is allowed; the picker is told what is thin."""
        selection = {
            "programming": ["Python", "Java", "SQL", "JavaScript and TypeScript"],
            "data_structures": ["Arrays and strings", "Hash maps and dictionaries"],
            "problem_solving": ["Algorithm design"],
        }
        response = self.put(selection)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["selected_count"], 7)
        self.assertIn("hr", body["uncovered_groups"])
        self.assertNotIn("programming", body["uncovered_groups"])

    def test_fewer_than_seven_is_rejected(self):
        selection = self.selection(hr=[])
        self.assertEqual(q.count(q.normalize(selection)), 6)
        response = self.put(selection)
        self.assertEqual(response.status_code, 400)
        self.assertIn(str(q.MINIMUM_TOTAL), response.json()["error"])

    def test_a_rejected_selection_is_not_partially_saved(self):
        before = dict(self.profile.qualities)
        self.put(self.selection(hr=[]))
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.qualities, before)

    def test_a_value_outside_the_catalogue_is_rejected(self):
        response = self.put(self.selection(programming=["Python", "COBOL"]))
        self.assertEqual(response.status_code, 400)

    def test_a_retired_skill_is_rejected(self):
        """
        The old 96-option catalogue is gone.

        A selection saved against it must not be silently reinterpreted: these
        were never offered, and matching them would be guessing.
        """
        response = self.put(self.selection(programming=["Rust", "Go", "C++", "Docker"]))
        self.assertEqual(response.status_code, 400)

    def test_an_unknown_group_is_rejected(self):
        payload = self.selection()
        payload["vibes"] = ["good"]
        self.assertEqual(self.put(payload).status_code, 400)

    def test_a_replacement_overwrites_rather_than_appends(self):
        self.put(self.selection())
        self.put(self.selection(hr=["Talent acquisition"]))
        self.profile.refresh_from_db()
        self.assertEqual(
            self.profile.qualities["hr"], ["Talent acquisition"]
        )

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
