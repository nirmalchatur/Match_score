# TailorUp — Architecture

How the product is put together, and the rules that hold it together. Every
diagram below describes the repository as it is; nothing here is aspirational.

The decisions that were expensive to make are recorded as
[Architecture Decision Records](adr/README.md), and the boundaries are enforced
by tests in `backend/apps/common/tests/test_architecture.py`.

---

## 1. Deployment shape

Two services, one database, one CI pipeline.

```text
Developer
   │  git push
   ▼
GitHub Repository
   │
   ▼
GitHub Actions
   ├── api-tests      (backend suite, migrations check, Django check)
   ├── ci             (frontend type-check, lint, production build)
   ├── codeql         (static analysis)
   ├── security       (secret scan, dependency audit)
   └── supply-chain   (lockfile / provenance checks)
   ▼
Quality gates on `main`   (branch protection: CI + secret scan must pass)


User (browser)
   │  HTTPS
   ▼
Vercel — React + Vite SPA (static bundle)
   │  HTTPS / JSON API, `VITE_API_URL`
   ▼
Render — Django REST API (gunicorn, one web service)
   │  session cookie + CSRF, `DATABASE_URL`
   ▼
Render PostgreSQL


AI provider (only when tailoring is used)
   ├── Ollama      local daemon / a machine the deployment can reach
   ├── Gemini      Google AI Studio (deployment key or the user's own)
   └── Groq        OpenAI-compatible (deployment key or the user's own)
```

Three things this diagram deliberately does not contain: a task worker, a broker
(Redis/RabbitMQ), and any AWS service. GitHub Actions is a **quality gate**, not
a deployment control plane -- it does not deploy Vercel or Render; both build
from the repository themselves.

The two surfaces of the application:

- **Public** — the marketing site and auth pages. Reachable only when signed out;
  an authenticated visitor is redirected to the workspace.
- **Private** — the application. Requires a session and (except for
  `/setup/resume`) a master resume.

---

## 2. Django application boundaries

One project, eight apps with explicit ownership. Why not microservices is
[ADR-001](adr/ADR-001-modular-monolith.md).

| App | Owns | Installed |
| --- | --- | --- |
| `apps.ai` | provider abstraction, orchestration, schemas, validators, `AIRun` | yes |
| `apps.resumes` | parsing, profiles, master/tailored versions, document generation | yes |
| `apps.jobs` | sources, normalisation, JD parsing, `MatchEngine`, skill normalisation, dedup | yes |
| `apps.applications` | application lifecycle, status pipeline, dashboard aggregation | yes |
| `apps.automation` | in-app notifications, notification preferences | yes |
| `apps.users` | authentication, profile, encrypted provider credentials, sessions, security events | yes |
| `apps.common` | throttling, error shaping, the activity record, operation logging | yes |
| `apps.sheets` | spreadsheet import | yes |

`apps.ai` and `apps.common` became **installed** apps in this phase for one
reason: Django creates a table only for a model in an installed app, and both now
own one (`AIRun`, `ActivityEvent`).

The rules that keep the boundary real:

1. An app owns its models. Other apps reach them through a service function or a
   documented query, not through the internals of another app's `models.py`.
2. Cross-domain work gets an application service ([ADR-007](adr/ADR-007-application-service-layer.md)),
   not a view that calls four other apps.
3. Dependency direction is enforced where it matters. The clearest case: the AI
   layer may not touch the deterministic score, and the match engine may not
   import the AI layer. Both are asserted, not just documented.
4. `apps.common` is not a `utils` dumping ground. It holds throttling, error
   shaping, the activity record and operation logging -- cross-cutting pieces with
   no other owner.

---

## 3. Layering

```text
APIView              authentication · throttling · request parsing · error → HTTP
   ↓
serializer           field validation, wire shape
   ↓
application service  ownership · provider + key resolution · audit · persistence
   ↓
domain               ResumeTailor · validators · MatchEngine · JDProfile · SkillNormalizer
   ↓
ORM                  Resume · Job · Application · AIRun · ActivityEvent
   ↓
PostgreSQL
```

