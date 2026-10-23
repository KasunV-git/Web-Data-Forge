"""
Unit tests for SafeFetcher and network security guardrails.
"""

from unittest.mock import MagicMock
import pytest
import requests

from web_data_forge.core.exceptions import (
    NetworkError,
    ResponseTooLargeError,
    SecurityError,
    UrlValidationError,
)
from web_data_forge.security.network_guard import SafeFetcher, fetch_html


class MockResponse:
    """Mock for requests.Response object."""

    def __init__(
        self,
        status_code: int = 200,
        content: bytes = b"<html><body><h1>Test</h1></body></html>",
        headers: dict = None,
        encoding: str = "utf-8",
    ):
        self.status_code = status_code
        self._content = content
        self.headers = headers or {}
        self.encoding = encoding

    def iter_content(self, chunk_size=8192):
        for i in range(0, len(self._content), chunk_size):
            yield self._content[i : i + chunk_size]

    def close(self):
        pass


class TestSafeFetcher:
    """Test suite for SafeFetcher HTTP client."""

    def test_fetch_success(self, monkeypatch):
        """Verify successful fetch returns HTML, final URL, and 200 status."""
        html_bytes = b"<html><body><h1>Success</h1></body></html>"
        mock_resp = MockResponse(200, html_bytes)

        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: mock_resp
        )

        html, final_url, status = fetch_html(
            "https://example.com/page", verify_dns=False
        )
        assert "<h1>Success</h1>" in html
        assert final_url == "https://example.com/page"
        assert status == 200

    def test_timeout_raises_network_error(self, monkeypatch):
        """Verify timeout raises clean NetworkError."""

        def mock_get(*args, **kwargs):
            raise requests.exceptions.Timeout("Connection timed out")

        monkeypatch.setattr(requests.Session, "get", mock_get)

        with pytest.raises(NetworkError, match="timed out"):
            fetch_html("https://example.com", timeout=2.0, verify_dns=False)

    def test_connection_error_raises_network_error(self, monkeypatch):
        """Verify transport failure raises NetworkError."""

        def mock_get(*args, **kwargs):
            raise requests.exceptions.ConnectionError("Failed to resolve")

        monkeypatch.setattr(requests.Session, "get", mock_get)

        with pytest.raises(NetworkError, match="HTTP connection failed"):
            fetch_html("https://example.com", verify_dns=False)

    def test_content_length_exceeded_rejected(self, monkeypatch):
        """Verify oversized Content-Length header is rejected before reading body."""
        mock_resp = MockResponse(
            200, b"", headers={"Content-Length": str(10 * 1024 * 1024)}
        )
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: mock_resp
        )

        fetcher = SafeFetcher(max_bytes=1024)  # 1 KB limit
        with pytest.raises(ResponseTooLargeError, match="Content-Length"):
            fetcher.fetch("https://example.com", verify_dns=False)

    def test_streaming_payload_size_exceeded(self, monkeypatch):
        """Verify streaming body exceeding max_bytes triggers ResponseTooLargeError."""
        oversized_content = b"X" * 2048
        mock_resp = MockResponse(200, oversized_content)
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: mock_resp
        )

        fetcher = SafeFetcher(max_bytes=1000)  # 1000 bytes limit
        with pytest.raises(ResponseTooLargeError, match="payload exceeded limit"):
            fetcher.fetch("https://example.com", verify_dns=False)

    def test_safe_redirect_followed(self, monkeypatch):
        """Verify safe 302 redirect is properly followed to new destination."""
        resp_redirect = MockResponse(
            302, b"", headers={"Location": "https://example.com/final"}
        )
        resp_final = MockResponse(200, b"<html>Final page</html>")

        responses = [resp_redirect, resp_final]

        def mock_get(*args, **kwargs):
            return responses.pop(0)

        monkeypatch.setattr(requests.Session, "get", mock_get)

        html, final_url, status = fetch_html(
            "https://example.com/initial", verify_dns=False
        )
        assert html == "<html>Final page</html>"
        assert final_url == "https://example.com/final"
        assert status == 200

    def test_dangerous_redirect_to_loopback_blocked(self, monkeypatch):
        """Verify SSRF: 302 redirect to loopback 127.0.0.1 is intercepted and blocked."""
        resp_redirect = MockResponse(
            302, b"", headers={"Location": "http://127.0.0.1/admin"}
        )
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: resp_redirect
        )

        with pytest.raises(UrlValidationError, match="Blocked dangerous redirect"):
            fetch_html("https://example.com/login", verify_dns=True)

    def test_dangerous_redirect_to_metadata_blocked(self, monkeypatch):
        """Verify SSRF: redirect to cloud metadata 169.254.169.254 is intercepted."""
        resp_redirect = MockResponse(
            302, b"", headers={"Location": "http://169.254.169.254/latest"}
        )
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: resp_redirect
        )

        with pytest.raises(UrlValidationError, match="Blocked dangerous redirect"):
            fetch_html("https://example.com/trigger", verify_dns=True)

    def test_max_redirects_exceeded(self, monkeypatch):
        """Verify redirect loop beyond limit raises SecurityError."""
        resp_loop = MockResponse(
            301, b"", headers={"Location": "https://example.com/loop"}
        )
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: resp_loop
        )

        fetcher = SafeFetcher(max_redirects=3)
        with pytest.raises(SecurityError, match="Too many redirects"):
            fetcher.fetch("https://example.com/loop", verify_dns=False)

    def test_redirect_without_location_header_fails(self, monkeypatch):
        """Verify redirect status missing Location header raises NetworkError."""
        resp_no_loc = MockResponse(302, b"", headers={})
        monkeypatch.setattr(
            requests.Session, "get", lambda *args, **kwargs: resp_no_loc
        )

        with pytest.raises(NetworkError, match="without Location header"):
            fetch_html("https://example.com/bad-redirect", verify_dns=False)
