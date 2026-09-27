"""
ATS-friendly PDF rendering.

Same input, same content as the DOCX
------------------------------------
This renderer consumes the identical
:class:`apps.resumes.services.document.ResumeDocument` as
:class:`~apps.resumes.services.docx_generator.ResumeDocxGenerator`, so the two
formats cannot drift. Both are produced by deterministic code from validated
structured data; neither ever asks a model to lay out a document.

ReportLab is used because it is pure Python: no system binaries, no headless
browser, and byte-identical output for identical input, which keeps CI and tests
reliable. PDF is generated on demand rather than cached on disk, so a stored
file can never go stale relative to the structured data it represents.
"""

from __future__ import annotations

import io

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    HRFlowable,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

from .document import ResumeDocument

_SECTION_ORDER = (
    ("summary", "Summary"),
    ("skills", "Skills"),
    ("experience", "Experience"),
    ("projects", "Projects"),
    ("education", "Education"),
    ("certifications", "Certifications"),
)


class ResumePdfGenerator:
    """Renders a :class:`ResumeDocument` to a ``.pdf`` byte string."""

    def render(self, document: ResumeDocument) -> bytes:
        """Return the finished PDF as bytes."""
        if not document.has_section("summary") and not document.has_section("experience"):
            raise ValueError("Refusing to render a resume with no content.")

        buffer = io.BytesIO()

        pdf = SimpleDocTemplate(
            buffer,
            pagesize=LETTER,
            leftMargin=0.75 * inch,
            rightMargin=0.75 * inch,
            topMargin=0.6 * inch,
            bottomMargin=0.6 * inch,
            title="%s - Resume" % (document.name or "Resume"),
            author=document.name or "TailorUp",
            subject="Resume",
        )

        styles = self._styles()
        story = []

        story.extend(self._header(document, styles))

        for attribute, heading in _SECTION_ORDER:
            value = getattr(document, attribute)

            if isinstance(value, str):
                if value.strip():
                    story.extend(self._section_heading(heading, styles))
                    story.append(Paragraph(_escape(value.strip()), styles["body"]))
            elif value:
                if attribute == "skills":
                    story.extend(self._section_heading(heading, styles))
                    story.append(Paragraph(_escape(", ".join(value)), styles["body"]))
                else:
                    story.extend(self._entries(heading, value, styles))

        pdf.build(story)
        return buffer.getvalue()

    # -- styles ------------------------------------------------------------

    def _styles(self) -> dict:
        body = ParagraphStyle(
            "body", fontName="Helvetica", fontSize=9.8, leading=13, spaceAfter=3
        )
        return {
            "name": ParagraphStyle(
                "name", parent=body, fontName="Helvetica-Bold", fontSize=17, leading=20,
                spaceAfter=2,
            ),
            "contact": ParagraphStyle(
                "contact", parent=body, fontSize=8.8, leading=12, textColor="#555555",
                spaceAfter=2,
            ),
            "section": ParagraphStyle(
                "section", parent=body, fontName="Helvetica-Bold", fontSize=10.5,
                leading=13, spaceBefore=10, spaceAfter=3, textColor="#333333",
            ),
            "body": body,
            "entry_title": ParagraphStyle(
                "entry_title", parent=body, fontName="Helvetica-Bold", spaceAfter=1,
            ),
        }

    # -- header ------------------------------------------------------------

    def _header(self, document: ResumeDocument, styles: dict) -> list:
        flowables = []

        if document.name:
            flowables.append(Paragraph(_escape(document.name), styles["name"]))

        contact = "  |  ".join(
            part for part in [document.email, document.location, document.headline] if part
        )
        if contact:
            flowables.append(Paragraph(_escape(contact), styles["contact"]))

        if document.links:
            flowables.append(
                Paragraph(
                    _escape("  |  ".join(
                        "%s: %s" % (l["label"], l["url"]) for l in document.links
                    )),
                    styles["contact"],
                )
            )
            flowables.append(Spacer(1, 4))

        return flowables

    # -- sections ----------------------------------------------------------

    def _section_heading(self, text: str, styles: dict):
        # A rule under the heading keeps sections visually separate without
        # needing a box, column or graphic.
        return [
            Paragraph(_escape(text.upper()), styles["section"]),
            HRFlowable(width="100%", thickness=0.5, color="#CCCCCC", spaceAfter=4),
        ]

    def _entries(self, heading: str, entries: list, styles: dict) -> list:
        flowables = self._section_heading(heading, styles)

        for index, entry in enumerate(entries):
            if index:
                flowables.append(Spacer(1, 5))

            title = entry.heading or entry.role
            if title or entry.dates:
                label = _escape(title)
                if entry.dates:
                    label += '  <font color="#555555">|  %s</font>' % _escape(entry.dates)
                flowables.append(Paragraph(label, styles["entry_title"]))

            if entry.bullets:
                flowables.append(
                    ListFlowable(
                        [
                            ListItem(
                                Paragraph(_escape(bullet), styles["body"]),
                                leftIndent=14,
                            )
                            for bullet in entry.bullets
                        ],
                        bulletType="bullet",
                        # A plain ASCII hyphen, deliberately: a U+2022 bullet is
                        # emitted from a symbol-encoded font and extracts as
                        # garbage (\x7f) in common PDF text extractors, which is
                        # exactly what an ATS parser relies on. A hyphen is a
                        # conventional resume bullet and survives extraction.
                        start="-",
                        leftIndent=10,
                        bulletFontName="Helvetica",
                        bulletFontSize=7,
                    )
                )

        return flowables


def _escape(text: str) -> str:
    """
    Escape the characters ReportLab's mini-HTML parser treats as markup.

    Without this, a bullet containing "<" or an ampersand renders incorrectly or
    raises. Escaping is what lets the PDF contain exactly the text the DOCX does.
    """
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