A service never raises an HTTP concept and a view never contains a business rule.
There is deliberately **no repository layer**: Django's manager already is one,
and the scoped-lookup idiom (`filter(user=request.user, pk=pk)`) is the mechanism
the tenant boundary depends on -- wrapping it would hide it.

Worked examples of the split:

```text
Resume upload API      → validate_resume_upload → ResumeParser → ResumeProfile (+ ActivityEvent)

Job analysis API       → ats_registry.collect → JobProcessor
                            → JDProfile.build → MatchEngine.calculate → Job (user, url)

AI tailoring API       → tailoring_service.generate_tailoring
                            → ResumeTailor → factory → provider
                            → schemas → validators → AIRun (+ ActivityEvent)
                            → review payload (nothing saved)

Tailored save API      → tailoring_service.save_tailored_resume
                            → re-validate → Resume(TAILORED) → link to AIRun
```

---

## 4. Tenancy model

Every user-owned row carries a foreign key to the account:

```text
User (django.contrib.auth.User)
  ├── resumes  →  Resume
  │                ├── profile → ResumeProfile  (skills, experience, education, qualities)
  │                ├── source_resume → Resume   (which master a version came from)
  │                └── source_job    → Job      (which posting it targets)
  ├── jobs     →  Job
  ├── applications  →  Application   (pipeline state, tailored_resume)
  ├── ai_runs       →  AIRun         (one audited AI operation)
  ├── activity_events → ActivityEvent (append-only, owner-scoped)
  ├── notifications →  Notification
  ├── security_events → SecurityEvent (authentication only)
  ├── provider_credentials → ProviderCredential (encrypted, never returned)
  └── profile  →  UserProfile    (headline, discipline, target locations)
```

Two rules make this safe:

1. **`user` is non-nullable.** There is no "ownerless" state, so no query can
   accidentally return data for an unknown account.
2. **The FK is scoped in the lookup, not filtered afterwards.**
   `Job.objects.get(pk=pk, user=request.user)` — a guessed primary key from
   another account resolves to `404`, never to someone else's data.

> **Never** write `Job.objects.all()` or `Resume.objects.all()` in a
> user-facing response. Those are the exact calls this architecture exists to
> prevent.

### URL uniqueness is per account

`Job.url` is no longer globally unique. Two users may analyse the same posting
independently:

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=["user", "url"], name="unique_job_url_per_user"),
    ]
```

This also means `JobProcessor.process()` must be given the acting user — it
upserts on `(user, url)`, and looks up the master resume with
`Resume.objects.get(user=user, is_master=True)`.

---

## 5. Authentication

Session-based, using Django's built-in machinery.

- Identity is `django.contrib.auth.models.User`. We did **not** introduce a
  second user system, and we did **not** swap `AUTH_USER_MODEL` — both would have
  added migration risk for no Phase 1 benefit. TailorUp-specific settings live in
  a 1:1 `UserProfile`.
- Signup sets `username = email`, so the built-in model is usable directly.
- Passwords are hashed by Django's default hashers and validated by
  `AUTH_PASSWORD_VALIDATORS`.
- The session cookie is `HttpOnly`: no token is ever exposed to JavaScript.
- CSRF is enforced by Django on all unsafe methods. `GET /api/auth/me/` is
  decorated with `ensure_csrf_cookie` so the SPA can always obtain a token.

### Why session auth and not JWT/localStorage

The brief for this phase explicitly warned against insecure client-stored auth
when the backend already supports secure sessions. Django sessions + CSRF are
the built-in secure path, and they avoid a class of XSS-token-theft bugs.

---

## 6. AI boundary

The provider abstraction is unchanged in shape and protected by an ADR: see
[ADR-002](adr/ADR-002-ai-provider-abstraction.md). What the layer may decide is
the important part.

```text
tailoring_service.generate_tailoring
        │
   AI orchestrator            apps/ai/tailor.py  (ResumeTailor)
        │      prompt in, validated result out -- no HTTP, no model name
        ▼
   Provider factory           apps/ai/factory.py  (the only module that knows the set)
        ├── providers/ollama.py       OllamaProvider
        ├── providers/gemini.py       GeminiProvider
        ├── providers/groq.py         GroqProvider
        └── providers/fake.py         FakeAIProvider (tests and CI only)
        │
   raw text
        ▼
   schemas.py       shape validation  -- forgiving: fences, prose, trailing commas
        ▼
   validators.py    truth validation  -- strict: every claim traced to the source resume
        ▼
   AIRun            the audit row (ADR-005)
