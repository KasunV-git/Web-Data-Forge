"""
Core module for Web Data Forge.
"""

from web_data_forge.core.exceptions import (
    ExtractionError,
    InvalidSelectorError,
    NetworkError,
    ResponseTooLargeError,
    SecurityError,
    UrlValidationError,
    WebDataForgeError,
)

__all__ = [
    "WebDataForgeError",
    "SecurityError",
    "UrlValidationError",
    "ResponseTooLargeError",
    "NetworkError",
    "ExtractionError",
    "InvalidSelectorError",
]

