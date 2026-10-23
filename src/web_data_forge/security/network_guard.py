"""
Network security guardrails: safe HTTP fetching with redirect revalidation,
strict timeouts, and bounded payload sizes.
"""

from typing import Optional, Tuple
from urllib.parse import urljoin
import requests

from web_data_forge.core.exceptions import (
    NetworkError,
    ResponseTooLargeError,
    SecurityError,
    UrlValidationError,
)
from web_data_forge.inspection.url_validator import validate_url

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MAX_BYTES = 5 * 1024 * 1024  # 5 Megabytes
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = (
    "WebDataForgeBot/0.1.0 (+https://github.com/KasunV-git/Web-Data-Forge)"
)
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}


class SafeFetcher:
    """
    HTTP client enforcing SSRF controls, redirect revalidation, bounded memory,
    and timeouts on every hop.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        max_redirects: int = DEFAULT_MAX_REDIRECTS,
        user_agent: str = DEFAULT_USER_AGENT,
    ) -> None:
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        self.user_agent = user_agent

    def fetch(
        self,
        url: str,
        verify_dns: bool = True,
        custom_headers: Optional[dict] = None,
    ) -> Tuple[str, str, int]:
        """
        Fetch HTML from a destination URL while enforcing SSRF checks on initial
        URL and on every redirect destination.

        Args:
            url: Target URL to fetch.
            verify_dns: Whether to perform DNS resolution and IP safety checks.
            custom_headers: Optional additional headers to merge.

        Returns:
            Tuple of (html_content, final_url, status_code).

        Raises:
            UrlValidationError: If any hop targets an unsafe IP/scheme.
            ResponseTooLargeError: If response payload exceeds max_bytes.
            SecurityError: If redirect depth exceeds max_redirects.
            NetworkError: If connection fails or times out.
        """
        current_url = validate_url(url, verify_dns=verify_dns)
        headers = {"User-Agent": self.user_agent, "Accept": "text/html,application/xhtml+xml"}
        if custom_headers:
            headers.update(custom_headers)

        redirects_followed = 0

        with requests.Session() as session:
            while True:
                try:
                    response = session.get(
                        current_url,
                        headers=headers,
                        timeout=self.timeout,
                        stream=True,
                        allow_redirects=False,
                    )
                except requests.exceptions.Timeout as e:
                    raise NetworkError(
                        f"Request timed out after {self.timeout}s: {e}"
                    ) from e
                except requests.exceptions.RequestException as e:
                    raise NetworkError(f"HTTP connection failed: {e}") from e

                # Handle HTTP redirects explicitly to inspect destination
                if response.status_code in REDIRECT_STATUS_CODES:
                    redirects_followed += 1
                    if redirects_followed > self.max_redirects:
                        response.close()
                        raise SecurityError(
                            f"Too many redirects: exceeded limit of {self.max_redirects}."
                        )

                    location = response.headers.get("Location")
                    if not location:
                        response.close()
                        raise NetworkError(
                            f"Redirect status {response.status_code} received without Location header."
                        )

                    # Resolve relative redirect paths (e.g. '/products' -> 'https://example.com/products')
                    next_url = urljoin(current_url, location)

                    # CRITICAL SSRF CHECK: Validate new redirect target before following
                    try:
                        current_url = validate_url(next_url, verify_dns=verify_dns)
                    except UrlValidationError as e:
                        response.close()
                        raise UrlValidationError(
                            f"Blocked dangerous redirect to '{next_url}': {e.message}"
                        ) from e

                    response.close()
                    continue

                # Final non-redirect response handling
                try:
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > self.max_bytes:
                        raise ResponseTooLargeError(
                            f"Response Content-Length ({content_length} bytes) exceeds limit ({self.max_bytes} bytes)."
                        )

                    total_bytes = 0
                    chunks = []
                    for chunk in response.iter_content(chunk_size=8192):
                        total_bytes += len(chunk)
                        if total_bytes > self.max_bytes:
                            raise ResponseTooLargeError(
                                f"Response payload exceeded limit of {self.max_bytes} bytes."
                            )
                        chunks.append(chunk)

                    raw_body = b"".join(chunks)
                    encoding = response.encoding or "utf-8"
                    try:
                        html_text = raw_body.decode(encoding, errors="replace")
                    except Exception:
                        html_text = raw_body.decode("utf-8", errors="replace")

                    return html_text, current_url, response.status_code
                finally:
                    response.close()


def fetch_html(
    url: str,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    verify_dns: bool = True,
) -> Tuple[str, str, int]:
    """
    Convenience function to safely fetch HTML content using default SafeFetcher.
    """
    fetcher = SafeFetcher(
        timeout=timeout,
        max_bytes=max_bytes,
        max_redirects=max_redirects,
    )
    return fetcher.fetch(url, verify_dns=verify_dns)
