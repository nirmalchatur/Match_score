
# TailorUp 🚀

### AI-Powered Job Matching & Resume Optimization Platform

> The repository is named `Match_score` for historical reasons. The product,
> its UI and its documentation are **TailorUp**. Internal Python modules keep
> their original names (`MatchEngine`, `JobProcessor`, `JDProfile`, …) rather
> than be renamed — a mechanical rename would touch every import for no user
> benefit and would make the history harder to follow. `MatchEngine` is a
> component name, not a brand.

TailorUp is an intelligent job-matching platform that analyzes a candidate's resume against job descriptions, calculates a transparent compatibility score, identifies skill gaps, evaluates experience and education requirements, and determines whether the candidate should use their master resume or tailor it for a specific job.

It is now a **multi-user SaaS application**: accounts, session authentication, and
strict per-user data isolation, with a public marketing site in front of an
authenticated workspace.

---

## 🏗️ Architecture at a glance

```text
                      TAILORUP
                         │
           ┌─────────────┴─────────────┐
           │                           │
      Marketing Site              SaaS Application
           │                           │
      / (Landing)                  Auth (session + CSRF)
      /login                            │
      /signup                           ▼
                                  /setup/resume  (master resume)
                                         │
                                         ▼
                                  /app/dashboard ── /app/jobs
                                  /app/resumes      /app/analyze
                                                         /app/settings
```

