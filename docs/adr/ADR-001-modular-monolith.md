# ADR-001: Stay a modular monolith with eight bounded apps

## Context

TailorUp is one Django project and one React SPA, deployed as two services: a
Vercel static bundle and a Render web service against Render PostgreSQL. There
is one team, no separate release cadence per feature, and traffic measured in
requests per minute rather than thousands per second.

Phase 1A asked for a maintainable architecture. The fashionable reading of that
is to split the backend along its seams -- an AI service, a resume service, a job
ingestion service -- and give each its own deployment. Before doing that it is
worth writing down what is actually shared: every request is authenticated by one
Django session, every row belongs to one user, and the AI work is *on* the same
resume and job rows the rest of the API reads. The seams are real, but they are
inside a single transaction boundary, not across a network one.

## Decision

TailorUp stays a modular monolith. The backend keeps one Django project and
eight apps with explicit ownership:

| App | Owns |
| --- | --- |
| `apps.ai` | provider abstraction, orchestration, schemas, validators, the `AIRun` audit |
| `apps.resumes` | parsing, profiles, master and tailored versions, document generation |
| `apps.jobs` | sources, normalisation, JD parsing, `MatchEngine`, skill normalisation |
| `apps.applications` | pipeline lifecycle and application analytics |
| `apps.automation` | in-app notifications and their preferences |
| `apps.users` | authentication, profile, encrypted provider credentials, sessions |
| `apps.common` | shared errors, throttling, the activity record, observability |
| `apps.sheets` | spreadsheet import |

The rules that keep it modular rather than merely monolithic:

1. An app owns its models. Another app reads them through a service function or
   a documented query, never by reaching into the internals of `models.py`.
2. Cross-domain work gets an **application service** (ADR-007), not a view that
   calls four other apps.
3. Dependencies point one way where a direction exists at all. The clearest case:
   `apps.jobs.services.match_engine` must not import `apps.ai`, because a
   deterministic score that depends on a generative layer is not deterministic.
   This is asserted in `test_architecture.py`.
4. `apps.common` holds cross-cutting pieces only. It is deliberately not a
   `utils` package: nothing is added there merely because no other app obviously
   owns it.

## Alternatives considered

- **Microservices per app.** Rejected. It would turn one indexed query into a
  network call, replace a `transaction.atomic()` block with distributed
  compensation, and require service-to-service authentication that does not
  exist today. The concrete problems it solves -- independent scaling, isolated
  failures -- are not problems TailorUp has at this scale. It would also mean
  running and paying for several always-on services instead of one.
- **A `core`/`utils` app for everything shared.** Rejected. This is how a
  modular monolith becomes a monolith with better marketing: the shared app
  accumulates logic nobody owns, and its test coverage drifts behind.
- **A separate service for AI only.** Rejected for now, and revisited in
  ADR-003. The provider call is long-running but it reads the caller's own rows
  and runs in the request that needs the answer; the boundary is drawn as a
  *service class* inside the app instead.
- **One app per feature.** Rejected. New features are columns, services and
  endpoints far more often than they are bounded domains, and a new app per
  feature multiplies migrations and models without adding isolation.

## Consequences

- Everything ships together, so a change to `MatchEngine` cannot be deployed
  independently of the API that exposes it. Accepted: it is one team.
- The transaction boundary is a database transaction, which is worth keeping.
  A tailoring run and the artifact it produces can be written atomically, which
  a distributed design would have to reason about explicitly.
- Discipline replaces the network as the boundary. There is nothing physically
  stopping `apps.resumes` from importing `apps.jobs.models`, so the boundary is
  enforced by convention plus the boundary tests in
  `apps/common/tests/test_architecture.py`.
- Scaling is vertical and then horizontal-replica, not per-service. If one part
  of the product ever needs to scale on its own, that is the moment to revisit
  this record -- with a measured reason, not a diagram.
