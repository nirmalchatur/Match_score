"""
Prompt construction for resume tailoring.

Prompts live here rather than inside the service so they can be reviewed,
diffed, and improved in one place. Nothing in this module knows which AI
provider will be used: it produces plain text, which every provider embeds in
its own request format.

The prompt's most important job is **factual integrity**: the model is
instructed to act as a tailoring assistant, not a fabricator.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import cycle guard
    # Imported for type checking only. At runtime this module must NOT import
    # the providers package: providers.ollama imports this module, so a
    # runtime import here would be circular.
    from .providers.base import TailoringRequest

# The hard rules. Kept as a module constant so they are unit-testable and
# cannot drift between prompts.
FACTUAL_INTEGRITY_RULES = [
    "Never invent or imply employment experience that is not in the source resume.",
    "Never invent, rename, or drop an employer, a job title, or an employment date range.",
    "Never invent projects, employers, technologies, tools, or libraries.",
    "Never claim a skill just because the job description mentions it. A skill may "
    "only appear in a bullet if the source resume already evidences it.",
    "Never invent metrics, percentages, dollar amounts, user counts, or durations. "
    "You may only reuse a number that already appears in the source resume.",
    "Never alter education facts (degree, institution, field, or dates).",
    "Never fabricate certifications.",
    "Never invent responsibilities that the source resume does not support.",
    "If a job requirement is not supported by the resume, list it under "
    "skills.unsupported_requirements instead of writing it into a bullet.",
    "Only rewrite, reorder and re-emphasise information that is already supported by "
    "the source resume.",
    "Prioritise the most relevant existing experience for the target role.",
    "Use the job description's terminology where the underlying fact is genuinely "
    "supported, but never keyword-stuff.",
    "Preserve factual accuracy at all times. Accuracy matters more than keyword match.",
]

SYSTEM_ROLE = (
    "Act as a resume tailoring assistant, not a resume fabricator. Your job is to "
    "surface the experience a candidate already has that is most relevant to a job, "
    "not to manufacture new experience."
)

OUTPUT_CONTRACT = """{
  "summary": {
    "original": "<source summary copied verbatim, or an empty string>",
    "tailored": "<rewritten summary, or empty to keep the original>",
    "reason": "<why this change helps, one short sentence>"
  },
  "experience": [
    {
      "experience_id": "<the id from the MASTER RESUME, copied exactly>",
      "original_bullets": ["<source bullets, copied verbatim>"],
      "tailored_bullets": ["<rewritten bullets, same count where possible>"],
      "changes": ["<short description of each change>"]
    }
  ],
  "projects": [
    {
      "project_id": "<the id from the MASTER RESUME, copied exactly>",
      "original_bullets": [],
      "tailored_bullets": [],
      "changes": []
    }
  ],
  "skills": {
    "emphasized": ["<skills already in the resume that this job values>"],
    "deemphasized": ["<real skills to move down, not delete>"],
    "unsupported_requirements": ["<job requirements the resume does NOT support>"]
  },
  "warnings": ["<anything a human should double-check>"]
}"""


def _compact(value: Any, limit: int = 4000) -> str:
    """Serialise a payload to JSON with a hard length ceiling.

    The ceiling protects the context window: an enormous job description must
    not push the source resume out of the model's window, because losing the
    source is exactly what causes hallucination.
    """
    text = json.dumps(value, indent=2, ensure_ascii=False, default=str)
    if len(text) <= limit:
        return text
    return text[:limit] + "\n... [truncated]"


def _prompt_blocks(request: TailoringRequest) -> tuple[dict, dict, dict, str]:
    """Assemble the three payload blocks plus the numbered rules list."""
    resume = request.resume or {}
    job = request.job or {}
    match = request.match or {}

    job_block = {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "required_skills": job.get("required_skills") or job.get("skills", []),
        "responsibilities": job.get("responsibilities", []),
        "qualifications": job.get("requirements") or job.get("qualifications", []),
        "preferred_skills": job.get("preferred_skills", []),
    }

    skills = match.get("skills") or {}
    match_block = {
        "score": match.get("score"),
        "matched_skills": skills.get("matched", []),
        "missing_skills": skills.get("missing", []),
    }

    # Each role/project carries a stable id. The model must echo the id back so
    # every suggestion stays traceable to its source entry.
    source_block = {
        "summary": resume.get("summary", ""),
        "skills": resume.get("skills", []),
        "experience": resume.get("experience", []),
        "projects": resume.get("projects", []),
        "education": resume.get("education", ""),
        "certifications": resume.get("certifications", ""),
    }

    rules = "\n".join(
        f"{index}. {rule}"
        for index, rule in enumerate(FACTUAL_INTEGRITY_RULES, start=1)
    )

    return source_block, job_block, match_block, rules



def build_tailoring_prompt(request: TailoringRequest) -> str:
    """
    Build the full user-message prompt for a tailoring request.

    The source resume is labelled emphatically as the only source of truth and
    the output contract is spelled out inline, because local models follow an
    explicit shape far more reliably than an implicit one.
    """
    source_block, job_block, match_block, rules = _prompt_blocks(request)

    return f"""{SYSTEM_ROLE}

