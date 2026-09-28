# Security

What TailorUp actually implements. Every claim here is backed by a test or a
CI gate that fails the build when it regresses. Anything aspirational belongs
in a backlog, not in this file.

## The core invariant

**One account can never observe another account's data.** A user's master
resume, analysed jobs, tailored versions, generated documents and application
history are private to that user, and the API never confirms that an id it
refuses belongs to somebody else.

That single property is enforced in exactly one way, everywhere:

```python
Model.objects.filter(user=request.user, pk=pk)
```

Ownership is applied by the query, so a foreign primary key never loads. The
consequence, which the tests assert directly, is that a foreign `pk` returns
**404, not 403**. 403 would confirm the row exists and belongs to someone else;
404 is indistinguishable from an id that was never issued.

Covered by `apps/users/tests/test_isolation.py` (12 tests) and the per-app
suites below.

## Request lifecycle

The order in which a request is evaluated matters, so it is written down:

```
authentication  ->  permission  ->  throttling  ->  object-level ownership  ->  handler
```

Note that throttling runs *before* object-level ownership. That is safe, and
the reason is specific: ownership is enforced by filtering the queryset, not
by loading an object and comparing its owner field. A non-owner therefore
gets 404 whether or not they are under quota. The only thing a throttled
caller can learn is that *their own* budget is exhausted, which is a fact about
their own traffic and reveals nothing about any record's existence.

If ownership were ever changed to load-then-compare, this ordering would
become a real oracle and would have to be revisited.

## Authentication

- Django session auth, `login` / `logout` views in `apps/users/views.py`.
- Password validators: similarity, minimum length, common password, numeric.
- Session and CSRF cookies are `Secure` and `SameSite` in production, driven by
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SESSION_COOKIE_SAMESITE`.
- `SECURE_SSL_REDIRECT`, HSTS (30 days, subdomains, preload) and
  `X_FRAME_OPTIONS = "DENY"` are enabled.
- `SECURE_PROXY_SSL_HEADER` trusts `X-Forwarded-Proto` from the platform proxy.

Tests: `test_auth.py` (19), `test_cookie_policy.py` (4).

## Rate limiting

DRF throttling, configured through `TAILORUP_RATE_LIMIT_*`. No Redis: the
counters live in whatever `CACHES` names, and `LocMemCache` is the default.

| Scope | Default | Keyed by |
| --- | --- | --- |
| `AUTH` | `5/min` | IP |
| `SIGNUP` | `5/hour` | IP |
| `ANONYMOUS` | `30/min` | IP |
| `USER` | `60/min` | user |
| `AI` | `5/min` | user |
| `AI_HOURLY` | `20/hour` | user |
| `DOCUMENT` | `10/min` | user |

Set `TAILORUP_RATE_LIMIT_ENABLED=False` to disable the whole layer; `_rate()`
returns `None`, which DRF treats as "never throttled". The test suite sets this
by default so that ordinary tests are not throttled against each other.

Exceeding a limit returns **429** with a stable body and `Retry-After`:


## User-supplied API keys (BYOK)

Users may store their own third-party AI provider key. These are:

- Encrypted at rest with Fernet (`apps/users/crypto.py`) before saving.
- **Never returned by the API.** The read endpoints expose only whether a
  credential exists, never the material.
- Written to no log.
- Scoped to the owner: deleting a key clears only that account's row.

Tests: `test_ai_credentials.py` (45).

## Document generation and downloads

- DOCX and PDF are generated server-side. PDF uses `reportlab`, which is pure
  Python, so no headless browser or system binary is involved.
- The download lookup is `Resume.objects.filter(user=request.user, pk=pk)`, so
  a foreign resume is 404.
- The `Content-Disposition` filename is derived from the resume's own stored
  name and sanitised, so a crafted name cannot inject headers or traverse paths.

Tests: `test_documents.py` (31), `test_download_api.py` (34).

## Input handling

- Job URLs are validated before fetching. A `javascript:` URL is rejected with
  400 and no job row is created (`test_dashboard_api.py`).
- AI output is parsed defensively, normalised into `TailoringResult`, and then
  **factually validated** against the inputs before a user ever sees it. A
  model that invents a job title or a company is caught by
  `apps/ai/validators.py` (35 tests).
- The tailored resume is written as a new version. The master resume is never
  mutated by tailoring; `test_isolation.py` asserts the user's single master
  row is unchanged.

## CORS and CSRF

`CORS_ALLOWED_ORIGINS`, `CORS_ALLOWED_ORIGINS_REGEX` and `CSRF_TRUSTED_ORIGINS`
are all environment-driven lists. The Vercel preview URL changes on every push,
which is why a regex form exists; it is a deliberate concession, scoped to the
deployment host pattern, and should be narrowed before any non-preview use.

## CI gates

`.github/workflows/security.yml` fails the build on:

| Job | Checks |
| --- | --- |
| `no-secrets-in-bundle` | Builds the real bundle and scans it for credential material |
| `no-secrets-in-source` | History-aware scan for committed keys |
| `django-deploy-check` | `check --deploy` policy (DEBUG off, host headers, cookies) |
| `dependency-audit` | `pip-audit --strict`, `npm audit --omit=dev --audit-level=high` |

The bundle scan matters most. Vite inlines every `VITE_*` variable into the
JavaScript at build time in plaintext, visible in devtools. A backend secret
that leaks into `VITE_*` is a real incident, so the scan reads the built
artifact rather than trusting a grep of the source.

`.github/workflows/codeql.yml` runs SAST over JavaScript/TypeScript and Python
weekly. `.github/workflows/supply-chain.yml` reviews the dependency diff on
every PR and emits an SPDX SBOM. `.github/dependabot.yml` keeps all three
ecosystems patched.

## Known limitations

Stated plainly, because a security document that claims completeness is worse
than none:

- `LocMemCache` throttling is per worker. See the operational caveat above.
- No HSTS preload submission has been made to the browser preload list.
- `CORS_ALLOWED_ORIGINS_REGEX` is broader than an exact allowlist.
- Rate-limit tests use DRF's cache and a fixed clock; there is no test that
  exercises a real shared-cache deployment.
- No third-party penetration test has been performed.

```json
{ "detail": "Too many requests. Please try again later.", "code": "rate_limited" }
```

The body never contains a cache key, an IP address, a scope name, a provider
name or a stack trace. The custom handler in `apps/common/throttle_handler.py`
exists to enforce exactly that shape.

Tests: `apps/common/tests/test_rate_limiting.py` (12).

### Operational caveat

`LocMemCache` is **per process**. Render runs multiple gunicorn workers, so the
effective limit is per worker, not global: `5/min` may behave like `5/min x N`.
For a strict global limit, point `CACHES` at a shared backend. Anonymous
limiting also depends on the client IP, so a trusted-proxy configuration must be
correct for it to mean anything.
