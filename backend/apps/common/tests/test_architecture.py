"""
Architectural boundaries, enforced by tests rather than by documentation.

A boundary that only exists in a diagram is a boundary until the first person in
a hurry needs a shortcut. Each test here asserts one of the rules stated in
``docs/ARCHITECTURE.md`` and ``docs/adr/``, and each is written so that the
tempting shortcut fails loudly rather than quietly.

Two techniques are used, deliberately:

* **Static.** ``ast`` walks a module's real import statements and attribute
  accesses, so a comment that *mentions* ``MatchEngine`` is not a violation but
  a call to it is. Text matching was rejected: several docstrings in
  ``apps/ai`` legitimately name the match engine while explaining why the AI
  layer must not own it.
* **Behavioural.** Where a rule is about a result rather than a structure, a
  request is made and the outcome is asserted -- the AI layer running end to end
  and leaving the deterministic score untouched is the strongest form of the
  claim.

Coverage that already lives elsewhere and is not repeated here: cross-account
resume and job access (``apps.users.tests.test_isolation``), document downloads
(``apps.resumes.tests.test_download_api``), credential handling
(``apps.users.tests.test_ai_credentials``), and the shape of a 429
(``apps.common.tests.test_rate_limiting``).
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase, override_settings

from apps.ai.models import AIRun
from apps.common.models import ActivityEvent

#: ``backend/apps/common/tests/test_architecture.py`` -> ``backend``
BACKEND = Path(__file__).resolve().parents[3]

User = get_user_model()


def source_files(*relative_dirs: str) -> list[Path]:
    """
    Product modules under the given directories.

    Generated code (migrations) and test packages are skipped. Migrations are
    machine-written, and the AI tests deliberately construct canned match
    payloads -- a fixture that builds ``{"decision": "TAILOR"}`` is evidence
    that the *prompt* receives an existing analysis, not that the AI layer
    decides one.
    """
    found = []
    for relative in relative_dirs:
        for path in sorted((BACKEND / relative).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            if "migrations" in path.parts or "tests" in path.parts:
                continue
            found.append(path)
    return found


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imported_modules(path: Path) -> set[str]:
    """
    Every module named by an import, at any depth.

    "At any depth" matters: a lazy import inside a function is still a
    dependency, and a boundary that is only respected at module level is not
    respected.
    """
    names = set()
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def attribute_writes(path: Path, names: set[str]) -> list[str]:
    """
    Attribute names that are *read or written as code*, e.g. ``job.match_score``.

    Deliberately not a text search, so a docstring explaining that the AI layer
    must not touch the score does not read as a violation.
    """
    hits = []
    for node in ast.walk(parse(path)):
        if isinstance(node, ast.Attribute) and node.attr in names:
            hits.append(node.attr)
        elif isinstance(node, ast.keyword) and node.arg in names:
            hits.append(node.arg)
    return hits


class StaticBoundaryTests(SimpleTestCase):
    """The dependency direction, read off the import graph."""

    def test_the_match_engine_does_not_import_the_ai_layer(self):
        """
        The deterministic score cannot depend on the generative layer. If it
        ever did, "your score is inspects" would stop being true and the score
        would become model-dependent.
        """
        modules = imported_modules(BACKEND / "apps" / "jobs" / "services" / "match_engine.py")

        for module in modules:
            with self.subTest(module=module):
                self.assertFalse(module.startswith("apps.ai"))

    def test_the_ai_layer_never_imports_the_match_engine(self):
        for path in source_files("apps/ai"):
            modules = imported_modules(path)

            for module in modules:
                with self.subTest(file=path.name, module=module):
                    self.assertNotIn("match_engine", module)

    def test_ai_providers_do_not_import_a_business_app(self):
        """
        A provider is a transport for prompts. Reaching into ``apps.jobs`` or
        ``apps.resumes`` would make swapping a provider a business change, which
        is the whole thing the abstraction exists to prevent.
        """
        for path in source_files("apps/ai/providers"):
            for module in imported_modules(path):
                with self.subTest(file=path.name, module=module):
                    self.assertFalse(
                        module.startswith(("apps.jobs", "apps.resumes", "apps.applications"))
                    )

    def test_no_ai_module_writes_a_score_or_a_decision(self):
        for path in source_files("apps/ai"):
            hits = attribute_writes(path, {"match_score", "match_result", "decision"})

            with self.subTest(file=path.name):
                self.assertEqual(hits, [])


# ---------------------------------------------------------------------------
# Explainability contract
# ---------------------------------------------------------------------------

#: A resume/JD pair small enough to reason about by hand. Every component of
#: the score is exercised: skills overlap, experience is short of the stated
#: requirement, and the posting names an education expectation.
RESUME_PROFILE = {
    "skills": ["python", "django", "postgresql"],
    "experience": {"years": 2},
    "education": "BSc Computer Science",
    "projects": "",
    "certifications": "",
    "qualities": {},
}

JOB_DESCRIPTION = """
Senior Backend Engineer

