#!/usr/bin/env python
"""
Build the Postman collection + environment used by the API test harness.

The collection is generated rather than hand-written so the fiddly parts stay
correct and reviewable:

* the Django session cookie and the ``csrftoken`` cookie are captured from
  responses and echoed into later requests
* the CSRF token is read out of the cookie jar and sent as ``X-CSRFToken``,
  which is what DRF's SessionAuthentication requires for unsafe methods
* every request carries explicit ``pm.test`` assertions, so Newman reports
  per-assertion results rather than just an HTTP status

Run:  python scripts/build_postman_collection.py
"""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "postman"

CSRF_HEADER = {"key": "X-CSRFToken", "value": "{{csrf}}", "type": "text"}


def pm(name: str, *body: str) -> list[dict]:
    """Build a ``pm.test`` block.

    ``name`` is the human-readable assertion label shown in the HTML and JUnit
    reports; the remaining lines are the body, indented inside the callback.

    Wrapping matters more than it looks: without the ``pm.test`` wrapper Newman
    records **zero** assertions for the request, so a suite can execute every
    request, exit 0, and report nothing at all. Assertions that throw inside the
    callback are what turn a red request into a recorded failure.
    """
    label = name.replace("\\", "\\\\").replace("'", "\\'")
    lines = [f"pm.test('{label}', function () {{"]
    lines += [f"    {line}" for line in body]
    lines.append("});")
    return [
        {
            "listen": "test",
            "script": {"type": "text/javascript", "exec": lines},
        }
    ]


def merge_tests(*blocks: list[dict]) -> list[dict]:
    """Combine several ``pm`` blocks into a **single** test event.

    Postman's schema allows one event per (item, listen) pair. When an item
    carries two separate ``"listen": "test"`` events Newman executes only one of
    them, so a CSRF refresh attached as its own event silently never ran and
    every later unsafe request came back 403. Concatenating the exec lines into
    a single event is the form that reliably executes, in order.
    """
    lines: list[str] = []
    for block in blocks:
        for event in block:
            lines.extend(event["script"]["exec"])
    return [
        {
            "listen": "test",
            "script": {"type": "text/javascript", "exec": lines},
        }
    ]