Every job, resume, and analysis is owned by exactly one account. API responses
are always filtered by `request.user`; see [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

| Layer | Technology |
| --- | --- |
| Backend | Django 6.1, Django REST Framework 3.18 |
| Database | SQLite (development) |
| Frontend | React 19, TypeScript, Vite, React Router 7 |
| Parsing | pypdf (resumes), BeautifulSoup (job HTML) |

---

## 🚀 Quick start

### 1. Backend

```bash
cd ai-job-agent
python -m venv venv
venv\Scripts\activate            # Windows
pip install -r backend/requirements.txt

cd backend
python manage.py migrate
python manage.py runserver
```

The API is served on <http://127.0.0.1:8000>.

### 2. Frontend

```bash
cd ai-job-agent/frontend
npm install
npm run dev
```

Open <http://127.0.0.1:5173>. Vite proxies `/api` and `/media` to Django, so no
CORS setup is needed for local development.

### 3. First run

1. Go to <http://127.0.0.1:5173/signup> and create an account.
2. Upload a PDF master resume on `/setup/resume`.
3. Land on the dashboard and paste a Greenhouse job URL.

> Uploading a master resume is required before the workspace is usable, because
> every match score is calculated against it.

---

## 🔐 Authentication

Session-based (not token-based): the browser holds an `HttpOnly` session cookie,
so no secret is ever readable from JavaScript. Django enforces CSRF on every
unsafe request.

| Endpoint | Method | Auth | Purpose |
| --- | --- | --- | --- |
| `/api/auth/register/` | POST | Public | Create an account (auto sign-in) |
| `/api/auth/login/` | POST | Public | Start a session |
| `/api/auth/logout/` | POST | Public | End the session and delete the stored AI key |
| `/api/auth/me/` | GET | Public | Current account, or `{authenticated: false}` |
| `/api/auth/profile/` | GET/PATCH | Required | Workspace preferences |
| `/api/auth/ai-key/` | GET/POST/DELETE | Required | Your own Gemini API key — **never returned** |

Full reference: [`docs/API.md`](docs/API.md).

---

## 🧪 Tests

```bash
cd backend
python manage.py test -v 2
```

Covers the original job pipeline (Greenhouse collection, JD parsing, matching)
plus authentication and cross-account isolation.

```bash
cd frontend
npm run build     # typecheck + production bundle
npx oxlint        # lint
```

---

## ✨ Why TailorUp?

Applying to hundreds of jobs manually creates a major problem:

- Which jobs are actually a good fit?
- Which skills am I missing?
- Does my experience meet the requirement?
- Should I use my master resume?
- Should I tailor my resume for this job?
- Is the job worth applying to?

TailorUp aims to automate this decision-making process.

Instead of simply performing keyword matching, TailorUp builds structured profiles from both the candidate's resume and the job description.

```text
                 ┌──────────────────────┐
                 │    Master Resume     │
                 └──────────┬───────────┘
                            │
                            ▼
                  ┌──────────────────┐
                  │ Resume Parser    │
                  └────────┬─────────┘
                           │
                           ▼
                  ┌──────────────────┐
                  │ Resume Profile   │
                  └────────┬─────────┘
                           │
                           │
                           ▼
Job Description ──► ┌──────────────────┐
                    │   JD Parser      │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   JD Profile     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │   Match Engine   │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │ Match Score +    │
                    │ Recommendation   │
                    └──────────────────┘
````

---

# 🎯 Current Features

## Resume Processing

TailorUp can:

* Extract text from PDF resumes
* Build a structured resume profile
* Detect technical skills
* Normalize skill names
* Extract education information
* Extract work experience
* Extract project information
* Extract certifications

Example:

```json
{
  "skills": [
    "aws",
    "docker",
    "python",
    "react",
    "rest api",
    "sql"
  ],
  "experience": {
    "total_months": 5,
    "total_years": 0.42
  }
}
```

---

# 🧠 Skill Normalization

Different resumes and job descriptions often use different names for the same technology.

For example:

```text
React.js
ReactJS
React JS
        ↓
      react
```

Similarly:

```text
Amazon Web Services
AWS
        ↓
      aws
```

The `SkillNormalizer` provides a centralized normalization layer.

### Supported examples

| Input               | Normalized |
| ------------------- | ---------- |
| React.js            | react      |
| ReactJS             | react      |
| Node.js             | node       |
| Amazon Web Services | aws        |
| Python 3.11         | python     |
| Postgres            | postgresql |
| REST                | rest api   |
| RESTful API         | rest api   |
| C/C++               | c++        |
| Scikit-learn        | sklearn    |

This prevents simple naming differences from incorrectly lowering match scores.

---

# 📄 Job Description Analysis

TailorUp extracts structured information from job descriptions.

The JD parser currently detects:

* Required skills
* Experience requirements
* Education requirements
* Responsibilities
* Requirements / qualifications

Example:

```text
Software Engineer

Requirements

- 2+ years of experience in Python
- Experience with Django and REST APIs
- Knowledge of AWS and Docker
- Bachelor degree in Computer Science

Responsibilities

- Build backend services
- Develop REST APIs
- Deploy applications on AWS
```

Produces a structured profile:

```json
{
  "skills": [
    "aws",
    "django",
    "docker",
    "python",
    "rest api"
  ],
  "experience_years": 2.0,
  "education": [
    "Bachelor degree in Computer Science"
  ]
}
```

---

# 📊 Match Engine

The core of TailorUp is the `MatchEngine`.

It evaluates multiple dimensions of a candidate's profile.

### Current scoring model

| Component    |   Weight |
| ------------ | -------: |
| Skills       |      50% |
| Experience   |      20% |
| Requirements |      20% |
| Education    |      10% |
| **Total**    | **100%** |

The final score is calculated as:

```text
Final Score =
    Skills × 0.50
  + Experience × 0.20
  + Requirements × 0.20
  + Education × 0.10
```

---

# 🔍 Skill Matching

The engine identifies:

* Matched skills
* Missing skills
* Skill match percentage

Example:

```json
{
  "score": 80.0,
  "matched": [
    "aws",
    "docker",
    "python",
    "rest api"
  ],
  "missing": [
    "django"
  ]
}
```

This gives the candidate an immediate understanding of what they are missing.

---

# 💼 Experience Matching

Experience requirements are extracted from the job description.

For example:

```text
2+ years of experience
```

becomes:

```json
{
  "required_years": 2.0
}
```

The candidate's structured experience is then compared against the requirement.

Example:

```json
{
  "score": 21.0,
  "required_years": 2.0,
  "candidate_years": 0.42,
  "note": "Experience requirement detected"
}
```

The experience scoring system is intentionally conservative.

---

# 🎓 Education Matching

The system also considers explicit education requirements.

For example:

```text
Bachelor degree in Computer Science
```

is detected as an education requirement.

The candidate's education section is then evaluated against the requirement.

---

# 🧩 Requirement Matching

TailorUp goes beyond simple skill matching.

Each job requirement can be classified as:

```text
MATCHED
PARTIALLY MATCHED
UNMATCHED
```

Example:

```json
{
  "score": 75.0,
  "matched": [
    "- 2+ years of experience in Python",
    "- Knowledge of AWS and Docker"
  ],
  "partially_matched": [
    "- Experience with Django and REST APIs",
    "- Bachelor degree in Computer Science"
  ],
  "unmatched": []
}
```

This provides explainability instead of returning only a single score.

---

# 🚦 Decision Engine

The final score is converted into an actionable decision.

Current decision logic:

```text
Score >= 95
        ↓
   USE_MASTER

Score < 95
        ↓
     TAILOR
```

The system is designed so that this can later evolve into:

```text
95+       → USE_MASTER
70–94     → TAILOR
50–69     → REVIEW
<50       → SKIP
```

---

# 🗄️ Job Management

Jobs are persisted in a Django database.

Each job contains:

```text
Job
├── URL
├── Company
├── Title
├── Location
├── Description
├── Match Score
├── Decision
├── Status
├── Created At
└── Updated At
```

### Job statuses

```text
NEW
PROCESSING
READY
SKIPPED
FAILED
```

### Job decisions

```text
USE_MASTER
TAILOR
SKIP
REVIEW
```

The URL is unique, preventing duplicate job postings from being inserted.

---

# 🔌 REST API

The backend is built using Django REST Framework.

## Match a Job

```http
POST /api/jobs/match/
```

Example request:

```json
{
  "resume_id": 3,
  "url": "https://example.com/jobs/software-engineer-123",
  "company": "Example Corp",
  "title": "Software Engineer",
  "location": "Pune",
  "jd_text": "Software Engineer Requirements..."
}
```

Example response:

```json
{
  "job_id": 2,
  "created": true,
  "match": {
    "score": 74.2,
    "skills": {
      "score": 80.0,
      "matched": [
        "aws",
        "docker",
        "python",
        "rest api"
      ],
      "missing": [
        "django"
      ]
    },
    "experience": {
      "score": 21.0,
      "required_years": 2.0,
      "candidate_years": 0.42
    },
    "decision": "TAILOR"
  }
}
```

---

## List Jobs

```http
GET /api/jobs/
```

Returns all stored jobs ordered by creation time.

---

## Get Job Details

```http
GET /api/jobs/<id>/
```

Example:

```http
GET /api/jobs/2/
```

---

# 🏗️ Project Architecture

```text
TailorUp
│
├── backend/
│   │
│   ├── apps/
│   │   │
│   │   ├── jobs/
│   │   │   │
│   │   │   ├── services/
│   │   │   │   ├── jd_parser.py
│   │   │   │   ├── jd_profile.py
│   │   │   │   └── match_engine.py
│   │   │   │
│   │   │   ├── models.py
│   │   │   ├── serializers.py
│   │   │   ├── views.py
│   │   │   └── urls.py
│   │   │
│   │   └── resumes/
│   │       │
│   │       ├── services/
│   │       │   ├── parser.py
│   │       │   ├── resume_profile.py
│   │       │   ├── skill_normalizer.py
│   │       │   └── experience_parser.py
│   │       │
│   │       ├── models.py
│   │       └── views.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   ├── urls.py
│   │   ├── asgi.py
│   │   └── wsgi.py
│   │
│   ├── manage.py
│   └── requirements.txt
│
├── .gitignore
└── README.md
```

---

# 🛠️ Tech Stack

### Backend

* Python
* Django
* Django REST Framework

### Resume Processing

* PyPDF
* Custom parsing services
* Rule-based profile extraction

### Job Description Processing

* BeautifulSoup
* Custom JD extraction logic
* Regex-based experience detection

### Database

* SQLite during development
* Django ORM

### Development

* Git
* GitHub
* VS Code
* Python virtual environment

---

# 🚀 Getting Started

## 1. Clone the repository

```bash
git clone https://github.com/nirmalchatur/Match_score.git
cd Match_score
```

---

## 2. Create a virtual environment

### Windows

```powershell
python -m venv venv
```

Activate:

```powershell
.\venv\Scripts\Activate.ps1
```

### Linux / macOS

```bash
python3 -m venv venv
source venv/bin/activate
```

---

## 3. Install dependencies

```bash
pip install -r backend/requirements.txt
```

---

## 4. Run migrations

```bash
cd backend

python manage.py migrate
```

---

## 5. Run the development server

```bash
python manage.py runserver
```

The API is available at:

```text
http://127.0.0.1:8000/
```

---

# 🧪 Testing the API

Example PowerShell request:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/jobs/match/" `
  -Method POST `
  -ContentType "application/json" `
  -Body '{
    "resume_id": 3,
    "url": "https://example.com/jobs/software-engineer-123",
    "company": "Example Corp",
    "title": "Software Engineer",
    "location": "Pune",
    "jd_text": "Software Engineer Requirements - 2+ years of experience in Python - Experience with Django and REST APIs - Knowledge of AWS and Docker - Bachelor degree in Computer Science Responsibilities - Build backend services - Develop REST APIs - Deploy applications on AWS"
  }'
