# AI resume tailoring — architecture

The end-to-end path, and the reasoning behind each boundary.

```
Master Resume (stored)          Job + JD (stored)
          |                            |
          +------ build_source_resume -+
                         |
                    TailoringRequest
                         |
                  apps.ai.factory  --(AI_PROVIDER)-->
                         |
                  AIProvider  ->  OllamaProvider / FakeAIProvider
                         |
                   raw text (JSON, fenced, or prose-wrapped)
                         |
               schemas.parse_tailoring_response
                         |  tolerates fences/prose, normalises shape
                    TailoringResult
                         |
               validators.validate(result, source)
                         |
                valid | warning | rejected
                         |
            rejected --raise-->  HTTP 422
            warning/valid ------>  before/after review UI
                         |
              POST /resumes/tailor/save/  (re-validated)
                         |
             new Resume(resume_type=TAILORED)
```

## Layers

| Module | Responsibility |
|---|---|
| `apps/ai/factory.py` | Maps `AI_PROVIDER` to a provider class. The only module that knows the set of providers. |
| `apps/ai/providers/base.py` | `AIProvider` interface and the `TailoringRequest` payload. |
| `apps/ai/providers/ollama.py` | The **only** module that knows Ollama exists: URLs, `/api/chat`, `stream`, `format`, health. |
| `apps/ai/providers/fake.py` | Deterministic in-process double for tests and CI. |
| `apps/ai/prompts.py` | Prompt text and the `FACTUAL_INTEGRITY_RULES` list. Provider-agnostic. |
| `apps/ai/schemas.py` | Defensive parsing and normalisation into `TailoringResult`. |
| `apps/ai/validators.py` | Deterministic factual checks. No model, no NLP. |
| `apps/ai/tailor.py` | `ResumeTailor`: orchestration only. No HTTP, no model name, no provider type. |
| `apps/resumes/views.py` | Auth, ownership, error-to-HTTP mapping, persistence. |
| `apps/resumes/services/document.py` | Resolves profile + approved tailoring into one renderer-agnostic model. |
| `apps/resumes/services/docx_generator.py` | ATS-friendly DOCX via python-docx. |
| `apps/resumes/services/pdf_generator.py` | ATS-friendly PDF via reportlab. |
| `apps/resumes/services/document_service.py` | Single entry point the views call. |

### Provider independence

`ResumeTailor` receives an `AIProvider` (or fetches one from the factory) and
only calls `tailor_resume(request) -> str`. Adding a hosted provider is:

```python
# apps/ai/providers/openai.py
class OpenAIProvider(AIProvider):
    name = "openai"
    ...
```

```python
# apps/ai/factory.py
_BUILTIN["openai"] = OpenAIProvider
```

No change to `tailor.py`, `validators.py`, or the views. This is asserted by
`ProviderIndependenceTests`, which drives the service with a custom provider and
checks the input it received.

## Why validation is separate from the schema

`schemas.py` validates **shape**: types, required keys, usable ids. It is
deliberately forgiving, because local models emit fences, prose and trailing
commas and a strict parser would reject usable output.

`validators.py` validates **truth**: does every claim trace back to the source
resume? It is deliberately strict, because a confident fabrication is the worst
possible outcome for a resume tool.

Keeping them apart means both stay independently testable, and a parse failure
(`AIProviderResponseError`) is never confused with a factual failure
(`AITailoringValidationError`).

## The three verdicts

| Verdict | Meaning | API behaviour |
|---|---|---|
| `valid` | Every claim traces to the source. | 200, review shown. |
| `warning` | Suspicious but explicable (an unknown proper noun, a figure reused from another role). | 200, review shown with a "needs review" badge. |
| `rejected` | The source does not support a claim. | 422, nothing returned as a suggestion. |

`rejected` is sticky: one hard fabrication sinks the whole result.

### What is checked

`REJECTED` — unambiguous fabrications:

- `fabricated_metric` — a figure absent from the resume
- `fabricated_technology` — a catalog skill absent from the resume
- `fabricated_certification` — a credential the resume never lists
- `changed_date` — an employment or education date not in that entry
- `unknown_entry_id` — an entry id that does not exist
- `unsupported_skill_emphasis` — emphasising a skill the resume lacks
- `unsupported_requirement_claimed` — writing a bullet for a requirement the model itself called unsupported

`WARNING` — genuinely uncertain, surfaced for a human:

