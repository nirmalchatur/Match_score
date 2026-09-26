# AI setup (Ollama)

How to run TailorUp's resume tailoring against a **local Ollama** daemon.

The application never imports Ollama outside `apps/ai/providers/ollama.py`.
Everything below is configuration, not code.

---

## 1. Install Ollama

Download and install from <https://ollama.com/download> (macOS, Windows, Linux).

Verify:

```bash
ollama --version
```

## 2. Start the daemon

Ollama runs as a local background service on install.

- **macOS / Linux** — it starts automatically. To run it in the foreground:
  ```bash
  ollama serve
  ```
- **Windows** — open the Ollama app, or run `ollama serve` in a terminal.

## 3. Verify it is running

```bash
curl http://localhost:11434/api/tags
```

A healthy daemon answers with JSON. On Windows PowerShell:

```powershell
Invoke-WebRequest http://localhost:11434/api/tags | Select-Object -ExpandProperty Content
```

`{}` means "running, but no models pulled yet" — that is a valid state.

You can also ask the application itself:

```bash
cd backend
AI_PROVIDER=ollama OLLAMA_BASE_URL=http://localhost:11434 OLLAMA_MODEL=llama3.1 \
  python -c "import os,django;os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');django.setup();from apps.ai import factory;print(factory.get_ai_provider().health())"
```

This prints `(True, 'Ollama is running and ... is installed.')` when ready.

## 4. Pull a model

Tailoring needs a model that reliably emits JSON. One that works well on CPU
hardware and is small enough to be usable locally:

```bash
ollama pull llama3.1
```

Other options that produce usable structured output:

```bash
ollama pull qwen2.5        # strong instruction-following
ollama pull mistral        # smaller and faster, less reliable on strict JSON
ollama pull llama3.1:8b    # explicit tag
```

Then confirm it is present:

```bash
ollama list
```

## 5. Configure the application

Copy the example and edit it:

```bash
cp backend/.env.example backend/.env
```

The variables that matter:

| Variable | Purpose | Example |
|---|---|---|
| `AI_PROVIDER` | Which provider to use. `ollama` or `fake`. | `ollama` |
| `OLLAMA_BASE_URL` | Where the daemon listens. | `http://localhost:11434` |
| `OLLAMA_MODEL` | The model tag to call. **Never hardcoded in code.** | `llama3.1` |
| `OLLAMA_TIMEOUT` | Seconds to wait. Raise it for large models on CPU. | `180` |
| `OLLAMA_TEMPERATURE` | Sampling temperature. Keep low. | `0.2` |

### Example `.env`

```dotenv
# --- AI provider ---------------------------------------------------------
# Set to "fake" to run without any AI at all (deterministic, used by CI).
AI_PROVIDER=ollama

OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1

# Local models can be slow, especially the first call on CPU.
OLLAMA_TIMEOUT=180

# Low on purpose: tailoring must stay close to the source text.
OLLAMA_TEMPERATURE=0.2
```

If `AI_PROVIDER` is left empty but both `OLLAMA_BASE_URL` and `OLLAMA_MODEL`
are set, it defaults to `ollama`. If none are set, tailoring is disabled and the
UI shows why rather than failing silently.

## 6. Run without Ollama

```dotenv
AI_PROVIDER=fake
```

The fake provider is deterministic and needs no network. It is what the test
suite uses, and it never requires Ollama to be installed.

## 7. Secrets

There are none in this integration. `OLLAMA_BASE_URL` points at a local daemon;
no API key is involved. Never commit a `.env` containing real secrets — the
example file holds placeholders only, and the provider's base URL is deliberately
excluded from every API response.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `ai_unavailable` (503) | Daemon not running | `ollama serve` |
| "model is not installed" | 404 from `/api/chat` | `ollama pull <model>` |
| `ai_timeout` (504) | Model too slow / too large | Raise `OLLAMA_TIMEOUT`, use a smaller model |
| `ai_not_configured` (500) | `AI_PROVIDER` unset or unknown | Set it to `ollama` or `fake` |
| `ai_validation_failed` (422) | The model changed facts | Not a setup problem: the validator rejected fabricated content. Re-run, or use a more capable model. |

### Validation is the point, not a bug

`ai_validation_failed` means the model attempted to change something it must
never change (a metric, a technology, a date, an employer). The result is
discarded rather than shown. This is working as designed. Lower
`OLLAMA_TEMPERATURE` or try a larger model if it happens constantly.
