# ADR-004: Tailored resumes are new, immutable versions -- never edits

## Context

The product's promise is that the evidence behind a score and behind a generated
resume can be inspected afterwards. That promise breaks the moment a generated
result can overwrite the document it came from, or can be quietly replaced by a
later run: there is then nothing to compare against, and no way to answer "what
did I actually send to this employer?".

Three specific hazards exist:

1. Tailoring mutating the master resume. It is the input to every match score, so
   a write there would silently change every number the user has already seen.
2. A second tailoring overwriting the first, so a version the user already
   downloaded and sent disappears.
3. A result edited in the browser being saved as though the server had approved it.

## Decision

A tailored resume is a **new `Resume` row** of type `TAILORED` that points back at
its source, and it is never mutated in place afterwards.

```text
Resume (MASTER, is_master=True)          the input, never written by tailoring
   │
   ├── source_resume ───────────────┐
   └── ResumeProfile               │
                                   ▼
   generate → review payload → user approves → Resume (TAILORED)
                                                   │  source_resume → MASTER
                                                   │  source_job    → Job
                                                   │  ai_provider
                                                   │  tailoring_result {result, validation, source}
                                                   └─ AIRun.result_resume (which run produced it)
```

Rules:

- `resume_type=TAILORED` rows are created with `is_master=False`. The pipeline
  looks up its input with `filter(user=..., is_master=True)`, so a version can
  never become the thing it was generated from.
- Every generated artifact records provenance: source resume, target job,
  provider, prompt version (on the `AIRun`), the deterministic validation verdict,
  and the creation time. The validation verdict is stored *with* the result, so
  the reason a version exists is not lost when the code that produced it changes.
- **Saving re-validates.** The payload comes from the browser, so
  `save_tailored_resume` re-runs normalisation and the deterministic factual
  validator against the stored master before writing anything. A `rejected`
  verdict is an HTTP 422 with the violations and no row.
- Nothing is approved automatically. A generated result is a *proposal*; the row
  only exists after the user saves it, so "saved" already means "reviewed".
- `source` in the stored payload is re-derived from the master server-side, never
  taken from the request. A client cannot tell the server what its own original
  said.

## Alternatives considered

- **Mutate the master in place (with a backup field).** Rejected. A backup field
  makes the master's meaning depend on whether a run happened, and every existing
  query that reads the master would have to know which one it wanted.
- **One `Resume` with a version counter and full history in JSON.** Rejected. It
  makes the common path (list my resumes, download one) read a history blob, and
  a partial write corrupts every version rather than one row.
- **Store only the diff against the master.** Rejected. A diff is only meaningful
  while the base is unchanged, and the user can change the master at any time --
  which would retroactively change what an old version says.
- **An `approved` flag on the generated result, with unapproved rows stored.**
  Rejected as unnecessary state: an unapproved proposal has no reason to be a
  row, and a flag adds a state in which a user can see something that was never
  accepted.
- **A separate `TailoredResume` model.** Rejected. It duplicates every field of
  `Resume` (name, file, profile, ownership) and splits the list/download/serialise
  paths in two for no gain.

## Consequences

- A resume library accumulates rows. That is the honest shape of the data: each
  is a document that existed and may have been sent somewhere. Deletion is
  available and scoped to the owner.
- Deleting a master leaves its versions with a null `source_resume` instead of
  cascading. The artifact survives its provenance, which is the right way round
  for a document the user may have already sent.
- Document rendering happens on demand from the stored representation, so a
  version can never go stale after an edit in the same way a cached file would.
- `AIRun.result_resume` links a run to what it produced, which is what makes
  "which model generated the resume I sent?" answerable months later.
