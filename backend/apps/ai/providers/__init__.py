"""
AI provider implementations.

``base``   the abstract contract every provider implements
``ollama`` the local, zero-cost default
``fake``   a deterministic test double (never used in production paths)

To add a provider (say a hosted API):

1. Subclass :class:`~apps.ai.providers.base.AIProvider` in a new module here.
2. Implement ``tailor_resume`` returning the raw JSON text, translating
   transport failures into ``apps.ai.exceptions`` errors.
3. Register it in :mod:`apps.ai.factory`.

No change to ``ResumeTailor`` or to any view is required.
"""

from .base import AIProvider, TailoringRequest
from .fake import FakeAIProvider
from .ollama import OllamaProvider

__all__ = [
    "AIProvider",
    "TailoringRequest",
    "OllamaProvider",
    "FakeAIProvider",
]
