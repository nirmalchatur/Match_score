"""
Which job board a URL belongs to, and how to read it.

The registry is the only place that knows the set of supported boards. The
analyze view calls :func:`collect` and never learns which adapter ran, so
adding Lever or Ashby is a new module plus one line in :data:`SOURCES`.

Order is load-bearing
---------------------
:data:`SOURCES` is scanned in order and the first adapter whose ``matches``
returns true wins. ``GenericCollector`` matches *everything*, so it is last
on purpose: registering it earlier would shadow every specific adapter and
silently turn the app back into a generic scraper.

Detection is on the hostname, via
:func:`~apps.jobs.services.sources.base.host_matches`, which compares on a dot
boundary. A suffix check without that boundary would treat
``greenhouse.io.example.com`` as Greenhouse.
"""

from __future__ import annotations

from urllib.parse import urlparse

from .job_collector import JobData
from .sources.base import JobSource
from .sources.generic import GenericCollector
from .sources.greenhouse import GreenhouseSource
from .sources.workday import WorkdayCollector

#: Adapters, most specific first. **Append, do not insert**, unless the new
#: adapter genuinely has to outrank one already here.
SOURCES: tuple[JobSource, ...] = (
    GreenhouseSource(),
    WorkdayCollector(),
    GenericCollector(),
)

#: The board assumed when a posting was saved before this field existed, or
#: when the URL is not recognisable. Matches the generic adapter's slug so a
#: re-analysis and a fresh import agree.
DEFAULT_SOURCE = "generic"


def supported_sources() -> list[dict]:
    """
    The supported boards, for the UI's help text.

    Returned as data rather than rendered client-side so the list cannot drift
    from what the server will actually accept.
    """
    return [
        {"name": source.name, "label": source.label, "fallback": source is SOURCES[-1]}
        for source in SOURCES
    ]


def detect(url: str) -> JobSource:
    """
    The adapter for ``url``.

    Never returns ``None``: anything that is not a recognised board falls
    through to the generic adapter, which is the whole point of "paste any
    job link".

    Raises:
        ValueError: the URL has no host, so there is nothing to fetch.
    """
    url = str(url or "").strip()
    parsed = urlparse(url)

    if not parsed.scheme or parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("Enter a full http(s) URL, for example https://example.com/jobs/123")

    for source in SOURCES:
        if source.matches(url):
            return source

    # Unreachable while SOURCES ends with the generic adapter, but returning a
    # source is better than returning None if that ever changes.
    return SOURCES[-1]


def source_slug(url: str) -> str:
    """
    The source name for a URL, without fetching anything.

    Used to label a job that failed to analyse, and by the UI to show what a
    link will be read as before it is submitted. Falls back rather than
    raising, because this is a display helper and must not break the page.
    """
    try:
        return detect(url).name
    except ValueError:
        return DEFAULT_SOURCE


def collect(url: str) -> JobData:
    """
    Read one posting from any supported board.

    Returns:
        JobData with ``source`` set to the adapter that read it.

    Raises:
        ValueError: the URL is unusable or the posting could not be read.
        requests.RequestException: the page could not be fetched.
    """
    source = detect(url)
    data = source.collect(url)

    # Normalise here rather than trusting each adapter: the slug is what gets
    # stored and rendered, so it must be the adapter's canonical name even if
    # an adapter forgot to set it.
    if not getattr(data, "source", ""):
        data.source = source.name
    return data
