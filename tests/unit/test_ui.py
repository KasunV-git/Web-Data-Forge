"""
Smoke and helper tests for Streamlit UI modules.
"""

from web_data_forge.ui.app import load_fixture_html


def test_ui_fixture_loader():
    """Verify UI helper properly locates and reads the product page fixture."""
    html = load_fixture_html()
    assert len(html) > 0
    assert "TechForge Store" in html
    assert ".product-card" in html or "product-card" in html
