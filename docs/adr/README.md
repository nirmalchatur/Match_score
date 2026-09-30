# Architecture Decision Records

One short record per decision that would be expensive to reverse, or that
somebody will otherwise re-litigate in a review.

Each record states the **Context** (what forced a choice), the **Decision**, the
**Alternatives considered** (including the ones rejected for being more
machinery than the problem deserves), and the **Consequences** -- the costs
accepted, not only the benefits.

| ADR | Decision |
| --- | --- |
| [001](ADR-001-modular-monolith.md) | Stay a modular monolith with eight bounded apps |
| [002](ADR-002-ai-provider-abstraction.md) | Keep the AI provider abstraction, with the deterministic engine as the source of truth |
| [003](ADR-003-long-running-job-boundary.md) | Persist long-running work as records; run it synchronously until scale demands otherwise |
| [004](ADR-004-resume-versioning.md) | Tailored resumes are new, immutable versions -- never edits |
| [005](ADR-005-ai-run-audit.md) | Record every AI operation as an `AIRun`, with no secrets and no payloads |
| [006](ADR-006-activity-record.md) | Record user-initiated actions as an append-only `ActivityEvent` |
| [007](ADR-007-application-service-layer.md) | Business logic lives in an application service, not in a view |
| [008](ADR-008-structured-operation-logging.md) | One structured log line per operation, through the standard logging tree |

The rules these settle are protected by tests in
`backend/apps/common/tests/test_architecture.py`, so a change that breaks one
fails CI rather than a review.
