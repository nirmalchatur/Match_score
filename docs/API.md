# TailorUp — API reference

Base URL in development: `http://127.0.0.1:8000/api` (the Vite dev server
proxies `/api` to it, so the browser normally talks to `/api` on port 5173).

**Authentication:** session cookie. Unsafe methods (`POST`/`PATCH`/`DELETE`)
must send the `X-CSRFToken` header, sourced from the `csrftoken` cookie that
`GET /auth/me/` sets. Send credentials with every request.

Every job and resume response is scoped to the authenticated account.

---

## Auth

### `POST /api/auth/register/` — public

```json
{ "email": "you@example.com", "password": "min-8-chars", "full_name": "Ada Lovelace" }
```

`201` → `{ "user": { … } }`, already signed in. Password is validated by
Django's `AUTH_PASSWORD_VALIDATORS`. `full_name` is optional.
`400` on duplicate email or weak password.

### `POST /api/auth/login/` — public

```json
{ "email": "you@example.com", "password": "…" }
```

`200` → `{ "user": { … } }` · `400` on bad credentials.

### `POST /api/auth/logout/` — public

`204` · ends the session.

### `GET /api/auth/me/` — public

`200` always. Seeds the CSRF cookie.

```json
{ "user": null, "authenticated": false }
```

or, when signed in:

```json
{
  "user": {
    "id": 4,
    "email": "you@example.com",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "date_joined": "2026-09-25T17:00:00Z",
    "profile": { "headline": "", "discipline": "", "target_locations": "" },
    "has_master_resume": true,
    "job_count": 9
  },
  "authenticated": true
}
```

### `GET /api/auth/profile/` — **requires auth**

Returns the workspace preferences.

### `PATCH /api/auth/profile/` — **requires auth**

```json
{ "headline": "Backend Engineer", "discipline": "ENGINEER", "target_locations": "Pune, Remote" }
```

`discipline` is one of `ENGINEER`, `DESIGNER`, `PRODUCT`, `DATA`, `MARKETING`,
`OTHER`.

---

## Jobs — all endpoints **require auth**

### `GET /api/jobs/`

Returns only the caller's jobs.

| Query param | Values |
| --- | --- |
| `q` | free text over title, company, url |
| `status` | `PENDING` `RUNNING` `COMPLETED` `FAILED` `NEW` `PROCESSING` `READY` `SKIPPED` |
| `sort` | `-created_at` (default) · `created_at` · `-match_score` · `match_score` |

```json
[
  {
    "id": 9,
    "url": "https://boards.greenhouse.io/…/jobs/4708558005",
    "company": "Acme",
    "title": "Python Backend Engineer",
    "location": "Pune",
    "description": "…",
    "match_score": 88.0,
    "match_result": { "score": 88.0, "decision": "USE_MASTER" },
    "decision": "USE_MASTER",
    "status": "COMPLETED",
    "error_message": "",
    "pipeline_steps": [{ "name": "URL validated", "status": "complete" }],
    "created_at": "2026-09-25T17:00:00Z",
    "updated_at": "2026-09-25T17:00:00Z"
  }
]
```

### `GET /api/jobs/<id>/`

`200` with the job, or `404` if it belongs to another account.

### `POST /api/jobs/analyze/`

```json
{ "url": "https://boards.greenhouse.io/company/jobs/4708558005" }
```

Collects the posting, scores it against **the caller's** master resume, and
saves the result.

`200` → `{ "job_id": 9, "status": "completed", "job": { … } }`
`400` → `{ "error": "…", "status": "failed" }`
`404` → no master resume configured.

### `POST /api/jobs/match/`

Analyses manually supplied description text instead of fetching a URL.
`{ url, company, title, location?, jd_text }`.

---

## Resumes — all endpoints **require auth**

### `GET /api/resumes/`

Only the caller's resumes.

```json
[
  {
    "id": 4,
    "name": "Master Resume",
    "file": "/media/resumes/master_resume.pdf",
    "resume_type": "MASTER",
    "is_master": true,
    "created_at": "2026-09-25T17:00:00Z"
  }
]
```

### `POST /api/resumes/` — multipart

| Field | Notes |
| --- | --- |
| `file` | required, PDF only, ≤ 10 MB |
| `name` | display name |
| `resume_type` | `MASTER` or `TAILORED` |
| `is_master` | `true` / `false` |

The PDF is text-extracted and profiled on upload. `201` → the created resume.
`400` if validation or parsing fails (the stored file is deleted again).

### `GET /api/resumes/master/`

The caller's master resume, or `404` when none is set.

### `GET /api/resumes/<id>/` · `DELETE /api/resumes/<id>/`

`404` for another account's resume. `DELETE` returns
`{ "deleted": true, "had_master": false }`.

### `POST /api/resumes/<id>/set-master/`

Promotes one of the caller's resumes, demoting the previous master.

---

## Error shapes

| Status | Meaning |
| --- | --- |
| `400` | Validation failed — `{ "error": "…" }` or a DRF field map |
| `401` / `403` | Missing or invalid session |
| `404` | Not found, **or** owned by another account |

`404` is deliberately used instead of `403` for other accounts' rows so the API
does not confirm that a given id exists.
