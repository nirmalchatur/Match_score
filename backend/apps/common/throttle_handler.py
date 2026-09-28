"""
One consistent shape for every 429, plus the ``Retry-After`` header.

DRF's default throttled response is a bare ``{"detail": "Request was throttled."}``
with no ``Retry-After``. That is a problem for a browser: without a header the
client has to guess when to try again, and the natural guess is "immediately",
which turns a rate limit into a retry storm.

The body is deliberately identical for every scope. A client that learns which
limit it hit, and by how much, can tune itself to stay just under the ceiling.
"""

from __future__ import annotations

import math

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler


def _retry_after(wait: float | None) -> int:
    """Whole seconds, never zero.

    ``max(1, ceil(...))`` because a ``Retry-After: 0`` invites an immediate
    retry, which is the opposite of what the header is for.
    """
    if not wait:
        return 1
    return max(1, math.ceil(wait))


def _is_throttled(exc) -> bool:
    # Imported lazily to keep this module importable without DRF configured,
    # and to avoid a hard dependency on the throttle module path.
    from rest_framework.exceptions import Throttled

    return isinstance(exc, Throttled)


def rate_limit_handler(exc, context):
    """API exception handler that special-cases ``Throttled``.

    Everything else falls straight through to DRF's default handler, so this
    does not change the shape of any other error.
    """
    if not _is_throttled(exc):
        return drf_exception_handler(exc, context)

    wait = getattr(exc, "wait", None)
    response = Response(
        {
            # Stable, machine-readable, and free of anything internal: no
            # cache key, no scope name, no limit value, no IP.
            "detail": "Too many requests. Please try again later.",
            "code": "rate_limited",
        },
        status=status.HTTP_429_TOO_MANY_REQUESTS,
    )
    response["Retry-After"] = str(_retry_after(wait))
    return response
