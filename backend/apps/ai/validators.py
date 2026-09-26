"""
Deterministic factual validation of a tailoring result.

The model is asked to rephrase, not to invent. Prompt instructions alone are not
enough: local models drift, and a confident-sounding fabricated metric is worse
than no tailoring at all. Every claim in the model's output is therefore checked
mechanically against the **source resume the user actually uploaded**.

Three verdicts
--------------
``valid``     every claim traces back to the source.
``warning``   something is suspicious but explicable -- surfaced for review.
``rejected``  the output asserts something the source does not support.

Design constraints
------------------
* **Deterministic.** No model, no embeddings, no statistical scoring: the same
  input always gives the same verdict, which is what makes this testable.
* **Our data is the source of truth, not the model's.** The model echoes
  ``original_bullets`` back; that echo is *checked* here but never trusted for
  display. The review UI renders the originals loaded from the database.
* **Reused vocabulary.** Technology detection goes through
  :mod:`apps.resumes.services.skill_catalog`, the same catalog the profilers use,
  so the validator and the match engine agree on what a "skill" is.
* **Not an NLP system.** Matching is regex, set membership and substring checks.
  A check that cannot be certain raises a warning for a human; only unambiguous
  fabrications are rejected outright.

Source format
-------------
``source`` is the dict built by :func:`apps.ai.tailor.build_source_resume`::

    {
      "summary": "...",
      "skills": ["python", "django"],
      "education": "...",
      "certifications": "...",
      "experience": [{"id": "exp-0", "label": "2021-03 - present", "bullets": [...]}],
      "projects":   [{"id": "proj-0", "name": "...", "bullets": [...]}],
    }
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from apps.resumes.services import skill_catalog

from .schemas import TailoringResult


#: Verdicts, ordered best to worst.
VALID = "valid"
WARNING = "warning"
REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

#: Numbers with optional separators and scale suffixes. "40%", "3,000" and
#: "1.2M" all reduce to a comparable token.
_NUMBER_RE = re.compile(
    r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*(%|x|k|m|b|bn|mn)?",
    re.IGNORECASE,
)

#: A four-digit year, for employment/education date checks.
_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

#: Month-name dates such as "Jan 2020".
_MONTH_YEAR_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s*\d{4}\b",
    re.IGNORECASE,
)

#: Claiming one of these when the source lists none means an invented credential.
_CERT_RE = re.compile(
    r"\b(?:certified|certification|certificate|licensed|accredited)\b",
    re.IGNORECASE,
)

#: Degree vocabulary, to detect education that was rewritten or added.
_DEGREE_RE = re.compile(
    r"\b(?:b\.?tech|b\.?sc|b\.?a|b\.?com|b\.?e|bachelor|master|m\.?tech|m\.?sc|"
    r"m\.?a|mba|ph\.?d|doctorate|diploma|associate)\b",
    re.IGNORECASE,
)

#: Capitalised tokens that could be an employer or product name. Sentence-initial
#: words are excluded, because capitalisation there is only grammar.
_PROPER_NOUN_RE = re.compile(r"(?<![.!?]\s)(?<!^)\b([A-Z][a-zA-Z&]{2,})\b")

#: Words a naive capitalisation heuristic flags but which are ordinary resume
#: vocabulary. Kept small and explicit rather than clever.
_PROPER_NOUN_STOPWORDS = frozenset(
    """
    the and for with from that this these those our your their its into over under
    built developed designed implemented created led managed improved delivered
    worked using used software engineering engineer developer application
    applications system systems service services platform platforms team teams
    project projects company client clients customer customers user users
    building designing shipping maintaining leading driving collaborating
    responsible ownership role roles position profile summary experience
    education skills certifications awards achievements requirements
    responsibilities qualifications preferred required january february march
    april may june july august september october november december present
    current end-to-end front-end back-end full-stack
    """.split()
)

#: Common words in requirement prose that carry no signal when checking whether
#: an unsupported requirement leaked into a bullet.
_REQUIREMENT_STOPWORDS = frozenset(
    """
    and the with for from you our your that this have has will are not but who
    using use used work working team teams role job years year plus strong good
    ability able knowledge experience skills skill such other others including
    etc deep new first level multiple across within
    """.split()
)


@dataclass(frozen=True)
class Violation:
    """One detected problem, with enough context to act on it."""

    code: str
    severity: str
    message: str
    section: str = ""
    entry_id: str = ""

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "section": self.section,
            "entry_id": self.entry_id,
        }


@dataclass
class ValidationOutcome:
    """The verdict for one tailoring attempt."""

    status: str = VALID
    violations: list = field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return self.status == REJECTED

    @property
    def needs_review(self) -> bool:
        return self.status in {WARNING, REJECTED}

    def add(self, code, severity, message, section="", entry_id=""):
        self.violations.append(
            Violation(
                code=code,
                severity=severity,
                message=message,
                section=section,
                entry_id=entry_id,
            )
        )
        # REJECTED is sticky: one hard fabrication sinks the whole result.
        if severity == REJECTED:
            self.status = REJECTED
        elif self.status == VALID:
            self.status = WARNING

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "rejected": self.rejected,
            "needs_review": self.needs_review,
            "violations": [v.as_dict() for v in self.violations],
        }


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def _norm(value: str) -> str:
    """Lowercase, strip bullet punctuation, collapse whitespace."""
    value = (value or "").lower().strip()
    value = re.sub(r"^[\s\-\*\u2022\u25cf]+", "", value)
    return re.sub(r"\s+", " ", value)


def _numbers_in(text: str) -> set:
    """
    Every numeric claim in ``text``, normalised for comparison.

    "3,000" and "1.2M" reduce to their canonical float form so formatting
    differences do not read as fabrications, while a genuinely new figure does.
    """
    found = set()

    for match in _NUMBER_RE.finditer(text or ""):
        digits = match.group(1).replace(",", "")
        suffix = (match.group(2) or "").lower()

        try:
            value = float(digits)
        except ValueError:
            continue

        # Scale multipliers, so "1.2M" and "1,200,000" compare equal.
        if suffix == "k":
            value *= 1000
        elif suffix in ("m", "mn"):
            value *= 1000000
        elif suffix in ("b", "bn"):
            value *= 1000000000

        found.add(str(value))

    return found


def _fmt_number(value: str) -> str:
    """
    Render a normalised number for a human-readable message.

    ``_numbers_in`` reduces everything to a float for comparison, so "40%" comes
    back as "40.0". A violation message reading "introduces the figure 40.0" is
    needlessly jarring, so integral values are shown without the trailing ".0".
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return str(int(number)) if number.is_integer() else str(number)


