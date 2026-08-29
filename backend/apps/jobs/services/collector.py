import requests
from urllib.parse import urlparse


class JobFetcher:
    """
    Fetches HTML content from a job posting URL.
    
    Responsibilities:
    - Validate URL format
    - Perform HTTP GET request
    - Handle network errors
    - Return raw HTML
    
    Does NOT parse or structure job data.
    """

    USER_AGENT = (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "Chrome/131.0 Safari/537.36"
    )
    TIMEOUT_SECONDS = 15

    @staticmethod
    def fetch(url: str) -> str:
        """
        Fetch HTML content from a URL.
        
        Args:
            url: Valid HTTP(S) URL string
            
        Returns:
            Raw HTML content as string
            
        Raises:
            ValueError: If URL is empty or invalid
            requests.RequestException: If HTTP request fails
        """
        if not url or not str(url).strip():
            raise ValueError("URL cannot be empty")

        url = str(url).strip()

        # Validate URL format
        try:
            parsed = urlparse(url)
            if not parsed.scheme:
                raise ValueError(
                    "URL must include http:// or https://"
                )
            if parsed.scheme not in ("http", "https"):
                raise ValueError(
                    "URL must be HTTP or HTTPS"
                )
            if not parsed.netloc:
                raise ValueError(
                    "URL must include a domain"
                )
        except Exception as e:
            raise ValueError(
                f"Invalid URL format: {str(e)}"
            )

        try:
            response = requests.get(
                url,
                timeout=JobFetcher.TIMEOUT_SECONDS,
                headers={
                    "User-Agent": JobFetcher.USER_AGENT
                },
            )

            response.raise_for_status()

            return response.text

        except requests.ConnectionError as e:
            raise requests.RequestException(
                f"Failed to connect to {url}: {str(e)}"
            )
        except requests.Timeout:
            raise requests.RequestException(
                f"Request to {url} timed out after "
                f"{JobFetcher.TIMEOUT_SECONDS} seconds"
            )
        except requests.HTTPError as e:
            raise requests.RequestException(
                f"HTTP error {response.status_code} "
                f"from {url}: {str(e)}"
            )
        except requests.RequestException as e:
            raise requests.RequestException(
                f"Failed to fetch {url}: {str(e)}"
            )