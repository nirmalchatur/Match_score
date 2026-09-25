"""
Greenhouse job board adapter.

Extracts job data from Greenhouse public job boards.

Supported URL format:
- https://[company].greenhouse.io/jobs/[job-id]
- https://[company].greenhouse.io/jobs/[job-slug]
- https://job-boards.greenhouse.io/[company]/jobs/[job-id]

Where [company] is the company's subdomain on Greenhouse.io.

The adapter extracts structured data from the job posting page and
returns a standard JobData object.

Note: Custom Greenhouse domains are not yet supported.
"""

import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from apps.jobs.services.job_collector import JobData


class GreenhouseCollector:
    """
    Extracts job data from Greenhouse public job postings.

    Does NOT:
    - Require authentication
    - Scrape LinkedIn
    - Use browser automation
    - Bypass anti-bot systems

    Does:
    - Parse public Greenhouse job board URLs
    - Extract structured job data
    - Return standard JobData object
    """

    TIMEOUT_SECONDS = 15
    USER_AGENT = (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    )

    @staticmethod
    def collect(url: str) -> JobData:
        """
        Extract job data from a Greenhouse job posting URL.

        Args:
            url: Greenhouse job board URL

        Returns:
            JobData with extracted job information

        Raises:
            ValueError: If URL is invalid or not a Greenhouse URL
            requests.RequestException: If fetch fails
            KeyError: If required fields are missing from response
        """
        if not url or not str(url).strip():
            raise ValueError("URL cannot be empty")

        url = str(url).strip()

        # Validate and parse URL
        parsed = urlparse(url)

        if not parsed.scheme or parsed.scheme not in (
            "http",
            "https",
        ):
            raise ValueError(
                "Invalid URL: must include http:// or https://"
            )

        if not parsed.netloc:
            raise ValueError("Invalid URL: missing domain")

        # Verify it's a Greenhouse URL
        if not GreenhouseCollector._is_greenhouse_url(
            parsed.netloc
        ):
            raise ValueError(
                "URL is not a Greenhouse job board"
            )

        # Fetch the job posting page
        try:
            response = requests.get(
                url,
                timeout=GreenhouseCollector.TIMEOUT_SECONDS,
                headers={
                    "User-Agent": (
                        GreenhouseCollector.USER_AGENT
                    )
                },
            )

            response.raise_for_status()

        except requests.Timeout:
            raise requests.RequestException(
                f"Request to {url} timed out after "
                f"{GreenhouseCollector.TIMEOUT_SECONDS} seconds"
            )
        except requests.ConnectionError as e:
            raise requests.RequestException(
                f"Failed to connect to {url}: {str(e)}"
            )
        except requests.HTTPError as e:
            raise requests.RequestException(
                f"HTTP error from {url}: {str(e)}"
            )
        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to fetch {url}: {str(e)}"
            )

        # Parse the response
        try:
            job_data = (
                GreenhouseCollector._parse_response(
                    response.text,
                    url,
                )
            )
        except Exception as e:
            raise ValueError(
                f"Failed to parse Greenhouse response: {str(e)}"
            )

        return JobData(
            url=url,
            company=job_data["company"],
            title=job_data["title"],
            location=job_data.get("location", ""),
            description=job_data["description"],
        )

    @staticmethod
    def _is_greenhouse_url(netloc: str) -> bool:
        """
        Strictly validate that URL is from official Greenhouse.io domain.

        Accepts:
        - [company].greenhouse.io (old format)
        - job-boards.greenhouse.io (new format, company in path)

        Rejects:
        - greenhouse.io (no subdomain)
        - www.greenhouse.io (reserved subdomain)
        - greenhouse.io.evil.com (domain suffix)
        - evilgreenhouse.io (unrelated domain)
        - Custom domains (not supported yet)

        Args:
            netloc: Network location (domain) from URL

        Returns:
            True if it's a valid Greenhouse URL, False otherwise
        """
        netloc_lower = netloc.lower()

        # Must end with .greenhouse.io exactly
        if not netloc_lower.endswith(".greenhouse.io"):
            return False

        # Extract subdomain
        parts = netloc_lower.split(".")

        # Must be exactly [subdomain].greenhouse.io (3 parts)
        if len(parts) != 3:
            return False

        subdomain = parts[0]

        # New format: job-boards.greenhouse.io (company in path)
        if subdomain == "job-boards":
            return True

        # Old format: [company].greenhouse.io
        # Reject reserved/special subdomains
        if subdomain in ("www", "mail", "ftp", "smtp"):
            return False

        # Subdomain must be non-empty and alphanumeric (with - and _)
        if not subdomain or not subdomain.replace("-", "").replace(
            "_", ""
        ).isalnum():
            return False

        return True

    @staticmethod
    def _is_job_posting(type_value) -> bool:
        """
        Check if @type indicates a JobPosting.

        Handles @type as:
        - string: "JobPosting"
        - list: ["JobPosting", "Thing"]

        Args:
            type_value: The @type field from JSON-LD

        Returns:
            True if this is a JobPosting, False otherwise
        """
        if isinstance(type_value, str):
            return type_value == "JobPosting"

        if isinstance(type_value, list):
            return "JobPosting" in type_value

        return False

    @staticmethod
    def _extract_company_from_url(url: str) -> str:
        """
        Extract company name from supported Greenhouse URL formats.

        Supported:
        - https://[company].greenhouse.io/jobs/...
        - https://job-boards.greenhouse.io/[company]/jobs/...
        """
        parsed = urlparse(url)
        netloc = parsed.netloc.lower()

        # New Greenhouse format:
        # https://job-boards.greenhouse.io/[company]/jobs/...
        if netloc == "job-boards.greenhouse.io":
            path_parts = [
                part for part in parsed.path.split("/")
                if part
            ]

            # Expected: /[company]/jobs/[job-id]
            if len(path_parts) >= 3 and path_parts[1].lower() == "jobs":
                company = path_parts[0]

                if company:
                    return (
                        company
                        .replace("-", " ")
                        .replace("_", " ")
                        .title()
                    )

            raise ValueError(
                f"Cannot extract company from {url}"
            )

        # Old Greenhouse format:
        # https://[company].greenhouse.io/jobs/...
        if not netloc.endswith(".greenhouse.io"):
            raise ValueError(
                "Cannot extract company: URL is not Greenhouse"
            )

        parts = netloc.split(".")

        if len(parts) != 3 or parts[1] != "greenhouse":
            raise ValueError(
                f"Cannot extract company from {netloc}"
            )

        company = parts[0]

        if company in ("www", "mail", "ftp", "smtp"):
            raise ValueError(
                f"Cannot extract company from reserved subdomain: {company}"
            )

        return (
            company
            .replace("-", " ")
            .replace("_", " ")
            .title()
        )

    @staticmethod
    def _parse_response(
        html: str,
        url: str,
    ) -> dict:
        """
        Extract job data from Greenhouse HTML response.

        Greenhouse embeds JSON-LD structured data in the page.
        This method extracts and parses that data.

        Args:
            html: Raw HTML from Greenhouse job posting
            url: Original job posting URL (for fallback company name)

        Returns:
            Dictionary with keys: company, title, location, description

        Raises:
            ValueError: If required fields are missing
            KeyError: If JSON structure is unexpected
        """
        soup = BeautifulSoup(html, "html.parser")

        # Try to extract JSON-LD structured data
        json_ld = None

        for script in soup.find_all(
            "script",
            type="application/ld+json",
        ):
            try:
                data = json.loads(script.string)

                # Look for JobPosting type
                if isinstance(data, dict):
                    if GreenhouseCollector._is_job_posting(
                        data.get("@type")
                    ):
                        json_ld = data
                        break
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and (
                            GreenhouseCollector._is_job_posting(
                                item.get("@type")
                            )
                        ):
                            json_ld = item
                            break

                if json_ld:
                    break

            except (json.JSONDecodeError, TypeError, AttributeError):
                continue

        if json_ld:
            try:
                return GreenhouseCollector._extract_from_json_ld(
                    json_ld,
                    url,
                )
            except (KeyError, ValueError):
                # JSON-LD parsing failed, try HTML fallback
                pass

        # Fallback: parse HTML directly
        return GreenhouseCollector._extract_from_html(
            soup,
            url,
        )

    @staticmethod
    def _extract_from_json_ld(
        json_ld: dict,
        url: str,
    ) -> dict:
        """
        Extract job data from JSON-LD structured data.

        Args:
            json_ld: Parsed JSON-LD JobPosting object
            url: Job posting URL (for company extraction)

        Returns:
            Dictionary with job data

        Raises:
            KeyError: If required fields are missing
        """
        # Extract title
        title = json_ld.get("title")
        if not title:
            raise KeyError("Missing job title in JSON-LD data")

        # Extract location
        location = GreenhouseCollector._extract_location(
            json_ld.get("jobLocation")
        )

        # Extract description and normalize HTML
        description = json_ld.get("description")
        if not description:
            raise KeyError(
                "Missing job description in JSON-LD data"
            )

        # Normalize description: convert HTML to clean text
        description = (
            GreenhouseCollector._normalize_description(
                description
            )
        )

        # Extract company
        company_data = json_ld.get("hiringOrganization", {})
        company = ""

        if isinstance(company_data, dict):
            company = company_data.get("name", "")

        if not company:
            # Fallback: extract from URL
            company = GreenhouseCollector._extract_company_from_url(
                url
            )

        return {
            "title": title,
            "location": location,
            "description": description,
            "company": company,
        }

    @staticmethod
    def _extract_from_html(
        soup: BeautifulSoup,
        url: str,
    ) -> dict:
        """
        Extract job data from Greenhouse HTML.
        """

        # -------------------------
        # TITLE
        # -------------------------
        title_element = soup.select_one(".job__title h1")

        if not title_element:
            title_element = soup.find("h1")

        if not title_element:
            raise ValueError(
                "Could not extract job title from HTML"
            )

        title = title_element.get_text(
            " ",
            strip=True,
        )

        if not title:
            raise ValueError(
                "Could not extract job title from HTML"
            )

        # -------------------------
        # LOCATION
        # -------------------------
        location = ""
        location_element = None

        for selector in (
            ".job__location",
            ".job-post__location",
            ".location",
            "[data-testid='job-location']",
            "[data-qa='job-location']",
        ):
            location_element = soup.select_one(selector)
            if location_element:
                break

        if location_element:
            location = location_element.get_text(
                " ",
                strip=True,
            )

        # Fallback: many Greenhouse pages omit an explicit location node.
        # In those cases we keep the job valid and leave the location blank.
        if not location:
            header = soup.select_one(
                ".job__header, .job-post__header, .job-header"
            )
            if header:
                header_text = " ".join(
                    chunk.strip()
                    for chunk in header.get_text(
                        " ",
                        strip=True,
                    ).split()
                    if chunk.strip()
                )
                if header_text:
                    candidates = [
                        part.strip()
                        for part in re.split(
                            r"\s+(?:Remote|Hybrid|On-site|Onsite|United States|Canada|UK|Europe|APAC)\b",
                            header_text,
                        )
                        if part.strip()
                    ]
                    if len(candidates) > 1:
                        location = candidates[-1]

        # -------------------------
        # DESCRIPTION
        # -------------------------
        description_element = soup.select_one(
            ".job__description"
        )

        if not description_element:
            raise ValueError(
                "Could not extract job description from HTML"
            )

        description = description_element.get_text(
            " ",
            strip=True,
        )

        if not description or len(description) < 20:
            raise ValueError(
                "Could not extract meaningful job description"
            )

        # -------------------------
        # COMPANY
        # -------------------------
        company = GreenhouseCollector._extract_company_from_url(
            url
        )

        return {
            "title": title,
            "location": location,
            "description": description,
            "company": company,
        }

    @staticmethod
    def _extract_location(location_data) -> str:
        """
        Extract location from jobLocation field.

        Handles various formats:
        - dict with address field
        - list of locations
        - None/missing

        Args:
            location_data: jobLocation from JSON-LD

        Returns:
            Location string or empty string if not found
        """
        if not location_data:
            return ""

        # Handle dict format
        if isinstance(location_data, dict):
            address = location_data.get("address", {})

            if isinstance(address, dict):
                city = address.get("addressLocality", "")
                state = address.get("addressRegion", "")
                country = address.get("addressCountry", "")

                location_parts = [
                    p for p in [city, state, country] if p
                ]

                if location_parts:
                    return ", ".join(location_parts)

        # Handle list format
        elif isinstance(location_data, list):
            locations = []

            for loc in location_data:
                if isinstance(loc, dict):
                    address = loc.get("address", {})

                    if isinstance(address, dict):
                        city = address.get(
                            "addressLocality",
                            "",
                        )
                        state = address.get(
                            "addressRegion",
                            "",
                        )
                        country = address.get(
                            "addressCountry",
                            "",
                        )

                        parts = [
                            p
                            for p in [city, state, country]
                            if p
                        ]

                        if parts:
                            locations.append(
                                ", ".join(parts)
                            )

            if locations:
                return "; ".join(locations)

        return ""

    @staticmethod
    def _normalize_description(description: str) -> str:
        """
        Normalize description: convert HTML to clean text.

        Greenhouse descriptions may contain HTML tags.
        Convert to readable plain text while preserving list-item
        boundaries so downstream JD parsing keeps responsibility and
        requirement sections meaningful.

        Args:
            description: Raw description (may contain HTML)

        Returns:
            Clean text description
        """
        if not description:
            return ""

        # If no HTML tags, return as-is
        if "<" not in description:
            return description.strip()

        try:
            soup = BeautifulSoup(description, "html.parser")

            for li in soup.find_all("li"):
                li.insert_after("\n")

            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines()]
            text = "\n".join(line for line in lines if line)
            text = re.sub(r"\n{3,}", "\n\n", text)
            text = "\n".join(
                line.strip()
                for line in text.splitlines()
                if line.strip()
            )
            return text
        except Exception:
            # If parsing fails, return original
            return description.strip()