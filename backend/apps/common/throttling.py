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
ownership is decided by the views and the querysets, never here.

The real order
--------------
An earlier version of this file claimed::

    authentication -> permission -> ownership -> throttling -> business logic

That is wrong, and it was wrong in the direction that matters. DRF's
``initial()`` runs authentication, then permission, then throttling, and
only then does the request reach the handler. Object-level ownership is not
checked there: it is enforced by the querysets, which filter to
``request.user`` and are evaluated once the handler runs. So the actual order
is::

    authentication -> permission -> throttling -> object-level ownership -> handler

Throttling therefore happens *before* ownership. That is safe, and the reason
is worth stating precisely rather than leaving to inference:

    Ownership is enforced by filtering the queryset, not by inspecting a
    loaded object.

Because a non-owner never retrieves the row, they get 404 whether or not
they are under quota. The worst a throttled caller learns is that *they*
have exhausted their own budget -- a fact about their own traffic, carrying
no information about whether any given resume or job exists. Had ownership
been decided by loading an object and comparing its owner, running throttling
first would have been a genuine oracle. It is not.

``SECURITY.md`` records this ordering and the reasoning.

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


class ProgressRateThrottle(UserRateThrottle):
    """
    Deliberately looser than the default ``user`` scope.

    The tailoring progress endpoint is polled every couple of seconds for the
    whole length of a run, and a run is measured in *minutes* on CPU. At the
    default 60/min a single long tailoring would exhaust the user's own API
    budget through status polling alone, and the requests that fail would be
    the status calls rather than the work.

    That is the argument for a separate scope rather than a raised default:
    polling should not compete with real work for the same allowance. It is
    still throttled, because an endpoint that any session can call in a loop
    is still something to bound.

    120/min allows a 2-second poll with headroom without touching the budget
    for the API calls the user is actually making.
    """

    scope = "progress"


__all__ = [
    "AnonRateThrottle",
    "UserRateThrottle",
    "StrictAnonRateThrottle",
    "SignupRateThrottle",
    "AIUserRateThrottle",
    "AIHourlyRateThrottle",
    "DocumentRateThrottle",
    "ProgressRateThrottle",
]