def request(
    name: str,
    method: str,
    path: str,
    *,
    body: dict | None = None,
    tests: list[dict] | None = None,
) -> dict:
    """Build one collection item. ``path`` is appended to ``{{baseUrl}}``.

    Note the trailing-slash handling. Every route in this project is declared
    with a trailing slash (``path("register/", ...)``), and Postman builds the
    request URL from the structured ``host``/``path`` arrays -- not from
    ``raw``. A plain ``strip("/")`` therefore silently drops the final slash,
    and Django's APPEND_SLASH middleware answers 301. For POST/PATCH/DELETE
    that turns the retry into a GET, so ``/api/auth/register/`` came back as
    ``405 Method Not Allowed`` and the session was never created. A trailing
    slash is represented as a final empty path segment.
    """
    headers = [{"key": "Accept", "value": "application/json"}]

    # Every unsafe method needs the CSRF header, not just authenticated ones:
    # Django validates the token before DRF validates permissions.
    if method in {"POST", "PATCH", "PUT", "DELETE"}:
        headers.append(CSRF_HEADER)

    raw_path = path.split("?")[0]
    segments = raw_path.strip("/").split("/")
    if raw_path.endswith("/"):
        segments.append("")

    item: dict = {
        "name": name,
        "event": tests or [],
        "request": {
            "method": method,
            "header": headers,
            "url": {
                "raw": "{{baseUrl}}" + path,
                "host": ["{{baseUrl}}"],
                "path": segments,
                **({"query": _query(path)} if "?" in path else {}),
            },
            "description": name,
        },
    }

    if body is not None:
        item["request"]["header"].append(
            {"key": "Content-Type", "value": "application/json"}
        )
        item["request"]["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }

    return item


def _query(path: str) -> list[dict]:
    """Split ``?a=1&b=2`` into Postman's query array."""
    out = []
    for pair in path.split("?", 1)[1].split("&"):
        key, _, value = pair.partition("=")
        out.append({"key": key, "value": value})
    return out


# Passwords differ per account: Django's UserAttributeSimilarityValidator is
# relaxed in settings_test, but keeping them distinct avoids surprising coupling
# if that is ever restored.
PASSWORD = "Str0ng-Passw0rd!42"


# ---------------------------------------------------------------------------
# Reusable script fragments
# ---------------------------------------------------------------------------

READ_CSRF_JS = [
    "function readCsrfToken() {",
    "    // Preferred: the cookie jar. Works in the Postman desktop app.",
    "    try {",
    "        var jar = pm.cookies.get('csrftoken');",
    "        if (jar && jar.value) { return jar.value; }",
    "    } catch (e) { /* jar API unusable under postman-runtime 5 */ }",
    "",
    "    // Fallback: scan every Set-Cookie response header.",
    "    //",
    "    // pm.response.headers.get('Set-Cookie') is unreliable here in two ways.",
    "    // postman-runtime 5 removed pm.cookies.list() and makes",
    "    // pm.cookies.get() return undefined, so the jar cannot be read at all.",
    "    // And .get() on a repeated header returns only ONE of them: a response",
    "    // that both signs a user in and rotates the CSRF token sends two",
    "    // Set-Cookie headers, and .get() hands back sessionid while silently",
    "    // dropping the csrftoken -- so the token appeared to vanish after login.",
    "    // headers.all() returns every occurrence, so scan them all.",
    "    var headers = pm.response.headers.all();",
    "    for (var i = 0; i < headers.length; i++) {",
    "        var h = headers[i];",
    "        if (String(h.key).toLowerCase() !== 'set-cookie') { continue; }",
    "        var m = /(?:^|[,;\\s])csrftoken=([^;,]+)/.exec(String(h.value));",
    "        if (m) { return m[1]; }",
    "    }",
    "    return null;",
    "}",
]


# The seed address is unique per run so the collection can be re-run against an
# existing database without failing on "an account with this email already
# exists". The same value is written into {{seedEmail}} by the prerequest hook
# below, and the register body references that variable.
CAPTURE_USER_ID = pm(
    "register returns the new account",
    "pm.response.to.have.status(201);",
    "const body = pm.response.json();",
    "pm.expect(body.user).to.be.an('object');",
    "pm.expect(body.user.id).to.be.a('number');",
    "pm.expect(body.user.email).to.be.a('string');",
    "pm.collectionVariables.set('userId', body.user.id);",
)

# Capture the CSRF token and publish it as a collection variable so the unsafe
# requests that follow can send it back in X-CSRFToken. The helper is inlined
# here as well as in REFRESH_CSRF because merge_tests concatenates the bodies
# into one script, and a function declared in one pm.test callback is not in
# scope in the next one.
CAPTURE_CSRF = pm(
    "csrf token is issued",
    *READ_CSRF_JS,
    "const token = readCsrfToken();",
    "pm.expect(token, 'no csrftoken found in the jar or the Set-Cookie header').to.be.a('string');",
    "pm.expect(token.length).to.be.above(0);",
    "if (token) { pm.collectionVariables.set('csrf', token); }",
)

# Django calls rotate_token() on every login, issuing a *new* csrftoken. A token
# captured before login is then stale, and every later POST/PATCH is rejected
# with 403 before the view is ever reached. This re-reads the token after any
# event that can rotate it, without asserting anything.
REFRESH_CSRF = [
    {
        "listen": "test",
        "script": {
            "type": "text/javascript",
            "exec": READ_CSRF_JS
            + [
                "const token = readCsrfToken();",
                "if (token) { pm.collectionVariables.set('csrf', token); }",
            ],
        },
    }
]


# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------

register = request(
    "01 Register a new account",
    "POST",
    "/api/auth/register/",
    body={"email": "{{seedEmail}}", "password": PASSWORD, "full_name": "Api Test User"},
    # register() also signs the new user in, so the token rotates here too.
    tests=merge_tests(REFRESH_CSRF, CAPTURE_USER_ID),
)

# RegisterView signs the new account straight in ("Log the new account straight
# in so onboarding can continue"), so by the time this runs there IS already a
# session. Asserting `authenticated === false` here would be wrong; the point of
# the request is to confirm the cookie works and to capture the CSRF token.
me_anonymous = request(
    "02 /me accepts the session register just created",
    "GET",
    "/api/auth/me/",
    tests=merge_tests(
        CAPTURE_CSRF,
        pm(
            "/me reports the freshly registered account",
            "pm.response.to.have.status(200);",
            "const body = pm.response.json();",
            "pm.expect(body.authenticated).to.eql(true);",
            "pm.expect(body.user.email).to.eql(pm.collectionVariables.get('seedEmail'));",
        ),
    ),
)

login = request(
    "03 Log in",
    "POST",
    "/api/auth/login/",
    body={"email": "{{seedEmail}}", "password": PASSWORD},
    # login() rotates the CSRF token, so the one captured in step 02 is stale
    # from here on. Without this refresh every later unsafe request 403s.
    tests=merge_tests(
        REFRESH_CSRF,
        pm(
            "login starts a session",
            "pm.response.to.have.status(200);",
            "const body = pm.response.json();",
            "pm.expect(body.user.email).to.eql(pm.collectionVariables.get('seedEmail'));",
        ),
    ),
)

me_authenticated = request(
    "04 /me reflects the signed-in account",
    "GET",
    "/api/auth/me/",
    tests=pm(
        "/me returns the authenticated user",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.authenticated).to.eql(true);",
        # Collection variables are always strings, so the numeric id from the
        # response has to be coerced before comparing.
        "pm.expect(String(body.user.id)).to.eql(pm.collectionVariables.get('userId'));",
        "pm.expect(body.user.job_count).to.eql(0);",
        "pm.expect(body.user.has_master_resume).to.eql(false);",
    ),
)

