# ADR-003: Persist long-running work as records; run it synchronously until scale demands otherwise

## Context

Several operations in TailorUp take longer than a comfortable HTTP request:

- AI resume tailoring -- **measured at 364 seconds** on a CPU-only machine with
  `llama3.1`. This is not a defect and not an edge case; it is the local default.
- Interview preparation, cover letter and recruiter email generation (planned).
- Large resume parsing, document generation, job ingestion and bulk analysis.

The obvious response is a task queue. Before adding one, some facts about this
deployment matter: it is a single Render web service against Render PostgreSQL,
there is no Redis instance, and the product has no requirement for work to
survive a deploy or to run on a schedule. A queue would add a broker, a worker
service, a result backend and a second failure mode, none of which the current
scale needs.

## Decision

Model long-running work as **records**, execute it **synchronously**, and keep the
two decisions separable so a worker can be added later without rewriting logic.

The state model, which any future driver must honour:

```text
PENDING → RUNNING → SUCCEEDED
                  ↘ FAILED
        ↘ CANCELLED
```

It is implemented today in `apps.ai.models.AIRun`, with the legal transitions
checked in code (`AIRun.VALID_TRANSITIONS`) rather than left to convention.
`PENDING → FAILED` is deliberately legal: a run that dies before it starts (no
provider configured, no key, no master resume) never reaches `RUNNING`, and
showing it as pending forever would hide a configuration problem behind a
spinner. A terminal row is immutable, and **a retry is a new row**, so the
history of a flaky provider stays visible instead of being overwritten.

Each record carries: owner, operation, status, created/started/completed
timestamps, duration, a failure *category* (never a free-text message), an error
*code*, the source objects, a result reference, and an attempt count.

Where the long operations live today:

| Operation | Record today | Execution |
| --- | --- | --- |
| Resume tailoring | `AIRun` (+ in-process progress) | synchronous, in the request |
| Job analysis | `Job.status` + `Job.pipeline_steps` | synchronous, in the request |
| Resume parsing | `Resume` row written on success | synchronous, in the request |

`apps.ai.progress` supplies the legibility that a queue would otherwise provide:
a bounded, per-user ring buffer of progress events that the tailoring screen
polls, so a slow run looks slow rather than broken.

## Alternatives considered

- **Celery + Redis (or RabbitMQ).** Rejected for this phase. It solves durability,
  retries and scheduling -- none of which is required yet -- at the cost of two
  new services on the deployment, a new failure mode ("queued and nothing is
  consuming"), a second log stream, and a contributor needing a broker to run
  the test suite. The reason is stated plainly: this is *deferral*, not a claim
  that a queue will never be needed.
- **Django-Q, Huey or RQ.** Same shape, fewer moving parts than Celery, still a
  broker and still a worker process. Rejected for the same reason.
- **A `django-q`-style app in-process worker thread.** Rejected. It hides a
  second execution context inside the web process, where it dies quietly on
  deploy and competes with request handling for CPU -- which, on a CPU-only
  host running inference, is the resource that matters most.
- **Return a 202 and do the work in `BackgroundTasks`-style detached mode.**
  Rejected for the current deployment. Render can recycle the instance, so
  "accepted" work would occasionally vanish with no record of it happening; a
  synchronous run that fails returns an error the user can see and retry.
- **Store the job state in the in-process progress buffer instead of a table.**
  Rejected. A buffer is per-process and dies with the worker; it cannot answer
  "what happened" afterwards, which is the actual requirement.

## Consequences

- A tailoring request holds a web worker for minutes. With multiple gunicorn
  workers a few concurrent tailorings can saturate the instance. This is
  documented rather than hidden, and the AI rate limits cap how many can be in
  flight per account.
- The progress buffer is per-process, so a poll can land on a different worker
  than the run and see nothing. Switching it to a shared cache is a configuration
  change, because every access goes through `apps.ai.progress`.
- Introducing a worker later becomes an implementation of the same contract: a
  driver that claims `PENDING` rows, calls the same
  `apps.resumes.services.tailoring_service` functions, and writes the same states.
  No business logic moves, because none of it is in the view (ADR-007).
- Retries are not implemented. `AIRun.attempts` exists so the column does not
  need a migration on the day they are, and so a first attempt is
  distinguishable from a tenth.
