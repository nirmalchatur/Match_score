# Vercel

The Vercel project deploys **only the React frontend**. The Django API is
deployed separately to Render (see `render.yaml`, which sets
`rootDir: backend`).

Two configurations are supported, and both work:

1. **Root Directory = `frontend`** (documented in `docs/DEPLOYMENT.md`).
   Vercel reads `frontend/vercel.json` and this file is ignored.

2. **Root Directory = repository root** (this file).
   Vercel reads this file, which builds `frontend/` explicitly and publishes
   `frontend/dist`.

`framework` is `null` on purpose. Without it Vercel inspects the repository
root, finds the legacy `manage.py`, decides this is a Django application,
and then fails on:

```
Failed to read Django application settings from /vercel/path0/manage.py
ModuleNotFoundError: No module named 'django'
```

The legacy root `manage.py` and the empty root `requirements.txt` were
removed because they were the only reason that misdetection could happen.
The real entry points are `backend/manage.py` and
`backend/requirements.txt`.

## The "Request failed (405)" trap

If signup, login or any other API call reports **405 Method Not Allowed**,
`VITE_API_URL` is not set on the Vercel project.

`src/lib/api.ts` falls back to a relative `/api` when the variable is empty:

```ts
const BASE_URL = (import.meta.env.VITE_API_URL || '/api')
```

That fallback exists for `vite dev`, where the dev proxy forwards `/api` to
Django. On Vercel the same relative URL points at the **static site**, which
answers a POST with a bare 405 and never contacts Django. Nothing in the
browser points at the real cause.

`frontend/vite.config.ts` now surfaces this at build time, so a deploy
cannot ship a bundle that can only 405:

| Build | Missing `VITE_API_URL` |
| --- | --- |
| Vercel **production** | hard **error** — the real site is blocked |
| Vercel **preview** (pull requests) | **warning** — branches stay deployable and reviewable |
| Local `vite build` | hard **error** — `dist/` is a deploy artefact |

Previews only warn on purpose: Vite builds them in `production` mode too, so
erroring there would turn every pull request into a red deployment and block
the very reviews the check exists to protect. Production stays gated, because
that is the site real users hit.

Set `ALLOW_RELATIVE_API=1` to skip the check entirely when `/api` really is
proxied to Django on the same host.

If a build slips through anyway, the app says so instead of failing opaquely:
`src/lib/api.ts` detects a production bundle with no `VITE_API_URL` and
returns

> This deployment is not connected to the API. VITE_API_URL was not set when
> the site was built...

instead of letting the CDN return a 404 that looks like a broken endpoint.

The SPA rewrite also excludes `api/`, so a stray API call returns a plain 404
rather than masquerading as a method error.

## Setting it

Vercel → Project → **Settings → Environment Variables** → add, then redeploy
(environment changes only affect the *next* build):

| Key | Value |
| --- | --- |
| `VITE_API_URL` | `https://<your-render-host>/api` |

Apply it to **every** branch, and to **all three environments** (Production,
Preview, Development). A variable added only to Production leaves preview
deploys broken, which is the usual reason a fixed bug reappears to look unfixed.

The trailing `/api` is required — the client appends `/auth/register/`.

On the Render side, allow the Vercel origin so the browser accepts the
credentialed request:

| Key | Value |
| --- | --- |
| `FRONTEND_ORIGIN` | `https://<your-vercel-app>.vercel.app` |
| `CSRF_TRUSTED_ORIGINS` | `https://<your-vercel-app>.vercel.app` |
| `CORS_ALLOWED_ORIGINS` | `https://<your-vercel-app>.vercel.app` |
| `ALLOWED_HOSTS` | your Render hostname |

See `render.yaml` for the full set.

