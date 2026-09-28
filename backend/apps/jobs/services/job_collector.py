from dataclasses import dataclass

from apps.jobs.services.collector import JobFetcher
from apps.jobs.services.jd_parser import JDParser


@dataclass
class JobData:
    url: str
    company: str
    title: str
    location: str
    description: str

    #: Which board this came from, e.g. "greenhouse", "workday", "generic".
    #:
    #: Set by the adapter rather than inferred from the URL afterwards, so the
    #: value records what actually *read* the posting. A default is given so
    #: the many existing call sites and tests that build JobData directly keep
    #: working; an empty value renders as a neutral badge in the UI rather than
    #: being hidden, because "we do not know where this came from" is worth
    #: showing once.
    source: str = ""


class JobCollector:

    def collect(self, source_data: dict) -> JobData:

        required_fields = [
            "url",
            "company",
            "title",
            "description",
        ]

        for field in required_fields:

            if not source_data.get(field):
                raise ValueError(
                    f"Missing required job field: {field}"
                )

        return JobData(
            url=source_data["url"].strip(),
            company=source_data["company"].strip(),
            title=source_data["title"].strip(),
            location=source_data.get(
                "location",
                ""
            ).strip(),
            description=source_data[
                "description"
            ].strip(),
        )

    def collect_from_url(
        self,
        source_data: dict,
    ) -> JobData:
        """
        Create JobData by fetching and parsing HTML from a URL.

        Args:
            source_data: Dictionary containing:
                - url: Job posting URL
                - company: Company name
                - title: Job title
                - location: Optional job location

        Returns:
            JobData with description populated from parsed HTML

        Raises:
            ValueError: If required fields are missing or invalid
            requests.RequestException: If fetch fails
        """

        # Validate required metadata
        required_metadata = [
            "url",
            "company",
            "title",
        ]

        for field in required_metadata:

            if not source_data.get(field):
                raise ValueError(
                    f"Missing required field: {field}"
                )

        url = source_data["url"].strip()
        company = source_data["company"].strip()
        title = source_data["title"].strip()
        location = source_data.get(
            "location",
            ""
        ).strip()

        # Fetch HTML from URL
        html = JobFetcher.fetch(url)

        # Parse HTML to clean text
        description = JDParser.parse(html)

        # Create and return JobData
        return JobData(
            url=url,
            company=company,
            title=title,
            location=location,
            description=description,
        )