# Contributing to TailorUp

Thanks for looking. This is a small project and contributions are genuinely
welcome, including fixes to anything below that is wrong or out of date.

The repository is named `Match_score`; the product is **TailorUp**. The
internal module names (`MatchEngine`, `JobProcessor`, `JDProfile`) are
component names, not brand, and are not being renamed.

## Getting set up

**Requirements:** Python 3.12 (CI and Render) and Node 20.

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

## What must pass before a PR

```bash
# Backend
cd backend
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test

# Frontend
cd ../frontend
npx tsc -b
npm run lint
npm run build
```

All of these are CI gates. A PR that fails them will not merge, and there is
no override. If a check fails, fix the cause rather than relaxing the check.

There is currently **no frontend test runner** — no `test` script and no test
files. Frontend correctness is enforced by `tsc` and the production build. If
you add a runner, that is a welcome contribution and it does not need to be
introduced as a framework.

## Branching and PRs

- Branch from `main` with a descriptive name: `feat/…`, `fix/…`, `docs/…`.
- **One concern per branch.** This repository has been bitten by long-lived
  reused branches: PRs #17 through #25 all came from a handful of branch
  names, and commits pushed after a merge silently went nowhere. Create a
  fresh branch per change and delete it once merged.
- Open a PR against `main` with a description of *why*, not just *what*.
- Reference the issue it closes, if there is one.

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

Be decent. Critique the code, not the person. Assume good faith.

## Licence

Contributions are accepted under the [MIT Licence](LICENSE). By opening a
pull request you agree that your contribution is licensed under it.
