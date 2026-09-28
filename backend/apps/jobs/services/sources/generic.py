"""
Generic job posting adapter: structured data first, HTML as a fallback.

This is the one that makes "paste any job link" true. It matches every URL, so
the registry must keep it **last** -- see
:mod:`apps.jobs.services.sources.base`.

Two strategies, in order
-----------------------
1. **JSON-LD ``JobPosting``.** Most ATSs (and most serious company career
   sites) embed a ``schema.org/JobPosting`` block. It is the most reliable
   source available without a browser: it is machine-readable, already
   structured, and unaffected by page layout.
2. **HTML fallback.** Open Graph and ``<meta>`` tags, then the main content
   element, then the whole page.

Why the order matters
---------------------
The HTML fallback will *always* return something -- a careers index page, a
cookie banner, a login wall. Scraping a page that is not the job produces a
plausible-looking title and a meaningless description, and the match score is
computed from that description. It would look authoritative and be wrong.
So the fallback has to be willing to fail, and :func:`GenericCollector.collect`
refuses to invent a company or a title rather than guessing.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from apps.jobs.services.job_collector import JobData

from .base import JobSource


class GenericCollector(JobSource):
    """Reads any posting: JSON-LD, then Open Graph/meta, then page text."""

    name = "generic"
    label = "Job posting"

    TIMEOUT_SECONDS = 15
    USER_AGENT = (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    )

    #: Containers that hold the actual posting on most career sites, tried in
    #: order. ``main`` and ``article`` first because a job description is
    #: almost always inside one and the page furniture is not.
    CONTENT_SELECTORS = (
        "[itemprop='description']",
        "main",
        "article",
        "#job-description",
        ".job-description",
        ".jobDescription",
        ".job-details",
        ".jobDetail",
        "[class*='description']",
        "[class*='Description']",
    )

    def matches(self, url: str) -> bool:
        """True for anything. That is the point of this adapter."""
        return bool(self.host_of(url))

    def collect(self, url: str) -> JobData:
        url = str(url or "").strip()
        if not url:
            raise ValueError("URL cannot be empty")

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Enter a full http(s) URL.")

        try:
            response = requests.get(
                url,
                timeout=self.TIMEOUT_SECONDS,
                headers={"User-Agent": self.USER_AGENT},
            )
        except requests.Timeout:
            raise requests.RequestException(
                f"Request to {url} timed out after {self.TIMEOUT_SECONDS} seconds"
            )
        except requests.RequestException as exc:
            raise requests.RequestException(f"Failed to fetch {url}: {exc}")

        html = response.text
        soup = BeautifulSoup(html, "html.parser")

        posting = self._from_json_ld(soup)
        if posting:
            posting["url"] = url
            posting["source"] = self.name
            return JobData(**posting)

        return self._from_html(url, soup, parsed)
    # -- JSON-LD ------------------------------------------------------------

    @classmethod
    def _from_json_ld(cls, soup) -> dict | None:
        """
        Find a ``JobPosting`` in any ``application/ld+json`` block.

        Returns a partial JobData dict, or ``None`` when the page has no usable
        structured data. A ``None`` here is normal and is not an error -- the
        HTML fallback runs next.
        """
        for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = tag.string or tag.get_text() or ""
            raw = raw.strip()
            if not raw:
                continue

            for payload in cls._iter_ld_payloads(raw):
                if not isinstance(payload, dict):
                    continue
                if payload.get("@type") != "JobPosting":
                    continue

                built = cls._job_posting_to_dict(payload)
                if built:
                    return built
        return None

    @staticmethod
    def _iter_ld_payloads(raw: str):
        """
        Yield candidate dicts from a JSON-LD block.

        Handles the three shapes seen in the wild: a single object, an array,
        and an object whose ``@graph`` holds the objects. A malformed block
        yields nothing rather than raising -- a page with one broken JSON-LD
        block is still worth scraping.
        """
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            # Some sites emit JSON-LD with trailing commas or unescaped
            # characters. A regex for the first balanced object is not worth
            # the complexity; the HTML fallback covers this case.
            return

        if isinstance(data, list):
            yield from data
            return

        if not isinstance(data, dict):
            return

        graph = data.get("@graph")
        if isinstance(graph, list):
            yield from graph
        yield data

    @classmethod
    def _job_posting_to_dict(cls, node: dict) -> dict | None:
        title = cls._first_string(node, "title", "name")
        description = cls._html_to_text(cls._first_string(node, "description"))

        if not title or not description:
            # A JobPosting with no description would score against nothing.
            return None

        return {
            "company": cls._company_from(node),
            "title": title.strip(),
            "location": cls._location_from(node),
            "description": description,
        }

    @staticmethod
    def _first_string(node: dict, *keys) -> str:
        for key in keys:
            value = node.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""

    @classmethod
    def _company_from(cls, node: dict) -> str:
        """
        The hiring organisation, as a string.

        ``hiringOrganization`` is a dict in valid JSON-LD but a bare string in
        a fair number of real pages, so both are accepted.
        """
        value = node.get("hiringOrganization")
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return cls._first_string(value, "name", "legalName").strip()
        return ""

    @classmethod
    def _location_from(cls, node: dict) -> str:
        value = node.get("jobLocation")
        entries = value if isinstance(value, list) else [value]
        parts: list[str] = []

        for entry in entries:
            if not isinstance(entry, dict):
                continue
            address = entry.get("address")
            if not isinstance(address, dict):
                continue
            locality = address.get("addressLocality")
            region = address.get("addressRegion")
            if isinstance(locality, str) and locality.strip():
                parts.append(locality.strip())
            elif isinstance(region, str) and region.strip():
                parts.append(region.strip())

        return ", ".join(parts[:3])

    # -- HTML fallback ------------------------------------------------------

    def _from_html(self, url: str, soup, parsed) -> JobData:
        title = self._title_from(soup) or (parsed.path.strip("/").split("/")[-1] or "")
        title = re.sub(r"[-|]\s*\w[\w .,&-]*$", "", title).strip() or "Untitled role"

        description = self._description_from(soup)
        if not description:
            raise ValueError(
                "That page did not contain a readable job description. It may "
                "be a search or sign-in page -- open the individual job and "
                "copy that URL."
            )

        return JobData(
            url=url,
            company=self._company_from_html(soup, parsed),
            title=title,
            location="",
            description=description,
            source=self.name,
        )

    @staticmethod
    def _title_from(soup) -> str:
        """``og:title`` first, then ``<title>``. The former is the job, the
        latter is often "<title> - <Company> Careers"."""
        for selector, attr in (
            ('meta[property="og:title"]', "content"),
            ('meta[name="twitter:title"]', "content"),
        ):
            tag = soup.select_one(selector)
            value = tag.get(attr) if tag else ""
            if value and value.strip():
                return value.strip()

        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return ""

    @classmethod
    def _company_from_html(cls, soup, parsed) -> str:
        for selector in (
            'meta[property="og:site_name"]',
            'meta[name="twitter:site"]',
        ):
            tag = soup.select_one(selector)
            value = tag.get("content") if tag else ""
            if value and value.strip():
                return value.strip()

        hostname = (parsed.netloc or "").lower()
        return hostname[4:] if hostname.startswith("www.") else hostname

    @classmethod
    def _description_from(cls, soup) -> str:
        for selector in cls.CONTENT_SELECTORS:
            node = soup.select_one(selector)
            if node is None:
                continue
            text = cls._html_to_text(node.decode_contents())
            if len(text) >= 200:
                return text

        return cls._html_to_text(soup.decode_contents())

    # -- text ---------------------------------------------------------------

    @staticmethod
    def _html_to_text(html: str) -> str:
        """
        Flatten HTML to text, preserving list-item boundaries.

        Keeping ``<li>`` on its own lines is what stops "Docker, Kubernetes,
        Terraform" from becoming one run-on string, which the skill extractor
        would then read as a single unknown skill.
        """
        if not html:
            return ""
        if "<" not in html:
            return html.strip()

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return html.strip()

        for element in soup(["script", "style", "noscript", "svg", "template"]):
            element.decompose()

        for item in soup.find_all("li"):
            item.insert_after("\n")
        for block in soup.find_all(["p", "div", "br", "h1", "h2", "h3", "h4", "h5", "tr"]):
            block.insert_after("\n")

        text = soup.get_text(separator="\n", strip=True)
        lines = [line.strip() for line in text.splitlines()]
        text = "\n".join(line for line in lines if line)
        return re.sub(r"\n{3,}", "\n\n", text).strip()
