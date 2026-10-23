"""
Core module for Web Data Forge.
"""

from web_data_forge.core.exceptions import (
    SecurityError,
    UrlValidationError,
    WebDataForgeError,
)

__all__ = ["WebDataForgeError", "SecurityError", "UrlValidationError"]
