"""
ATS-friendly DOCX rendering.

Why plain paragraphs
--------------------
Applicant tracking systems parse documents structurally. Tables, text boxes,
columns, decorative glyphs and images are the classic causes of a resume parsing
into fragments. This renderer therefore uses a single column of ordinary
paragraphs with real heading styles, and nothing else. The visual result is
intentionally plain: that is a feature, not a limitation.

Every value comes from :class:`apps.resumes.services.document.ResumeDocument`.
This module never sees the AI response and never contacts a model.
"""

from __future__ import annotations

import io
import zipfile

from docx import Document as DocxDocument
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from .document import ResumeDocument

#: A restrained, high-contrast palette. Near-black on white parses reliably.
_INK = RGBColor(0x1A, 0x1A, 0x1A)
_ACCENT = RGBColor(0x33, 0x33, 0x33)
_MUTED = RGBColor(0x55, 0x55, 0x55)

_SECTION_ORDER = (
    ("summary", "Summary"),
    ("skills", "Skills"),
    ("experience", "Experience"),
    ("projects", "Projects"),
    ("education", "Education"),
    ("certifications", "Certifications"),
)


class ResumeDocxGenerator:
    """Renders a :class:`ResumeDocument` to a ``.docx`` byte string."""

    #: Spacing is centralised so the format can be retuned in one place.
    BODY_SIZE = Pt(10.5)
    SECTION_SIZE = Pt(11.5)
    NAME_SIZE = Pt(18)

    def render(self, document: ResumeDocument) -> bytes:
        """Return the finished document as bytes."""
        doc = DocxDocument()
        self._configure_page(doc)
        self._configure_styles(doc)

        self._header(doc, document)

        for attribute, heading in _SECTION_ORDER:
            value = getattr(document, attribute)

            if isinstance(value, str):
                if value.strip():
                    self._text_section(doc, heading, value)
            elif value:
                if attribute == "skills":
                    self._render_skills(doc, heading, value)
                else:
                    self._render_entries(doc, heading, value)

        if not document.has_section("summary") and not document.has_section("experience"):
            # An empty resume is a bug upstream, not a document to ship.
            raise ValueError("Refusing to render a resume with no content.")

        buffer = io.BytesIO()
        doc.save(buffer)
        return self._normalise_archive(buffer.getvalue())

    # -- determinism -------------------------------------------------------

    #: A fixed modification time for every archive member.
    #:
    #: 1980-01-01 is the earliest value the ZIP format can represent, so it is
    #: the conventional choice for reproducible archives. Any constant works;
    #: what matters is that it is not the wall clock.
    _FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

    @classmethod
    def _normalise_archive(cls, payload: bytes) -> bytes:
        """
        Rewrite the ``.docx`` archive with fixed member timestamps.

        Why this is needed
        ------------------
        A ``.docx`` is a ZIP, and ``zipfile.writestr`` stamps each member with
        the current time when saving. So two renders of an identical
        :class:`ResumeDocument` produce different bytes whenever they straddle
        a one-second boundary -- and identical bytes when they do not. That is
        the worst kind of bug for a test: ``test_output_is_deterministic``
        passes almost always and fails occasionally for no visible reason.

        Only the member timestamps are rewritten. Each part is copied
        uncompressed data and re-deflated, so the document content, the part
        order, and the compression type are all preserved; only the four-byte
        DOS time/date fields change.
        """
        source = zipfile.ZipFile(io.BytesIO(payload))
        buffer = io.BytesIO()

        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as target:
            for info in source.infolist():
                entry = zipfile.ZipInfo(filename=info.filename, date_time=cls._FIXED_TIMESTAMP)
                # Carry the original permissions and compression across. Only
                # the timestamp is being normalised.
                entry.external_attr = info.external_attr
                entry.compress_type = info.compress_type
                entry.create_system = info.create_system
                target.writestr(entry, source.read(info.filename))

        return buffer.getvalue()

    # -- setup -------------------------------------------------------------

    def _configure_page(self, doc) -> None:
        for section in doc.sections:
            section.top_margin = Pt(54)
            section.bottom_margin = Pt(54)
            section.left_margin = Pt(54)
            section.right_margin = Pt(54)

    def _configure_styles(self, doc) -> None:
        normal = doc.styles["Normal"]
        normal.font.name = "Calibri"
        normal.font.size = self.BODY_SIZE
        normal.font.color.rgb = _INK
        normal.paragraph_format.space_after = Pt(4)
        normal.paragraph_format.line_spacing = 1.08

    # -- header ------------------------------------------------------------

    def _header(self, doc, document: ResumeDocument) -> None:
        if document.name:
            paragraph = doc.add_paragraph()
            paragraph.alignment = WD_ALIGN_PARAGRAPH.LEFT
            run = paragraph.add_run(document.name)
            run.bold = True
            run.font.size = self.NAME_SIZE
            run.font.color.rgb = _INK
            paragraph.paragraph_format.space_after = Pt(2)

        contact = " | ".join(
            part for part in [document.email, document.location, document.headline] if part
        )
        if contact:
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(contact)
            run.font.size = Pt(9.5)
            run.font.color.rgb = _MUTED
            paragraph.paragraph_format.space_after = Pt(2)

        if document.links:
            paragraph = doc.add_paragraph()
            run = paragraph.add_run(
                " | ".join("%s: %s" % (l["label"], l["url"]) for l in document.links)
            )
            run.font.size = Pt(9)
            run.font.color.rgb = _MUTED
            paragraph.paragraph_format.space_after = Pt(8)

    # -- sections ----------------------------------------------------------

    def _section_heading(self, doc, text: str) -> None:
        paragraph = doc.add_paragraph()
        run = paragraph.add_run(text.upper())
        run.bold = True
        run.font.size = self.SECTION_SIZE
        run.font.color.rgb = _ACCENT
        paragraph.paragraph_format.space_before = Pt(10)
        paragraph.paragraph_format.space_after = Pt(4)

    def _text_section(self, doc, heading: str, body: str) -> None:
        self._section_heading(doc, heading)
        paragraph = doc.add_paragraph()
        paragraph.add_run(body.strip())

    def _render_skills(self, doc, heading: str, skills: list) -> None:
        """
        Render skills as a single comma-separated line.

        A single paragraph is the most parseable form and keeps the document
        short; one bullet per skill adds length without adding information.
        """
        self._section_heading(doc, heading)
        paragraph = doc.add_paragraph(", ".join(skills))
        paragraph.paragraph_format.space_after = Pt(2)

    def _render_entries(self, doc, heading: str, entries: list) -> None:
        self._section_heading(doc, heading)

        for index, entry in enumerate(entries):
            if index:
                # Breathing room between roles, without an empty paragraph
                # that would confuse a parser.
                spacer = doc.add_paragraph()
                spacer.paragraph_format.space_after = Pt(2)

            self._entry_title(doc, entry)

            for bullet in entry.bullets:
                paragraph = doc.add_paragraph(bullet, style="List Bullet")
                paragraph.paragraph_format.space_after = Pt(2)
                paragraph.paragraph_format.left_indent = Pt(18)

    def _entry_title(self, doc, entry) -> None:
        title = entry.heading or entry.role
        dates = entry.dates

        if not title and not dates:
            return

        paragraph = doc.add_paragraph()
        paragraph.paragraph_format.space_after = Pt(2)

        if title:
            run = paragraph.add_run(title)
            run.bold = True
            run.font.color.rgb = _INK

        if dates:
            if title:
                separator = paragraph.add_run("  |  ")
                separator.font.color.rgb = _MUTED
            run = paragraph.add_run(dates)
            run.font.color.rgb = _MUTED
