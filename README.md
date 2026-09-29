# TailorUp

Open-source job analysis. Point it at a job posting, score the posting against
your master resume, see the specific skill gap, and generate a tailored version
of the resume for that role.

The scoring is deterministic and inspectable. Every number the product shows can
be traced to the evidence that produced it, and the reasons for the decision are
in the response rather than behind a spinner.

## What it does

- Parses an uploaded resume into structured data: skills, experience, education,
  certifications, projects.
- Extracts requirements from a job posting and normalises both sides against a
  shared skill taxonomy, so "React.js", "React" and "ReactJS" are one skill
  rather than three.
- Scores the pairing on skills, experience, requirements and education, with the
  weights stated in the response.
- Reports a skill gap in both directions: what the posting asks for that the
  resume does not show, and what the resume claims that the posting never asked
  for.
- Generates a tailored resume as DOCX or PDF.
- Tracks applications through a pipeline and records where each one ended up.
- Ranks the jobs already in your account against your current resume.

## Quick start

Requires Python 3.10 or later and Node.js 20 or later.

```bash
git clone https://github.com/nirmalchatur/Match_score.git
cd Match_score
```

### Backend

```bash
cd backend
python -m venv .venv
```

Activate it:

```bash
# Windows
.venv\Scripts\activate

# Linux and macOS
source .venv/bin/activate
```

Install dependencies, create a database, and start the server:

```bash
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

The API is then on `http://127.0.0.1:8000/api/`.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The dev server proxies `/api` to Django, so no CORS configuration is needed for
local work.

### First run

1. Register an account in the browser at `http://localhost:5173`.
2. Upload a resume and mark it as the master resume.
3. Go to Analyze, paste a job posting URL, and run it.

An AI provider has to be configured before analysis will work. The project runs
against Ollama, Gemini or Groq; see [docs/AI_SETUP.md](docs/AI_SETUP.md). Users
can also paste their own provider key into Settings, which is stored encrypted
with Fernet and is never returned by any endpoint.

## How the match score works

The score is a weighted sum of four components. The weights are fixed, they live
in one place, and they are returned with every result so a score can be checked
rather than trusted.

| Component     | Weight | What it measures                                     |
| ------------- | ------ | ---------------------------------------------------- |
| Skills        | 0.50   | Overlap between resume skills and posting skills      |
| Experience    | 0.20   | Years against the posting's stated requirement       |
| Requirements  | 0.20   | Named must-haves in the posting                       |
| Education     | 0.10   | Whether the posting states a requirement at all       |

Two decisions are worth stating, because both are places where a higher number
would have been easier to produce and less useful.

**Qualities are reported but never scored.** Skills are evidence parsed out of
the uploaded document, so counting them against the posting is a measurement.
Qualities are a self-assessment the user picks from a list. Folding them into
the weights would let someone raise their match score by ticking more boxes,
which is precisely the behaviour a match score exists to prevent.

**A posting with no listed skills scores full marks on the skill component.**
The skill component measures the candidate against the requirements the employer
stated, and a posting that states none is not a poor match for anyone. The
consequence is that job search, which ranks a user's whole account rather than
one posting, skips any job whose requirements were never extracted. Ranking
unparsed jobs by a default would put them at the top of the list, which is
worse than leaving them out.

## Architecture

```
backend/
  config/            Django settings, root URL conf, WSGI
  apps/
    ai/              Provider abstraction: Ollama, Gemini, Groq
    applications/    Application tracker and its pipeline
    automation/      In-app notifications
    common/          Throttling, shared error handling
    jobs/            Posting collection, parsing, match engine, search
    resumes/         Upload, parsing, tailoring, export
    users/           Accounts, profiles, provider keys, security
    sheets/          Spreadsheet export
frontend/
  src/
    components/      Shared UI
    pages/           One file per route
    lib/             API client, types, formatting, SEO
    styles/          Design system
docs/                Long-form documentation
scripts/             Asset generation
```

The backend is a Django REST application with one app per bounded concern. The
frontend is a React single-page application with no state-management library:
the shell owns the data it needs and passes it down.

The tenant boundary is `user` on every model that holds user data, and every
query in the API is scoped by it. A lookup that forgets the filter is the one
bug class this design is built to make difficult, so a guessed id resolves to
404 rather than 403 and never confirms that a record exists.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the longer version.

## REST API

All endpoints are under `/api/` and require a session cookie unless noted.

| Method | Path                                   | Purpose                            |
| ------ | -------------------------------------- | ---------------------------------- |
| POST   | `/api/auth/register/`                  | Create an account                  |
| POST   | `/api/auth/login/`                     | Start a session                    |
| POST   | `/api/auth/logout/`                    | End the session, drop the API key   |
| GET    | `/api/auth/me/`                        | Current account                    |
| GET    | `/api/auth/profile/`                   | Profile settings                   |
| GET    | `/api/auth/ai-key/`                    | Whether a provider key is saved    |
| GET    | `/api/auth/security/`                  | Active sessions, recent activity   |
| POST   | `/api/auth/security/revoke-others/`    | Sign out every other session       |
| POST   | `/api/auth/security/password/`         | Change password                    |
| POST   | `/api/resumes/upload/`                 | Upload and parse a resume          |
| GET    | `/api/resumes/`                        | List this account's resumes        |
| POST   | `/api/jobs/analyze/`                   | Analyse a posting against the resume |
| POST   | `/api/jobs/match/`                     | Re-score a saved job               |
| GET    | `/api/jobs/`                           | List this account's jobs           |
| GET    | `/api/jobs/search/`                    | Rank jobs against the resume       |
| GET    | `/api/applications/`                   | Application tracker                |
| GET    | `/api/applications/dashboard/`         | Aggregated tracker statistics      |
| GET    | `/api/notifications/`                  | In-app notifications               |
| POST   | `/api/notifications/<id>/read/`        | Mark one read                      |
| POST   | `/api/notifications/read-all/`         | Mark all read                      |

