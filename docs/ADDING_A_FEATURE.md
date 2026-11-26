# Adding a feature

A walkthrough for your first feature PR: where code goes, which tests you need,
and what CI checks. It assumes you have a working setup from
[DEVELOPMENT.md](DEVELOPMENT.md).

The short version:

1. Open (or pick up) an issue so the idea is agreed before the code is written.
2. Put logic in a **service**, keep the **view** thin, and scope every query to
   `request.user`.
3. Add tests at each layer you touched: Django for the API and service, Vitest
   for frontend logic and components, Playwright if you changed a route or a
   guard.
4. Run `make check` (or the commands it lists) before you push.

---

## 1. Agree on it first

Open a **Feature request** issue (the template asks the right questions), or
comment on an existing one to say you're taking it. A five-line discussion up
front is cheaper than a rewritten PR. Issues labelled `good first issue` are
scoped to be finishable without knowing the whole codebase.

If the feature changes an architectural boundary (new app, new external
service, a new kind of long-running work), it needs a short ADR in
[`docs/adr/`](adr/README.md) in the same PR. If you're unsure whether it does,
ask on the issue.

## 2. Where the code goes

### Backend

The backend is a modular monolith ([ADR-001](adr/ADR-001-modular-monolith.md)):
one Django project, one app per domain under `backend/apps/`.

| You are adding… | It goes in… |
| --- | --- |
| Something about jobs, matching, scoring | `apps/jobs` |
| Resumes, tailoring, documents | `apps/resumes` |
| Application tracking, dashboard | `apps/applications` |
| Notifications | `apps/automation` |
| Accounts, credentials, security events | `apps/users` |
| AI provider or prompt work | `apps/ai` (see "Adding an AI provider" in CONTRIBUTING.md) |
| Cross-cutting: throttling, logging, activity | `apps/common` |

A new app is rarely the answer. Add one only when none of the above owns the
concept, and record why in an ADR.

Within an app, follow the layering from
[ADR-007](adr/ADR-007-application-service-layer.md):

```text
views.py        auth, throttling, parse request, map errors → HTTP
services/*.py   ownership, the flow itself, audit writes, persistence
models.py       data
```

- **No HTTP in a service.** No `Response`, `status`, or `request`. Raise a named
  error and let the view map it.
- **Scope in the query, not after.** `Job.objects.get(pk=pk, user=request.user)`,
  never `get(pk=pk)` followed by an ownership check. Another account's id must
  return the same 404 as a missing one. `apps/users/tests/test_isolation.py`
  shows the pattern.
- **Every model has an owner.** A non-null `user` foreign key with a
  `related_name`.
- **Wire the URL** in the app's `urls.py`. If it's a new app, also add it in
  `config/urls.py` and `INSTALLED_APPS`.
- **Run `python manage.py makemigrations`** after any model change and commit
  the migration. CI fails if one is missing.

### Frontend

| You are adding… | It goes in… |
| --- | --- |
| A new route / screen | `src/pages/` (one file per route) + a `<Route>` in `src/App.tsx` |
| A reusable piece of UI | `src/components/` |
| An API call | a method on `api` in `src/lib/api.ts`, response type in `src/lib/types.ts` |
| Pure helpers (formatting, parsing) | `src/lib/` |

Always call the backend through `api.*`. It handles the CSRF token, cookie
credentials, timeouts, and turning Django's error shapes into a readable
message. A bare `fetch` skips all of that.

## 3. Tests

Every PR that changes behaviour adds or changes a test. Pick the cheapest layer
that would catch the bug.

### Django (`backend/apps/<app>/tests/`)

```bash
cd backend
python manage.py test apps.jobs                       # one app
python manage.py test apps.jobs.tests.test_job_search # one module
```

For an endpoint, cover at least:

- the happy path,
- an unauthenticated request (401/403),
- **another user's object id → 404** (the tenant boundary),
- invalid input → 400 with a message.

For a service, call it directly without a client. That is the point of having
one. Never call a real AI model or the network in a test: use `FakeProvider`
and `unittest.mock`.

When you add a model, service, or endpoint, check whether
`apps/common/tests/test_architecture.py` should assert something about it
(owner field, no secret-named fields, the 404 rule). The cheapest time to add
that assertion is in the same PR.

Coverage is measured in CI and has a floor (`fail_under` in
`backend/pyproject.toml`). New code without tests will push it down.

### Frontend unit and component tests (Vitest)

Test files sit next to the code: `Foo.tsx` → `Foo.test.tsx`.

```bash
cd frontend
npm test              # run once
npm run test:watch    # re-run on save
npm run test:coverage # with a coverage report in coverage/
```

- Pure functions: plain `expect` (see `src/lib/format.test.ts`).
- Components: render with Testing Library and query by **role and label**, the
  way a user would find the element (see `src/components/UrlForm.test.tsx`).
  If you can't find an element by role, that's usually an accessibility bug
  worth fixing.
- Anything that calls the API: stub `fetch` (see `src/lib/api.test.ts`). Tests
  never reach a server.

### End-to-end smoke tests (Playwright)

`frontend/e2e/` runs the **production bundle** in Chromium with the API faked
per test, so no Django is needed. Add a case here when you add a route, change
a redirect or guard, or change what a signed-out visitor sees.

```bash
cd frontend
npx playwright install chromium   # once
npm run test:e2e
npm run test:e2e:ui               # interactive, with time-travel debugging
```

Register fake responses with the `api` fixture:

```ts
test('shows my new page', async ({ page, api }) => {
  api.anonymous().json('GET', '/my-feature/', 200, { items: [] })
  await page.goto('/my-feature')
  await expect(page.getByRole('heading', { name: 'My feature' })).toBeVisible()
})
```

### API contract tests (Newman)

If you add or change an endpoint, add it to
`scripts/build_postman_collection.py` (the collection JSON is generated from
it) and run `python scripts/run_api_tests.py`. See
[scripts/README.md](../scripts/README.md).

## 4. Before you push

```bash
make check
```

That runs, in order: ruff, Django system checks, the migrations check, the
Django suite with coverage, oxlint, Vitest, and the type-check plus production
build. Without `make`, run the commands listed under `check:` in the
`Makefile`. The Playwright suite is separate (`make e2e`) because it needs a
browser download the first time.

Then open a PR. The template asks what changed, why, and how you tested it.
CI runs everything above plus the dependency audit and security scans, and
posts a single **CI status** result. A PR merges only when that is green.

## 5. Docs

- New or changed endpoint → [`docs/API.md`](API.md).
- New environment variable → `.env.example` (root and/or `backend/`, `frontend/`)
  with a comment, and [`docs/DEPLOYMENT.md`](DEPLOYMENT.md) if production needs it.
- New architectural decision → an ADR.
- A user-visible change → a line in the PR description under "Screenshots /
  user-visible change".