```

| Question | Owner |
| --- | --- |
| What is the match score? | `MatchEngine` — deterministic, weighted, inspectable |
| Does the candidate have a skill? | `SkillNormalizer` + the parsed `ResumeProfile` |
| Which requirements are unmet? | `JDProfile` + `MatchEngine` |
| How should this experience be phrased? | the AI provider |
| Is the phrasing factually supported? | `validators` — deterministic, no model |

A provider contains no TailorUp business rules, may not import `apps.jobs` or
`apps.resumes`, and no module under `apps/ai` may read or write `match_score`,
`match_result` or `decision`. `test_architecture.py` asserts all three by walking
the import graph and the attribute accesses, and by running a tailoring end to end
and checking the deterministic result is untouched.

**OpenRouter is not implemented.** It is not in the factory, so it does not appear
in any diagram here. Adding a provider is a class plus a factory entry.

---

## 7. Deterministic analysis and the explainability contract

```text
Resume                       Job posting
  → ResumeParser               → ats_registry.collect (source adapter)
  → ResumeProfile              → JDProfile.build       (description → structured profile)
  → SkillNormalizer  ────────► SkillNormalizer  ◄────── normalised skill names
                    └────────────┬────────────┘
                        MatchEngine.calculate
                                 │
                            MatchResult
                                 ├── overall score     (weighted, 0–100)
                                 ├── skills            score + matched / missing
                                 ├── experience        score + note
                                 ├── requirements      score + matched / partially / unmatched
                                 ├── education         score + note
                                 ├── qualities          reported, never scored
                                 └── decision          USE_MASTER / TAILOR / REVIEW / SKIP
```

```text
score = 0.50 · skills + 0.20 · experience + 0.20 · requirements + 0.10 · education
```

Every user-facing score has a deterministic explanation, and the explanation comes
from the same pass that produced the number: the weights live in one place, each
component carries its own evidence, and the whole result is stored on the job
(`Job.match_result`). An LLM never writes a score or an explanation of one.

Qualities are reported but **never scored** — they are the candidate's own shortlist
rather than parsed evidence, so counting them would let someone raise their score by
ticking more boxes.

`test_architecture.py` recomputes the score from the stored resume profile and the
stored description and asserts it matches, and asserts the weighted sum equals the
reported number.

AI may *consume* a `MatchResult`. It may not produce one.

---

## 8. Job sources and normalisation

```text
Greenhouse ─┐
Workday     ─┼─► ATS registry ─► Collector ─► Normalisation ─► Deduplication ─► JD parsing ─► MatchEngine
Generic     ─┘   (by URL)        JobData       one shape         (user, url)      JDProfile
```

- The board is chosen from the URL by `ats_registry`, so the user pastes a link
  rather than picking a provider, and a Workday link is not reported as "not a
  Greenhouse job board".
- Deduplication is per account: `UniqueConstraint(user, url)`. Two users may
  analyse the same posting independently.
- `JobProcessor.process` is given the acting user, looks up the master resume with
  `filter(user=…, is_master=True)` and upserts on `(user, url)`.
- Job search ranks the postings already stored for the account. It does not fetch
  fresh postings at search time — that is a different system with rate limits and a
  freshness problem, and it is not built.
- Collection happens on the request path today (§10).

---

## 9. Resume pipeline, versioning and documents

```text
Upload (PDF ≤ 10 MB)
  → validate extension · content type · size
  → ResumeParser.extract_text()          empty text → reject and delete the file
  → ResumeProfile.build()                skills, experience, education, projects, certifications
  → Resume (MASTER)                      ActivityEvent: RESUME_UPLOADED
  → ResumeProfile record