me_shape = request(
    "05 User payload matches the serializer contract",
    "GET",
    "/api/auth/me/",
    tests=pm(
        "user payload exposes exactly the documented fields",
        "pm.response.to.have.status(200);",
        "const user = pm.response.json().user;",
        "pm.expect(user).to.have.all.keys('id', 'email', 'first_name', 'last_name', "
        + "'date_joined', 'profile', 'has_master_resume', 'job_count');",
        "pm.expect(user.profile).to.be.an('object');",
    ),
)

# ---------------------------------------------------------------------------
# Onboarding answers
#
# The career-stage rule is the interesting one: "working professional" with
# zero years is a contradiction the server refuses, and years sent alongside a
# student or fresher are zeroed rather than stored. Both are asserted here
# because a hand-written PATCH has to behave exactly like the onboarding form.
# ---------------------------------------------------------------------------

profile_stage_student = request(
    "45 A student is stored with no years",
    "PATCH",
    "/api/auth/profile/",
    body={"career_stage": "student", "years_experience": 4},
    tests=pm(
        "years are zeroed rather than stored for a student",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.career_stage).to.eql('student');",
        "pm.expect(body.years_experience).to.eql(0);",
    ),
)

profile_stage_professional_no_years = request(
    "46 A professional with no years is rejected",
    "PATCH",
    "/api/auth/profile/",
    body={"career_stage": "professional"},
    tests=pm(
        "the contradiction is refused, not silently stored",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.text()).to.include('years_experience');",
    ),
)

profile_stage_professional = request(
    "47 A professional with years is stored",
    "PATCH",
    "/api/auth/profile/",
    body={"career_stage": "professional", "years_experience": 4},
    tests=pm(
        "the answer is kept as sent",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.career_stage).to.eql('professional');",
        "pm.expect(body.years_experience).to.eql(4);",
    ),
)

profile_stage_unknown = request(
    "48 An unknown career stage is rejected",
    "PATCH",
    "/api/auth/profile/",
    body={"career_stage": "wizard"},
    tests=pm(
        "the stage list is closed",
        "pm.response.to.have.status(400);",
    ),
)

profile_ai_setup = request(
    "49 Both AI setups are accepted",
    "PATCH",
    "/api/auth/profile/",
    body={"ai_setup": "gemini"},
    tests=pm(
        "the hosted choice is recorded",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json().ai_setup).to.eql('gemini');",
    ),
)

profile_ai_setup_unknown = request(
    "50 An unknown AI setup is rejected",
    "PATCH",
    "/api/auth/profile/",
    body={"ai_setup": "gpt"},
    tests=pm(
        "only the two documented setups are accepted",
        "pm.response.to.have.status(400);",
    ),
)



profile_read = request(
    "06 Read the workspace profile",
    "GET",
    "/api/auth/profile/",
    tests=pm(
        "profile is readable and auto-created on first access",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body).to.have.all.keys('headline', 'discipline', "
        + "'target_locations', 'career_stage', 'years_experience', "
        + "'ai_setup', 'created_at', 'updated_at');",
    ),
)

# ``discipline`` is a choices field, so only the declared values are valid, and
# ``target_locations`` is a plain CharField holding a comma-separated string --
# not a JSON list. Sending a list or a free-text discipline would be rejected
# with a 400 that says nothing useful about the real contract.
profile_update = request(
    "07 Update the workspace profile",
    "PATCH",
    "/api/auth/profile/",
    body={
        "headline": "Backend engineer, API platform",
        "discipline": "ENGINEER",
        "target_locations": "Remote, Bengaluru",
    },
    tests=pm(
        "profile patch is accepted",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.headline).to.eql('Backend engineer, API platform');",
        "pm.expect(body.discipline).to.eql('ENGINEER');",
    ),
)

profile_persisted = request(
    "08 Profile change reads back",
    "GET",
    "/api/auth/profile/",
    tests=pm(
        "profile persisted what was written",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.target_locations).to.eql('Remote, Bengaluru');",
    ),
)

jobs_empty = request(
    "09 Job list is empty for a new account",
    "GET",
    "/api/jobs/",
    tests=pm(
        "job list returns an empty array, not an error",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json()).to.be.an('array');",
        "pm.expect(pm.response.json()).to.have.lengthOf(0);",
    ),
)

# An unknown sort key silently falls back to -created_at rather than 400. Locking
# that in prevents a future change from turning it into a 500.
jobs_filters = request(
    "10 Job list tolerates filters and an unknown sort key",
    "GET",
    "/api/jobs/?q=engineer&status=completed&company=acme&sort=bogus",
    tests=pm(
        "filtered job list still returns 200",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json()).to.be.an('array');",
    ),
)

