"""
Structured output contract for AI tailoring.

The model is required to answer with JSON, never prose. This module owns:

* parsing that JSON defensively (models wrap it in fences, add trailing commas,
  return lists instead of objects, and so on),
* normalising it into a predictable, typed shape,
* rejecting anything structurally unusable.

No external schema library is used: the dependency list stays small, and the
contract is small enough to express with plain functions. The normalisation is
deliberately forgiving about *shape* and deliberately strict about *content* â€”
forgiving here keeps local models usable, strict content checking happens in
:mod:`apps.ai.validators`.

Traceability note: entry ids (``experience_id`` / ``project_id``) are **not**
invented by the model. They are minted deterministically from the parsed resume
by ``apps.resumes.services.tailor`` and echoed back by the model, which is what
lets the review UI show "original -> tailored" per entry.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .exceptions import AIProviderResponseError

logger = logging.getLogger(__name__)

# Models sometimes wrap JSON in a fenced block despite being told not to.
_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)


def extract_json(raw: str) -> dict[str, Any]:
    """
    Turn a raw model response into a dict, or raise a clear error.

    Handles the common real-world deviations: surrounding prose, ```json
    fences, and leading/trailing whitespace.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise AIProviderResponseError(
            "The AI provider returned an empty response.",
            detail="Response body was empty",
        )

    candidate = _FENCE_RE.sub("", raw.strip()).strip()

    try:
        parsed = json.loads(candidate)
    except ValueError:
        # Fall back to the outermost brace-balanced span. This rescues
        # "Here you go: {...}" style responses without a full JSON repair pass.
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise AIProviderResponseError(
                "The AI provider returned a response that could not be read.",
                detail=f"Non-JSON response: {raw[:400]}",
            )
        try:
            parsed = json.loads(candidate[start : end + 1])
        except ValueError as exc:
            raise AIProviderResponseError(
                "The AI provider returned a malformed response.",
                detail=f"Invalid JSON ({exc}): {raw[:400]}",
            ) from exc

    if not isinstance(parsed, dict):
        raise AIProviderResponseError(
            "The AI provider returned an unexpected response format.",
            detail=f"Expected a JSON object, got {type(parsed).__name__}",
        )

    return parsed


def _as_text(value: Any) -> str:
    """Coerce to a clean string; anything non-scalar becomes empty."""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, (int, float)):
        return str(value)
def _as_text_list(value: Any) -> list[str]:
    """Coerce to a list of non-empty strings, ignoring junk entries."""
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value:
        text = _as_text(item)
        if text:
            out.append(text)
    return out


@dataclass
class SummaryChange:
    original: str = ""
    tailored: str = ""
    reason: str = ""


@dataclass
class EntryChange:
    """A per-experience-entry or per-project rewrite."""

    entry_id: str = ""
    original_bullets: list[str] = field(default_factory=list)
    tailored_bullets: list[str] = field(default_factory=list)
    changes: list[str] = field(default_factory=list)


@dataclass
class SkillChanges:
    emphasized: list[str] = field(default_factory=list)
    deemphasized: list[str] = field(default_factory=list)
    unsupported_requirements: list[str] = field(default_factory=list)


@dataclass
class TailoringResult:
    """The structured, pre-validation tailoring payload."""

    summary: SummaryChange = field(default_factory=SummaryChange)
    experience: list[EntryChange] = field(default_factory=list)
    projects: list[EntryChange] = field(default_factory=list)
    skills: SkillChanges = field(default_factory=SkillChanges)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-safe dict, used for storage and for the API response."""
        return {
            "summary": {
                "original": self.summary.original,
                "tailored": self.summary.tailored,
                "reason": self.summary.reason,
            },
            "experience": [
                {
                    "experience_id": item.entry_id,
                    "original_bullets": list(item.original_bullets),
                    "tailored_bullets": list(item.tailored_bullets),
                    "changes": list(item.changes),
                }
                for item in self.experience
            ],
            "projects": [
                {
                    "project_id": item.entry_id,
                    "original_bullets": list(item.original_bullets),
                    "tailored_bullets": list(item.tailored_bullets),
                    "changes": list(item.changes),
                }
                for item in self.projects
            ],
            "skills": {
                "emphasized": list(self.skills.emphasized),
                "deemphasized": list(self.skills.deemphasized),
                "unsupported_requirements": list(self.skills.unsupported_requirements),
            },
            "warnings": list(self.warnings),
        }

    @property
    def is_empty(self) -> bool:
        """True when the model proposed no change at all."""
        return not (
            self.summary.tailored
            or any(item.tailored_bullets for item in self.experience)
            or any(item.tailored_bullets for item in self.projects)
        )


def _normalise_entries(raw: Any, id_key: str) -> list[EntryChange]:
    """Coerce one section (experience or projects) into EntryChange objects."""
    if not isinstance(raw, list):
        return []

    entries: list[EntryChange] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        entry_id = _as_text(item.get(id_key) or item.get("id"))
        if not entry_id:
            # Without an id we cannot trace the change back to its source, so
            # the entry is dropped rather than saved unattributably.
            logger.warning("ai.schema_dropped_entry reason=missing_id section=%s", id_key)
            continue
        entries.append(
            EntryChange(
                entry_id=entry_id,
                original_bullets=_as_text_list(item.get("original_bullets")),
                tailored_bullets=_as_text_list(item.get("tailored_bullets")),
                changes=_as_text_list(item.get("changes")),
            )
        )
    return entries


def normalise(payload: dict[str, Any]) -> TailoringResult:
    """
    Convert a parsed AI payload into a :class:`TailoringResult`.

    This validates *structure* (types, required keys, usable ids) and nothing
    about *truth*. Factual checks live in :mod:`apps.ai.validators` so that the
    two concerns stay separately testable.
    """
    summary_raw = payload.get("summary")
    summary = SummaryChange()
    if isinstance(summary_raw, dict):
        summary = SummaryChange(
            original=_as_text(summary_raw.get("original")),
            tailored=_as_text(summary_raw.get("tailored")),
            reason=_as_text(summary_raw.get("reason")),
        )

    skills_raw = payload.get("skills")
    skills = SkillChanges()
    if isinstance(skills_raw, dict):
        skills = SkillChanges(
            emphasized=_as_text_list(skills_raw.get("emphasized")),
            deemphasized=_as_text_list(skills_raw.get("deemphasized")),
            unsupported_requirements=_as_text_list(
                skills_raw.get("unsupported_requirements")
            ),
        )

    return TailoringResult(
        summary=summary,
        experience=_normalise_entries(payload.get("experience"), "experience_id"),
        projects=_normalise_entries(payload.get("projects"), "project_id"),
        skills=skills,
        warnings=_as_text_list(payload.get("warnings")),
    )


def parse_tailoring_response(raw: str) -> TailoringResult:
    """Public entry point: raw model text -> validated-shape TailoringResult."""
    return normalise(extract_json(raw))
