"""
The renderer-agnostic structured resume.

This is the contract between the AI layer and document generation. The AI
produces *tailoring suggestions*; this module resolves them against the stored
master resume into a single, fully-resolved document model, and the DOCX and PDF
renderers both consume that. Neither renderer ever sees the AI response, and
neither renderer talks to a model.

Why resolve here rather than in the renderers
---------------------------------------------
If each renderer resolved tailoring itself, the two formats could drift: a
bullet could survive into the PDF but not the DOCX, or an unaccepted AI
suggestion could leak into one of them. Resolving once, in one deterministic
place, is what makes the two outputs provably equivalent.

The no-invention rule
---------------------
Every field is either copied from the stored profile or is an explicitly
accepted AI edit. In particular:

* ``education`` and ``certifications`` are **never** taken from the AI. The
  prompts forbid it and the validator rejects it; ignoring them here means a bug
  upstream still cannot rewrite someone's degree into a document.
* ``skills`` is filtered to the intersection with the source skill list, so
  reordering can never introduce a skill the candidate does not have.
* Contact links are *extracted* from the resume text, never generated.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

#: URLs in the source resume. LinkedIn and GitHub are the two that matter to a
#: recruiter, and both are recognisable by host rather than by guessing.
_URL_RE = re.compile(r"https?://[^\s,;)\]]+", re.IGNORECASE)

_LINK_LABELS = (
    ("linkedin.com", "LinkedIn"),
    ("github.com", "GitHub"),
    ("gitlab.com", "GitLab"),
    ("portfolio", "Portfolio"),
)


@dataclass
class DocumentEntry:
    """One role or project block."""

    heading: str = ""
    organisation: str = ""
    role: str = ""
    dates: str = ""
    bullets: list = field(default_factory=list)

    def is_empty(self) -> bool:
        return not any([self.heading, self.organisation, self.role, self.dates, self.bullets])


@dataclass
class ResumeDocument:
    """A fully-resolved resume, ready to render in any format."""

    name: str = ""
    email: str = ""
    headline: str = ""
    location: str = ""
    links: list = field(default_factory=list)

    summary: str = ""
    skills: list = field(default_factory=list)
    experience: list = field(default_factory=list)
    projects: list = field(default_factory=list)
    education: str = ""
    certifications: str = ""

    def has_section(self, name: str) -> bool:
        value = getattr(self, name)
        if isinstance(value, str):
            return bool(value.strip())
        return bool(value)


def extract_links(text: str) -> list:
    """
    Pull profile URLs out of the source resume text.

    Extraction, not generation: a URL only appears here if the candidate wrote
    it. Order is stable and duplicates are dropped.
    """
    seen, links = set(), []

    for match in _URL_RE.finditer(text or ""):
        url = match.group(0).rstrip(".,;")
        lowered = url.lower()

        label = next(
            (name for needle, name in _LINK_LABELS if needle in lowered), None
        )
        if not label or label in seen:
            continue

        seen.add(label)
        links.append({"label": label, "url": url})

    return links


def _strip_urls(text: str) -> str:
    """Remove inline URLs so a heading reads "Resume Parser", not "Resume Parser <url>"."""
    return _URL_RE.sub("", text or "").strip().strip("-—|").strip()


def _split_heading(heading: str, dates: str):
    """
    Split a role heading into (role, organisation).

    ``ExperienceParser`` stores roles as a date range plus a context blob, so the
    heading is whatever the candidate wrote, typically "Role, Company". When the
    shape is not recognisable the whole string is kept as the role and no
    organisation is claimed -- guessing here would be inventing.
    """
    heading = _strip_urls(heading)
    if not heading:
        return "", ""

    parts = [p.strip() for p in heading.split(",") if p.strip()]
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) > 2:
        return parts[0], ", ".join(parts[1:])
    return parts[0], ""


def _accepted_bullets(change, fallback: list) -> list:
    """
    Resolve one entry's bullets.

    A saved tailoring result carries the **user-approved** bullets, so a bullet
    the user rejected is simply absent from ``tailored_bullets`` and the source
    bullet is used instead. ``fallback`` is therefore the source list, which is
    what makes a rejection safe rather than destructive.
    """
    if change is None:
        return list(fallback)

    tailored = [b for b in (change.get("tailored_bullets") or []) if b and b.strip()]
    return tailored or list(fallback)


def _order_skills(source_skills: list, emphasised: list) -> list:
    """
    Reorder skills to lead with the ones this job values.

    Intersected with the source list, so emphasis can promote but never invent.
    """
    source = [s for s in (source_skills or []) if s and s.strip()]
    if not source:
        return []

    lowered = {s.lower(): s for s in source}
    ordered, seen = [], set()

    for skill in emphasised or []:
        match = lowered.get((skill or "").strip().lower())
        if match and match not in seen:
            seen.add(match)
            ordered.append(match)

    ordered.extend(s for s in source if s not in seen)
    return ordered


def build_document(
    resume_profile: dict,
    tailoring_result: dict | None = None,
    user=None,
) -> ResumeDocument:
    """
    Resolve a stored profile plus an approved tailoring into a document model.

    :param resume_profile: the dict stored on ``ResumeProfile`` (the same shape
        ``JobProcessor`` consumes), so this reuses the existing profile rather
        than re-parsing the uploaded PDF.
    :param tailoring_result: the *user-approved* tailoring, as stored on a saved
        resume. ``None`` renders the master resume as-is.
    :param user: optional account, used only for the header (name, email).
    """
    resume_profile = resume_profile or {}
    tailoring_result = tailoring_result or {}

    result = tailoring_result.get("result") or {}
    source = tailoring_result.get("source") or {}

    document = ResumeDocument()

    # --- header ----------------------------------------------------------
    if user is not None:
        document.name = " ".join(
            part for part in [user.first_name, user.last_name] if part
        ).strip() or getattr(user, "email", "")
        document.email = getattr(user, "email", "")

        profile = getattr(user, "profile", None)
        if profile is not None:
            document.headline = (profile.headline or "").strip()
            document.location = (profile.target_locations or "").strip()

    # --- skills ----------------------------------------------------------
    source_skills = list(resume_profile.get("skills") or [])
    document.skills = _order_skills(
        source_skills, (result.get("skills") or {}).get("emphasized")
    )

    # --- summary ---------------------------------------------------------
    # A summary is only rendered when one exists. The master profile has no
    # summary field, so this is populated by an approved tailoring only.
    document.summary = ((result.get("summary") or {}).get("tailored") or "").strip()

    # --- experience ------------------------------------------------------
    source_experience = source.get("experience") or []
    changes_by_id = {
        c.get("experience_id"): c for c in (result.get("experience") or [])
    }

    # The stored profile is the authority on how many roles exist; the tailoring
    # only ever rewrites them.
    roles = (resume_profile.get("experience") or {}).get("roles") or []
    for index, role in enumerate(roles):
        entry_id = "exp-%d" % index
        fallback = _bullets_for(source_experience, entry_id)
        if not fallback:
            fallback = _context_bullets(role.get("context"))

        role_text, organisation = _split_heading(
            (fallback[0] if fallback else ""), role.get("end", "")
        )

        document.experience.append(
            DocumentEntry(
                heading=" - ".join(
                    p for p in [role_text, organisation] if p
                ),
                organisation=organisation,
                role=role_text,
                dates=_format_dates(role.get("start"), role.get("end")),
                bullets=_accepted_bullets(changes_by_id.get(entry_id), fallback),
            )
        )

    # --- projects --------------------------------------------------------
    changes_by_id = {
        c.get("project_id"): c for c in (result.get("projects") or [])
    }
    for index, block in enumerate(_split_projects(resume_profile.get("projects") or "")):
        entry_id = "proj-%d" % index
        fallback = _bullets_for(source.get("projects") or [], entry_id) or block["bullets"]

        document.projects.append(
            DocumentEntry(
                heading=block["name"],
                bullets=_accepted_bullets(changes_by_id.get(entry_id), fallback),
            )
        )

    # --- education & certifications: source only, never the AI -----------
    document.education = (resume_profile.get("education") or "").strip()
    document.certifications = (resume_profile.get("certifications") or "").strip()

    # --- contact links, extracted from the source text -------------------
    document.links = extract_links(_all_source_text(resume_profile, source))

    document.experience = [e for e in document.experience if not e.is_empty()]
    document.projects = [p for p in document.projects if not p.is_empty()]

    return document


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BULLET_RE = re.compile(r"^[\s\-\*\u2022\u25cf]+")


def _context_bullets(context) -> list:
    """Split a role's raw context blob into marker-free bullets."""
    bullets = []
    for line in str(context or "").splitlines():
        cleaned = _BULLET_RE.sub("", line).strip()
        if cleaned:
            bullets.append(cleaned)
    return bullets


