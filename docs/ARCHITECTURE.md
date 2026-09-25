# TailorUp — Architecture

How the SaaS foundation is put together, and the rules that must hold for
data isolation to be correct.

---

## 1. System shape

```text
                    TAILORUP
                       │
         ┌─────────────┴─────────────┐
         │                           │
    Marketing Site              SaaS Application
         │                           │
    /  (landing)               Session auth + CSRF
    /login                           │
    /signup                          ▼
                              /setup/resume
                              (master resume)
                                     │
                                     ▼
                              /app/dashboard
                              /app/jobs
                              /app/resumes
                              /app/analyze
                              /app/settings
```

Two separate surfaces:

- **Public** — the marketing site and auth pages. Reachable only when signed out;
  an authenticated visitor is redirected to the workspace.
- **Private** — the application. Requires a session, and (except for
  `/setup/resume`) requires a master resume.

---

## 2. Tenancy model

Every user-owned row carries a foreign key to the account:

```text
User (django.contrib.auth.User)
  ├── resumes  →  Resume
  │                └── profile → ResumeProfile  (skills, experience, …)
  ├── jobs     →  Job
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

## 3. Authentication

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

## 4. Existing pipeline (preserved)

The original job analysis chain is unchanged apart from gaining a `user`:

```text
Job URL
  → GreenhouseCollector.collect()      (HTML → JobData)
  → JDProfile.build()                  (description → structured profile)
  → MatchEngine.calculate()            (resume profile + JD profile → score)
  → Job.objects.update_or_create(user=…, url=…)
```

`GreenhouseCollector`, `JDProfile`, `SkillNormalizer`, `ResumeParser`, and
`MatchEngine` were **not** rewritten. They had no ownership concept and did not
need one; the tenant boundary lives in the model and the view layer.

---

## 5. Resume lifecycle

```text
React dropzone
   ↓  POST /api/resumes/  (multipart)
validate (extension · content-type · size ≤ 10 MB)
   ↓
ResumeParser.extract_text()             (pypdf)
   ↓  empty text → reject and delete the file
ResumeProfile.build()                   (skills, experience, education, …)
   ↓
ResumeProfile record written
   ↓
response → frontend refreshes /auth/me/ → dashboard unlocks
```

A failed parse deletes the stored file, so the library never contains
unusable documents. `POST /api/resumes/<id>/set-master/` demotes the previous
master first, guaranteeing at most one per account — which the pipeline relies
on when it looks up `is_master=True`.

---

## 6. Data preservation during migration

Pre-TailorUp rows had no owner. Rather than delete them, migrations
`0004_job_user_ownership` and `0004_resume_user_ownership` run in three steps:

1. Add `user` as **nullable**.
2. Backfill every existing row onto a single `legacy@tailorup.local` account,
   created with an unusable password (`!…`) so it can never be signed into.
3. Alter the field back to **non-nullable**.

Reversible via the paired `RunPython` reverse functions.

---

## 7. Frontend structure

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

## 8. Deliberately not built

Per the Phase 1 scope, and to avoid dead code:

- **Application model** — `apps/applications/models.py` already exists (unused,
  not in `INSTALLED_APPS`). It is the natural home for tracking states in
  Phase 3; no new model was added now.
- **Usage / billing model** — would have no consumer until subscriptions exist.
- **Redis, Celery, WebSockets, Kubernetes** — none are used today.

