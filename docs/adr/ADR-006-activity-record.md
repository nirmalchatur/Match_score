# ADR-006: Record user-initiated actions as an append-only `ActivityEvent`

## Context

Three tables already sit close to this problem, and none of them is it:

- `apps.users.security.SecurityEvent` -- authentication events only. Its own
  docstring says so, and it carries columns (`user_agent`, `is_current_session`)
  that exist purely to render the security page.
- `apps.automation.models.Notification` -- user-facing, suppressible by
  preference, and de-duplicated on a natural key. It is a *view* of events, not a
  record of them: a user who turns notifications off still performed the actions.
- `apps.ai.models.AIRun` -- one provider call, which is an implementation detail
  of one action rather than the action itself.

So a support question like "this person's match score changed yesterday, what did
they do?" or "when was this account's master resume last replaced?" had no
answer, and a system like that cannot be operated without reading logs.

## Decision

Add `apps.common.models.ActivityEvent`: one append-only row per user-initiated
product action, owner-scoped like every other table.

```text
User
 └── ActivityEvent (user, action, object_type, object_id, summary, metadata, created_at)
```

Recorded actions, a closed set:

| Action | Written by |
| --- | --- |
| `RESUME_UPLOADED` | the resume upload endpoint, after the parse succeeds |
| `MASTER_RESUME_CHANGED` | the set-master endpoint |
| `JOB_ANALYSED` / `JOB_ANALYSIS_FAILED` | the job analysis endpoint |
| `TAILORING_GENERATED` | `tailoring_service.generate_tailoring` |
| `TAILORING_SAVED` | `tailoring_service.save_tailored_resume` |
| `APPLICATION_CREATED` | the application create endpoint |
| `APPLICATION_STATUS_CHANGED` | the status endpoint, only on a real transition |

Decisions about the shape:

- **Append-only.** No update path, no `updated_at`. A record whose history can be
  rewritten is not evidence of anything. The Django admin registration is
  read-only for the same reason.
- **`object_id` is an integer, not a foreign key.** An activity record must
  outlive the row it describes; a cascade would punch holes in the history
  exactly when a user deletes something and wants to know what happened.
- **`summary` is one line, capped.** It names the action, not its content: the
  record answers "a resume was uploaded", not "here is the resume".
- **Metadata holds identifiers and counts only.** Keys that name a secret are
  dropped entirely (not masked -- a `[redacted]` marker promises that something
  was there), and values that are not scalars are dropped, because a nested
  structure is a payload and a payload here would eventually be a resume. The
  judgement reuses `apps.common.observability.is_sensitive_name`, so the log
  redactor and this recorder cannot disagree about what a secret looks like.
- **No `request` argument**, unlike `SecurityEvent.record`. This record has no
  client-context columns, and the values a request would contribute (a user agent,
  an IP) are attacker-controlled input with no use in a product history.
- **Writing never raises.** Each call site is an action that has already
  succeeded. Failing the request because a bookkeeping row failed would trade a
  real result for something the user never asked for, so the failure is logged
  instead.

## Alternatives considered

- **A distributed event bus (Kafka, RabbitMQ, an `Outbox` + consumer).** Rejected.
  There is one consumer, it is the same process, and the events are read by a
  person or a query. A bus would add operational surface for a table insert.
- **Extend `SecurityEvent` to hold product events.** Rejected. Its columns and
  its read path belong to the security page, and mixing "signed in from a new
  device" with "uploaded a resume" makes the one list where unusual activity
  should stand out harder to read.
- **Reuse `Notification` as the history.** Rejected. Preferences and de-duplication
  are features of a *notification*; neither should be able to erase the fact that
  an action happened.
- **A row per field change (a generic change-log / audit trigger).** Rejected. It
  produces a volume of rows nobody reads, requires a diffing strategy per model,
  and cannot carry intent (an endpoint knows *why* a change happened; a database
  trigger does not).
- **`django-simple-history` or `django-auditlog`.** Rejected. Full row snapshots
  per model are the most expensive version of this, and they store the row's
  content -- resumes and job descriptions -- in an audit table, which is the
  opposite of the constraint above.

## Consequences

- Support and debugging questions about a specific account are answerable with one
  indexed query (`(user, -created_at)`).
- The table grows with usage and has no retention policy yet. The index and the
  per-user pagination shape are in place for the day one is needed; storing less
  (no payloads) is what keeps the growth proportional to actions rather than to
  documents.
- There is **no read API in this phase**. Writing without reading is a deliberate
  trade: the rows are needed now (they explain an incident), and inventing an
  endpoint would have forced frontend types and UI work that the phase did not
  include. Rows are readable in Django admin, asserted by tests, and the read
  surface is a later phase's decision on the same data.
- The same event stream is the natural feed for future notifications and analytics
  -- which is why the action set is closed and machine-readable now, rather than
  free text that would have to be normalised later.
