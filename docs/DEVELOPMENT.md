# Development

## Layout

```
backend/          Django project (config/) and 8 apps under apps/
  config/         settings, urls, wsgi/asgi
  apps/ai         provider abstraction, schemas, validators, tailor
  apps/applications  application tracker + dashboard aggregation
  apps/jobs       fetchers, parsers, MatchEngine, skill gap
  apps/resumes    upload, parsing, tailoring, DOCX/PDF, versions
  apps/users      auth, profile, encrypted provider credentials
  apps/common     throttling, throttle handler
  apps/automation greenhouse collection
  apps/sheets     import
frontend/         React + TypeScript + Vite
  src/pages       one file per route
  src/components  shared UI
  src/styles      layout, components, marketing, motion, auth
docs/             this file and its neighbours
```

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

The full backend suite is 507 tests and takes roughly 200 seconds.

There is no frontend test runner configured — `package.json` has no `test`
script and `src` contains no test files. Frontend correctness is currently
enforced by `tsc` and the production build only. Adding a runner is a
reasonable next step, and the animation and theme code are the places that
would most benefit.

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