def _bullets_for(entries: list, entry_id: str) -> list:
    """Look up a source entry's bullets by its deterministic id."""
    for entry in entries or []:
        if entry.get("id") == entry_id:
            return list(entry.get("bullets") or [])
    return []


def _split_projects(text: str) -> list:
    """
    Recover project blocks from the flat projects section.

    Mirrors ``apps.ai.tailor._split_projects`` so the document and the validator
    agree on which project is ``proj-0``, which is what keeps the before/after
    review pointing at the right block in the generated file.
    """
    blocks, current = [], None

    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue

        if _BULLET_RE.match(line):
            if current is None:
                current = {"name": "", "bullets": []}
                blocks.append(current)
            cleaned = _BULLET_RE.sub("", line).strip()
            if cleaned:
                current["bullets"].append(cleaned)
            continue

        name = _strip_urls(line)
        current = {"name": name, "bullets": []}
        blocks.append(current)

    return [b for b in blocks if b["name"] or b["bullets"]]


def _format_dates(start, end) -> str:
    """Render the parser's ``2021-03``/``present`` as ``Mar 2021 - Present``."""
    if not start and not end:
        return ""

    def pretty(value):
        if not value:
            return ""
        if str(value).strip().lower() in {"present", "current", "now"}:
            return "Present"
        text = str(value)
        try:
            year, month = text.split("-", 1)
            months = [
                "Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
            ]
            return "%s %s" % (months[int(month) - 1], year)
        except (ValueError, IndexError):
            return text

    left, right = pretty(start), pretty(end)
    if left and right:
        return "%s - %s" % (left, right)
    return left or right


def _all_source_text(resume_profile: dict, source: dict) -> str:
    """Every scrap of source text, for contact-link extraction."""
    parts = [
        str(resume_profile.get("education") or ""),
        str(resume_profile.get("certifications") or ""),
        str(resume_profile.get("projects") or ""),
    ]
    for role in (resume_profile.get("experience") or {}).get("roles") or []:
        parts.append(str(role.get("context") or ""))
    for entry in (source.get("experience") or []) + (source.get("projects") or []):
        parts.extend(str(b) for b in entry.get("bullets") or [])
    return "\n".join(parts)