You will be given a candidate's MASTER RESUME, a target JOB DESCRIPTION, and an
existing MATCH ANALYSIS. Tailor the resume for that specific job.

============================= ABSOLUTE RULES =============================
{rules}
======================================================================

Any requirement you cannot support with evidence from the master resume must be
reported in "skills.unsupported_requirements". Never write it into a bullet.

----------------------------- MASTER RESUME -----------------------------
This is the ONLY source of factual truth. If a fact is not here, it does not
exist for this candidate.
{_compact(source_block)}

----------------------------- JOB DESCRIPTION ----------------------------
Target role. Use for emphasis and terminology only.
{_compact(job_block)}

------------------------------ MATCH ANALYSIS ----------------------------
Computed by TailorUp. Use it to decide what to emphasise.
{_compact(match_block)}

---------------------------- REQUIRED OUTPUT ----------------------------
Reply with a single JSON object and nothing else. No prose, no markdown fences.
This is the exact shape:

{OUTPUT_CONTRACT}

Hard requirements for the JSON:
- Only include entries whose id exists in the MASTER RESUME. Never invent an id.
- Copy "original_bullets" verbatim from the source. Never edit them.
- Do not add employers, titles, dates, or education anywhere in the output.
- "tailored_bullets" may only rephrase, reorder and emphasise existing facts.
- Any number in "tailored_bullets" must already appear in the source bullets.
- If a section has no useful change, return an empty list for it.
"""


def build_unsupported_requirements_prompt(request: TailoringRequest) -> str:
    """
    A focused prompt for classifying job requirements as supported or not.

    Kept separate from the main prompt so the (much more reliable) binary
    classification does not compete with rewriting for the model's attention.
    """
    resume = request.resume or {}
    job = request.job or {}

    source = {
        "skills": resume.get("skills", []),
        "experience": resume.get("experience", []),
        "projects": resume.get("projects", []),
    }
    requirements = job.get("requirements") or job.get("qualifications", [])

    return f"""{SYSTEM_ROLE}

Classify each job requirement as SUPPORTED or UNSUPPORTED by the candidate's
master resume. A requirement is SUPPORTED only if the resume contains concrete
evidence of it. Mentioning a tool in the job description is not evidence.

----------------------------- MASTER RESUME -----------------------------
{_compact(source, limit=3000)}

----------------------------- JOB REQUIREMENTS ---------------------------
{_compact(requirements, limit=3000)}

Reply with JSON only:
{{
  "supported": ["<requirement text that IS evidenced>"],
  "unsupported_requirements": ["<requirement text that is NOT evidenced>"]
}}
"""