We need 5 years of experience building services with Python, Django and
Docker. PostgreSQL is required.

Requirements: REST APIs, CI/CD pipelines, unit testing.

Bachelor's degree in Computer Science or a related field required.
"""


class ExplainabilityTests(SimpleTestCase):
    """
    A score must be checkable from its own response.

    This is the "no black box" rule: the number, the weights and the component
    evidence come from the same deterministic pass, so a user (or this test) can
    recompute the score from what the API returned.
    """

    def setUp(self):
        from apps.jobs.services.jd_profile import JDProfile
        from apps.jobs.services.match_engine import MatchEngine

        self.MatchEngine = MatchEngine
        self.jd_profile = JDProfile.build(JOB_DESCRIPTION)
        self.result = MatchEngine.calculate(RESUME_PROFILE, self.jd_profile)

    def test_each_component_carries_a_score_and_an_explanation(self):
        """
        Evidence, not just a number. The keys differ per component -- skills
        reports matched/missing names, experience and education report a note --
        so the assertion is that each one carries *something* traceable, in the
        form its data actually supports.
        """
        evidence_keys = {"note", "matched", "missing", "unmatched", "partially_matched"}

        for component in ("skills", "experience", "requirements", "education"):
            with self.subTest(component=component):
                result = self.result[component]

                self.assertIn(component, self.result)
                self.assertIn("score", result)
                self.assertTrue(
                    evidence_keys & set(result),
                    "component %r reports no evidence: %s" % (component, result),
                )

    def test_the_reported_score_is_the_weighted_sum_of_the_components(self):
        engine = self.MatchEngine
        weights = {
            "skills": engine.SKILL_WEIGHT,
            "experience": engine.EXPERIENCE_WEIGHT,
            "requirements": engine.REQUIREMENT_WEIGHT,
            "education": engine.EDUCATION_WEIGHT,
        }

        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)

        recomputed = round(
            sum(self.result[name]["score"] * weight for name, weight in weights.items()),
            2,
        )

        self.assertEqual(recomputed, self.result["score"])

    def test_the_weights_are_actually_applied(self):
        """
        A guard against the weights being decorative. Zeroing the skill
        component must move the score by exactly its weighted contribution,
        which a hardcoded or averaged score would not do.
        """
        engine = self.MatchEngine

        stripped = dict(RESUME_PROFILE)
        stripped["skills"] = []

        without_skills = engine.calculate(stripped, self.jd_profile)

        expected = round(
            self.result["score"]
            - self.result["skills"]["score"] * engine.SKILL_WEIGHT
            + without_skills["skills"]["score"] * engine.SKILL_WEIGHT,
            2,
        )

        self.assertEqual(without_skills["score"], expected)

    def test_the_same_input_always_gives_the_same_score(self):
        """Deterministic means reproducible, which is what makes this testable."""
        again = self.MatchEngine.calculate(RESUME_PROFILE, self.jd_profile)

        self.assertEqual(again["score"], self.result["score"])
        self.assertEqual(again["decision"], self.result["decision"])

    def test_the_decision_is_a_pure_function_of_the_score(self):
        for score, decision in (
            (96.0, "USE_MASTER"),
            (80.0, "TAILOR"),
            (60.0, "REVIEW"),
            (20.0, "SKIP"),
        ):
            with self.subTest(score=score):
                self.assertEqual(self.MatchEngine._decision(score), decision)


# ---------------------------------------------------------------------------
# Behavioural boundaries
# ---------------------------------------------------------------------------


class BoundaryTestCase(TestCase):
    """One account with a stored, scored job and a profiled master resume."""

    def setUp(self):
        from apps.ai import factory
        from apps.ai.providers.fake import FakeAIProvider
        from apps.ai.tests.fixtures import SOURCE_PROFILE, valid_payload
        from apps.jobs.models import Job
        from apps.jobs.services.jd_profile import JDProfile
        from apps.jobs.services.match_engine import MatchEngine
        from apps.resumes.models import Resume, ResumeProfile
        from apps.resumes.services import tailoring_service

        self.factory = factory
        self.FakeAIProvider = FakeAIProvider
        self.valid_payload = valid_payload
        self.services = tailoring_service

        self.user = User.objects.create_user(
            username="arch@example.test",
            email="arch@example.test",
            password="pw-arch-1234",
        )
        self.master = Resume.objects.create(
            user=self.user, name="Master", resume_type="MASTER", is_master=True
        )
        # The shared AI fixture, so the canned tailoring payload in
        # ``valid_payload()`` is a statement about *this* resume. A profile
        # invented here would be rejected by the factual validator for reasons
        # that have nothing to do with the boundary under test.
        self.profile = ResumeProfile.objects.create(
            resume=self.master,
            skills=SOURCE_PROFILE["skills"],
            experience=SOURCE_PROFILE["experience"],
            education=SOURCE_PROFILE["education"],
            projects=SOURCE_PROFILE["projects"],
            certifications=SOURCE_PROFILE["certifications"],
        )

        # The score is *computed*, not typed in. A hardcoded number would make
        # "the stored score is reproducible" unfalsifiable, and would let the
        # AI layer change the score without this file noticing.
        analysis = MatchEngine.calculate(
            {
                "skills": self.profile.skills,
                "experience": self.profile.experience,
                "education": self.profile.education,
                "projects": self.profile.projects,
                "certifications": self.profile.certifications,
                "qualities": self.profile.qualities,
            },
            JDProfile.build(JOB_DESCRIPTION),
        )

        self.job = Job.objects.create(
            user=self.user,
            url="https://boards.greenhouse.io/acme/jobs/77",
            company="Acme",
            title="Senior Backend Engineer",
            description=JOB_DESCRIPTION,
            match_score=analysis["score"],
            match_result=analysis,
            decision=analysis["decision"],
        )

    def use_provider(self, payload=None):
        provider = self.FakeAIProvider(
            json.dumps(payload if payload is not None else self.valid_payload())
        )
        self.factory.register("test_fake", lambda: provider)
        self.addCleanup(self.factory._registry.pop, "test_fake", None)
        return provider

    def use_failing_provider(self, provider):
        self.factory.register("test_fake", lambda: provider)
        self.addCleanup(self.factory._registry.pop, "test_fake", None)
        return provider


@override_settings(AI_PROVIDER="test_fake")
class RuntimeBoundaryTests(BoundaryTestCase):
    """What the AI layer can and cannot change when it actually runs."""

    def test_a_generating_run_cannot_move_the_match_score(self):
        """
        The strongest form of the boundary: run the whole tailoring flow and
        check the deterministic result is untouched, including the analysis the
        prompt was handed as context.
        """
        self.use_provider()
        before = (self.job.match_score, dict(self.job.match_result))

        self.services.generate_tailoring(self.user, self.job.id)

        self.job.refresh_from_db()
        self.assertEqual(self.job.match_score, before[0])
        self.assertEqual(self.job.match_result, before[1])

    def test_the_stored_score_is_reproducible_from_the_stored_data(self):
        """
        The explanation the user is shown must come from the same deterministic
        data that produced the number, so recomputing it from the stored resume
        profile and the stored description has to agree exactly.
        """
        from apps.jobs.services.jd_profile import JDProfile
        from apps.jobs.services.match_engine import MatchEngine

        recomputed = MatchEngine.calculate(
            {
                "skills": self.profile.skills,
                "experience": self.profile.experience,
                "education": self.profile.education,
                "projects": self.profile.projects,
                "certifications": self.profile.certifications,
                "qualities": self.profile.qualities,
            },
            JDProfile.build(self.job.description),
        )

        self.assertEqual(recomputed["score"], self.job.match_score)

    def test_a_failed_run_leaves_the_resume_and_the_master_untouched(self):
        from apps.ai.exceptions import AIProviderUnavailableError
        from apps.resumes.models import Resume

        before = (
            list(self.profile.skills),
            dict(self.profile.experience),
            self.profile.education,
            self.profile.projects,
        )

        self.use_failing_provider(self.FakeAIProvider.unavailable())

        with self.assertRaises(AIProviderUnavailableError):
            self.services.generate_tailoring(self.user, self.job.id)

        self.master.refresh_from_db()
        self.profile.refresh_from_db()

        self.assertTrue(self.master.is_master)
        self.assertEqual(self.master.resume_type, "MASTER")
        self.assertEqual(
            (
                list(self.profile.skills),
                dict(self.profile.experience),
                self.profile.education,
                self.profile.projects,
            ),
            before,
        )
        self.assertFalse(
            Resume.objects.filter(user=self.user, resume_type="TAILORED").exists()
        )

    def test_no_run_is_recorded_as_succeeded_without_a_result(self):
        """
        A rejected result is a *failed* run, not a successful one that happened
        to produce nothing. The distinction is what keeps the audit usable:
        "SUCCEEDED and there is no artifact" would be an unresolvable state.
        """
        from apps.ai.exceptions import AITailoringValidationError

        payload = self.valid_payload()
        payload["experience"][0]["tailored_bullets"] = ["Shipped 400% growth in 2 weeks."]
        self.use_provider(payload)

        with self.assertRaises(AITailoringValidationError):
            self.services.generate_tailoring(self.user, self.job.id)

        self.assertFalse(AIRun.objects.filter(status=AIRun.SUCCEEDED).exists())
        self.assertTrue(AIRun.objects.filter(status=AIRun.FAILED).exists())


class OwnershipBoundaryTests(BoundaryTestCase):
    """
    The tenant boundary, asserted for the resources this phase added.

    Cross-account resume and job access is covered in
    ``apps.users.tests.test_isolation``; what is new here is that the audit
    tables obey the same rule and that the service layer -- not only the view --
    refuses a foreign id.
    """

    def test_every_new_model_carries_a_non_nullable_owner(self):
        """There is no 'ownerless' state, so no query can leak by omission."""
        for model in (AIRun, ActivityEvent):
            with self.subTest(model=model.__name__):
                field = model._meta.get_field("user")
                self.assertFalse(field.null)
                self.assertTrue(field.remote_field.related_name)

    def test_audit_rows_are_invisible_to_another_account(self):
        other = User.objects.create_user(
            username="other-arch@example.test",
            email="other-arch@example.test",
            password="pw-arch-1234",
        )

        ActivityEvent.record(self.user, ActivityEvent.RESUME_UPLOADED)
        ActivityEvent.record(other, ActivityEvent.RESUME_UPLOADED)

        mine = ActivityEvent.objects.filter(user=self.user)

        self.assertEqual(mine.count(), 1)
        self.assertNotIn(other.pk, {row.user_id for row in mine})

    def test_the_service_refuses_another_accounts_job(self):
        """
        Enforced in the query, not after loading the row: the same 404 whether
        the id is missing or someone else's, which is what stops the API being
        used to confirm that an id exists.
        """
        from apps.resumes.models import Resume
        from apps.resumes.services.tailoring_service import JobMissing

        other = User.objects.create_user(
            username="stranger@example.test",
            email="stranger@example.test",
            password="pw-arch-1234",
        )
        # A master resume of their own, so the *only* thing that can refuse
        # this request is the job not belonging to them.
        Resume.objects.create(
            user=other, name="Theirs", resume_type="MASTER", is_master=True
        )

        with self.assertRaises(JobMissing):
            self.services.generate_tailoring(other, self.job.id)

        self.assertEqual(AIRun.objects.filter(user=other).count(), 0)


#: A credential-shaped string that must never appear in a response body. Short on
#: purpose: the committed tree must not contain anything that reads as a real key,
#: or `.github/scripts/scan_source_secrets.py` fails the build -- correctly.
PROBE_KEY = "AIza1234-probe"


@override_settings(AI_PROVIDER="test_fake")
class ApiContractTests(BoundaryTestCase):
    """
    One shape for a refusal, whatever the feature.

    A client that has to special-case each endpoint's error body is a client
    that will silently miss the next one, so every user-facing refusal from this
    flow carries ``error`` (for a person) and ``code`` (for the client).

    ``AI_PROVIDER`` is overridden for the whole class, and that is not
    decoration: the service resolves the provider from settings (per account),
    so registering a test double under a name nothing selects would send these
    requests to whatever the developer's machine is running.
    """

    def post_json(self, url, payload):
        return self.client.post(
            url, data=json.dumps(payload), content_type="application/json"
        )

    def assert_refusal(self, response, status_code, code):
        self.assertEqual(response.status_code, status_code)

        body = response.json()
        self.assertEqual(body.get("code"), code)
        self.assertIsInstance(body.get("error"), str)
        self.assertTrue(body["error"], "a refusal must explain itself to a person")

        # No internals: no exception type, no message from the provider, no
        # stack. Those are logged server-side and never returned.
        self.assertNotIn("traceback", body)
        self.assertNotIn("detail", body)
        return body

    def test_a_foreign_job_id_is_a_404_not_a_403(self):
        """A 403 would confirm the id exists, which is the leak to avoid."""
        self.client.force_login(self.user)

        self.assert_refusal(
            self.post_json("/api/resumes/tailor/", {"job_id": 999_999}),
            404,
            "job_missing",
        )

    def test_an_account_without_a_master_resume_gets_a_named_refusal(self):
        from django.contrib.auth import get_user_model

        stranger = get_user_model().objects.create_user(
            username="nomaster@example.test",
            email="nomaster@example.test",
            password="pw-arch-1234",
        )
        self.client.force_login(stranger)

        self.assert_refusal(
            self.post_json("/api/resumes/tailor/", {"job_id": self.job.id}),
            404,
            "resume_missing",
        )

    def test_a_job_with_nothing_to_tailor_against_is_a_400(self):
        self.job.description = ""
        self.job.save(update_fields=["description"])
        self.client.force_login(self.user)

        self.assert_refusal(
            self.post_json("/api/resumes/tailor/", {"job_id": self.job.id}),
            400,
            "job_description_missing",
        )

    def test_a_save_without_a_result_is_a_400(self):
        self.client.force_login(self.user)

        self.assert_refusal(
            self.post_json("/api/resumes/tailor/save/", {"job_id": self.job.id}),
            400,
            "result_missing",
        )

    def test_a_fabricated_result_is_a_422_carrying_its_violations(self):
        payload = self.valid_payload()
        payload["experience"][0]["tailored_bullets"] = ["Grew revenue 340% in 3 months."]
        self.use_provider(payload)
        self.client.force_login(self.user)

        body = self.assert_refusal(
            self.post_json("/api/resumes/tailor/", {"job_id": self.job.id}),
            422,
            "ai_validation_failed",
        )

        self.assertTrue(body["violations"])
        self.assertIsInstance(body["violations"][0]["code"], str)


@override_settings(AI_PROVIDER="test_fake")
class SecretHygieneTests(BoundaryTestCase):
    """
    A credential must be unreachable from anything a browser can read.

    The provider override matters as much here as in any functional test: this
    class generates a real tailoring, and without it the request would go to
    whichever provider the deployment names.
    """

    def test_no_audit_model_field_is_named_like_a_secret(self):
        """
        A structural guard rather than a behavioural one: the way a key reaches
        a database column or an API response is somebody adding a field for it.

        ``prompt_version`` is the one deliberate exemption. The redactor treats a
        field named ``prompt`` as prompt *content* -- correctly, since that is
        what a field with that name holds in a log call -- while this one stores
        a version token like ``tailoring-1``, which is metadata about the prompt
        rather than the prompt.
        """
        from apps.common.observability import is_sensitive_name

        exemptions = {"prompt_version"}

        for model in (AIRun, ActivityEvent):
            for field in model._meta.get_fields():
                if not hasattr(field, "attname") or field.name in exemptions:
                    continue
                with self.subTest(model=model.__name__, field=field.name):
                    self.assertFalse(is_sensitive_name(field.name))

    def test_the_provider_status_endpoint_returns_no_key_material(self):
        from apps.users.models import ProviderCredential

        credential = ProviderCredential.objects.create(user=self.user, provider="gemini")
        credential.set_key(PROBE_KEY)
        credential.save()

        self.client.force_login(self.user)
        response = self.client.get("/api/resumes/tailor/status/")

        self.assertEqual(response.status_code, 200)
        self.assertNotIn(PROBE_KEY, response.content.decode())

    def test_a_stored_key_never_reaches_an_audit_row(self):
        from apps.users.models import ProviderCredential

        credential = ProviderCredential.objects.create(user=self.user, provider="gemini")
        credential.set_key(PROBE_KEY)
        credential.save()

        self.use_provider()
        self.services.generate_tailoring(self.user, self.job.id)

        row = AIRun.objects.get(user=self.user)
        dumped = json.dumps({**row.__dict__, **row.public_dict()}, default=str)

        self.assertNotIn(PROBE_KEY, dumped)
        self.assertNotIn("encrypted", dumped)
