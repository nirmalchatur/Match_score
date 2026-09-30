# Development

## Layout

```
backend/          Django project (config/) and 8 apps under apps/
  config/         settings, urls, wsgi/asgi
  apps/ai         provider abstraction, orchestration, schemas, validators, AIRun audit
  apps/applications  application tracker + dashboard aggregation
  apps/jobs       fetchers, parsers, MatchEngine, skill gap
  apps/resumes    upload, parsing, tailoring service, DOCX/PDF, versions
  apps/users      auth, profile, encrypted provider credentials, security events
  apps/common     throttling, throttle handler, activity record, operation logging
  apps/automation notifications and preferences
  apps/sheets     import
frontend/         React + TypeScript + Vite
  src/pages       one file per route
  src/components  shared UI
  src/styles      layout, components, marketing, motion, auth
docs/             this file and its neighbours
  adr/            one short record per architectural decision
```

`apps.ai` and `apps.common` are installed apps, not just packages: `AIRun` (the
audit of one AI operation) and `ActivityEvent` (the append-only record of
user-initiated actions) live in them, and Django creates a table only for a model
in an installed app.

## Requirements

| | CI / Render | Local (this machine) |
| --- | --- | --- |
| Python | 3.12 | 3.10 |
| Django | 6.1 | 5.2 |

Django 6.1 requires Python 3.12+. If you are on 3.10, pin `Django==5.2` in a
local requirements copy. The suite passes on both, but `check --deploy` reports
`mail.E001` only on 6.1, so a 5.2 run cannot be a full substitute for CI.

## Backend setup

```bash
cd backend
python -m venv ../venv
../venv/Scripts/pip install -r requirements.txt   # Windows
../venv/Scripts/python manage.py migrate
../venv/Scripts/python manage.py runserver
```

## Frontend setup

```bash
cd frontend
npm install
npm run dev
```

`VITE_API_URL` must point at the Django API **including the trailing `/api`**.
The Vite config refuses to build without it, because a missing value silently
produces a bundle that calls its own origin. For a deliberate same-origin
bundle, set `ALLOW_RELATIVE_API=1`.

## Checks

```bash
# backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test

# frontend
npx tsc -b
npm run lint
npm run build
```

The full backend suite is 674 tests and takes roughly 205 seconds.

There is no frontend test runner configured — `package.json` has no `test`
script and `src` contains no test files. Frontend correctness is currently
enforced by `tsc` and the production build only. Adding a runner is a
reasonable next step, and the animation and theme code are the places that
would most benefit.

## Architecture rules and boundary tests

`docs/ARCHITECTURE.md` describes the boundaries; `docs/adr/` records why each one
exists. Neither is enforced by review alone — `backend/apps/common/tests/test_architecture.py`
asserts them, so a shortcut fails CI:

```bash
cd backend
..\venv\Scripts\python.exe manage.py test apps.common.tests.test_architecture   # ~7s
..\venv\Scripts\python.exe manage.py test apps.ai.tests.test_airun apps.common.tests.test_observability
```

Four rules most likely to be broken by accident, and what each test does:

- **The AI layer never touches a score or a decision.** Static (import graph and
  attribute accesses, so a docstring naming `MatchEngine` is fine and a call to it
  is not) plus behavioural: run a tailoring, then assert the job's score and match
  analysis are unchanged and reproducible from the stored data.
- **An audit write cannot break the operation it records.** `AIRun` and
  `ActivityEvent` writers are guarded and log instead of raising; the tests drive
  the failure paths.
- **A credential never reaches a log line, an audit column or a response.** By field
  *name* and by value *shape*, asserted against real key formats.
- **Ownership is enforced in the query**, not after loading a row, so another
  account's id produces the same 404 as a missing one.

When you add a model, a service or an endpoint, the cheapest time to add the
corresponding boundary assertion is in the same pull request.

## AI providers

The default provider is Ollama running locally. See `AI_SETUP.md` for setup and
`AI_ARCHITECTURE.md` for the provider boundary.

**Be realistic about latency.** On a CPU-only machine a `llama3.1` tailoring
request has been measured at **364 seconds** wall clock. `OLLAMA_TIMEOUT` must
exceed 180 seconds or the request is abandoned before the model finishes. This
is not a bug and is not interactive; do not describe it as such.

Tests never call a real model. They use `FakeProvider`; the real
`OllamaProvider` has its own suite that mocks HTTP. Rerunning a genuine model
request costs several minutes, so do it deliberately, not as a smoke test.

## Diagnostics

Two scripts live in `backend/` and are prefixed with `_` so they read as
tooling rather than application modules. They are not imported by anything
and no test touches them.

```bash
cd backend

# Is the provider wired up, and is the daemon actually answering?
python _check_provider.py

# One real, capped generation. Prints the model's output and how long it took.
python _demo_ollama.py
```

`_check_provider.py` prints the resolved settings, describes the provider, and
then calls `provider.health()` — the one call that touches the network, so it
distinguishes *configured* from *reachable*. It exits non-zero when the
provider cannot be built or the daemon does not answer, so it is usable in a
script.

It exists because "AI is not configured" and "the daemon is down" and "the
model is not pulled" all present as the same vague failure otherwise, and the
difference between them is the whole diagnosis.

`_demo_ollama.py` sends a fixed, generic prompt with `num_predict` capped, so
it returns in seconds rather than the minutes a real tailoring run costs. It
proves the transport, the model and the output. It is **not** a tailoring run
and must not be read as evidence that the tailoring contract holds — that is
covered by the test suite with `FakeProvider`, and by the one real end-to-end
run recorded in `AI_SETUP.md`.

Both are read-only with respect to your data: neither reads a resume, and
neither writes to the database.

## Rate limiting during development

Throttling is on by default and will otherwise throttle your own test suite.
`settings.py` disables it when `"test" in sys.argv` — that is, whenever
`manage.py test` is running — using `os.environ.setdefault`, so an explicit
`TAILORUP_RATE_LIMIT_ENABLED=True` in the environment still wins and you can
deliberately exercise the throttled path. The tests that assert 429 patch the
rate table themselves, so they are unaffected.

## Security

Read `SECURITY.md` before changing anything that touches ownership, document
downloads, credentials or throttling. The ordering documented there is load
bearing.