Full request and response shapes are in [docs/API.md](docs/API.md).

## Security

Transport and account security are handled in the framework rather than in
per-endpoint code, so a new endpoint inherits them by existing.

- HSTS with a 30-day max-age, subdomains and preload.
- Session and CSRF cookies marked Secure and SameSite.
- `X-Frame-Options: DENY` on every response.
- A CORS allow-list, not a wildcard, with credentials enabled only for listed
  origins. CSRF trusted origins are configured separately because the frontend
  and API are deployed on different hosts.
- Rate limits on authentication, document upload and AI calls, with a consistent
  429 body and a `Retry-After` header.
- Provider keys encrypted at rest with Fernet. No endpoint returns a key; the
  status endpoint returns a boolean.

The security page under Settings is the user-facing half: it lists the live
sessions for the account, lets the user sign out every other session, and
records sign-ins, sign-outs and password changes. Sessions are read from
Django's own session store rather than a parallel table, so "sign out other
sessions" revokes exactly the rows the auth middleware will consult.

Password changes require the current password. Without that check, anyone who
found an unlocked browser session could set a new one and take the account over
permanently.

The threat model, the trust boundaries, and what is deliberately out of scope
are in [docs/SECURITY.md](docs/SECURITY.md).

## Testing

```bash
cd backend
python manage.py test
```

605 tests. Run one app or one module with a path:

```bash
python manage.py test apps.jobs
python manage.py test apps.automation.tests.NotificationApiTests
```

The suite is weighted towards the properties that fail silently rather than
loudly: cross-tenant isolation, idempotency of de-duplicated writes, and the
cases where a result is empty for a reason the caller has to be told about.

Continuous integration runs the suite, a dependency audit, and a CodeQL scan on
every push. `main` requires both the CI status and the secret-scan check to pass
before a pull request can merge, and the branch does not allow force pushes.

## Configuration

Every setting the project reads is documented in `.env.example`. The values that
matter most:

| Variable              | Purpose                                              |
| --------------------- | ---------------------------------------------------- |
| `SECRET_KEY`          | Django signing key. Must be replaced to deploy.      |
| `DEBUG`               | Must be `False` in production.                       |
| `ALLOWED_HOSTS`       | Comma-separated hostnames the API will answer for.   |
| `VITE_API_URL`        | Where the frontend sends API calls.                  |
| `FRONTEND_ORIGIN`     | Added to the CORS and CSRF allow-lists.              |
| `AI_PROVIDER`         | `ollama`, `gemini` or `groq`.                        |
| `GEMINI_API_KEY`      | Fallback key when a user has not saved their own.    |
| `OLLAMA_BASE_URL`     | Base URL for a local Ollama instance.                |

`VITE_API_URL` is read at build time, not at runtime. A production build
without it fails rather than shipping, because the bundle would otherwise call
the static host's own origin and every request would return the CDN's 404.

Deployment, including the Render and Vercel split and the environment variables
each side needs, is in [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Documentation

| Document                                          | Covers                                    |
| ------------------------------------------------- | ----------------------------------------- |
| [ARCHITECTURE.md](docs/ARCHITECTURE.md)           | How the pieces fit together               |
| [AI_SETUP.md](docs/AI_SETUP.md)                   | Configuring a provider                    |
| [AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md)     | The extraction and generation pipeline    |
| [API.md](docs/API.md)                             | Every endpoint, with request and response |
| [DEVELOPMENT.md](docs/DEVELOPMENT.md)             | Conventions and the local loop            |
| [DEPLOYMENT.md](docs/DEPLOYMENT.md)               | Production setup                          |
| [SECURITY.md](docs/SECURITY.md)                   | Threat model and trust boundaries         |
| [SKILL_GAP.md](docs/SKILL_GAP.md)                 | The skill-gap analysis                    |
| [APPLICATIONS.md](docs/APPLICATIONS.md)           | The application tracker                   |
| [VERCEL.md](docs/VERCEL.md)                       | Frontend deployment specifics             |

## Contributing

Issues and pull requests are welcome. Before opening a pull request:

```bash
cd backend && python manage.py test
cd frontend && npm run build
```

Branch protection on `main` requires the CI status and the secret scan, so a
local run is for your own confidence rather than to satisfy a check.

Two conventions are worth knowing before you write code:

- **Tenant scoping is not optional.** Every query on user data filters by
  `user=request.user`. A lookup that omits it is the bug class this project is
  organised to prevent, and it will be caught in review.
- **Comments explain why, not what.** The existing code comments the decisions
  and the rejected alternatives, because most of them are not obvious from the
  code. A comment restating the line below it is noise.

## What this is not

Stated plainly, so nobody has to discover it by trying:

- It does not apply to jobs on your behalf. There is no browser automation and no
  application submission.
- It does not scrape job boards at search time. Job search ranks the postings
  already in your account. Fetching fresh postings from many providers is a
  different system with rate limits and a freshness problem.
- It does not tell you whether you will get the job. It tells you how well your
  resume matches a posting, which is a different and much smaller claim.
- Notifications are in-app only. There is no email or push delivery, so a
  notification cannot reach a browser you have closed.

## License

MIT. See [LICENSE](LICENSE).
