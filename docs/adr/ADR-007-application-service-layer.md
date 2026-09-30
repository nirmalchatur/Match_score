# ADR-007: Business logic lives in an application service, not in a view

## Context

The tailoring endpoint had grown into the product's most complex code path, and
all of it was inside two `APIView.post` methods: resolving the master resume,
scoping the job lookup, deciding whether the job was usable, choosing a provider,
decrypting the caller's key *for that provider*, emitting progress events, running
the AI, validating the output, mapping failures onto status codes, and persisting
the artifact. Roughly 200 lines, in a file that is an HTTP module.

Two consequences were already visible. The rules could only be tested through a
request, so a test that wanted to check "a refused job id is not distinguishable
from a missing one" had to build a session, a resume, a job and a client. And the
logic could not be reused from anywhere but a request -- which is a problem the
moment ADR-003 is revisited and a worker needs to call it.

## Decision

Introduce one application service per flow, and keep views thin.

```text
APIView              auth, throttling, request parsing, error → HTTP
   ↓
service              ownership, provider + key resolution, audit, persistence
   ↓
domain               ResumeTailor · validators · MatchEngine · JDProfile
   ↓
ORM                  Resume · Job · AIRun · ActivityEvent
```

`apps/resumes/services/tailoring_service.py` is the worked example. It owns:

- `generate_tailoring(user, job_id) -> dict` -- the review payload, saved nothing.
- `save_tailored_resume(user, job_id, result, provider_name) -> (Resume, dict)` --
  re-validated, creates a new version.

and it defines its own error vocabulary (`TailoringError` and subclasses:
`ResumeMissing`, `JobMissing`, `JobDescriptionMissing`, `ResultMissing`,
`TailoringRejected`) carrying a machine `code` and a suggested HTTP status. The
view's whole job is now:

```python
try:
    payload = tailoring_service.generate_tailoring(request.user, request.data.get("job_id"))
except AITailoringValidationError as exc:   # 422 with the violations
    ...
except AIError as exc:                      # the AI layer's own mapping
    return _ai_error_response(exc)
except TailoringError as exc:               # a refusal the service named
    return _tailoring_error_response(exc)
return Response(payload, status=200)
```

Rules that keep this from becoming theatre:

1. **No HTTP inside a service.** No `Response`, no `status`, no `request`.
   `status_code` on an exception is a *suggestion* the API layer may override.
2. **No repository classes.** Django's manager already is one, and the querysets
   here are small and readable. An abstraction layer would add indirection and
   lose `select_related` and the scoped-lookup idiom the security model depends on.
3. **A service is not a bag of helpers.** It owns one flow end to end. When a
   second flow needs the same step, that is a signal it belongs in the domain
   layer (`apps/jobs/services`, `apps/ai`), which is where `MatchEngine`,
   `JDProfile` and `ResumeTailor` already live and stay.
4. **The audit is written by the service**, not by the caller, so the record
   cannot be forgotten by one entry point and present in another.

Where services exist today: `tailoring_service` (resumes),
`document_service` (resumes, rendering), `job_search` and `job_processor` (jobs),
`apps.ai.tailor` (the AI orchestration). Not everything needs one: a view with a
single scoped queryset and a serializer does not.

## Alternatives considered

- **Fat views with private helpers.** The status quo. Rejected because the flow is
  the product's riskiest code and it should be callable from a test without HTTP.
- **Fat models.** Rejected. `Resume.save()` doing provider resolution, key
  decryption and an audit write would make every path that touches a resume --
  including an admin edit -- run the AI flow.
- **A repository layer per model.** Rejected as abstraction for its own sake: it
  would wrap `objects.filter(user=...)` and hide exactly the idiom the tenant
  boundary depends on.
- **Command/handler classes with a dispatcher.** Rejected. Two flows do not
  justify a bus; functions with clear names are shorter and easier to follow.
- **Move the flows into `apps.common`.** Rejected. A tailoring is a resume
  concern; `apps.common` holds cross-cutting pieces only (ADR-001).

## Consequences

- The tailoring rules are testable without a request:
  `apps/ai/tests/test_airun.py` and `apps/common/tests/test_architecture.py` drive
  `generate_tailoring` directly, including the cross-tenant refusal.
- The API contract is unchanged. The response bodies are byte-for-byte what the
  views returned before, which is what the existing endpoint tests assert.
- There is now one obvious place for the next flow to add audit, progress or a
  retry, and one obvious place to look when a tailoring misbehaves.
- The layer is only as good as the discipline of not calling the ORM around it. A
  view that queries `Resume` directly for a tailoring input would put ownership
  back in the view; reviews and the architecture test are the guard.
