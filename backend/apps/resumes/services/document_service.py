"""
Single entry point for producing a resume document.

The views call :func:`render_resume_document` and nothing else, so the
"which format, which renderer, which payload" decision lives in one place. It
also guarantees both formats are driven by the *same* resolved
:class:`~apps.resumes.services.document.ResumeDocument`: the document is built
once and handed to whichever renderer was asked for.

Documents are generated on demand rather than written to disk. That is a
deliberate choice:

* a stored file can go stale the moment the user edits the tailoring;
* it avoids leaving candidate PII sitting in MEDIA_ROOT unmanaged;
* the output is deterministic, so there is no benefit to caching it.
"""

from __future__ import annotations

import re

from apps.resumes.models import Resume

from .document import build_document
from .docx_generator import ResumeDocxGenerator
from .pdf_generator import ResumePdfGenerator

#: Formats the API exposes. Both are produced by deterministic code.
FORMATS = {
    "docx": {
        "generator": ResumeDocxGenerator,
        "content_type": (
            "application/vnd.openxmlformats-officedocument"
            ".wordprocessingml.document"
        ),
        "extension": "docx",
    },
    "pdf": {
        "generator": ResumePdfGenerator,
        "content_type": "application/pdf",
        "extension": "pdf",
    },
}

_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._ -]+")


def stored_profile(resume) -> dict:
    """The stored profile dict, in the shape ``build_document`` expects."""
    try:
        profile = resume.profile
    except Exception:
        return {}

    return {
        "summary": "",
        "skills": profile.skills or [],
        "experience": profile.experience or {},
        "education": profile.education or "",
        "projects": profile.projects or "",
        "certifications": profile.certifications or "",
    }


def safe_filename(resume, extension: str) -> str:
    """
    Build a Content-Disposition filename.

    Derived entirely from the resume's own name -- never from a path, a user
    id, or anything the client supplied -- so a crafted name cannot escape the
    header or steer the write location.
    """
    base = _UNSAFE_FILENAME.sub("", resume.name or "resume").strip() or "resume"
    base = re.sub(r"\s+", " ", base)[:80]
    return "%s.%s" % (base, extension)


def render_resume_document(resume, user, fmt: str) -> tuple:
    """
    Render ``resume`` in ``fmt``.

    :returns: ``(bytes, content_type, filename)``.
    :raises ValueError: unknown format.
    :raises ValueError: the resume has no renderable content.
    """
    spec = FORMATS.get((fmt or "").lower())
    if spec is None:
        raise ValueError("Unsupported format: %r" % (fmt,))

    # A tailored resume renders its user-approved result; the master renders
    # exactly what was uploaded.
    tailoring = resume.tailoring_result if resume.resume_type == "TAILORED" else None

    document = build_document(
        stored_profile(resume),
        tailoring_result=tailoring,
        user=user,
    )

    payload = spec["generator"]().render(document)

    if not payload:
        raise ValueError("The renderer produced an empty document.")

    return payload, spec["content_type"], safe_filename(resume, spec["extension"])
