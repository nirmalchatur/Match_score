from bs4 import BeautifulSoup


class JDParser:
    """
    Parses HTML content into clean text.
    
    Responsibilities:
    - Accept raw HTML
    - Remove non-content elements (script, style, etc.)
    - Extract clean text
    - Validate output
    
    Does NOT extract job data fields or score matches.
    """

    @staticmethod
    def parse(html: str) -> str:
        """
        Parse HTML into clean text.
        
        Args:
            html: Raw HTML string
            
        Returns:
            Clean text extracted from HTML
            
        Raises:
            ValueError: If HTML is empty or contains no text
        """
        if not html or not str(html).strip():
            raise ValueError("HTML cannot be empty")

        html = str(html).strip()

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception as e:
            raise ValueError(
                f"Failed to parse HTML: {str(e)}"
            )

        # Remove non-content elements
        for element in soup(
            ["script", "style", "noscript", "svg"]
        ):
            element.decompose()

        # Extract text
        text = soup.get_text(
            separator=" ",
            strip=True,
        )

        if not text or not text.strip():
            raise ValueError(
                "No text content found in HTML"
            )

        return text.strip()