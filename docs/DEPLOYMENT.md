# Deployment

TailorUp is two deployables. They need different hosts.

```text
Vercel  ──────────────►  React SPA (static, serverless)
   │  HTTPS, VITE_API_URL
   ▼
Render / Railway / Fly  ►  Django API (stateful)
```

---

## Why the backend cannot live on Vercel

Vercel functions run in stateless, short-lived containers. This project needs:

| Needs | Vercel provides |
| --- | --- |
| A persistent filesystem (SQLite, uploaded PDFs) | Ephemeral, wiped between invocations |
| Long-running requests (15s Greenhouse scrape) | Function timeout limits |
| Background work | None |

Putting Django here would appear to work, then silently lose users' accounts,
resumes, and jobs — and log everyone out constantly, because Django's default
session engine is database-backed.

Deploy the SPA to Vercel and the API to a stateful host.

---

## 1. Frontend → Vercel

**Project settings**

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Node.js | 20 or newer |

**Environment variable**

```
VITE_API_URL=https://<your-backend-host>/api
```

The trailing `/api` is required — the client appends `/auth/me/`, `/jobs/`, etc.

`frontend/vercel.json` already handles SPA fallback, so a hard refresh on
`/app/dashboard` serves `index.html` instead of a 404.

> Vercel auto-detection is not used here. With Root Directory set to
> `frontend`, the stray root-level `manage.py` and the empty root-level
> `requirements.txt` are never read.

---

## 2. Backend → a stateful host

Build from the `backend/` directory:

```bash
pip install -r backend/requirements.txt
python manage.py migrate
python manage.py runserver 0.0.0.0:$PORT
```

Required environment variables:

| Variable | Value |
| --- | --- |
| `SECRET_KEY` | a long random string |
| `DEBUG` | `False` |
| `ALLOWED_HOSTS` | your API hostname |
| `CSRF_TRUSTED_ORIGINS` | your Vercel URL, e.g. `https://tailorup.vercel.app` |
| `CORS_ALLOWED_ORIGINS` | your Vercel URL |
| `DATABASE_URL` | hosted Postgres (recommended) |

`settings.py` reads the first three from the environment; see the deployment
section of that file before deploying.

### Persisting data

SQLite is fine for local development only. For a real deployment, either:

- point `DATABASES` at a managed Postgres (Neon, Supabase, Railway), or
- mount a persistent disk and keep SQLite on it.

Uploaded resumes need persistent storage too — either a disk-backed
`MEDIA_ROOT`, or S3-compatible object storage.

---

## 3. After the backend is live

1. Run migrations against the hosted database.
2. Create the first account: `/admin` after `createsuperuser`, or just sign up.
3. Upload a master resume on `/setup/resume`.