```

---

# 🔐 Security

Sensitive information should never be committed to the repository.

The project ignores:

```text
.env
db.sqlite3
*.pdf
resumes/
storage/
venv/
```

Environment-specific secrets should be stored in `.env`.

Example:

```env
SECRET_KEY=your-secret-key
OPENAI_API_KEY=your-api-key
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_REGION=
```

---

# 📈 What is built

Everything in this table is implemented, tested, and merged. Test counts come
from `python manage.py test`.

| Area | Status |
| ------------------------- | :----: |
| Django backend + DRF API | ✅ |
| Authentication, user isolation | ✅ |
| Master resume upload + parsing | ✅ |
| Job ingestion (Greenhouse, Workday, generic) | ✅ |
| Job description parsing | ✅ |
| Skill normalization | ✅ |
| MatchEngine + requirement matching | ✅ |
| Skill gap analysis | ✅ |
| AI tailoring (Ollama + Gemini) | ✅ |
| AI schema + factual validation | ✅ |
| Resume versioning | ✅ |
| DOCX + PDF generation | ✅ |
| Application tracker | ✅ |
| API rate limiting | ✅ |
| React dashboard, jobs, resumes, applications, settings | ✅ |
| In-app help and developer console | ✅ |

**518 backend tests, all passing.** There is no frontend test runner configured
— frontend correctness is enforced by `tsc` and the production build only.

---

# 🧩 Architecture

```text
                 ┌──────────────────────────────┐
  Browser ──────▶│  React + TypeScript + Vite   │
                 │  dashboard · jobs · resumes  │
                 │  applications · settings     │
                 └──────────────┬───────────────┘
                                │  session cookie, JSON over /api
                 ┌──────────────▼───────────────┐
                 │  Django + DRF                │
                 ├──────────────────────────────┤
                 │  users    auth, encrypted BYOK│
                 │  jobs     ingest · parse ·    │
                 │           MatchEngine · gap   │
                 │  resumes  versions · tailor  │
                 │           DOCX · PDF         │
                 │  applications  tracker       │
                 │  ai       provider factory   │
                 │           schema · validators │
                 │  common   throttling         │
                 └──────────────┬───────────────┘
                                │
        ┌───────────────────────┼────────────────────────┐
        ▼                       ▼                        ▼
   PostgreSQL          Ollama (local)          Gemini (BYOK, optional)
   or SQLite           llama3.1                user-supplied key