resumes_empty = request(
    "11 Resume list is empty for a new account",
    "GET",
    "/api/resumes/",
    tests=pm(
        "resume list returns an empty array",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json()).to.be.an('array');",
        "pm.expect(pm.response.json()).to.have.lengthOf(0);",
    ),
)

master_missing = request(
    "12 No master resume yet",
    "GET",
    "/api/resumes/master/",
    tests=pm(
        "master resume lookup reports none uploaded",
        "pm.response.to.have.status(404);",
    ),
)

job_detail_missing = request(
    "13 Unknown job id is a 404",
    "GET",
    "/api/jobs/999999999/",
    tests=pm(
        "missing job returns 404, not 500",
        "pm.response.to.have.status(404);",
    ),
)

resume_detail_missing = request(
    "14 Unknown resume id is a 404",
    "GET",
    "/api/resumes/999999999/",
    tests=pm(
        "missing resume returns 404, not 500",
        "pm.response.to.have.status(404);",
    ),
)


# ---------------------------------------------------------------------------
# Validation
#
# Every request here is rejected by the serializer or by a precondition, so none
# of them reach the network, the AI provider, or the database. That is what
# makes them safe to run on every push.
# ---------------------------------------------------------------------------

analyze_invalid_url = request(
    "15 Analyze rejects a malformed URL",
    "POST",
    "/api/jobs/analyze/",
    body={"url": "not-a-url"},
    tests=pm(
        "analyze rejects a malformed URL at the serializer",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.json()).to.have.property('url');",
    ),
)

# Documents current behaviour rather than what is arguably ideal.
# AnalyzeJobSerializer.url is a plain URLField, and DRF's URLField accepts any
# scheme with a host -- so "ftp://..." passes validation, reaches
# GreenhouseCollector, and is rejected downstream. The request is refused
# (400) but the error shape is {error, status} rather than a field-level
# {url: [...]} validation error, and the collector was reached first.
#
# Tightening this to HttpUrl (or a scheme allowlist) would reject the request at
# the serializer with a proper field error and avoid the pointless fetch.
analyze_bad_scheme = request(
    "16 Analyze rejects a non-http scheme",
    "POST",
    "/api/jobs/analyze/",
    body={"url": "ftp://example.com/jobs/1"},
    tests=pm(
        "analyze refuses a non-http(s) URL",
        "pm.response.to.have.status(400);",
        "const body = pm.response.json();",
        "pm.expect(body).to.have.property('error');",
    ),
)

match_no_resume = request(
    "17 Match without a master resume is a clean 404",
    "POST",
    "/api/jobs/match/",
    body={
        "url": "https://boards.greenhouse.io/acme/jobs/1",
        "company": "Acme",
        "title": "Backend Engineer",
        "location": "Remote",
        "jd_text": "We are hiring a backend engineer with Python and Django experience.",
    },
    tests=pm(
        "match reports a missing master resume rather than crashing",
        "pm.response.to.have.status(404);",
        "pm.expect(pm.response.json().error).to.eql('No master resume found');",
    ),
)

duplicate_email = request(
    "18 Duplicate registration is rejected",
    "POST",
    "/api/auth/register/",
    body={
        "email": "{{seedEmail}}",
        "password": "Whatever-Passw0rd!1",
        "full_name": "Impostor",
    },
    tests=pm(
        "register refuses an email that already exists",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.json()).to.have.property('email');",
    ),
)

weak_password = request(
    "19 Weak password is rejected",
    "POST",
    "/api/auth/register/",
    body={
        "email": "weak-{{$guid}}@example.test",
        "password": "1234",
        "full_name": "Weak Password",
    },
    tests=pm(
        "register enforces the password policy",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.json()).to.have.property('password');",
    ),
)

bad_email = request(
    "20 Malformed email is rejected",
    "POST",
    "/api/auth/register/",
    body={
        "email": "not-an-email",
        "password": PASSWORD,
        "full_name": "Bad Email",
    },
    tests=pm(
        "register validates the email format",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.json()).to.have.property('email');",
    ),
)

wrong_password = request(
    "21 Wrong password is rejected",
    "POST",
    "/api/auth/login/",
    body={"email": "{{seedEmail}}", "password": "definitely-not-the-password"},
    tests=pm(
        "login refuses an incorrect password",
        "pm.response.to.have.status(400);",
        "pm.expect(pm.response.json().error).to.eql('Incorrect email or password.');",
    ),
)

# ---------------------------------------------------------------------------
# Tenant isolation
#
# Registering a second account replaces the session cookie, so any request that
# follows is made as the newcomer. If any of these can see the first account's
# data, the user-scoped queries have regressed.
# ---------------------------------------------------------------------------

