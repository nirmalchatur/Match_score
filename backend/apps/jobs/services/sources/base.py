"""
The contract every job-board adapter implements.

Why an adapter layer at all
---------------------------
The analyze endpoint used to call ``GreenhouseCollector.collect`` directly, so
"paste a job link" meant "paste a Greenhouse link" and anything else failed
with "URL is not a Greenhouse job board". That is a product bug dressed up as
a validation error: the user did nothing wrong.

An adapter answers two questions for a URL -- *is this mine?* and *what can I
read from it?* -- and the registry picks one. Adding Lever, Ashby or an
internal board is then one new module plus one registry entry, with no change
to the view.

The order of the registry matters
---------------------------------
:mod:`apps.jobs.services.sources.generic` must stay last. It matches every
URL, so anything registered after it would be unreachable. See
:mod:`apps.jobs.services.ats_registry`.
"""

from __future__ import annotations

import abc
from typing import Any
from urllib.parse import urlparse


class JobSource(abc.ABC):
    """One job board's URL shape and extraction rules."""

    #: Stable slug stored on ``Job.source`` and shown in the UI. Never change
    #: one without a data migration: the UI maps it to a logo.
    name: str = "generic"

    #: Human label for errors and the settings help text.
    label: str = "Job posting"

    @abc.abstractmethod
    def matches(self, url: str) -> bool:
        """True when this adapter should handle ``url``."""

    @abc.abstractmethod
    def collect(self, url: str) -> Any:
        """
        Fetch and structure one posting.

        Returns a :class:`~apps.jobs.services.job_collector.JobData`.

        Raises:
            ValueError: the URL is unusable, or the posting could not be read.
            requests.RequestException: the page could not be fetched.
        """

    @staticmethod
    def host_of(url: str) -> str:
        """Lower-cased hostname, or "" when the URL is unusable."""
        try:
            return (urlparse(str(url or "").strip()).netloc or "").lower()
        except ValueError:
            return ""


def host_matches(host: str, domain: str) -> bool:
    """
    True when ``host`` is ``domain`` itself or a subdomain of it.

    Written as a suffix check *on a dot boundary* on purpose. The obvious
    alternative, ``host.endswith("greenhouse.io")``, also matches
    ``greenhouse.io.evil.com`` and ``notgreenhouse.io``, both of which are
    attacker-controlled. The registry routes on a hostname, so getting this
    wrong means sending a stranger's URL to a parser that trusts the domain.
    """
    host = (host or "").lower().rstrip(".")
    domain = domain.lower().rstrip(".")
    return host == domain or host.endswith("." + domain)