def _years_in(text: str) -> set:
    return set(_YEAR_RE.findall(text or ""))


def _join_all(source: dict) -> str:
    """
    Flatten the whole source resume into one searchable blob.

    The skills list is included: it is genuine source content extracted from the
    resume, and a skill can legitimately appear only there. Omitting it would
    make every catalog skill whose spelling never occurs in a bullet read as
    fabricated.
    """
    parts = [
        str(source.get("summary") or ""),
        str(source.get("education") or ""),
        str(source.get("certifications") or ""),
    ]
    parts.extend(str(skill) for skill in source.get("skills") or [])
    for section in ("experience", "projects"):
        for entry in source.get(section) or []:
            parts.append(str(entry.get("label") or ""))
            parts.append(str(entry.get("name") or ""))
            parts.extend(str(b) for b in entry.get("bullets") or [])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Entry-level checks
# ---------------------------------------------------------------------------


def _check_entry(outcome, *, section, change, source_entry, source_text, source_numbers):
    """Validate one experience/project entry against its source counterpart."""
    entry_id = change.entry_id
    label = str(source_entry.get("label") or source_entry.get("name") or entry_id)
    source_bullets = [_norm(b) for b in (source_entry.get("bullets") or [])]
    source_entry_text = "\n".join(source_bullets)
    norm_source_text = _norm(source_text)
    tailored = [b for b in change.tailored_bullets if b and b.strip()]

    if not tailored:
        return

    # -- numbers -----------------------------------------------------------
    # A metric may only be reused from *this* entry. Reusing a figure from a
    # different role misattributes the achievement, so it is at best a review
    # flag and at worst a fabrication.
    entry_numbers = _numbers_in(source_entry_text)

    for bullet in tailored:
        for value in sorted(_numbers_in(bullet)):
            if value in entry_numbers:
                continue
            if value in source_numbers:
                outcome.add(
                    "metric_moved_between_entries", WARNING,
                    "'%s' reuses the figure %s, which appears elsewhere in the resume "
                    "but not under this role. Check it belongs here." % (label, value),
                    section=section, entry_id=entry_id,
                )
            else:
                outcome.add(
                    "fabricated_metric", REJECTED,
                    "'%s' introduces the figure %s, which does not appear anywhere in "
                    "the source resume." % (label, _fmt_number(value)),
                    section=section, entry_id=entry_id,
                )

    # -- technologies ------------------------------------------------------
    # The source skill *list* is catalog-extracted and can miss a technology that
    # is plainly written in the bullets, so this runs against the whole source
    # text rather than the skills list.
    for bullet in tailored:
        for skill in skill_catalog.extract_skills(bullet):
            if _norm(skill) not in norm_source_text:
                outcome.add(
                    "fabricated_technology", REJECTED,
                    "'%s' claims %s, which the source resume never mentions."
                    % (label, skill),
                    section=section, entry_id=entry_id,
                )

    # -- employment / education dates -------------------------------------
    entry_years = _years_in(source_entry_text) | _years_in(
        str(source_entry.get("label") or "")
    )

    for bullet in tailored:
        for year in sorted(_years_in(bullet)):
            if year not in entry_years:
                outcome.add(
                    "changed_date", REJECTED,
                    "'%s' introduces the year %s, which is not in that role's source "
                    "dates." % (label, year),
                    section=section, entry_id=entry_id,
                )
        for month_date in sorted(set(_MONTH_YEAR_RE.findall(bullet))):
            if _norm(month_date) not in norm_source_text:
                outcome.add(
                    "changed_date", REJECTED,
                    "'%s' introduces the date '%s', which is not in the source resume."
                    % (label, month_date),
                    section=section, entry_id=entry_id,
                )

    # -- certifications ----------------------------------------------------
    if _CERT_RE.search(" ".join(tailored)) and not _CERT_RE.search(source_text):
        outcome.add(
            "fabricated_certification", REJECTED,
            "'%s' claims a certification, but the source resume lists none." % label,
            section=section, entry_id=entry_id,
        )

    # -- education ---------------------------------------------------------
    for bullet in tailored:
        for degree in sorted({m.group(0) for m in _DEGREE_RE.finditer(bullet)}):
            if _norm(degree) not in norm_source_text:
                outcome.add(
                    "changed_education", WARNING,
                    "'%s' mentions '%s', which is not in the source education section."
                    % (label, degree),
                    section=section, entry_id=entry_id,
                )

    # -- employer / product names -----------------------------------------
    # Not decidable deterministically, so this is always a review flag rather
    # than a rejection: a false rejection would block legitimate tailoring.
    source_words = set(re.findall(r"[a-z0-9&]+", source_text.lower()))

    for bullet in tailored:
        for match in _PROPER_NOUN_RE.finditer(bullet):
            word = match.group(1)
            lowered = word.lower()
            if lowered in _PROPER_NOUN_STOPWORDS or lowered in source_words:
                continue
            outcome.add(
                "unknown_name", WARNING,
                "'%s' introduces '%s', which does not appear in the source resume. "
                "Verify it is not a new employer or project." % (label, word),
                section=section, entry_id=entry_id,
            )

    # -- traceability ------------------------------------------------------
    # The model is asked to echo the originals verbatim. If it does not, the
    # review UI still renders our stored copy, but the mismatch is worth a flag.
    reported = [_norm(b) for b in change.original_bullets]
    if reported and source_bullets and sorted(reported) != sorted(source_bullets):
        outcome.add(
            "original_mismatch", WARNING,
            "'%s' reported different source bullets than the ones on file. The review "
            "shown to the user uses the stored originals." % label,
            section=section, entry_id=entry_id,
        )


