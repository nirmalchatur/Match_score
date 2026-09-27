"""
The provider-independent resume tailoring service.

This is the only orchestration layer. It knows about prompts, schemas and
validation, and it talks to the AI backend **exclusively** through the
:class:`~apps.ai.providers.base.AIProvider` interface obtained from
:mod:`apps.ai.factory`. There is no HTTP code, no model name, and no notion of
Ollama anywhere in this file; adding a hosted provider later requires no change
here.

Flow
----
1. Build a structured, ID-bearing view of the source resume.
2. Build the job / match-analysis context.
3. Get the configured provider from the factory.
4. Ask it to tailor the resume (raw text back).
5. Parse and normalise that text into a :class:`TailoringResult`.
6. Validate it factually against the source.
7. Return everything the review UI needs.

Rejection policy
----------------
A result that fabricates content raises
:class:`~apps.ai.exceptions.AITailoringValidationError`, carrying the violations
so the API can show the user exactly what was wrong. A result that is merely
*suspicious* is returned with ``validation.status == "warning"``: the user
reviews it and decides. Suspicious-but-acceptable output must not be silently
discarded, and clearly fabricated output must never be presented as a suggestion.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from . import factory, validators
from .exceptions import AITailoringValidationError
from .providers.base import TailoringRequest
from .schemas import TailoringResult, parse_tailoring_response

logger = logging.getLogger(__name__)

#: Bullet markers stripped when turning a block of text into discrete bullets.
_BULLET_RE = re.compile(r"^[\s\-\*\u2022\u25cf]+")


def _lines_to_bullets(text: str) -> list:
    """Split a block of text into trimmed, marker-free bullet strings."""
    bullets = []
    for line in (text or "").splitlines():
        cleaned = _BULLET_RE.sub("", line).strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets


def _split_projects(text: str) -> list:
    """
    Split the projects section into blocks, deterministically.

    ``ResumeProfile`` stores this section as flat text, so structure has to be
    recovered. The heuristic is intentionally simple and predictable: a line
    that does not start with a bullet marker begins a new project, and the
    bullet lines that follow become its bullets. This is a heuristic, not an NLP
    parse, and it is deterministic so the review UI and the validator agree on
    the ids.
    """
    blocks: list = []
    current = None

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        if _BULLET_RE.match(line):
            marker = _BULLET_RE.match(line).group(0)
            if current is None:
                current = {"name": "", "bullets": []}
                blocks.append(current)
            cleaned = _BULLET_RE.sub("", line).strip()
            if cleaned:
                current["bullets"].append(cleaned)
            continue

        current = {"name": line, "bullets": []}
        blocks.append(current)

    return blocks


def _entry_label(bullets: list, fallback: str) -> str:
    """
    Build a human-readable label for a source entry.

    ``ExperienceParser`` stores only date ranges, so the role's heading line
    ("Backend Engineer, Northwind") is the most useful label we have. It is
    detected the way resumes are written: a first line that is short and does not
    end in a full stop is a heading, not a sentence. Anything else falls back to
    the date range.

    This label appears in violation messages, so a bad one makes rejections much
    harder to act on.
    """
    if bullets:
        heading = bullets[0].strip()
        if heading and len(heading) <= 80 and not heading.endswith((".", ":", ";")):
            return heading
    return fallback


def build_source_resume(resume_profile: dict) -> dict:
    """
    Turn a stored resume profile into the source dict the AI sees.

    Entry ids are minted here, deterministically and by position, and echoed back
    by the model. That is what lets the review UI pair "original" with
    "tailored" per entry, and what the validator uses to detect an invented id.

    ``resume_profile`` is the dict shape stored on ``ResumeProfile``
    (see ``JobProcessor.process``), so this reuses the existing profile rather
    than re-parsing the PDF.
    """
    resume_profile = resume_profile or {}

    experience_block = resume_profile.get("experience") or {}
    roles = experience_block.get("roles") or []

    experience = []
    for index, role in enumerate(roles):
        bullets = _lines_to_bullets(str(role.get("context") or ""))
        dates = "%s - %s" % (role.get("start", ""), role.get("end", ""))
        experience.append(
            {
                "id": "exp-%d" % index,
                "label": _entry_label(bullets, dates),
                "start": role.get("start", ""),
                "end": role.get("end", ""),
                "months": role.get("months"),
                "bullets": bullets,
            }
        )

    projects = []
    for index, block in enumerate(_split_projects(str(resume_profile.get("projects") or ""))):
        projects.append(
            {
                "id": "proj-%d" % index,
                "name": block["name"],
                "bullets": block["bullets"],
            }
        )

    return {
        "summary": str(resume_profile.get("summary") or ""),
        "skills": list(resume_profile.get("skills") or []),
        "education": str(resume_profile.get("education") or ""),
        "certifications": str(resume_profile.get("certifications") or ""),
        "experience": experience,
        "projects": projects,
    }


def build_job_context(job: dict, jd_profile: dict | None = None) -> dict:
    """
    Build the job half of the prompt input.

    ``job`` is a dict with at least ``title`` / ``company`` / ``description``.
    ``jd_profile`` is the existing ``JDProfile.build`` output, reused rather than
    recomputed so the tailoring emphasis agrees with the match score the user
    already sees.
    """
    job = job or {}
    jd_profile = jd_profile or {}

    return {
        "title": job.get("title", ""),
        "company": job.get("company", ""),
        "location": job.get("location", ""),
        "description": job.get("description", ""),
        "skills": list(jd_profile.get("skills") or []),
        "responsibilities": list(jd_profile.get("responsibilities") or []),
        "requirements": list(jd_profile.get("requirements") or []),
        "education": list(jd_profile.get("education") or []),
    }


@dataclass
class TailoringOutcome:
    """
    Everything the before/after review screen needs, in one object.

    ``source`` is included so the UI can render the originals from **our** data
    rather than from whatever the model echoed back.
    """

    result: TailoringResult
    validation: Any
    source: dict
    provider: dict = field(default_factory=dict)

    @property
    def rejected(self) -> bool:
        return bool(self.validation and self.validation.rejected)

    def as_dict(self) -> dict:
        return {
            "result": self.result.to_dict(),
            "validation": self.validation.as_dict() if self.validation else None,
            "source": self.source,
            "provider": self.provider,
        }


class ResumeTailor:
    """
    Tailors a master resume for one job.

    Deliberately free of any provider detail: it receives an
    :class:`~apps.ai.providers.base.AIProvider` (or fetches one from the factory)
    and never learns which backend is behind it.
    """

    @classmethod
    def tailor_resume(
        cls,
        resume: dict,
        job: dict,
        match_analysis: dict | None = None,
        *,
        jd_profile: dict | None = None,
        provider=None,
        api_key: str = "",
    ) -> TailoringOutcome:
        """
        Produce a validated tailoring of ``resume`` for ``job``.

        :param resume: the stored resume profile dict (see
            :func:`build_source_resume`).
        :param job: job context (see :func:`build_job_context`).
        :param match_analysis: the existing ``MatchEngine.calculate`` output,
            used only to tell the model what to emphasise.
        :param jd_profile: existing ``JDProfile.build`` output, reused so the
            tailoring agrees with the match score the user already sees.
        :param provider: inject a provider (tests). Defaults to the configured
            one from :func:`apps.ai.factory.get_ai_provider`.
        :param api_key: the calling user's own provider key, decrypted by the
            view. Absent for keyless providers like Ollama. It is placed on the
            request for the provider to read and is kept out of the prompt
            payload by ``TailoringRequest.to_payload``.
        :raises AIConfigurationError: no usable provider is configured.
        :raises AIProviderUnavailableError: the provider could not be reached.
        :raises AIProviderTimeoutError: the provider did not answer in time.
        :raises AIProviderResponseError: the response was not readable JSON.
        :raises AITailoringValidationError: the output fabricated content.
        """
        source = build_source_resume(resume)
        job_context = build_job_context(job, jd_profile)

        # Resolved here, not imported, so swapping providers never touches this
        # module's logic -- only the factory's registry.
        active_provider = provider if provider is not None else factory.get_ai_provider()

        request = TailoringRequest(
            resume=source,
            job=job_context,
            match=dict(match_analysis or {}),
            api_key=api_key,
        )

        logger.info(
            "ai.tailor_start provider=%s experience=%d projects=%d",
            active_provider.name,
            len(source["experience"]),
            len(source["projects"]),
        )

        raw = active_provider.tailor_resume(request)

        # Parse first: a malformed or fenced response is a provider error, not a
        # validation failure, and the two must be distinguishable by the API.
        result = parse_tailoring_response(raw)

        validation = validators.validate(result, source)

        outcome = TailoringOutcome(
            result=result,
            validation=validation,
            source=source,
            provider=active_provider.describe(),
        )

        logger.info(
            "ai.tailor_done provider=%s status=%s violations=%d",
            active_provider.name,
            validation.status,
            len(validation.violations),
        )

        if validation.rejected:
            raise AITailoringValidationError(
                "The tailored resume could not be verified as accurate and was "
                "not produced.",
                violations=[v.as_dict() for v in validation.violations],
                detail="rejected codes: %s"
                % sorted({v.code for v in validation.violations if v.severity == validators.REJECTED}),
            )

        return outcome