- `unknown_name` — a capitalised token absent from the source (a heuristic, never an auto-reject)
- `changed_education` — a degree the education section does not contain
- `metric_moved_between_entries` — a figure that exists but under a different role
- `original_mismatch` — the model echoed different originals than the ones on file
- `unknown_deemphasised_skill` — de-emphasising something the resume lacks

### Deliberate non-goals

- No embeddings, no semantic similarity, no learned classifier.
- No automatic repair: rejected output is discarded, not silently patched.
- A proper-noun check that cannot be certain never blocks a result.

## Traceability

Entry ids (`exp-0`, `proj-0`) are minted deterministically by
`build_source_resume` from the stored profile, and the model echoes them back.
That is what lets the review UI pair each tailored bullet with its original.

**The originals rendered in the UI come from our database, not the model's
echo.** The echo is checked against the stored copy (`original_mismatch`) and
discarded. A model cannot rewrite history by claiming a bullet it invented was
the original.

## Versioning

`Resume` already had `resume_type` (`MASTER` / `TAILORED`). This slice extends
it minimally with `source_resume`, `source_job`, `tailoring_result` and
`ai_provider`, and makes `file` optional so a tailoring is a first-class resume
before a document generator exists.

```
User
 ├── Master Resume                       (resume_type=MASTER, is_master=True)
 ├── Tailored Resume - Acme / BE         (TAILORED, source_resume=master, source_job=Acme)
 ├── Tailored Resume - Beta / Platform   (TAILORED, source_resume=master, source_job=Beta)
 └── Tailored Resume - ...
```

The master is never written to by the tailoring flow. `SaveTailoredResumeView`
**re-validates** the submitted result against the current master before writing,
so a payload edited in the browser cannot persist content the validator would
have rejected.

## API

| Endpoint | Purpose |
|---|---|
| `POST /api/resumes/tailor/` | Produce a review payload. Sends `{job_id}` only. Saves nothing. |
| `POST /api/resumes/tailor/save/` | Persist a reviewed result as a new version. Re-validated. |
| `GET /api/resumes/tailor/status/` | Is tailoring configured? Lets the UI disable the button. |

The request carries an **id**, never content. The resume, job description, JD
profile and match analysis are all loaded server-side from the caller's own rows,
so there is no id-guessing path across tenants.

### Error mapping

| `code` | HTTP | Meaning |
|---|---|---|
| `ai_unavailable` | 503 | Daemon not running |
| `ai_timeout` | 504 | Too slow |
| `ai_not_configured` | 500 | `AI_PROVIDER` unset or unknown |
| `ai_invalid_response` | 502 | Unreadable model output |
| `ai_validation_failed` | 422 | Fabricated content, discarded |
| `resume_missing` | 404 | No master resume |
| `job_missing` | 404 | Job not found **or not owned by this account** |
| `result_missing` | 400 | Save called without a result |

Only the public `message` is returned. `detail` (base URL, model name, raw
response) is logged server-side and never sent to the browser.

## Document generation

The model produces *tailoring suggestions* and nothing else. Layout is
deterministic code:

```
Stored profile + user-approved tailoring
        |
   build_document()          apps/resumes/services/document.py
        |
   ResumeDocument            one resolved model
        |
        +--> ResumeDocxGenerator (python-docx)
        +--> ResumePdfGenerator  (reportlab)
```

`build_document()` is the single point where a suggestion becomes content, which
is what guarantees the two formats match. It also enforces the no-invention rule
structurally: education and certifications come only from the stored profile,
skills are intersected with the source list, and an emptied entry falls back to
its originals rather than disappearing.

Documents are rendered on demand rather than cached, so a saved file can never
go stale after an edit.

## Known limitations

- **No document generation.** There is no DOCX/PDF generator in the codebase, so
  a saved tailoring is a structured `Resume` with no file attached. The flow is
  ready for one: validated JSON is already stored in `profile_data`.
- **Proper-noun detection is a heuristic.** It produces warnings, not rejections,
  because a wrong rejection would block legitimate tailoring.
- **The projects section is flat text.** `ResumeProfile` stores it unstructured;
  `_split_projects` recovers blocks with a simple, deterministic rule.
- **No summary field exists.** `ResumeProfile` has no summary, so summary
  tailoring works from an empty source and is validated against the whole resume.
- **No document download was verified against a real user's file.** Rendering is
  covered by unit and API tests against fixtures.
- **Ollama is not exercised in CI.** `test_ollama_provider.py` runs a local stub
  that speaks Ollama's wire format, which covers the transport but not a real
  model's output quality.
