# Security Policy

## The core invariant

**One account can never observe another account's data.** Resumes, analysed
jobs, tailored versions, generated documents and application history are
private to their owner, and the API never confirms that an id it refuses
belongs to someone else.

Enforced in one way, everywhere:

```python
Model.objects.filter(user=request.user, pk=pk)
```

Ownership is applied by the query, so a foreign primary key never loads. A
foreign `pk` returns **404, not 403** — 403 would confirm the row exists and
belongs to someone else.

This is enforced **server-side**. The frontend route guards are a
convenience, not a control.

## Reporting a vulnerability

Report privately through **GitHub Security Advisories**:

**Repository → Security → Report a vulnerability**

That opens a private advisory visible only to you and the maintainers. It is
the supported route and requires no email address to be published, which is
deliberate: a maintainer contact that is not already public is better kept
out of the repository.

Please include: what you found, how to reproduce it, and the impact you
believe it has. You will get an acknowledgement, and a fix or an explanation
if the report turns out not to be a vulnerability.

Do not open a public issue for a security report, even a seemingly minor one.

## Full security documentation

**[docs/SECURITY.md](docs/SECURITY.md)** is the substantive document. It
covers, with the reasoning behind each:

- the request lifecycle and the exact order of authentication, permission,
  throttling, ownership and the handler
- authentication, sessions, cookies and CSRF
- CORS and trusted origins
- encrypted per-user provider credentials (bring-your-own-key)
- file uploads, downloads, and `Content-Disposition` filename sanitisation
- rate limiting, the scope table, and the 429 response shape
- AI output validation, and what it does and does not guarantee
- the CI gates that fail the build when any of the above regresses

## What the AI validation does and does not do

TailorUp parses model output into a schema and then checks it against the
source resume. Output that asserts facts not present in the source is
rejected; output that is merely suspicious is returned flagged, and the user
decides.

**This is a safeguard, not a guarantee.** It is validation against a specific
source, not a proof that the model cannot produce an unsupported statement.
The user reviews and approves every tailored resume before it is saved. Treat
TailorUp as an assistant that checks its work, not as an authority on what is
true about you.

## Known limitations

Stated plainly, because a security document that implies completeness is
worse than none:

- **Uploaded files are lost on redeploy** unless a persistent volume is
  attached. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). This is a data
  durability problem, not a confidentiality one, but it is real.
- **Rate-limit counters are per process.** With multiple gunicorn workers the
  effective limit is per worker, so the real ceiling is higher than the
  documented one. It is an abuse control, not an authorisation control.
- **`CORS_ALLOWED_ORIGINS_REGEX` is broader than an exact allowlist**, because
  Vercel preview URLs change per commit. Narrow it if you do not use previews.
- **No third-party penetration test** has been performed.