register_outsider = request(
    "22 Register a second, unrelated account",
    "POST",
    "/api/auth/register/",
    body={
        "email": "outsider-{{$guid}}@example.test",
        "password": "An0ther-Passw0rd!77",
        "full_name": "Unrelated Outsider",
    },
    tests=merge_tests(
        REFRESH_CSRF,
        pm(
            "second account registers with its own distinct id",
            "pm.response.to.have.status(201);",
            "const body = pm.response.json();",
            "pm.expect(body.user.id).to.be.a('number');",
            "pm.expect(String(body.user.id)).to.not.eql(pm.collectionVariables.get('userId'));",
        ),
    ),
)

outsider_jobs = request(
    "23 The new session cannot see the first user's jobs",
    "GET",
    "/api/jobs/",
    tests=pm(
        "tenant isolation: the newcomer starts with an empty job list",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json()).to.have.lengthOf(0);",
    ),
)

outsider_profile = request(
    "24 The new session cannot see the first user's profile",
    "GET",
    "/api/auth/profile/",
    tests=pm(
        "tenant isolation: the profile belongs to the newcomer",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json().headline).to.not.eql("
        + "'Backend engineer, API platform');",
    ),
)

outsider_me = request(
    "25 /me is the newcomer, not the original user",
    "GET",
    "/api/auth/me/",
    tests=pm(
        "the session switched identity cleanly",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.user.id).to.not.eql(pm.collectionVariables.get('userId'));",
        "pm.expect(body.user.email).to.include('outsider-');",
    ),
)


# ---------------------------------------------------------------------------
# Logout — run last, in the outsider's session
# ---------------------------------------------------------------------------

logout = request(
    "26 Log out",
    "POST",
    "/api/auth/logout/",
    tests=pm(
        "logout returns 204 No Content",
        "pm.response.to.have.status(204);",
    ),
)

me_after_logout = request(
    "27 /me is anonymous again after logout",
    "GET",
    "/api/auth/me/",
    tests=pm(
        "the session is genuinely closed",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json().authenticated).to.eql(false);",
    ),
)

jobs_after_logout = request(
    "28 Job list is closed to a logged-out visitor",
    "GET",
    "/api/jobs/",
    tests=pm(
        "job list requires authentication",
        "pm.response.to.have.status(403);",
    ),
)

profile_after_logout = request(
    "29 Profile is closed to a logged-out visitor",
    "GET",
    "/api/auth/profile/",
    tests=pm(
        "profile requires authentication",
        "pm.response.to.have.status(403);",
    ),
)


# ---------------------------------------------------------------------------
# Bring-your-own AI key
#
# Runs last, and re-authenticates as the primary account first. Two things make
# this folder worth having in CI:
#
# 1. **It asserts the security contract at the wire level.** Every other place
#    that talks about "the key is never returned" is a Django test. This one
#    goes over real HTTP against a real session, so a change to middleware, the
#    renderer, or a filter that re-serialises the request would be caught here
#    and nowhere else.
# 2. **It covers the logout side effect.** Logging out deletes the key. That is
#    a behaviour in the Django test suite, but logout is also the one request
#    that must keep returning 204 with an empty body, and the two facts are
#    easy to satisfy one at a time and not together.
#
# The login is needed because the Logout folder above ends with a closed
# session; without it every request here would 403 and the folder would pass
# while asserting nothing. Hence the explicit "signed in again" check first: if
# that regresses, the failure is obvious rather than a cascade of 403s.
# ---------------------------------------------------------------------------

# A structurally valid but entirely fictional key. Long enough to clear the
# 8-character minimum, and containing no whitespace, so it exercises the happy
# path rather than the validators. The prefix matches Google AI Studio's real
# shape because the 4+4 hint would otherwise look wrong in the report.
AI_KEY = "AIzaSyD-PostmanFixture0000000000000000000000000abcd"
AI_KEY_REPLACEMENT = "AIzaSyD-PostmanFixture000000000000000000000000wxyz"

# ---------------------------------------------------------------------------
# Qualities
#
# Runs after the AI-key folder, which ends signed-in. The assertions are about
# the server's rules rather than the UI's: the picker disables its save button
# below the minimum, but a hand-written PUT has to be refused too, and that is
# what these check.
#
# The master resume does not exist for this account, so GET has to degrade to an
# empty selection rather than 404 -- otherwise a brand new user cannot even see
# the options. PUT, which would have nothing to attach them to, must 404.
# ---------------------------------------------------------------------------

qualities_get_without_resume = request(
    "45 /qualities/ is readable before a master resume exists",
    "GET",
    "/api/resumes/qualities/",
    tests=pm(
        "the picker can render and explain itself to a new account",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.selected_count).to.eql(0);",
        "pm.expect(body.minimum_total).to.eql(7);",
        "pm.expect(body.kinds).to.eql("
        "['programming', 'data_structures', 'problem_solving', "
        + "'soft_skills', 'project_management', 'leadership', 'hr']);",
        "const total = Object.values(body.catalogue).flat().length;",
        "pm.expect(total).to.eql(50);",
    ),
)

