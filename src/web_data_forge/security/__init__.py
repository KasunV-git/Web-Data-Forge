"""
Security controls module for Web Data Forge.
"""

from web_data_forge.security.network_guard import SafeFetcher, fetch_html

__all__ = ["SafeFetcher", "fetch_html"]
