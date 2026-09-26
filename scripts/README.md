# API test suite

Automated API tests for the TailorUp backend, run with **Newman** against a real
Django server. A GitHub Actions workflow executes them on every pull request and
again on the merge commit to `main`, then posts the result back on the PR.

```
scripts/build_postman_collection.py   generates postman/*.json (source of truth)
scripts/run_api_tests.py              boots Django, runs Newman, reports
backend/config/settings_test.py       hermetic settings for the run
.github/workflows/api-tests.yml       the CI workflow
```

## Running it locally

```bash
cd ai-job-agent

# once: Newman plus the HTML reporter
npm install --no-save newman newman-reporter-html

python -m pip install -r backend/requirements.txt

python scripts/build_postman_collection.py   # regenerate the collection
python scripts/run_api_tests.py
```

Exit code `0` means everything passed, `1` means an assertion failed, `2` means
the harness itself could not run (bad settings, missing reporter, zero
assertions). Reports land in `reports/`:

| File | Purpose |
| --- | --- |
| `newman-report.html` | browsable run, with request/response detail |
| `newman-junit.xml` | machine-readable, for CI test reporters |
| `newman-report.json` | full structured summary, used to build the PR comment |

Useful flags:

```bash
python scripts/run_api_tests.py --folder "Auth lifecycle"
python scripts/run_api_tests.py --bail          # stop at the first failure
python scripts/run_api_tests.py --keep-server   # leave Django up for poking at
```

> `--folder` only works for folders that are self-contained. Most of this
> collection is **order dependent** — later steps reuse the session and CSRF
> token established earlier — so running one folder alone will fail the
> authenticated steps. The `Validation` folder is the exception.

## What is covered

29 requests / 30 assertions across six folders:

- **Auth lifecycle** — register, the session it creates, log in, `/me`
- **Profile** — read, patch, read back
- **Jobs and resumes** — empty list, filters, and the 404 paths
- **Validation** — malformed URLs, duplicate email, weak password, bad login
- **Tenant isolation** — a second account must not see the first one's data
- **Logout** — the session must actually be revoked

The collection deliberately **excludes** the happy path of `/api/jobs/analyze/`
and `/api/jobs/match/`. Those scrape a live Greenhouse page and invoke the AI
provider, so they are neither deterministic nor fast enough for CI. They are
covered by the pytest suite using `apps.ai.providers.fake.FakeAIProvider`.

## Why Newman runs as a subprocess

The PyPI `newman` package cannot be installed. Its `__init__.py` does:

```python
from argument import Argument      # singular
```


## How the session and CSRF token are threaded through

The API uses **session cookies with CSRF**, not tokens, so the collection has to
carry state between requests. Three things about that are non-obvious and are
handled explicitly:

1. **Login rotates the CSRF token.** Django calls `rotate_token()` on every
   `login()`, so a token captured before logging in is stale and every later
   `POST`/`PATCH` is rejected with 403 before the view is reached.
   `REFRESH_CSRF` re-reads the token after register and login.

2. **The cookie jar is not readable under Newman 6.** Newman 6 ships
   postman-runtime 5, where `pm.cookies.list()` no longer exists and
   `pm.cookies.get()` returns `undefined` for a cookie the server just set. The
   token is therefore parsed out of the `Set-Cookie` **response header** instead,
   with the jar kept as a fallback for the Postman desktop app.

3. **`.get('Set-Cookie')` returns only one header.** A response that signs a
   user in *and* rotates the token sends two `Set-Cookie` headers, and `.get()`
   hands back `sessionid` while silently dropping `csrftoken`. The helper scans
   `pm.response.headers.all()` and picks the right one.

## Two invariants the harness enforces

A test harness that cannot fail is worse than no harness, so:

- **Zero assertions is a failure, not a pass.** `newman-reporter-html` ships
  separately; without it Newman prints `could not find "html" reporter`, runs
  nothing, and *still exits 0*. The first version of this harness reported
  `PASSED: all 0 assertions` and went green. `run_api_tests.py` now treats a
  zero-assertion run as an error (exit 2).
- **A missing report is an error.** If Newman produces no JSON summary the run
  is aborted rather than summarised from nothing.

## Notes for maintainers

- **Edit the generator, not the JSON.** `postman/*.json` is generated. CI
  regenerates it and fails if the result differs from what is committed, so a
  hand-edited collection cannot silently drift.
- **Folders are order dependent.** Requests share a session and CSRF token, so
  inserting a step that logs out or switches accounts will break everything
  after it. The `Tenant isolation` folder deliberately replaces the session with
  a second account, which is why `Logout` runs last, as the newcomer.
- **The test database is disposable but not wiped between runs.** It lives in
  the system temp directory (`settings_test.py`), never in the repo, and each
  run registers a fresh account with a GUID address, so repeat runs are safe.
  Your real `db.sqlite3` is never opened.
- `DEBUG` is `False` during tests on purpose, so the production security block
  in `settings.py` is exercised. SSL redirect, HSTS and the `Secure` cookie
  flags are forced back off, because Newman talks plain HTTP to 127.0.0.1.

but every published release of `argument` (0.2.2 … 1.4.0) exports `Arguments`
— plural. Installation dies in the build step:

```
ModuleNotFoundError: No module named 'argument'
ImportError: cannot import name 'Argument' from 'argument'
```

It is an unmaintained wrapper. Newman is a Node program and the npm distribution
is the supported install path, so `run_api_tests.py` drives the npm CLI while
keeping the server lifecycle, reporting and exit codes in Python.