Master Resume
  → Resume Profile
  → deterministic match             (MatchEngine, §7)
  → AI tailoring                    (ResumeTailor → provider → schemas → validators)
  → validation verdict              valid | warning | rejected  (rejected → 422, nothing saved)
  → review payload                  the user sees original → tailored per entry
  → Tailored Resume Version         a new Resume(TAILORED) pointing at the master
  → DOCX / PDF                      rendered on demand from the stored representation
```

A failed parse deletes the stored file, so the library never contains unusable
documents. `POST /api/resumes/<id>/set-master/` demotes the previous master first,
guaranteeing at most one per account — which the pipeline relies on when it looks
up `is_master=True`.

Versioning rules ([ADR-004](adr/ADR-004-resume-versioning.md)):

- The master is **never** written by the tailoring flow.
- A run never overwrites an existing version; it creates a new row, or nothing.
- Saving **re-validates** the submitted result against the stored master, so a
  payload edited in the browser cannot persist content the validator refused.
- A saved version records its provenance: source resume, target job, provider,
  prompt version (on the `AIRun`), the deterministic validation verdict and
  timestamps.

Document generation is deterministic code, not a model:

```text
stored profile + user-approved tailoring
        │
   build_document()          apps/resumes/services/document.py   (one resolved model)
        │
   ResumeDocument            renderer-agnostic
        │
        ├── ResumeDocxGenerator   (python-docx)
        └── ResumePdfGenerator    (reportlab)
```

`build_document()` is the single point where a suggestion becomes content, which is
what guarantees the two formats agree. Education and certifications come only from
the stored profile, skills are intersected with the source list, and an emptied
entry falls back to its originals rather than disappearing. Documents are rendered
on demand rather than cached, so a saved file cannot go stale — and no filesystem
path is ever returned: downloads are streamed through an authenticated,
owner-scoped view.

---

## 10. Long-running work

The state model ([ADR-003](adr/ADR-003-long-running-job-boundary.md)):

```text
JobRequest
   ↓
JobRecord            AIRun today; the same contract for a future worker
   ↓
PENDING ──► RUNNING ──► SUCCEEDED
   │           │    └──► FAILED      (bucket + error code + validation verdict)
   └───────────┴────────► CANCELLED   (abandoned, not a failure)
