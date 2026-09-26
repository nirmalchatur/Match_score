"""
Application-level AI errors.

Raw provider exceptions (connection resets, JSON decode failures, HTTP status
codes) must never reach the API layer, because they leak internal details
(Ollama URLs, model names, stack traces) to the browser. Everything the AI
layer raises is one of these, and ``apps.ai.views``/the resume views map them
onto HTTP responses.
"""


class AIError(Exception):
    """Base class for every AI-layer failure."""

    #: Machine-readable code surfaced to the client.
    code = "ai_error"

    #: Default HTTP status used when this error reaches the API layer.
    status_code = 502

    def __init__(self, message: str, *, detail: str = ""):
        super().__init__(message)
        # Public, user-facing message.
        self.message = message
        # Operator-facing context. Logged server-side, never returned.
        self.detail = detail


class AIConfigurationError(AIError):
    """The AI layer is misconfigured (e.g. unknown or missing provider)."""

    code = "ai_not_configured"
    status_code = 500


class AIProviderUnavailableError(AIError):
    """The provider could not be reached (Ollama not running, refused, 5xx)."""

    code = "ai_unavailable"
    status_code = 503


class AIProviderTimeoutError(AIError):
    """The provider did not answer within the configured timeout."""

    code = "ai_timeout"
    status_code = 504


class AIProviderResponseError(AIError):
    """The provider answered, but not with the structured data we asked for."""

    code = "ai_invalid_response"
    status_code = 502


class AITailoringValidationError(AIError):
    """
    The provider's output violated the factual-integrity contract.

    Raised when the model changed something it must never change (education,
    employers, dates) or invented claims. ``violations`` carries the detail so
    the failure can be logged and surfaced for review.
    """

    code = "ai_validation_failed"
    status_code = 422

    def __init__(self, message: str, violations: list | None = None, *, detail: str = ""):
        super().__init__(message, detail=detail)
        self.violations = violations or []
