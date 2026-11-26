# Contributing to TailorUp

Thanks for looking. This is a small project and contributions are genuinely
welcome, including fixes to anything below that is wrong or out of date.

The repository is named `Match_score`; the product is **TailorUp**. The
internal module names (`MatchEngine`, `JobProcessor`, `JDProfile`) are
component names, not brand, and are not being renamed.

## Getting set up

**Requirements:** Python 3.12 (CI and Render) and Node 22 (CI).

```bash
git clone https://github.com/nirmalchatur/Match_score.git
cd Match_score

# Backend
cd backend
python -m venv ../venv
../venv/Scripts/pip install -r requirements.txt   # Windows
../venv/Scripts/python manage.py migrate
../venv/Scripts/python manage.py runserver

# Frontend, in a second terminal
cd frontend
npm install
npm run dev
```

Copy `.env.example` to `.env` and fill in what you need. It is loaded
automatically, and a real environment variable always takes precedence over
`.env` — which is what lets Render's dashboard stay authoritative in
production.

The frontend needs `VITE_API_URL` pointing at the Django API **including the
trailing `/api`**. The build refuses to run without it, because a missing
value silently produces a bundle that calls its own origin. For a deliberate
same-origin build, set `ALLOW_RELATIVE_API=1`.

For lint and coverage tooling, install `requirements-dev.txt` instead of
`requirements.txt` (it includes it):

```bash
pip install -r backend/requirements-dev.txt
```

**Adding a feature?** Read [docs/ADDING_A_FEATURE.md](docs/ADDING_A_FEATURE.md)
first. It covers where code goes, which tests a feature PR needs, and how to
fake the API in frontend tests.

## What must pass before a PR

```bash
make check      # everything below except e2e
make e2e        # Playwright smoke tests
```

Or by hand:

```bash
# Backend
cd backend
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
coverage run manage.py test && coverage report   # fails under the coverage floor

# Frontend
cd ../frontend
npm run lint
npm test                 # Vitest unit + component tests
npm run build            # includes tsc
npm run test:e2e         # Playwright, against the production bundle
```

All of these are CI gates, rolled up into a single **CI status** check. A PR
that fails them will not merge, and there is no override. If a check fails,
fix the cause rather than relaxing the check.

### Tests

| Layer | Tool | Lives in |
| --- | --- | --- |
| Django models, services, API | `manage.py test` | `backend/apps/<app>/tests/` |
| Architecture boundaries | `manage.py test` | `backend/apps/common/tests/test_architecture.py` |
| API contract | Newman | `scripts/build_postman_collection.py` |
| Frontend logic and components | Vitest + Testing Library | `frontend/src/**/*.test.ts(x)`, next to the code |
| Routing, guards, the built bundle | Playwright | `frontend/e2e/` |

A PR that changes behaviour adds or changes a test. A bug fix starts with a
test that fails without the fix.

**Coverage** is measured for the backend in CI, with a floor set in
`backend/pyproject.toml` (`fail_under`). If your PR raises coverage, you're
welcome to raise the floor. Never lower it to make a PR pass.

**Lint** for the backend is ruff with bug-finding rules only (pyflakes and
syntax errors; see `backend/pyproject.toml`). Style isn't gated. If you need
an unused import on purpose, for example a name a test patches, keep it with
`# noqa: F401` and a comment saying why.

Optionally, `pip install pre-commit && pre-commit install` runs ruff and a
private-key check on every commit.

## Finding something to work on

- Issues labelled **`good first issue`** are scoped to be finishable without
  knowing the whole codebase. **`help wanted`** marks larger ones the
  maintainer would welcome help on.
- Comment on the issue to say you're taking it, so two people don't build the
  same thing.
- For a new idea, open a **Feature request** first. The template asks the
  questions a reviewer would.

## Branching and PRs

- Branch from `main` with a descriptive name: `feat/…`, `fix/…`, `docs/…`.
- **One concern per branch.** This repository has been bitten by long-lived
  reused branches: PRs #17 through #25 all came from a handful of branch
  names, and commits pushed after a merge silently went nowhere. Create a
  fresh branch per change and delete it once merged.
- Open a PR against `main` with a description of *why*, not just *what*. The
  PR template has a short checklist.
- Reference the issue it closes, if there is one.
- Review is requested automatically from the owners in `.github/CODEOWNERS`.

## Code style

**Backend** — follow the surrounding file. Type hints on public functions,
docstrings that explain *why* rather than restating the signature. Comments
that record a decision and its reasoning are welcome; comments that narrate
the next line are not.

**Frontend** — TypeScript, no `any` without a comment saying why. Prefer
semantic HTML over ARIA. `oxlint` is the linter; `npm run lint` must pass.

Whatever you do, please do not weaken a security control or a test to make
something pass. If a test is wrong, change the test and say so in the PR
description.

## Adding an AI provider

The provider abstraction is the point — please extend it rather than
special-casing a provider somewhere in the service layer.

1. Implement `AIProvider` in `apps/ai/providers/yourprovider.py`. It
   translates a request to your transport and returns raw text. It does
   **not** parse, validate, or interpret the response.
2. Register it in `apps/ai/factory.py`.
3. Add tests mirroring `test_ollama_provider.py`.

`apps/ai/tailor.py` talks only to the interface and must stay
provider-agnostic.

`FakeProvider` exists so the test suite never needs a network or a model. If
your change makes tests require a live provider, the change is wrong.

## Reporting a security issue

Please do **not** open a public issue for a vulnerability. See
[SECURITY.md](SECURITY.md) for the reporting route.

## Code of conduct

Be decent. Critique the code, not the person. Assume good faith. The full
version, including how to report a problem, is in
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## Licence

Contributions are accepted under the [MIT Licence](LICENSE). By opening a
pull request you agree that your contribution is licensed under it.
