"""
URL validation and security controls.

Guarantees that input URLs use permitted schemes, do not embed credentials,
and meet basic format standards before network resolution.
"""

import ipaddress
import socket
from typing import List, Tuple
from urllib.parse import urlsplit

from web_data_forge.core.exceptions import UrlValidationError

PERMITTED_SCHEMES = {"http", "https"}

# Cloud metadata endpoints and additional dangerous addresses
CLOUD_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS, GCP, Azure, OpenStack
    ipaddress.ip_address("fd00:ec2::254"),   # AWS IPv6 metadata
}

# Carrier-Grade NAT (RFC 6598) and special reserved networks
SPECIAL_BLOCKED_NETWORKS = [
    ipaddress.ip_network("100.64.0.0/10"),     # Shared Address Space / CGNAT
    ipaddress.ip_network("0.0.0.0/8"),         # This host on this network
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved for future use
]


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


def is_ip_allowed(ip_str: str) -> Tuple[bool, str]:
    """
    Check if an IP address string is safe for outbound requests.

    Returns:
        (True, "") if allowed.
        (False, reason_message) if forbidden.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False, f"Invalid IP address format: {ip_str}"

    if ip in CLOUD_METADATA_IPS:
        return False, f"Access to cloud metadata service ({ip}) is strictly forbidden."

    if ip.is_loopback:
        return False, f"Access to loopback address ({ip}) is forbidden."

    if ip.is_private:
        return False, f"Access to private RFC1918 address ({ip}) is forbidden."

    if ip.is_link_local:
        return False, f"Access to link-local address ({ip}) is forbidden."

    if ip.is_multicast:
        return False, f"Access to multicast address ({ip}) is forbidden."

    if ip.is_reserved:
        return False, f"Access to reserved address ({ip}) is forbidden."

    if ip.is_unspecified:
        return False, f"Access to unspecified address ({ip}) is forbidden."

    for blocked_net in SPECIAL_BLOCKED_NETWORKS:
        if ip in blocked_net:
            return False, f"Access to restricted network ({blocked_net}) is forbidden."

    return True, ""


def resolve_hostname_ips(hostname: str) -> List[str]:
    """
    Resolve a hostname to all associated IPv4 and IPv6 addresses.
    """
    try:
        # socket.getaddrinfo returns a list of 5-tuples: (family, type, proto, canonname, sockaddr)
        addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        resolved_ips = list({info[4][0] for info in addr_info if info[4]})
        if not resolved_ips:
            raise UrlValidationError(f"Could not resolve hostname '{hostname}' to any IP address.")
        return resolved_ips
    except socket.gaierror as e:
        raise UrlValidationError(f"DNS resolution failed for hostname '{hostname}': {e}") from e
    except Exception as e:
        raise UrlValidationError(f"Unexpected error resolving hostname '{hostname}': {e}") from e


def validate_destination_safety(hostname: str) -> List[str]:
    """
    Resolve a hostname or direct IP and verify all resolved addresses are safe.

    Raises:
        UrlValidationError: If any resolved IP is loopback, private, link-local,
                            cloud metadata, or restricted.
    """
    # Check if the hostname itself is an IP literal
    try:
        ip = ipaddress.ip_address(hostname)
        allowed, reason = is_ip_allowed(str(ip))
        if not allowed:
            raise UrlValidationError(f"SSRF Protection: {reason}")
        return [str(ip)]
    except ValueError:
        pass  # It is a domain/hostname, proceed to DNS resolution

    resolved_ips = resolve_hostname_ips(hostname)
    for resolved_ip in resolved_ips:
        allowed, reason = is_ip_allowed(resolved_ip)
        if not allowed:
            raise UrlValidationError(
                f"SSRF Protection: Hostname '{hostname}' resolves to restricted IP {resolved_ip}. {reason}"
            )

    return resolved_ips


def validate_url(url: str, verify_dns: bool = True) -> str:
    """
    Comprehensive URL validation entrypoint.

    Args:
        url: The candidate URL string.
        verify_dns: Whether to perform DNS resolution and SSRF IP safety checks.

    Returns:
        The validated, stripped URL string.

    Raises:
        UrlValidationError: If the URL fails syntactic, credential, or SSRF destination checks.
    """
    cleaned_url = validate_url_syntax(url)
    parsed = urlsplit(cleaned_url)

    if verify_dns and parsed.hostname:
        validate_destination_safety(parsed.hostname)

    return cleaned_url

