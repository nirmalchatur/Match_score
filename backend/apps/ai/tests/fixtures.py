"""Shared fixtures for the AI tailoring tests.

A single realistic resume profile is used everywhere so the validation tests
assert on *behaviour* rather than on data that drifts between test modules.
"""

# The stored ``ResumeProfile`` shape, exactly as ``JobProcessor`` reads it.
SOURCE_PROFILE = {
    "skills": ["python", "django", "postgresql", "docker"],
    "experience": {
        "total_months": 24,
        "total_years": 2.0,
        "roles": [
            {
                "start": "2021-03",
                "end": "present",
                "months": 24,
                "context": (
                    "Backend Engineer, Northwind\n"
                    "- Built internal REST API services using Django and PostgreSQL.\n"
                    "- Cut p99 latency by 40% across the platform."
                ),
            },
        ],
    },
    "education": "B.Tech Computer Science, 2020",
    "projects": (
        "Resume Parser\n"
        "- Parsed 3,000 PDF resumes and extracted structured profiles."
    ),
    "certifications": "",
}

SOURCE_BULLETS = [
    "Backend Engineer, Northwind",
    "Built internal REST API services using Django and PostgreSQL.",
    "Cut p99 latency by 40% across the platform.",
]

JOB = {
    "title": "Senior Backend Engineer",
    "company": "Acme",
    "location": "Remote",
    "description": (
        "We are hiring a backend engineer. You will build services with Django "
        "and PostgreSQL. Experience with Docker is required."
    ),
}

JD_PROFILE = {
    "skills": ["python", "django", "postgresql", "docker"],
    "responsibilities": ["Build and operate backend services"],
    "requirements": ["5+ years of backend experience", "Experience with Docker"],
    "education": [],
}

MATCH = {
    "score": 82.5,
    "skills": {"score": 100.0, "matched": ["django"], "missing": []},
    "decision": "TAILOR",
}


def valid_payload() -> dict:
    """
    A well-behaved tailoring result: rephrased, but every fact still traceable.

    Built to produce a clean ``valid`` verdict -- no invented figures, no new
    technologies, no new proper nouns, and the originals echoed verbatim.
    """
    return {
        "summary": {
            "original": "",
            "tailored": "Backend engineer focused on Django services.",
            "reason": "Leads with the most relevant experience for this role.",
        },
        "experience": [
            {
                "experience_id": "exp-0",
                "original_bullets": list(SOURCE_BULLETS),
                "tailored_bullets": [
                    "Cut p99 latency by 40% across the platform.",
                    "Built internal REST API services.",
                ],
                "changes": [
                    "Moved the measured outcome to the front.",
                    "Dropped implementation detail that repeats the skills section.",
                ],
            }
        ],
        "projects": [
            {
                "project_id": "proj-0",
                "original_bullets": [
                    "Parsed 3,000 PDF resumes and extracted structured profiles."
                ],
                "tailored_bullets": [
                    "Parsed 3,000 PDF resumes and extracted structured profiles."
                ],
                "changes": ["Kept as is: already relevant to the role."],
            }
        ],
        "skills": {
            "emphasized": ["django", "postgresql"],
            "deemphasized": ["docker"],
            "unsupported_requirements": ["kubernetes"],
        },
        "warnings": [],
    }
