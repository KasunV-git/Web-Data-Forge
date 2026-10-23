"""
Pytest configuration and shared fixtures for Web Data Forge.
"""

import pytest


@pytest.fixture
def sample_test_target():
    """Provides a sample URL for basic testing."""
    return "https://example.com"
