import re
from datetime import date


class ExperienceParser:

    MONTHS = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    @classmethod
    def parse(cls, text: str) -> dict:

        if not text or not text.strip():
            return {
                "total_months": 0,
                "total_years": 0.0,
                "roles": [],
            }

        roles = cls._extract_roles(text)

        total_months = cls._calculate_total_months(roles)

        return {
            "total_months": total_months,
            "total_years": round(total_months / 12, 2),
            "roles": roles,
        }

    @classmethod
    def _extract_roles(cls, text: str) -> list:

        roles = []

        pattern = re.compile(
            r"""
            (?P<start_month>
                Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|
                Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|
                Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|
                Nov(?:ember)?|Dec(?:ember)?
            )
            \s+
            (?P<start_year>\d{4})

            \s*(?:to|-|–|—)\s*

            (?:
                (?P<end_month>
                    Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|
                    Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|
                    Aug(?:ust)?|Sep(?:t|tember)?|Oct(?:ober)?|
                    Nov(?:ember)?|Dec(?:ember)?
                )
                \s+
                (?P<end_year>\d{4})
                |
                (?P<current>present|current|now)
            )
            """,
            re.IGNORECASE | re.VERBOSE,
        )

        for match in pattern.finditer(text):

            start_month = cls.MONTHS[
                match.group("start_month").lower()
            ]

            start_year = int(match.group("start_year"))

            if match.group("current"):
                end_year = date.today().year
                end_month = date.today().month
            else:
                end_month = cls.MONTHS[
                    match.group("end_month").lower()
                ]
                end_year = int(match.group("end_year"))

            months = (
                (end_year - start_year) * 12
                + (end_month - start_month)
            )

            if months < 0:
                continue

            # Capture some surrounding text.
            start = max(0, match.start() - 150)
            end = min(len(text), match.end() + 150)

            context = text[start:end]

            roles.append({
                "start": f"{start_year:04d}-{start_month:02d}",
                "end": (
                    "present"
                    if match.group("current")
                    else f"{end_year:04d}-{end_month:02d}"
                ),
                "months": months,
                "context": context.strip(),
            })

        return roles

    @staticmethod
    def _calculate_total_months(roles: list) -> int:

        if not roles:
            return 0

        # V1 assumes roles do not overlap.
        # We'll improve overlap handling later.

        intervals = []

        for role in roles:

            start_year, start_month = map(
                int,
                role["start"].split("-")
            )

            if role["end"] == "present":
                end = date.today()
                end_year = end.year
                end_month = end.month
            else:
                end_year, end_month = map(
                    int,
                    role["end"].split("-")
                )

            start_index = start_year * 12 + start_month
            end_index = end_year * 12 + end_month

            intervals.append(
                (start_index, end_index)
            )

        intervals.sort()

        merged = []

        for start, end in intervals:

            if not merged or start > merged[-1][1]:
                merged.append([start, end])
            else:
                merged[-1][1] = max(
                    merged[-1][1],
                    end
                )

        return sum(
            end - start
            for start, end in merged
        )