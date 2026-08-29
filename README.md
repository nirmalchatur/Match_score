
# MatchScore 🚀

### AI-Powered Job Matching & Resume Optimization Platform

MatchScore is an intelligent job-matching backend that analyzes a candidate's resume against job descriptions, calculates a transparent compatibility score, identifies skill gaps, evaluates experience and education requirements, and determines whether the candidate should use their master resume or tailor it for a specific job.

The project is being built as a modular backend-first system with Django REST Framework, with plans to integrate AI-powered resume tailoring and automated job application workflows.

---

## ✨ Why MatchScore?

Applying to hundreds of jobs manually creates a major problem:

- Which jobs are actually a good fit?
- Which skills am I missing?
- Does my experience meet the requirement?
- Should I use my master resume?
- Should I tailor my resume for this job?
- Is the job worth applying to?

MatchScore aims to automate this decision-making process.

Instead of simply performing keyword matching, MatchScore builds structured profiles from both the candidate's resume and the job description.

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

MatchScore can:

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

MatchScore extracts structured information from job descriptions.

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

The core of MatchScore is the `MatchEngine`.

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

MatchScore goes beyond simple skill matching.

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
MatchScore
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

The API will be available at:

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

# 📈 Current Development Status

| Feature                   | Status |
| ------------------------- | :----: |
| Django backend            |    ✅   |
| REST API                  |    ✅   |
| Resume database model     |    ✅   |
| Job database model        |    ✅   |
| PDF resume parsing        |    ✅   |
| Resume profile extraction |    ✅   |
| Skill normalization       |    ✅   |
| JD parsing                |    ✅   |
| JD profile extraction     |    ✅   |
| Experience extraction     |    ✅   |
| Match scoring             |    ✅   |
| Requirement matching      |    ✅   |
| Job creation              |    ✅   |
| Job listing               |    ✅   |
| Job detail endpoint       |   🚧   |
| Resume tailoring          |   🚧   |
| AI integration            |   🔜   |
| Job scraping              |   🔜   |
| Automated applications    |   🔜   |
| Frontend dashboard        |   🔜   |

---

# 🗺️ Roadmap

## Phase 1 — Core Matching Engine

* [x] Resume storage
* [x] Resume PDF parsing
* [x] Resume profile generation
* [x] Skill normalization
* [x] Job description parsing
* [x] Experience extraction
* [x] Requirement matching
* [x] Match scoring
* [x] Job persistence

## Phase 2 — Resume Intelligence

* [ ] Job-specific resume tailoring
* [ ] Resume bullet optimization
* [ ] ATS keyword optimization
* [ ] Missing skill analysis
* [ ] AI-generated resume variants
* [ ] Resume version management

## Phase 3 — AI Layer

Planned integration with local or hosted LLMs.

Potential architecture:

```text
Match Engine
     │
     ▼
Tailoring Engine
     │
     ▼
LLM
     │
     ├── Analyze JD
     ├── Identify important keywords
     ├── Select relevant projects
     ├── Rewrite bullets
     └── Generate tailored resume
```

A local LLM such as Ollama may be used to keep experimentation inexpensive and privacy-friendly.

## Phase 4 — Job Discovery

Future integrations may include:

* Job boards
* Company career pages
* LinkedIn job listings
* Automated job ingestion
* Duplicate detection
* Job status tracking

## Phase 5 — Application Automation

The long-term goal is:

```text
Discover Job
     ↓
Parse JD
     ↓
Calculate Match
     ↓
Decision
     ↓
Tailor Resume
     ↓
Generate Application
     ↓
Submit
     ↓
Track Application
```

---

# 🧠 Design Principles

MatchScore is being developed around several principles.

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

AI capabilities will be introduced where they provide clear value.

```text
Rule-based foundation
        ↓
Structured profiles
        ↓
Deterministic scoring
        ↓
AI-assisted tailoring
        ↓
Automated job workflow
```

---

### 4. Privacy

Personal resumes contain sensitive information.

The architecture therefore keeps resume files and secrets outside version control.

Future AI integrations will also prioritize privacy-aware processing.

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

This project is currently intended as a personal/portfolio project.

License information will be added as the project approaches public release.

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

MatchScore is being built with one simple goal:

> **Turn job searching from a repetitive manual process into an intelligent, explainable and automated workflow.**

The final system aims to understand a candidate, understand a job, determine whether the opportunity is worth pursuing, tailor the candidate's application when necessary, and eventually automate the repetitive parts of the application process.

```