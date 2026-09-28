"""
In-process progress reporting for long-running AI work.

Why this exists
---------------
A local llama3.1 tailoring run takes minutes on CPU. The UI previously showed
nothing at all during that time, so a slow request and a hung request were
indistinguishable and both looked like a bug. This makes the wait legible:
the user can see which phase is running and how long it has been going.

Design constraints, and why
--------------------------
**No new infrastructure.** The obvious alternatives were Redis pub/sub or a
queue. Neither is justified: the buffer holds a few hundred short strings
that live for the length of one request.

**Per user, always.** The buffer is keyed by user id and every read is scoped
to the requesting user. A shared buffer would let one account read another's
progress, which is a small information leak about their activity.

**Bounded.** A ring buffer, so a client that never reads cannot grow the
process memory without limit. A user who opens the console and leaves it open
is the realistic way this would otherwise grow.

**In-process, and that is a real limitation.** With multiple gunicorn workers a
polling request can land on a different worker from the one running the
tailoring, and see an empty buffer. The same per-process caveat already
applies to the rate-limit cache and is recorded in SECURITY.md. Switching to a
shared cache is a configuration change, not a rewrite, because every access
here goes through these two functions.
"""

from __future__ import annotations

import threading
import time
from collections import deque

#: Per-user history. 200 is generous for a single run (a few dozen events) and
#: small enough that a few thousand idle users cannot matter.
_MAX_EVENTS = 200

#: Events older than this are dropped even if the ring has room. A run that
#: finished ten minutes ago has no business showing up in a status poll.
_TTL_SECONDS = 30 * 60

_lock = threading.Lock()
_buffers: dict[int, deque] = {}


def _prune(user_id: int, now: float) -> deque:
    buffer = _buffers.setdefault(user_id, deque(maxlen=_MAX_EVENTS))
    cutoff = now - _TTL_SECONDS
    while buffer and buffer[0][0] < cutoff:
        buffer.popleft()
    return buffer


def emit(user_id: int, phase: str, message: str, *, level: str = "info") -> None:
    """Record one progress event for ``user_id``.

    Never raises. A progress report failing must not be able to fail the
    tailoring request it was reporting on.
    """
    try:
        now = time.monotonic()
        with _lock:
            buffer = _prune(user_id, now)
            buffer.append((now, phase, message, level))
    except Exception:  # pragma: no cover - defensive by design
        pass


def snapshot(user_id: int, since: float | None = None) -> dict:
    """
    Return this user's recent events, plus the server's own time base.

    ``since`` is the ``elapsed`` of the last event the caller already saw, so a
    polling client re-reads only what is new. The comparison is against
    ``elapsed`` rather than a wall-clock timestamp because ``time.monotonic``
    is immune to the clock changes that would make a wall-clock cursor
    silently skip or replay events.
    """
    now = time.monotonic()
    with _lock:
        buffer = _prune(user_id, now)

        events = [
            {
                "elapsed": round(stamp - buffer[0][0], 3) if buffer else 0.0,
                "phase": phase,
                "message": message,
                "level": level,
            }
            for stamp, phase, message, level in buffer
            if since is None or stamp - buffer[0][0] > since
        ]

        return {
            "elapsed": round(now - buffer[0][0], 3) if buffer else 0.0,
            "active": bool(events) and events[-1]["level"] not in ("done", "error"),
            "events": events,
        }


def reset(user_id: int) -> None:
    """Clear a user's buffer. Called when a run starts, and on sign-out."""
    with _lock:
        _buffers.pop(user_id, None)
