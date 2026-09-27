# AI setup

## Two ways to run the model

| | Local | Hosted |
| --- | --- | --- |
| Provider | Ollama | Google Gemini |
| Setting | `AI_PROVIDER=ollama` | `AI_PROVIDER=gemini` |
| Key | None needed | **The user's own**, via Settings |

A web host cannot run an Ollama daemon, so a deployed instance uses Gemini. Both
paths go through the same `AIProvider` interface, so the rest of the app does not
know which is in use.

---

## Bring your own Gemini key

There is deliberately **no `GEMINI_API_KEY` server variable**. Every user pastes
their own free key into **Settings → AI**, and it is stored encrypted. That means:

- the owner's quota is never spent on someone else's tailoring, and
- there is no shared secret on the server to leak.

```bash
AI_PROVIDER=gemini
GEMINI_MODEL=gemini-2.0-flash   # optional, this is the default
GEMINI_TIMEOUT=120              # optional
```

### Where a stored key lives

`apps/users/models.py` → `ProviderCredential`, one row per (user, provider).

- `encrypted_key` — a Fernet token. **Never** the plaintext. The encryption key
  is derived from `SECRET_KEY` via SHA-256 (`apps/users/crypto.py`), so there is
  no second secret to provision.
- `key_hint` — a 4+4 mask like `AIza...4f2b`, so a user with two keys can tell
  them apart. Eight characters cannot reconstruct a 39-character key.

### The rules the code enforces

1. **No endpoint returns a key.** `GET /api/auth/ai-key/` reports
   `configured: true/false` and the hint. There is no reveal route — it would
   put the value in a browser cache and every proxy log on the path.
2. **A key never enters a prompt.** `TailoringRequest.to_payload()` omits
   `api_key`, and the payload is what gets serialised into the prompt.
3. **A key is decrypted only at call time**, inside the tailoring view, and the
   decrypted string is not logged.
4. **Signing out deletes it.** `POST /api/auth/logout/` removes the caller's rows
   — scoped to that account, so nobody else's key is touched.

### Rotating `SECRET_KEY` invalidates stored keys

Because the encryption key is derived from `SECRET_KEY`, rotating it makes every
stored key undecryptable. This fails **loudly and safely**: the unreadable row
is deleted and the user is told to re-paste. There is no silent fallback to
plaintext. Render's `generateValue: true` generates the secret once and keeps it,
so redeploys are unaffected — but treat it as effectively permanent once users
have saved keys.

### What this does not protect against

Encryption at rest defends a stolen database dump or backup. It does **not**
defend against code execution on the web host, where the running process can
decrypt any user's key. That is inherent to persisting a credential server-side.
Users can remove their key at any time, and it is removed on sign-out.

---

# Local: Ollama

> ## Verification status: PENDING
>
> **Ollama is now installed on the development machine** (`ollama` 0.34.4, daemon
> reachable on `:11434`), and `llama3.1` is the intended model.
>
> What remains unverified: an actual TailorUp tailoring request executed against
> the real model. Until that has run and its output is recorded here, this project
> makes **no claim** that a real model round-trips end to end.
>
> What **is** verified today:
>
> - The full pipeline against `FakeAIProvider` (the entire test suite).
> - The Ollama HTTP **transport**: `apps/ai/tests/test_ollama_provider.py` runs a
>   local stub that speaks Ollama's wire format, covering the request we build,
>   the envelope we read, and every failure mapping (404 -> "run ollama pull",
>   5xx -> 503, slow -> 504, empty/garbage -> 502, and that `describe()` never
>   leaks the base URL).
>
> Neither proves a real model's output quality. Close this out by following steps
> 1-5 below, then the manual check at the end of this file.

Ollama needs no API key, so the Settings key form does not appear when
`AI_PROVIDER=ollama` — there would be nothing for the user to paste.

```bash
# Install once: https://ollama.com/download
ollama serve
ollama pull llama3.1
```

```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1
```

---

# Resume documents (DOCX and PDF)

## What generates them

Deterministic application code. **The LLM never lays out a document.**

```
Stored master resume profile
      +
User-approved tailoring result
      |
      v
ResumeDocument              apps/resumes/services/document.py
      |
      +--> ResumeDocxGenerator   (python-docx)
      +--> ResumePdfGenerator    (reportlab)
```

