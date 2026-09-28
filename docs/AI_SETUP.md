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
GEMINI_MODEL=gemini-3.8-flash   # optional, this is the default
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

---

## Verified local run

Recorded rather than asserted. Chain, in order, with nothing mocked:

    provider factory -> OllamaProvider -> llama3.1 (real weights)
      -> extract_json -> schema normalise -> factual validation

| stage | result |
|---|---|
| provider | `ollama`, model `llama3.1` |
| health | True - Ollama is running and 'llama3.1' is installed. |
| generation | raw response in **364.0s**, 1614 chars |
| schema | parsed `TailoringResult` |
| factual validation | `status='valid'`, no violations |

Environment: llama3.1 8B, Q4_K_M, CPU inference, no GPU.

Two things worth knowing before deploying:

- **364s is the real number on CPU.** Usable, not interactive. The default
  `OLLAMA_TIMEOUT` of 180 will time out on hardware without a GPU; raise it.
- **`size_vram: 0`** -- the model ran entirely from system RAM.

The validation verdict is the result that matters. The product promise is that
the AI cannot invent resume facts, and the factual validator raised no
violations on a real model response rather than a stub.

---

# Running a provider on deployed infrastructure

The obstacle is specific and worth stating plainly. `OLLAMA_BASE_URL` defaults to
`http://127.0.0.1:11434`. On Render, `127.0.0.1` means *the Render container
itself*, and no Ollama runs there. Your laptop's daemon is not reachable from
there, so a deployed TailorUp cannot use the `ollama` provider as configured.

There are two supported ways out. Both are configuration only -- no code
change is required for either, and that is deliberate. The provider reads its
settings from the environment, and the Gemini provider takes its credential
per-request from the user rather than from the server.

## Which to choose

| | Gemini BYOK | Tunnel to local Ollama |
| --- | --- | --- |
| Works when your PC is off | yes | **no** |
| Needs a secret on Render | no (the key is per-user) | no |
| Cost to you | user's own free tier | free |
| Data leaves the machine | yes | no |
| Setup effort | one env var | env var + a tunnel left running |

Use **Gemini BYOK** for a site real users hit. Use the **tunnel** for
development, or for keeping inference on your own hardware. They are not
mutually exclusive: set the env var per environment.

## 1. Gemini BYOK (recommended for deployment)

There is deliberately **no server-wide `GEMINI_API_KEY`**. The provider reads
the key from the caller and sends it as an `x-goog-api-key` header, so nothing
secret is configured on Render and no shared credential exists to leak.

1. In **Render**, set one environment variable:

   ```
   AI_PROVIDER=gemini
   ```

2. Redeploy. Nothing else is required.

3. Each user pastes their own key in **Settings > AI provider**. It is
   encrypted at rest with Fernet, is never returned by the API, and is removed
   on sign-out.

The `GEMINI_TIMEOUT` default is 120s, which is appropriate for a hosted
model. Only `AI_PROVIDER` needs setting -- `OLLAMA_*` are ignored once the
provider is `gemini`.

Get a key at <https://aistudio.google.com/apikey>.

## 2. Tunnel to a local Ollama

Useful for development, and for keeping inference on your own hardware. The
catch is unavoidable: **your machine must be awake and running the tunnel**
whenever anyone tailors, or the request fails.

1. Start the daemon and expose it:

   ```powershell
   ollama serve
   cloudflared tunnel --url http://localhost:11434
   ```

   `cloudflared` prints something like `https://random-words.trycloudflare.com`.

2. Set that URL in **Render** (or a local `.env`):

   ```
   AI_PROVIDER=ollama
   OLLAMA_BASE_URL=https://random-words.trycloudflare.com
   OLLAMA_MODEL=llama3.1
   OLLAMA_TIMEOUT=600
   ```

3. Confirm the tunnel works before blaming TailorUp:

   ```powershell
   curl.exe https://random-words.trycloudflare.com/api/tags
   ```

The provider builds `{base_url}/api/chat` and its availability check calls
`{base_url}/api/tags`, so a stock Cloudflare quick tunnel needs no extra
configuration -- it proxies all paths.

### Two things to know before exposing a tunnel

**Ollama has no authentication.** Anything that can reach the tunnel URL can
run inference on your machine. A quick tunnel URL is random but not secret, and
it leaks through logs, clipboard history, and screenshots. Treat it as public
and do not leave it up. For anything longer-lived than a session, put a
reverse proxy with auth in front of it, or bind Ollama to an interface the
tunnel cannot route to.

**Quick tunnels have no uptime guarantee.** The subdomain changes when the
process restarts, so `OLLAMA_BASE_URL` goes stale and every tailoring call
starts failing with a connection error until you update it.

**The tunnel URL is not exposed to clients.** `OllamaProvider.describe()`
deliberately omits the base URL, and `GET /api/resumes/tailor/status/`
returns only the provider name, model and availability. Your infrastructure
detail stays server-side.

## Still local end to end

The configuration the real llama3.1 verification ran against, still the
fastest way to iterate:

```powershell
# terminal 1
cd backend; python manage.py runserver

# terminal 2
cd frontend; npm run dev

# AI_PROVIDER=ollama
# OLLAMA_BASE_URL=http://127.0.0.1:11434
# OLLAMA_MODEL=llama3.1
# OLLAMA_TIMEOUT=600
```

Expect **364 seconds** for a real CPU run. That is measured, not a hang, and
the UI gives no progress feedback for it -- which is worth knowing before you
conclude something has hung.

## Diagnosing a provider that will not answer

Open the Dev console in the app and run:

```
status
```

It reports the provider name, the model, availability, and whether a user key
is stored. The shapes it can take:

| Report | Meaning |
| --- | --- |
| `(none configured)` | `AI_PROVIDER` is unset on the server |
| `available: no` | provider set, but the daemon is unreachable -- wrong host, tunnel down, or Ollama not running |
| `ai provider 'x' is not available` | name is misspelled, or not registered in the factory |
| `AI is not configured. Set AI_PROVIDER` | empty; a deliberate error rather than a silent fallback to a stub |


