"""
Unit tests for URL syntax and basic safety validation.
"""

import pytest
from web_data_forge.core.exceptions import UrlValidationError
from web_data_forge.inspection.url_validator import validate_url_syntax, validate_url


class TestUrlSyntaxValidation:
    """Test suite for URL syntax and permitted schemes."""

    @pytest.mark.parametrize(
        "valid_url",
        [
            "https://example.com",
            "http://example.com/products",
            "https://sub.domain.co.uk/page?id=123&sort=asc#results",
            "https://api.github.com/repos",
        ],
    )
    def test_valid_urls_pass(self, valid_url):
        assert validate_url_syntax(valid_url) == valid_url
        assert validate_url(valid_url) == valid_url

    def test_empty_or_whitespace_urls_fail(self):
        with pytest.raises(UrlValidationError, match="cannot be empty"):
            validate_url_syntax("")

        with pytest.raises(UrlValidationError, match="cannot be empty"):
            validate_url_syntax("   ")

    def test_missing_scheme_fails(self):
        with pytest.raises(UrlValidationError, match="explicit scheme"):
            validate_url_syntax("example.com")

        with pytest.raises(UrlValidationError, match="explicit scheme"):
            validate_url_syntax("//example.com/test")

    @pytest.mark.parametrize(
        "forbidden_scheme_url",
        [
            "file:///etc/passwd",
            "ftp://ftp.example.com/data.txt",
            "data:text/html,<h1>Hello</h1>",
            "javascript:alert(1)",
            "gopher://gopher.floodgap.com",
        ],
    )
    def test_forbidden_schemes_rejected(self, forbidden_scheme_url):
        with pytest.raises(UrlValidationError, match="is forbidden"):
            validate_url_syntax(forbidden_scheme_url)

    @pytest.mark.parametrize(
        "credentials_url",
        [
            "https://admin:secret@example.com/dashboard",
            "http://user@example.com",
            "https://alice:pass123@api.service.internal",
        ],
    )
    def test_embedded_credentials_rejected(self, credentials_url):
        with pytest.raises(UrlValidationError, match="embedded credentials"):
            validate_url_syntax(credentials_url)

    def test_missing_hostname_fails(self):
        with pytest.raises(UrlValidationError, match="valid, non-empty hostname"):
            validate_url_syntax("https:///path/only")