qualities_put_without_resume = request(
    "46 /qualities/ refuses to save with no master resume",
    "PUT",
    "/api/resumes/qualities/",
    body={
        "qualities": {
            "technical": ["Python", "Java", "Go", "Rust"],
            "project_management": ["Scrum"],
            "soft_skills": ["Communication", "Empathy"],
        }
    },
    tests=pm(
        "there is nothing to attach a selection to",
        "pm.response.to.have.status(404);",
    ),
)

qualities_valid_but_no_resume = request(
    "47 A valid selection is still refused with no master resume",
    "PUT",
    "/api/resumes/qualities/",
    body={
        "qualities": {
            "technical": ["Python", "Java", "Go", "Rust"],
            "project_management": ["Scrum"],
            "soft_skills": ["Communication", "Empathy"],
        }
    },
    tests=pm(
        "the 404 is about the missing resume, not the payload",
        "pm.response.to.have.status(404);",
        "pm.expect(pm.response.json().error).to.include('master resume');",
    ),
)






ai_key_relogin = request(
    "30 Log back in to manage the AI key",
    "POST",
    "/api/auth/login/",
    body={"email": "{{seedEmail}}", "password": PASSWORD},
    tests=merge_tests(
        REFRESH_CSRF,
        pm(
            "the key tests below need a live session",
            "pm.response.to.have.status(200);",
            # login/ returns {user: ...}; only /me/ carries `authenticated`,
            # so asserting that here would read undefined and pass for the
            # wrong reason.
            "pm.expect(pm.response.json().user.email).to.eql("
            "pm.collectionVariables.get('seedEmail'));",
        ),
    ),
)

ai_key_before = request(
    "31 /ai-key/ reports no key before one is saved",
    "GET",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "a fresh account has no key, and the response says so plainly",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.provider).to.eql('gemini');",
        "pm.expect(body.configured).to.eql(false);",
        "pm.expect(body).to.not.have.property('api_key');",
        "pm.expect(body).to.not.have.property('key_hint');",
    ),
)

ai_key_save = request(
    "32 Save a Gemini API key",
    "POST",
    "/api/auth/ai-key/",
    body={"provider": "gemini", "api_key": AI_KEY},
    tests=pm(
        "saving a key reports configured without echoing the key",
        "pm.response.to.have.status(201);",
        "const body = pm.response.json();",
        "pm.expect(body.configured).to.eql(true);",
        "pm.expect(body).to.not.have.property('api_key');",
        "// The hint is a 4+4 mask, never the value itself.",
        "pm.expect(body.key_hint).to.eql('AIza...abcd');",
        "pm.expect(pm.response.text()).to.not.include('" + AI_KEY + "');",
    ),
)

ai_key_read_back = request(
    "33 A saved key is never returned by GET",
    "GET",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "the read path discloses configuration state only",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.configured).to.eql(true);",
        "pm.expect(body).to.not.have.property('api_key');",
        "pm.expect(pm.response.text()).to.not.include('" + AI_KEY + "');",
        "// Nor any interior fragment: a partial echo is still a leak.",
        "pm.expect(pm.response.text()).to.not.include('PostmanFixture');",
    ),
)

ai_key_replace = request(
    "34 Replacing a key updates the hint",
    "POST",
    "/api/auth/ai-key/",
    body={"provider": "gemini", "api_key": AI_KEY_REPLACEMENT},
    tests=pm(
        "a second save overwrites rather than duplicating",
        "pm.response.to.have.status(201);",
        "const body = pm.response.json();",
        "pm.expect(body.key_hint).to.eql('AIza...wxyz');",
        "pm.expect(pm.response.text()).to.not.include('" + AI_KEY + "');",
        "pm.expect(pm.response.text()).to.not.include('"
        + AI_KEY_REPLACEMENT
        + "');",
    ),
)
ai_key_bad_provider = request(
    "35 An unknown provider is rejected",
    "GET",
    "/api/auth/ai-key/?provider=not-a-provider",
    tests=pm(
        "the provider list is closed, so this cannot be used as free storage",
        "pm.response.to.have.status(400);",
    ),
)

ai_key_url = request(
    "36 A pasted URL is rejected instead of being stored",
    "POST",
    "/api/auth/ai-key/",
    body={"provider": "gemini", "api_key": "https://aistudio.google.com/apikey"},
    tests=pm(
        "copying the page URL rather than the key is caught early",
        "pm.response.to.have.status(400);",
    ),
)

ai_key_too_short = request(
    "37 A too-short key is rejected",
    "POST",
    "/api/auth/ai-key/",
    body={"provider": "gemini", "api_key": "short"},
    tests=pm(
        "an obviously truncated paste is refused",
        "pm.response.to.have.status(400);",
    ),
)