# ---------------------------------------------------------------------------
# Summary checks
# ---------------------------------------------------------------------------


def _check_summary(outcome, result, source_text, source_numbers):
    """
    Validate a rewritten professional summary.

    A summary is written from scratch rather than copied, so it is the most
    likely place for a model to invent a headline metric. The same rules as the
    bullets apply: only figures and technologies already in the source.
    """
    tailored = (result.summary.tailored or "").strip()
    if not tailored:
        return

    norm_source_text = _norm(source_text)

    for value in sorted(_numbers_in(tailored)):
        if value in source_numbers:
            continue
        outcome.add(
            "fabricated_metric", REJECTED,
            "The summary introduces the figure %s, which does not appear anywhere in "
            "the source resume." % _fmt_number(value),
            section="summary",
        )

    for skill in skill_catalog.extract_skills(tailored):
        if _norm(skill) not in norm_source_text:
            outcome.add(
                "fabricated_technology", REJECTED,
                "The summary claims %s, which the source resume never mentions."
                % skill,
                section="summary",
            )

    if _CERT_RE.search(tailored) and not _CERT_RE.search(source_text):
        outcome.add(
            "fabricated_certification", REJECTED,
            "The summary claims a certification, but the source resume lists none.",
            section="summary",
        )


# ---------------------------------------------------------------------------
# Section-level checks
# ---------------------------------------------------------------------------


