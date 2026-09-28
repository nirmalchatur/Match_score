"""
Workday job board adapter.

Supported URL formats:
- https://[tenant].wd[N].myworkdayjobs.com/[site]/[job-title]_[JR-12345]
- https://[tenant].myworkdayjobs.com/en-GB/[job-title]_JR-12345

Why this uses a JSON API rather than the HTML
---------------------------------------------
Workday boards are client-rendered: the posting's text is not in the HTML the
server sends, so scraping the page yields navigation chrome and nothing else.
The data is fetched by the page from a CXS endpoint, and that endpoint is
public and stable, so this adapter calls it directly:

    /wday/cxs/[tenant]/[site]/[job-path]

The response is JSON with a ``jobPostingInfo`` object holding the title,
company, location and an HTML ``jobDescription``.

Honest limitation
-----------------
This works for the majority of Workday tenants but not all of them. Some
require a session token, some are fronted by a WAF that answers a bare
request with a challenge page, and a few are fully behind a login. Those
raise :class:`ValueError` with a message that says so rather than returning
an empty posting -- a job analysed from a blank description is worse than one
that failed loudly, because the match score is computed from the description
and would look authoritative while meaning nothing.

Fixing those properly needs browser automation, which this project does not
do.
"""

from __future__ import annotations

import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from apps.jobs.services.job_collector import JobData

from .base import JobSource

#: ``<slug>.wd1.myworkdayjobs.com`` and the ``wdN`` variants.
_TENANT_HOST = re.compile(r"^(?P<tenant>[a-z0-9][a-z0-9\-]*)\.wd\d+\.myworkdayjobs\.com$")

#: Also seen without the ``wdN`` label, and on regional hosts.
_PLAIN_HOST = re.compile(
    r"^(?P<tenant>[a-z0-9][a-z0-9\-]*)\.(?:[a-z0-9\-]+\.)?myworkdayjobs\.com$"
)

#: A job reference looks like ``JR-12345`` somewhere in the path.
_JOB_REF = re.compile(r"JR-?\d+")


class WorkdayCollector(JobSource):
    """Extracts a job from a Workday posting."""

    name = "workday"
    label = "Workday"

    TIMEOUT_SECONDS = 15
    USER_AGENT = (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )

    def matches(self, url: str) -> bool:
        host = self.host_of(url)
        return bool(_TENANT_HOST.match(host) or _PLAIN_HOST.match(host))

    def collect(self, url: str) -> JobData:
        url = str(url or "").strip()
        if not url:
            raise ValueError("URL cannot be empty")
        if not self.matches(url):
            raise ValueError("URL is not a Workday job board")

        api_url = self.cxs_url(url)
        try:
            response = requests.get(
                api_url,
                timeout=self.TIMEOUT_SECONDS,
                headers={
                    "User-Agent": self.USER_AGENT,
                    "Accept": "application/json",
                },
            )
        except requests.Timeout:
            raise requests.RequestException(
                f"Request to {api_url} timed out after {self.TIMEOUT_SECONDS} seconds"
            )
        except requests.RequestException as exc:
            raise requests.RequestException(f"Failed to fetch {api_url}: {exc}")

        if response.status_code in (401, 403):
            raise ValueError(
                "This Workday posting is not public. Workday tenants that "
                "require a session cannot be read without a browser, and this "
                "project does not use one."
            )
        if response.status_code >= 400:
            raise requests.RequestException(
                f"Workday returned HTTP {response.status_code} for {api_url}"
            )

        try:
            payload = response.json()
        except ValueError:
            # A WAF challenge page arrives here: HTML where JSON was expected.
            raise ValueError(
                "This Workday posting returned a page that is not job data. "
                "It is likely fronted by a bot check, which this project does "
                "not attempt to bypass."
            )

        return self._to_job_data(url, payload)
    # -- helpers ------------------------------------------------------------

    @classmethod
    def cxs_url(cls, url: str) -> str:
        """
        Derive the CXS API URL from a posting URL.

        ``https://acme.wd1.myworkdayjobs.com/en-GB/Engineer_JR-1234``
        becomes
        ``https://acme.wd1.myworkdayjobs.com/wday/cxs/acme/en-GB/Engineer_JR-1234``

        Raises:
            ValueError: the path does not look like a job posting.
        """
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        match = _TENANT_HOST.match(host) or _PLAIN_HOST.match(host)
        if not match:
            raise ValueError("URL is not a Workday job board")

        path = (parsed.path or "").strip("/")
        if not path:
            raise ValueError(
                "That Workday link is a company careers page, not a single "
                "job. Open the job and copy that URL."
            )
        if not _JOB_REF.search(path) and "/" not in path:
            raise ValueError("That Workday link does not point at a job posting.")

        tenant = match.group("tenant")
        return f"https://{host}/wday/cxs/{tenant}/{path}"

    @classmethod
    def _to_job_data(cls, url: str, payload: dict) -> JobData:
        info = (payload or {}).get("jobPostingInfo")
        if not isinstance(info, dict):
            raise ValueError(
                "This Workday posting did not include job details. The link "
                "may point at a search page rather than a single role."
            )

        title = (info.get("title") or "").strip()
        if not title:
            raise ValueError("This Workday posting has no job title.")

        return JobData(
            url=url,
            company=(info.get("company") or "").strip(),
            title=title,
            location=cls._location(info),
            description=cls._html_to_text(info.get("jobDescription") or ""),
            source=cls.name,
        )

    @staticmethod
    def _location(info: dict) -> str:
        """
        Best-effort location string.

        Workday's field names differ between tenants, so this reads the common
        ones and returns "" rather than guessing. A blank location is
        cosmetically unhelpful; a wrong one is worse.
        """
        for key in ("location", "locationName", "country", "timeType"):
            value = info.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        primary = info.get("primaryLocation")
        if isinstance(primary, dict):
            for key in ("location", "country", "countryCode"):
                value = primary.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""

    @staticmethod
    def _html_to_text(html: str) -> str:
        """
        Flatten Workday's HTML description to text, keeping list boundaries.

        The description drives the skill extraction, so ``<li>`` items must
        stay on their own lines -- collapsing them into one paragraph makes
        "Docker, Kubernetes, Terraform" indistinguishable from a run-on
        sentence and quietly degrades the match score.
        """
        if not html:
            return ""
        if "<" not in html:
            return html.strip()

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return html.strip()

        for element in soup(["script", "style", "noscript", "svg"]):
            element.decompose()

        for item in soup.find_all("li"):
            item.insert_after("\n")
        for block in soup.find_all(["p", "div", "br", "h1", "h2", "h3", "h4", "tr"]):
            block.insert_after("\n")

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
