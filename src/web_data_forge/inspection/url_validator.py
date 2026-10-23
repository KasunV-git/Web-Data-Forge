"""
URL validation and security controls.

Guarantees that input URLs use permitted schemes, do not embed credentials,
and meet basic format standards before network resolution.
"""

from urllib.parse import urlsplit
from web_data_forge.core.exceptions import UrlValidationError

PERMITTED_SCHEMES = {"http", "https"}


def validate_url_syntax(url: str) -> str:
    """
    Validate the syntax of a candidate URL.

    Checks:
    - URL must not be empty or whitespace.
    - Scheme must be strictly 'http' or 'https'.
    - Hostname must be present and non-empty.
    - Embedded credentials (userinfo) are prohibited.

    Returns:
        The stripped, verified URL string.

    Raises:
        UrlValidationError: If the URL fails any syntactic or safety criteria.
    """
    if not url or not url.strip():
        raise UrlValidationError("URL cannot be empty or whitespace.")

    cleaned_url = url.strip()

    try:
        parsed = urlsplit(cleaned_url)
    except Exception as e:
        raise UrlValidationError(f"Failed to parse URL: {e}") from e

    scheme = parsed.scheme.lower()
    if not scheme:
        raise UrlValidationError("URL must include an explicit scheme (e.g., https://).")

    if scheme not in PERMITTED_SCHEMES:
        raise UrlValidationError(
            f"Scheme '{scheme}' is forbidden. Only {sorted(PERMITTED_SCHEMES)} are permitted."
        )

    if not parsed.hostname:
        raise UrlValidationError("URL must include a valid, non-empty hostname.")

    if parsed.username or parsed.password:
        raise UrlValidationError(
            "URLs containing embedded credentials (username:password) are forbidden."
        )

    return cleaned_url


def validate_url(url: str) -> str:
    """
    Primary URL validation entrypoint.
    Runs syntactic and safety checks.
    """
    return validate_url_syntax(url)
