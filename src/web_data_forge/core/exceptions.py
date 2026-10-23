"""
Domain exceptions and error hierarchy for Web Data Forge.
"""

from typing import Optional


class WebDataForgeError(Exception):
    """Base exception for all Web Data Forge application errors."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class SecurityError(WebDataForgeError):
    """Raised when an operation violates security policies."""


class UrlValidationError(SecurityError):
    """Raised when a supplied URL is invalid, malformed, or targets a forbidden network destination."""
