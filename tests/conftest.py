"""
Pytest configuration and shared fixtures for Web Data Forge.
"""

from pathlib import Path
import pytest


@pytest.fixture
def sample_test_target():
    """Provides a sample URL for basic testing."""
    return "https://example.com"


@pytest.fixture
def sample_product_html():
    """Load the offline sample product page HTML fixture."""
    fixture_path = Path(__file__).parent / "fixtures" / "sample_product_page.html"
    return fixture_path.read_text(encoding="utf-8")