```

Legal transitions are checked in code (`AIRun.VALID_TRANSITIONS`), a terminal row
is immutable, and a retry is a **new row**, so an unsuccessful attempt stays
visible. `PENDING → FAILED` is legal on purpose: a run that dies before it starts
(no provider configured, no key, no master resume) never reaches `RUNNING`, and
showing it as pending forever would hide a configuration error behind a spinner.

| Operation | Record | Execution |
| --- | --- | --- |
| Resume tailoring (measured at 364 s on CPU) | `AIRun` + in-process progress | synchronous, in the request |
| Job analysis | `Job.status` + `Job.pipeline_steps` | synchronous, in the request |
| Resume parsing, document rendering | `Resume` row, or on demand | synchronous, in the request |

**No worker and no broker.** A tailoring holds a web worker for minutes; with
several gunicorn workers a few concurrent runs can saturate the instance, and the
AI rate limits bound how many can be in flight per account. That is a real
limitation, stated rather than hidden. `apps.ai.progress` — a bounded, per-user,
in-process ring buffer of progress events the UI polls — is what makes a slow run
legible instead of looking hung. With multiple workers a poll can land on a
different process, and moving it to a shared cache is a configuration change
because every access goes through that module.

Introducing a worker later means implementing this contract — claim `PENDING` rows,
call the same service functions, write the same states — not a rewrite, because the
business logic is not in the view (§3).

---

## 11. Records: audit, activity, security, notifications

Four tables record things, each with a deliberately narrow claim:

| Model | Holds | Read by |
| --- | --- | --- |
| `apps.ai.models.AIRun` | one AI operation: provider, model, status, failure bucket, validation verdict, duration | Django admin, tests |
| `apps.common.models.ActivityEvent` | one user-initiated action, append-only | Django admin, tests |
| `apps.users.security.SecurityEvent` | authentication events: sign-in, sign-out, password change, key change, session revocation | the security page |
| `apps.automation.models.Notification` | what to tell the user, suppressible and de-duplicated | the notification bell |

None of them stores a secret, a prompt, a provider response or resume content. The
AI run row records a failure *bucket* and an error *code*, never a message, because
a provider message carries the base URL and the response body. Activity metadata
drops a key that names a secret rather than masking it, and drops anything that is
not a scalar, because a nested structure here would eventually be a resume.

Writing a record never fails the operation it describes: every writer is guarded and
logs instead of raising, because a user's upload should not fail over a bookkeeping
row.

---

## 12. Data preservation during migration

Pre-TailorUp rows had no owner. Rather than delete them, migrations
`0004_job_user_ownership` and `0004_resume_user_ownership` run in three steps:

1. Add `user` as **nullable**.
2. Backfill every existing row onto a single `legacy@tailorup.local` account,
   created with an unusable password (`!…`) so it can never be signed into.
3. Alter the field back to **non-nullable**.

Reversible via the paired `RunPython` reverse functions.

---

## 13. API contract

Every endpoint answers with one of a small number of shapes, so a client does not
special-case each one:

| Situation | Shape | Status |
| --- | --- | --- |
| Success, list | `[ … ]` or `{ "results": [ … ] }` | 200 |
| Success, create | the created resource | 201 |
| The user's input is wrong | `{ "error", "code", "detail": {field: [msg]} }` | 400 |
| No session | DRF's own `{"detail": …}` | 401 / 403 |
| Not found, **or not yours** | `{ "error", "code" }` | 404 |
| A fact failed validation | `{ "error", "code", "violations": [...] }` | 422 |
| A conflict of state (e.g. no master resume) | `{ "error", "code" }` | 409 |
| Rate limited | `{ "detail", "code": "rate_limited" }` + `Retry-After` header | 429 |
| Anything unexpected | `{ "error" }` — never a stack, never a provider message | 5xx |

`code` is machine-readable and stable; `error` is one sentence for a person.
Ownership gaps return 404 rather than 403, because a 403 confirms that an id
exists — and that distinction is asserted in the tests.

On the frontend, API types live in one place (`src/lib/types.ts`) and requests go
through one client (`src/lib/api.ts`). A duplicate type defined in a component is
the thing that drifts when a response shape changes.

---

## 14. Frontend structure

```text
src/
  auth/
    AuthProvider.tsx   component: bootstraps the session
    useAuth.ts         context + hook (no components, keeps Fast Refresh working)
    guards.tsx         RequireAnonymous · RequireAuth · RequireMasterResume
  lib/
    api.ts             typed client, CSRF handling, ApiError
    types.ts           shared types
    format.ts          score/status/date formatting
  hooks/
    useData.ts         useJobs / useResumes (shared useResource)
    useToasts.ts       toast queue
  components/          Sidebar, Topbar, JobRow, JobDetail, primitives, Icons
  pages/               Landing, Login, Signup, Onboarding, Settings, plus the
                       existing Dashboard/Jobs/Resumes/Analyze pages
  styles/              layout · components · marketing · auth