```

Tailoring runs through `ProviderFactory → AIProvider → parse →
TailoringResult → factual validation`. The validator refuses output that
invents experience, so a fabricated result is never presented as a suggestion.

---

# 🗺️ What genuinely remains

Everything below is **not** built. It is listed so the gap is visible rather
than implied.

- [ ] Job boards beyond Greenhouse/Workday/generic. LinkedIn and similar have
      no integration, and scraping them is a legal question, not just an
      engineering one.
- [ ] Duplicate job-posting detection
- [ ] Scheduled job re-fetching and status-change alerts
- [ ] Bulk tailoring across many jobs
- [ ] Notification delivery (email/webhook) for application status changes
- [ ] Structured in-product feedback collection
- [ ] Localisation
- [ ] Frontend test runner — currently absent
- [ ] Object storage for uploads. `MEDIA_ROOT` is local disk and the
      persistent-disk block in `render.yaml` is commented out, so **resumes
      are lost on redeploy** on a default Render deployment. This is the
      highest-priority item on this list.
- [ ] Live progress for long runs — implemented in `#39`, not yet merged

## Deliberate non-goals

- **No auto-submit.** TailorUp tracks applications; it does not submit them on
  your behalf. Automated submission is a different product with different
  consent and terms implications.
- **No telemetry.** Nothing is sent anywhere except the AI provider you chose.