ai_key_delete = request(
    "38 Remove the stored key",
    "DELETE",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "deleting reports unconfigured and returns no key",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.configured).to.eql(false);",
        "pm.expect(pm.response.text()).to.not.include('" + AI_KEY_REPLACEMENT + "');",
    ),
)

ai_key_delete_again = request(
    "39 Removing a key that is not there is not an error",
    "DELETE",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "the delete is idempotent, so a double click cannot 500",
        "pm.response.to.have.status(200);",
        "pm.expect(pm.response.json().configured).to.eql(false);",
    ),
)

ai_key_read_deleted = request(
    "40 The removed key is really gone",
    "GET",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "deletion is reflected on the next read",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.configured).to.eql(false);",
        "pm.expect(body).to.not.have.property('key_hint');",
    ),
)

# The logout side effect, end to end. Save a key, sign out, sign back in, and
# confirm the key did not survive. The Django suite asserts the row is deleted;
# this asserts the same thing a user would observe.
ai_key_save_for_logout = request(
    "41 Save a key so logout has something to delete",
    "POST",
    "/api/auth/ai-key/",
    body={"provider": "gemini", "api_key": AI_KEY},
    tests=pm(
        "a key is stored before signing out",
        "pm.response.to.have.status(201);",
        "pm.expect(pm.response.json().configured).to.eql(true);",
    ),
)

ai_key_logout = request(
    "42 Log out with a key stored",
    "POST",
    "/api/auth/logout/",
    # 204 with an empty body: the collection has always asserted this, and the
    # key-deletion behaviour must not tempt anyone into returning a payload.
    tests=merge_tests(
        REFRESH_CSRF,
        pm(
            "logout still returns 204 No Content",
            "pm.response.to.have.status(204);",
            "pm.expect(pm.response.text()).to.eql('');",
        ),
    ),
)

ai_key_relogin_after_logout = request(
    "43 Sign back in after logging out",
    "POST",
    "/api/auth/login/",
    body={"email": "{{seedEmail}}", "password": PASSWORD},
    tests=merge_tests(
        REFRESH_CSRF,
        pm(
            "the session is open again",
            "pm.response.to.have.status(200);",
            "pm.expect(pm.response.json().user.email).to.eql("
            "pm.collectionVariables.get('seedEmail'));",
        ),
    ),
)

ai_key_gone_after_logout = request(
    "44 Signing out deleted the stored key",
    "GET",
    "/api/auth/ai-key/?provider=gemini",
    tests=pm(
        "a key does not survive a logout",
        "pm.response.to.have.status(200);",
        "const body = pm.response.json();",
        "pm.expect(body.configured).to.eql(false);",
        "pm.expect(body).to.not.have.property('key_hint');",
        "pm.expect(pm.response.text()).to.not.include('" + AI_KEY + "');",
    ),
)


# ---------------------------------------------------------------------------
# Collection assembly
# ---------------------------------------------------------------------------

