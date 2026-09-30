# ADR-005: Record every AI operation as an `AIRun`, with no secrets and no payloads

## Context

Before this record, a tailoring run left no durable trace. `ResumeTailor` returned
a review payload and everything else was discarded: which provider answered,
which model, whether the factual validator approved the output, how long it took,
and how it failed. If a user reported "the AI produced something wrong" or
"tailoring just does not work", the only evidence was a log line that had already
scrolled away -- and the two most common failures (no provider configured; the
daemon not reachable) are indistinguishable from the browser.

Meanwhile the risk of *over*-recording is specific and serious: this is the code
path that handles API keys and whole resumes. An audit table is an obvious place
for both to end up by accident.

## Decision

Every AI operation writes one `AIRun` row, inside `apps.ai.models`, around the
provider call.

What is recorded, and why each field is safe:

| Field | Content | Why it is safe |
| --- | --- | --- |
| `user` | the owner | the tenant boundary |
| `operation` | `RESUME_TAILORING` | a closed choice set |
| `provider`, `model` | `"gemini"`, `"gemini-2.0-flash"` | identification, never a URL or a key |
| `status` | `PENDING`/`RUNNING`/`SUCCEEDED`/`FAILED`/`CANCELLED` | see ADR-003 |
| `failure_category` | a bucket, from a closed set | answers "why did AI fail this week" without reading messages |
| `error_code` | `"ai_timeout"` | the machine code the API returned; a *code*, never a message |
| `prompt_version` | `"tailoring-1"` | a version token, not a prompt |
| `validation_status` | `valid` / `warning` / `rejected` | the deterministic verdict |
| `source_resume`, `source_job` | nullable FKs | what it read; survives deletion |
| `result_resume` | nullable FK | what it produced, once saved |
| `attempts` | `1` | a retry gets its own row (ADR-003) |
| `usage` | counters only | never a prompt, never a response body |
| timestamps, `duration_ms` | | the cost of the operation |

What is deliberately **not** recorded: the API key, the prompt, the raw provider
response, the resume text. A stored response would be a second copy of the user's
resume in a table nobody asked for, and a stored prompt would be the same problem
with the added attraction of holding the credential in some providers' payload
shapes.

Two mechanisms enforce this rather than relying on review:

- The writer (`apps.ai.runs.AIRunRecorder`) never passes a credential to a field,
  and only takes identity from `provider.describe()`, which is already documented
  as non-secret and is the same object the status endpoint exposes.
- `AIRun.public_dict()` defines the *only* shape any future endpoint may return,
  and `apps/common/tests/test_architecture.py` asserts that no field on the model
  is named like a secret and that no stored credential appears in any column of a
  row produced by a real run.

## Alternatives considered

- **Log only, no table.** Rejected. Logs are disposable, unqueryable by user, and
  cannot answer "why was this specific result generated" after the retention
  window.
- **Store the raw provider response for debugging.** Rejected. It is a copy of
  personal data with no retention story, and the parse failure it would help
  debug is already reported as `AIProviderResponseError` with a truncated body in
  the server log.
- **Store the full prompt.** Rejected for the same reason, and because the prompt
  embeds the resume.
- **Attribute runs to the provider rather than the user.** Rejected: the question
  that gets asked is about a user's result, and `user` is the tenant boundary
  every other table already uses.
- **A generic `AuditLog` for AI, jobs and applications at once.** Rejected at this
  stage. The three have genuinely different shapes (an AI run has a provider and a
  verdict; an application has a status transition), and one wide table with mostly
  null columns answers none of them well. See ADR-006 for the narrower claim the
  activity record makes.
- **A separate `AIUsage` table for token counts.** Rejected. `usage` is a JSON
  field that may stay empty; a table for a metric nothing reads yet is exactly the
  dead code this project avoids.

## Consequences

- Every tailoring -- including the failures, which are the useful ones -- is
  answerable afterwards, with a duration and a bucket.
- A failed run is genuinely distinguishable from a successful one: a rejected
  result is `FAILED`/`VALIDATION_FAILED`, never `SUCCEEDED` with no artifact.
- There is no API surface for `AIRun` yet. The rows are read through Django admin
  and by tests; the read endpoint is a later phase's decision, and this record is
  the reason that is a small change rather than an archaeology exercise.
- The write is best-effort and guarded. If the insert fails, the tailoring still
  succeeds and the failure is logged -- the audit is evidence, not a gate.
