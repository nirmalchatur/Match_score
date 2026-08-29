from dataclasses import dataclass


@dataclass
class JobData:
    url: str
    company: str
    title: str
    location: str
    description: str


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