`build_document()` resolves the stored profile plus the approved tailoring into
one fully-resolved model. Both renderers consume *that same object*, which is
what makes the two formats provably equivalent rather than merely similar — a
regression test asserts it.

## The no-invention rule

`build_document()` never takes `education`, `certifications` or contact details
from the AI:

- Education and certifications are copied from the stored profile, always.
- Skills are intersected with the source skill list, so emphasis reorders but
  can never add a skill the candidate does not have.
- Contact links are *extracted* from the resume text, never generated.
- A rejected suggestion falls back to the original bullet, so rejecting
  everything reverts a section instead of blanking it.

## ATS-friendly by construction

- Single column, no tables, no text boxes, no columns, no images.
- Real heading styles and plain paragraphs.
- PDF bullets use an ASCII hyphen. A U+2022 bullet is emitted from a
  symbol-encoded font and extracts as `\x7f` in common PDF text extractors,
  which is exactly what an ATS parser reads. There is a test asserting no
  garbage glyphs appear in the extracted text.

## Endpoints

| Endpoint | Returns |
|---|---|
| `GET /api/resumes/<id>/download/docx/` | The resume as a `.docx` attachment |
| `GET /api/resumes/<id>/download/pdf/` | The resume as a `.pdf` attachment |

Both are authenticated and scoped to the owner: the lookup is
`Resume.objects.filter(user=request.user, pk=pk)`, so another account's resume
returns **404**, not 403 — the response never confirms that an id exists. The
`Content-Disposition` filename is derived from the resume's own name, sanitised,
and no filesystem path is ever disclosed. Responses are `Cache-Control: private,
no-store`.

## Review, edit, save, download

1. Open a job and choose **? Tailor My Resume**.
2. Review each section: **Original** vs **AI suggestion**, with *Why this changed*.
3. Per bullet: **Accept**, **Edit** (your own wording), or **Reject** (falls back
   to the original). The summary is freely editable. Nothing is auto-approved.
4. **Save as a new resume** — the master is never overwritten. The saved row
   records `source_resume`, `source_job`, `ai_provider`, the validation verdict
   and the re-derived `source` view, so a version can always explain itself.
5. **Download DOCX** / **Download PDF** appear immediately, and again in the
   Resume Workspace.

User edits are re-validated on save. A hand-edited bullet that introduces a
fabricated figure is rejected with `422` — the backend is not a rubber stamp.

---

# Verifying a real tailoring request

Once Ollama is installed, this exercises the genuine path end to end.

1. Start the daemon and pull a model (steps 1-5 above).
2. Configure `backend/.env`:

   ```dotenv
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   OLLAMA_MODEL=llama3.1
   ```

3. Confirm the provider is healthy:

   ```bash
   cd backend
   python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from apps.ai import factory;print(factory.get_ai_provider().health())"
   ```

4. Upload a master resume, analyse a job, then from the job page click
   **? Tailor My Resume**.

What to look for:

| Outcome | Meaning |
|---|---|
| `ai_unavailable` | Daemon not running, or the model is not pulled |
| `ai_timeout` | Model too slow — raise `OLLAMA_TIMEOUT` or use a smaller model |
| `ai_invalid_response` | The model did not return readable JSON |
| `ai_validation_failed` | The model changed a fact. Working as designed. Lower `OLLAMA_TEMPERATURE` or use a larger model. |
| A review screen with a "needs review" badge | The output was usable but flagged. |

A `422` is the validator doing its job, not a failure of the setup. Re-running
with a lower temperature is the right response, not bypassing the check.

To see the raw provider round-trip without the HTTP layer:

```bash
cd backend
AI_PROVIDER=ollama OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=llama3.1 \
  python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from apps.ai import factory;from apps.ai.providers.base import TailoringRequest;from apps.ai.tests.fixtures import SOURCE_PROFILE;from apps.ai.tailor import ResumeTailor;print(ResumeTailor.tailor_resume(SOURCE_PROFILE, {'title':'Backend Engineer','company':'Acme','description':'Django and PostgreSQL.'}, {'score':80}).as_dict()['validation'])"
```