---

# 🧠 Design Principles

TailorUp is developed around several principles.

### 1. Explainability

The system should explain *why* a candidate received a score.

Instead of:

```text
Match Score: 74%
```

it should provide:

```text
Skills:       80%
Experience:   21%
Requirements: 75%
Education:   100%

Missing:
- Django

Matched:
- Python
- AWS
- Docker
- REST API
```

---

### 2. Modular Architecture

Resume parsing, JD parsing, normalization, matching, tailoring, and job ingestion are separated into independent services.

This makes individual components easier to test and replace.

---

### 3. Incremental Intelligence

The project starts with deterministic rule-based matching.

AI capabilities were added where they provide clear value, and nowhere else.
The deterministic engine remains the source of every number the user sees; the
model is only ever asked to rewrite text, and its output is fact-checked
against the original resume before it is shown.

```text
Rule-based foundation          ← match scores, skill gaps
        ↓
Structured profiles
        ↓
Deterministic scoring
        ↓
AI-assisted tailoring          ← rewrites prose only
        ↓
Factual validation             ← refuses invented experience
```

Automated submission is explicitly *not* on this path. See
[What genuinely remains](#%F0%9F%97%B0%EF%B8%8F-what-genuinely-remains).

---

### 4. Privacy

Personal resumes contain sensitive information.

The architecture therefore keeps resume files and secrets outside version control,
and the default AI provider runs on your own machine so resume text is not
shipped to a third party to be scored. See [docs/SECURITY.md](docs/SECURITY.md).

**One caveat worth stating plainly:** if you choose the hosted Gemini provider
and paste your own key, your resume text *is* sent to Google. That is a
deliberate, per-user choice, and it is the only path on which resume content
leaves the machine. The provider in use is always shown in the UI and in the
Dev console's `status` command.

---

# 📊 Example Match

For a Software Engineer position requiring:

```text
Python
Django
REST API
AWS
Docker
2+ years experience
Bachelor's degree
```

A candidate might receive:

```text
┌─────────────────────────────┐
│       MATCH SCORE           │
│                             │
│          74.2%              │
│                             │
│        TAILOR RESUME        │
└─────────────────────────────┘

Skills
████████████████░░░░ 80%

Experience
████░░░░░░░░░░░░░░░░ 21%

Requirements
███████████████░░░░░ 75%

Education
████████████████████ 100%

Missing Skills
• Django
```

The result is actionable rather than just a percentage.

---

# 🤝 Contributing

This project is currently under active development.

If you want to experiment with the project:

1. Fork the repository
2. Create a feature branch

```bash
git checkout -b feature/my-feature
```

3. Make your changes
4. Commit them

```bash
git commit -m "Add my feature"
```

5. Push the branch

```bash
git push origin feature/my-feature
```

6. Open a Pull Request

---

# 📜 License

This project is licensed under the **MIT License**. The full text is in
[LICENSE](LICENSE).

Copyright (c) 2026 TailorUp contributors

MIT is a permissive licence: you may use, modify and redistribute this software
including for commercial purposes, provided the copyright notice and the
licence text are retained. It carries no warranty — see the licence for the
full terms and disclaimer.

*If you want the copyright line to name an individual or organisation rather
than "TailorUp contributors", change it in both this file and `LICENSE` so they
stay in agreement.*

---

# 👨‍💻 Author

**Nirmal Chaturvedi**

Backend & Cloud Engineering | Python | Django | AWS | AI

GitHub:
[https://github.com/nirmalchatur](https://github.com/nirmalchatur)

LinkedIn:
[https://linkedin.com/in/nirmal-chaturvedi-0931b225](https://linkedin.com/in/nirmal-chaturvedi-0931b225)

---

# ⭐ Project Vision

TailorUp is built with one simple goal:

> **Turn job searching from a repetitive manual process into an intelligent, explainable and automated workflow.**

The final system aims to understand a candidate, understand a job, determine whether the opportunity is worth pursuing, tailor the candidate's application when necessary, and eventually automate the repetitive parts of the application process.

```

## Documentation

| Area | Doc |
|---|---|
| AI setup, Ollama, deployed providers | [docs/AI_SETUP.md](docs/AI_SETUP.md) |
| AI architecture | [docs/AI_ARCHITECTURE.md](docs/AI_ARCHITECTURE.md) |
| Application tracker | [docs/APPLICATIONS.md](docs/APPLICATIONS.md) |
| Skill gap analysis | [docs/SKILL_GAP.md](docs/SKILL_GAP.md) |
| API reference | [docs/API.md](docs/API.md) |
| Security model | [docs/SECURITY.md](docs/SECURITY.md) |
| Development setup | [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) |
| Deployment | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| System architecture | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| Vercel frontend deployment | [docs/VERCEL.md](docs/VERCEL.md) |

## AI verification status

**Verified against a real local model.** Not a stub.

A real end-to-end run completed against `llama3.1` on local hardware, through
the full production path — no mocks, no test doubles:

```text
ProviderFactory → OllamaProvider → llama3.1 real weights
                → extract_json → schema normalisation
                → TailoringResult → factual validation
```

| | |
| --- | --- |
| Provider | `ollama` |
| Model | `llama3.1` |
| Health check | passed |
| Generation | **364 seconds** |
| Response | 1,614 characters |
| Schema | parsed as `TailoringResult` |
| Factual validation | **valid**, zero violations |

**About that 364 seconds:** it is a measured wall-clock figure for CPU-only
inference, not a round trip. The machine reported `size_vram: 0` — the model
ran entirely from system RAM with no GPU. It is not a bug and not an
interactive experience; it is what local CPU inference costs.
`OLLAMA_TIMEOUT` defaults to **600s** for exactly this reason, and the previous
180s default aborted requests mid-generation.

The test suite never requires Ollama: it runs on `FakeProvider`, plus a stub
that speaks Ollama's wire format. The real run above was a one-off, recorded
because a stub cannot tell you whether a real model will comply with the
schema.