```

Auth state lives in React memory and is refreshed from `/api/auth/me/`. Nothing
sensitive is written to `localStorage`.

---

## 15. Architecture tests

The boundaries above are protected by tests, not only by this document. They live in
`backend/apps/common/tests/test_architecture.py` and fail CI when a shortcut is
taken.

| Assertion | Technique |
| --- | --- |
| `MatchEngine` does not import the AI layer | import graph (`ast`) |
| The AI layer never imports the match engine | import graph |
| AI providers import no business app | import graph |
| No AI module reads or writes `match_score` / `match_result` / `decision` | attribute accesses (`ast`) — a docstring that *names* the engine is not a violation |
| Running a tailoring leaves the match score and analysis untouched | end-to-end behaviour |
| The stored score is reproducible from the stored resume and description | recomputation |
| Every component of the score carries evidence, and the weights sum to the score | recomputation |
| A failed run leaves the master resume and its profile untouched | behaviour |
| A rejected result is recorded as `FAILED`, never as `SUCCEEDED` with no artifact | behaviour |
| The service refuses another account's job, in the query | behaviour |
| The audit tables carry a non-nullable owner and are invisible across accounts | model introspection + queries |
| No audit field is named like a secret; no stored credential reaches a row or a response | structure + `ProviderCredential` round trip |
| Refusals share one body shape (`error` + `code`, no `detail`) | API requests |
| A credential cannot be rendered into a log line | `apps/common/tests/test_observability.py` |
| State transitions reject illegal moves | `apps/ai/tests/test_airun.py` |

Coverage that already lives elsewhere and is not duplicated: cross-account resume and
job access (`apps/users/tests/test_isolation.py`), document downloads and filename
sanitisation (`apps/resumes/tests/test_download_api.py`), credentials
(`apps/users/tests/test_ai_credentials.py`), and the shape of a 429
(`apps/common/tests/test_rate_limiting.py`).

---

## 16. Observability

Important operations emit one structured line, through the standard logging tree,
under one logger name (`tailorup.operations`):

```text
operation=resume_tailoring outcome=ok duration_ms=14203 provider=ollama model=llama3.1 validation=valid user=7
```

The helper redacts by field *name* (key, secret, token, password, credential,
authorization, cookie, session, prompt) and by value *shape* (`AIza…`, `gsk_…`,
`sk-…`, `eyJ…`), collapses a container to its size, never logs an exception message,
and cannot raise — it is called on the success path of real work. Duration is logged
on the failure path too, because the slow, failing operation is the one worth
measuring. See [ADR-008](adr/ADR-008-structured-operation-logging.md).

Deliberately not introduced: OpenTelemetry, Sentry, a hosted APM, or JSON log
shipping. One web service whose logs Render already collects does not justify the
dependency, the account and the second place errors are visible.

---

## 17. Deliberately not built

So that nobody has to discover these by trying:

- **Microservices, Kubernetes, AWS.** The deployment is Vercel + Render + Render
  PostgreSQL, and nothing here needs otherwise. No AWS service appears in any
  diagram above, and GitHub Actions is a quality gate rather than a deployment
  control plane.
- **Celery, Redis, RabbitMQ, Kafka, a task worker.** See
  [ADR-003](adr/ADR-003-long-running-job-boundary.md): the work is modelled as
  records and run synchronously, and the reason a queue is not justified *yet* is
  written down with the conditions that would change it.
- **A `utils` module or app.** `apps.common` holds named, owned cross-cutting
  pieces; nothing is added to it because no other app obviously wants it.
- **Usage / billing model.** It would have no consumer until subscriptions exist.
- **Outbound email and push notifications.** Notifications are in-app only, so a
  notification cannot reach a browser that has been closed. The mail backend is
  configured so enabling email is a configuration change, not a code change.
- **A read API for `AIRun` / `ActivityEvent`.** The rows are written, indexed and
  tested; the endpoints are a later phase's decision on the same data
  ([ADR-006](adr/ADR-006-activity-record.md)).
- **Job-board scraping at search time.** Search ranks the postings already stored
  for the account.
- **A frontend test runner.** Not configured; the frontend is enforced by `tsc`,
  lint and the production build. Noted as a real gap rather than a design choice.

---

## 18. Decision records

| ADR | Decision |
| --- | --- |
| [001](adr/ADR-001-modular-monolith.md) | Stay a modular monolith with eight bounded apps |
| [002](adr/ADR-002-ai-provider-abstraction.md) | Keep the provider abstraction; the deterministic engine is the source of truth |
| [003](adr/ADR-003-long-running-job-boundary.md) | Long-running work is a record, executed synchronously until scale demands otherwise |
| [004](adr/ADR-004-resume-versioning.md) | Tailored resumes are new, immutable versions — never edits |
| [005](adr/ADR-005-ai-run-audit.md) | Every AI operation is an `AIRun`, with no secrets and no payloads |
| [006](adr/ADR-006-activity-record.md) | User-initiated actions are an append-only `ActivityEvent` |
| [007](adr/ADR-007-application-service-layer.md) | Business logic lives in an application service, not in a view |
| [008](adr/ADR-008-structured-operation-logging.md) | One structured line per operation, through the standard logging tree |

