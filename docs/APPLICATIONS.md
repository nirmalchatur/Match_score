# Application Tracker

## What it is

A pipeline record for one job the user is actively pursuing. It is a real row in
the database, not a view derived from match scores.

The previous version of `/app/applications` was a **preview board** that faked
pipeline stages by mapping each analysed job's match score onto a column. That
was honest about being a placeholder but it was misleading to read: a 95% match
appeared under "Rejected". This release replaces it with persisted status.

## Model

`apps/applications/models.py`

| Field | Notes |
|---|---|
| `user` | The owner. The tenant boundary. |
| `job` | The tracked job. `on_delete=CASCADE` — deleting a job removes its application. |
| `tailored_resume` | Optional. The tailored version used, if any. |
| `status` | Controlled choice, default `SAVED`. |
| `applied_at` | Stamped on the first transition into a submitted state. Never overwritten. |
| `notes` | Free text. |
| `created_at` / `updated_at` | |

### Statuses

```
SAVED → APPLIED → ASSESSMENT → INTERVIEW → OFFER
                                              ↘ REJECTED
                                              ↘ WITHDRAWN
```

The model does not enforce a strict linear order — a candidate may hear back out
of sequence, or withdraw at any point. What it does enforce is the *meaning* of
`applied_at`: it is set once, when the status first becomes a submitted state,
and a later status edit never rewrites it.

`ACTIVE_STATUSES` (`APPLIED`, `ASSESSMENT`, `INTERVIEW`) and `CLOSED_STATUSES`
(`OFFER`, `REJECTED`, `WITHDRAWN`) are class constants so "am I waiting on
them?" is one property, not a hardcoded list at three call sites.

### Constraints

- `UniqueConstraint(user, job)` — one application per job per account. Enforced
  in the database *and* in the serializer (see below).
- Index on `(user, status)` — the tracker filters and groups by status.
- Index on `(user, -updated_at)` — the recent list.

## API

| Endpoint | Purpose |
|---|---|
| `GET /api/applications/` | List, scoped to the caller |
| `GET /api/applications/?summary=1` | Status counts, scoped to the caller |
| `GET /api/applications/?status=INTERVIEW` | Filter by status |
| `GET /api/applications/?job=<id>` | The application for one job |
| `POST /api/applications/` | Create (`{"job": id, "tailored_resume": id?}`) |
| `GET /api/applications/<id>/` | Retrieve |
| `PATCH /api/applications/<id>/` | Update notes / resume |
| `POST /api/applications/<id>/status/` | Change status (`{"status": "APPLIED"}`) |
| `DELETE /api/applications/<id>/` | Delete |
| `GET /api/applications/dashboard/` | Dashboard aggregates |

## Security

Every query is `Application.objects.filter(user=request.user, ...)`. Consequences:

- A foreign `pk` returns **404, not 403**. The API never confirms that an id
  exists on another account, so it cannot be used to probe for one.
- `user` is not a serializer field at all. It is assigned by the view from
  `request.user`, so a `user_id` in the request body has nothing to bind to.
- `validate_job` and `validate_tailored_resume` reject references to rows the
  caller does not own, so a create cannot attach someone else's job.

### The duplicate bug worth remembering

The database had a `UniqueConstraint(user, job)`, but DRF only derives a
uniqueness check from `unique_together`. A second application for the same job
therefore passed validation and blew up as an `IntegrityError` — a **500** for
what is really a **400**. `ApplicationSerializer.validate()` now checks for the
duplicate explicitly. A test pins this.

## Dashboard aggregates

`apps/applications/dashboard.py` computes the tiles from real rows:

- jobs total / scored
- applications total, per-status counts, active, interviews, offers
- resumes total, tailored count, has-master
- average match score — `Avg` ignores unscored jobs, so an unanalysed job does
  not drag the average toward zero
- the five most recent applications

An account with nothing tracked gets `0` and a `null` average. There are no
placeholder numbers.

`select_related("job", "tailored_resume")` on the recent list keeps it at one
query. A test asserts the query count is *constant* as rows grow — the honest
form of an N+1 check, since session and auth lookups make the absolute number
depend on the framework.

## UI

- **Job Details** — an Application panel: *Save Job* to start tracking, then a
  status select and *Mark as Applied*.
- **`/app/applications`** — status counters that double as filters, then the
  list with per-row status change, *Open Job*, resume download, and delete.

### Tailoring is not applying

Creating an application starts it at `SAVED`. Generating a tailored resume never
advances a status. Inferring otherwise would write a false "Applied" record
into the user's tracker, which is the kind of quiet inaccuracy this product
exists to avoid. There is a test for it.
