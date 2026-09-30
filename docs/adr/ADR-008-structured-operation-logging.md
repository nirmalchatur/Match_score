# ADR-008: One structured log line per operation, through the standard logging tree

## Context

Every module already logged, and each invented its own shape:
`ai.tailor_start provider=ollama experience=3`, `resume.render_failed resume=12
fmt=pdf`, and a dozen variations on the same three fields. That is readable by a
person and useless to a filter, so questions the deployment can already answer --
"how long did tailoring take yesterday", "which provider was failing at 14:00" --
could not be asked without knowing every spelling of every field.

The operations worth measuring are few and known: tailoring (request and save),
job analysis, document rendering. A tailoring run is measured in minutes on CPU,
so duration is not a nice-to-have: it is the number that distinguishes "the
product is slow" from "the product is broken".

The other half of the problem is what must *not* be logged. This code path handles
provider API keys and whole resumes, and a structured logger makes it natural to
write `log_operation(..., api_key=key)`.

## Decision

Add `apps/common/observability.py` with one line format, one logger name, and
redaction applied inside the helper rather than trusted to the call site.

```text
initializing
operation=resume_tailoring outcome=ok duration_ms=14203 provider=ollama model=llama3.1 validation=valid user=7
```

Three rules, each enforced by a test in
`apps/common/tests/test_observability.py`:

1. **Redaction is not optional.** A field whose *name* matches
   key/secret/token/password/credential/authorization/cookie/session/prompt is
   written as `[redacted]`, and so is any value shaped like a real credential
   (`AIza…`, `gsk_…`, `sk-…`, `eyJ…`). A container value reports its size rather
   than its contents, so a resume dict cannot be printed by accident.
2. **Logging cannot break the operation.** `log_operation` never raises: it is
   called on the success path of real work, and a broken log sink must cost a log
   line, not a response.
3. **No new platform.** Lines go to the standard `logging` tree under one name,
   `tailorup.operations`. Render already collects stdout; there is no hosted
   observability service, and none is needed for a single web service.

`OperationTimer` is the ergonomic form and exists for the failure path
specifically: a `try/finally` in every caller is the code that gets forgotten on
the branch nobody tests, and the slow, failing operation is the one an operator
most needs a duration for. It logs the exception *class*, never its message,
because a provider error message carries the base URL and the response body.

What is never logged: API keys, passwords, session cookies, resume contents,
provider response bodies.

## Alternatives considered

- **Leave each module's logging as it is.** Rejected. The formats already
  disagreed, and the next module to log would have invented a fourth.
- **Structured JSON logs.** Rejected for now. One web service, one log stream, and
  a human reading `render`'s log view is the actual consumer. JSON would be the
  right shape if a log platform were ingesting them; adding it before there is one
  trades readability for nothing.
- **OpenTelemetry, Sentry or a hosted APM.** Rejected for this phase. Each adds a
  dependency, an account, a second place errors are visible, and -- for tracing --
  per-request overhead, to answer questions the operation line already answers at
  this scale. This is the concrete-problem test from the architecture gate, and
  the honest answer is that the problem is not yet big enough.
- **A decorator that instruments every view.** Rejected. Most views are a scoped
  query and a serializer; instrumenting them produces noise and dilutes the signal
  in the lines that matter. Operations are logged deliberately, where they mean
  something.
- **Redaction at the call site.** Rejected. The field *name* is the only thing
  between a credential and a log aggregator that keeps it for a year, and call
  sites are exactly where that gets forgotten.

## Consequences

- Duration, provider, model, validation verdict and outcome are queryable for the
  operations that matter, and the same fields appear in the `AIRun` row so a log
  line and an audit row can be correlated by user and operation.
- There is no alerting. A threshold ("tailoring slower than 10 minutes") is a
  deployment-platform feature and would be configured there, not in code.
- Redaction is by name and by shape, so an unusually-shaped credential passed under
  an innocent name would still be logged. That gap is accepted and is why the
  audit *table* (ADR-005) never receives credential values at all: the table, not
  the log, is the record of truth.
- If JSON logs or a hosted platform are added later, the change is in one module,
  because every call site goes through `log_operation` and `OperationTimer`.