def _check_skills(outcome, result, source_text):
    """Validate the skill emphasis block against the source resume."""
    norm_source_text = _norm(source_text)

    for skill in result.skills.emphasized:
        if _norm(skill) not in norm_source_text:
            outcome.add(
                "unsupported_skill_emphasis", REJECTED,
                "Emphasises '%s', which the source resume does not contain." % skill,
                section="skills",
            )

    for skill in result.skills.deemphasized:
        if _norm(skill) not in norm_source_text:
            outcome.add(
                "unknown_deemphasised_skill", WARNING,
                "De-emphasises '%s', which is not in the source resume." % skill,
                section="skills",
            )


def _check_leaked_requirements(outcome, result):
    """
    Catch a requirement written into a bullet *and* listed as unsupported.

    The model is told to report unsupported requirements under
    ``skills.unsupported_requirements`` instead of claiming them. Doing both means
    the output contradicts itself, which is how a fabricated claim slips through.
    """
    terms = set()
    for requirement in result.skills.unsupported_requirements:
        terms.update(re.findall(r"[a-z][a-z0-9+#.\-]{2,}", requirement.lower()))
    terms -= _REQUIREMENT_STOPWORDS

    if not terms:
        return

    for section_name, entries in (
        ("experience", result.experience),
        ("projects", result.projects),
    ):
        for change in entries:
            for bullet in change.tailored_bullets:
                lowered = bullet.lower()
                for term in sorted(terms):
                    if term in lowered:
                        outcome.add(
                            "unsupported_requirement_claimed", REJECTED,
                            "A bullet claims '%s', which the model itself listed as an "
                            "unsupported requirement." % term,
                            section=section_name, entry_id=change.entry_id,
                        )
                        break


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def validate(result: TailoringResult, source: dict) -> ValidationOutcome:
    """
    Check a parsed tailoring result against the source resume.

    Returns a :class:`ValidationOutcome` whose ``status`` is ``valid``,
    ``warning`` or ``rejected``. This never raises: the caller decides what to do
    with a rejection, and the violations are always available for the
    user-facing "needs review" screen.
    """
    outcome = ValidationOutcome()

    source_text = _join_all(source)
    source_numbers = _numbers_in(source_text)

    known_ids = {"experience": {}, "projects": {}}
    for section_name in ("experience", "projects"):
        for entry in source.get(section_name) or []:
            entry_id = str(entry.get("id") or "")
            if entry_id:
                known_ids[section_name][entry_id] = entry

    for section_name, changes in (
        ("experience", result.experience),
        ("projects", result.projects),
    ):
        for change in changes:
            source_entry = known_ids[section_name].get(change.entry_id)

            if source_entry is None:
                # An id absent from the source is an invented entry: there is
                # nothing for a reviewer to trace it back to.
                outcome.add(
                    "unknown_entry_id", REJECTED,
                    "The result refers to a %s entry '%s', which is not in the source "
                    "resume." % (section_name[:-1], change.entry_id),
                    section=section_name, entry_id=change.entry_id,
                )
                continue

            _check_entry(
                outcome,
                section=section_name,
                change=change,
                source_entry=source_entry,
                source_text=source_text,
                source_numbers=source_numbers,
            )

    _check_summary(outcome, result, source_text, source_numbers)
    _check_skills(outcome, result, source_text)
    _check_leaked_requirements(outcome, result)

    return outcome
