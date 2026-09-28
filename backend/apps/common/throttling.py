"""
Server-side API rate limiting.

Why DRF's own throttling
------------------------
It is already a dependency, needs no new infrastructure, and keeps the
counters in whatever cache ``CACHES`` names. django-ratelimit would be a
second system doing one job; Redis would be new infrastructure to hold
five-minute counters.

What throttling is and is not
-----------------------------
It is *not* an authorisation control. It never decides who may read a resume,
and it must not be the reason a request is refused for the wrong reason --
ownership is decided by the views, and ``SECURITY.md`` records the order:

    authentication -> permission -> ownership -> throttling -> business logic

DRF runs ``check_throttles`` during ``initial()``, which is after
authentication and permission but before the handler, so this ordering holds by
construction.

A ``None`` rate means "unlimited". ``_rate()`` in settings returns ``None``
when throttling is switched off, which is how the whole layer becomes a no-op
for tests and local development without any branching in here.
"""

from __future__ import annotations

from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class StrictAnonRateThrottle(AnonRateThrottle):
    """Per-IP limit for endpoints that are cheap but worth protecting.

    Login is the motivating case: it is the one endpoint where an attacker
    gains something by repeating it, and where the victim is a real user whose
    account gets locked out.
    """

    scope = "auth"


class SignupRateThrottle(AnonRateThrottle):
    """Signup is limited per IP *and* per hour, which is far tighter than login.

    Account creation is the one action that can be mass-produced for no benefit
    to the attacker, so the cheapest defence is simply to make it slow.
    """

    scope = "signup"


class AIUserRateThrottle(UserRateThrottle):
    """Per-minute ceiling on AI tailoring, which costs a real provider call."""

    scope = "ai"


class AIHourlyRateThrottle(UserRateThrottle):
    """Hourly ceiling on the same.

    A per-minute limit alone bounds the burst rate but not the daily spend; a
    client that waits out each window can still make thousands of calls. Both
    are needed, which is why the view lists two classes.
    """

    scope = "ai_hourly"


class DocumentRateThrottle(UserRateThrottle):
    """DOCX/PDF rendering burns CPU in-process, so it is capped separately."""

    scope = "document"


__all__ = [
    "AnonRateThrottle",
    "UserRateThrottle",
    "StrictAnonRateThrottle",
    "SignupRateThrottle",
    "AIUserRateThrottle",
    "AIHourlyRateThrottle",
    "DocumentRateThrottle",
]
