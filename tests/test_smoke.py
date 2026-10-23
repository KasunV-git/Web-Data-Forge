"""
Baseline smoke tests for Web Data Forge foundation.
"""

import web_data_forge


def test_package_metadata():
    """Verify package imports correctly and exposes expected metadata."""
    assert web_data_forge.__version__ == "0.1.0"
    assert hasattr(web_data_forge, "__author__")


def test_environment_fixture(sample_test_target):
    """Verify test fixture wiring operates as expected."""
    assert sample_test_target.startswith("https://")
