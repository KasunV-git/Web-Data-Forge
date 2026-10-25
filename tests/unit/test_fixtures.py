"""
Verification tests for offline test fixtures.
"""

from bs4 import BeautifulSoup


def test_sample_product_html_fixture_loads(sample_product_html):
    """Verify HTML fixture loads and contains expected sample elements."""
    assert len(sample_product_html) > 0
    assert "<title>TechForge Store" in sample_product_html

    soup = BeautifulSoup(sample_product_html, "html.parser")
    cards = soup.select(".product-card")
    assert len(cards) == 4

    titles = [card.select_one(".product-title").get_text(strip=True) for card in cards]
    assert "Wireless Noise-Canceling Headphones" in titles
    assert "Mechanical RGB Gaming Keyboard" in titles
    assert "Ultra-Wide 34-Inch Curved Monitor" in titles
    assert "Ergonomic Mesh Office Chair" in titles