FOLDERS = [
    {
        "name": "Auth lifecycle",
        "description": "Register, log in, inspect the session, then tear it down.",
        "item": [register, me_anonymous, login, me_authenticated, me_shape],
    },
    {
        "name": "Onboarding answers",
        "description": (
            "Career stage, years of experience and the AI setup choice, "
            "asserted over HTTP. The professional-without-years combination "
            "is a contradiction the server refuses, and years sent with a "
            "student or fresher are zeroed rather than stored -- both rules "
            "enforced server-side so a hand-written PATCH behaves exactly "
            "like the onboarding form."
        ),
        "item": [
            profile_stage_student,
            profile_stage_professional_no_years,
            profile_stage_professional,
            profile_stage_unknown,
            profile_ai_setup,
            profile_ai_setup_unknown,
        ],
    },
    {
        "name": "Profile",
        "description": "Workspace profile read/write round trip.",
        "item": [profile_read, profile_update, profile_persisted],
    },
    {
        "name": "Jobs and resumes",
        "description": (
            "List endpoints on a brand new account, plus the 404 paths for "
            "records that do not exist."
        ),
        "item": [
            jobs_empty,
            jobs_filters,
            resumes_empty,
            master_missing,
            job_detail_missing,
            resume_detail_missing,
        ],
    },
    {
        "name": "Validation",
        "description": (
            "Requests that must be rejected before any external call happens. "
            "Nothing here touches the network or the AI provider, which is why "
            "this folder is safe to run on every push."
        ),
        "item": [
            analyze_invalid_url,
            analyze_bad_scheme,
            match_no_resume,
            duplicate_email,
            weak_password,
            bad_email,
            wrong_password,
        ],
    },
    {
        "name": "Tenant isolation",
        "description": (
            "A second account must not see the first account's jobs, profile, "
            "or identity. Registering the outsider replaces the session cookie, "
            "so every request after it runs as the newcomer."
        ),
        "item": [
            register_outsider,
            outsider_jobs,
            outsider_profile,
            outsider_me,
        ],
    },
    {
        "name": "Logout",
        "description": "Ending a session must actually revoke access.",
        "item": [logout, me_after_logout, jobs_after_logout, profile_after_logout],
    },
    {
        "name": "Bring your own AI key",
        "description": (
            "The bring-your-own-key contract, asserted over real HTTP. The key "
            "is written and deleted, and no response anywhere contains it -- "
            "only configured state and a 4+4 mask. Ends by proving that "
            "signing out destroys the stored key. Runs last because it starts "
            "by logging back in: the Logout folder leaves the session closed, "
            "and without that step every request here would 403 and the folder "
            "would pass while asserting nothing."
        ),
        "item": [
            ai_key_relogin,
            ai_key_before,
            ai_key_save,
            ai_key_read_back,
            ai_key_replace,
            ai_key_bad_provider,
            ai_key_url,
            ai_key_too_short,
            ai_key_delete,
            ai_key_delete_again,
            ai_key_read_deleted,
            ai_key_save_for_logout,
            ai_key_logout,
            ai_key_relogin_after_logout,
            ai_key_gone_after_logout,
        ],
    },
    {
        "name": "Qualities",
        "description": (
            "The chosen-qualities endpoint, asserted over real HTTP. This "
            "account has no master resume, which is the interesting case: GET "
            "must still return the catalogue and the minimum so a brand new "
            "user can see the options, and PUT must refuse to save a selection "
            "it has nothing to attach to. The minimum-of-seven rules "
            "themselves are covered in apps/resumes/tests/test_qualities.py -- "
            "they cannot be reached over HTTP here, because the missing resume "
            "is rejected before the payload is ever validated."
        ),
        "item": [
            qualities_get_without_resume,
            qualities_put_without_resume,
            qualities_valid_but_no_resume,
        ],
    },
]


# The prerequest hook mints a fresh address for the primary account. It runs on
# every request, so the guard keeps the value stable across the whole run: {{$guid}}
# would otherwise change between step 01 and step 18 and the duplicate-email test
# would silently pass for the wrong reason.
PREREQ = {
    "listen": "prerequest",
    "script": {
        "type": "text/javascript",
        "exec": [
            "if (!pm.collectionVariables.get('seedEmail')) {",
            "    const token = pm.variables.replaceIn('{{$guid}}');",
            "    pm.collectionVariables.set('seedEmail', 'api-test-' + token + '@example.test');",
            "}",
        ],
    },
}


COLLECTION = {
    "info": {
        "_postman_id": "b1f0c3d2-7a41-4c58-9f0e-2d6a8b1c4e77",
        "name": "TailorUp API",
        "description": (
            "Generated by scripts/build_postman_collection.py - edit the "
            "generator, not this file.\n\n"
            "Exercises the Django REST API the React frontend consumes: session "
            "auth, the profile endpoint, the job and resume list endpoints, "
            "tenant isolation, and input validation.\n\n"
            "The happy path of /api/jobs/analyze/ and /api/jobs/match/ is "
            "deliberately excluded: those scrape a live Greenhouse page and run "
            "the AI provider, so they are neither deterministic nor fast enough "
            "for CI. They are covered by the pytest suite using the fake AI "
            "provider."
        ),
        "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
    },
    "auth": {"type": "noauth"},
    "event": [PREREQ],
    "item": FOLDERS,
    "variable": [
        {"key": "baseUrl", "value": "http://127.0.0.1:8000", "type": "string"},
        {"key": "seedEmail", "value": "", "type": "string"},
        {"key": "csrf", "value": "", "type": "string"},
        {"key": "userId", "value": "", "type": "string"},
    ],
}


ENVIRONMENT = {
    "id": "9c2d4e6f-1a3b-4d5e-8f70-2b6c9d1e4a85",
    "name": "TailorUp API (local)",
    "values": [
        {
            "key": "baseUrl",
            "value": "http://127.0.0.1:8000",
            "type": "default",
            "enabled": True,
        }
    ],
    "_postman_variable_scope": "environment",
}


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    collection_path = OUT_DIR / "tailorup-api.postman_collection.json"
    collection_path.write_text(
        json.dumps(COLLECTION, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    env_path = OUT_DIR / "local.postman_environment.json"
    env_path.write_text(
        json.dumps(ENVIRONMENT, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    count = sum(len(f["item"]) for f in FOLDERS)
    print(f"wrote {collection_path.relative_to(REPO_ROOT.parent)}")
    print(f"wrote {env_path.relative_to(REPO_ROOT.parent)}")
    print(f"  {len(FOLDERS)} folders, {count} requests")


if __name__ == "__main__":
    main()
