"""
The ``AIProvider`` contract.

Design rule: **no Ollama concepts leak out of ``providers/ollama.py``**. The
base contract speaks only in terms of a structured tailoring request and a raw
model response, so swapping Ollama for a hosted provider later is a matter of
adding one more implementation and registering it in the factory — the
``ResumeTailor`` business logic does not change.

A provider is responsible for exactly three things:

1. Turn a :class:`TailoringRequest` into whatever wire format it needs.
2. Return the model's raw response text.
3. Translate transport failures into :mod:`apps.ai.exceptions` errors.

It is explicitly NOT responsible for parsing, validating, or interpreting the
response. That belongs to the service layer, so every provider benefits from
the same fact protection.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Any, ClassVar


@dataclass(frozen=True)
class TailoringRequest:
    """
    Provider-agnostic tailoring input.

    All three payloads are already normalised into plain JSON-safe structures
    by ``apps.resumes.services.tailor`` (which reuses the existing
    ``ResumeProfile`` / ``JDProfile`` / ``MatchEngine`` output). Providers must
    treat this as read-only.
    """

    #: Master resume: skills, experience roles, education, projects, certs.
    resume: dict[str, Any] = field(default_factory=dict)

    #: Job description: title, company, responsibilities, requirements, skills.
    job: dict[str, Any] = field(default_factory=dict)

    #: Existing match analysis: matched/missing skills, score, decision.
    match: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        """A plain dict copy, safe to serialise into a prompt or request body."""
        return {
            "resume": self.resume,
            "job": self.job,
            "match": self.match,
        }


class AIProvider(abc.ABC):
    """Abstract base class for every AI backend."""

    #: Short identifier used in logs and in the ``provider`` API field.
    name: ClassVar[str] = "abstract"

    #: Human-readable description, safe to expose in API responses.
    display_name: ClassVar[str] = "Abstract provider"

    @abc.abstractmethod
    def tailor_resume(self, request: TailoringRequest) -> str:
        """
        Ask the model to tailor a resume and return its **raw** response text.

        The returned string is expected to contain the JSON document described
        by :mod:`apps.ai.schemas`. Implementations must not raise provider
        specific exceptions: transport problems are converted into
        :class:`~apps.ai.exceptions.AIProviderUnavailableError` or
        :class:`~apps.ai.exceptions.AIProviderTimeoutError`.
        """

    def health(self) -> tuple[bool, str]:
        """
        Best-effort reachability check.

        Returns ``(ok, message)``. The default implementation reports healthy
        without doing I/O so test doubles need not override it.
        """
        return True, f"{self.display_name} ready"

    def describe(self) -> dict[str, Any]:
        """Non-secret provider metadata, safe to return from the API."""
        return {
            "provider": self.name,
            "display_name": self.display_name,
        }
