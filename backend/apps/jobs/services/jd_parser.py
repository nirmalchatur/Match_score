from bs4 import BeautifulSoup


class JDParser:

    @staticmethod
    def parse(html):
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        for element in soup(
            ["script", "style", "noscript", "svg"]
        ):
            element.decompose()

        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        return text