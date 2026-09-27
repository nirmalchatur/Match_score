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

Set `VITE_API_URL` in the Vercel environment, including the trailing
`/api`:

```
VITE_API_URL=https://<your-render-host>/api
```
