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
        assert validate_url(valid_url, verify_dns=False) == valid_url

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


class TestSsrfAndIpValidation:
    """Test suite for IP filtering and SSRF defenses."""

    @pytest.mark.parametrize(
        "restricted_ip_url",
        [
            "http://127.0.0.1/admin",
            "http://127.0.0.254",
            "http://10.0.0.1/secret",
            "http://10.255.255.255/",
            "http://172.16.0.1/",
            "http://172.31.255.255/",
            "http://192.168.1.100/router",
            "http://169.254.169.254/latest/meta-data/",
            "http://0.0.0.0/",
            "http://100.64.0.1/",
            "http://[::1]/",
        ],
    )
    def test_direct_restricted_ips_rejected(self, restricted_ip_url):
        with pytest.raises(UrlValidationError, match="SSRF Protection"):
            validate_url(restricted_ip_url, verify_dns=True)

    def test_localhost_rejected(self, monkeypatch):
        """Simulate localhost resolving to 127.0.0.1."""
        def mock_getaddrinfo(host, port, family, socktype):
            return [(2, 1, 0, "", ("127.0.0.1", 80))]

        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
        with pytest.raises(UrlValidationError, match="loopback"):
            validate_url("http://localhost/metrics")

    def test_cloud_metadata_domain_rejected(self, monkeypatch):
        """Simulate a custom domain resolving to cloud metadata IP."""
        def mock_getaddrinfo(host, port, family, socktype):
            return [(2, 1, 0, "", ("169.254.169.254", 80))]

        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
        with pytest.raises(UrlValidationError, match="cloud metadata"):
            validate_url("http://attacker-owned-domain.com/credentials")

    def test_private_rfc1918_domain_rejected(self, monkeypatch):
        """Simulate DNS rebinding or internal domain resolving to private network."""
        def mock_getaddrinfo(host, port, family, socktype):
            return [(2, 1, 0, "", ("192.168.1.50", 80))]

        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
        with pytest.raises(UrlValidationError, match="private RFC1918"):
            validate_url("http://internal-payroll.company.local/dashboard")

    def test_safe_public_ip_passes(self, monkeypatch):
        """Simulate valid public IP resolution."""
        def mock_getaddrinfo(host, port, family, socktype):
            return [(2, 1, 0, "", ("93.184.216.34", 80))]

        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
        url = "https://safe-public-website.com/data"
        assert validate_url(url, verify_dns=True) == url

    def test_dns_resolution_failure(self, monkeypatch):
        """Simulate unresolvable hostname throwing UrlValidationError."""
        import socket

        def mock_getaddrinfo(host, port, family, socktype):
            raise socket.gaierror(-2, "Name or service not known")

        monkeypatch.setattr("socket.getaddrinfo", mock_getaddrinfo)
        with pytest.raises(UrlValidationError, match="DNS resolution failed"):
            validate_url("https://nonexistent-domain-404xyz.org")

