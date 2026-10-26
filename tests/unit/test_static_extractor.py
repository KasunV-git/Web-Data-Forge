"""
Unit tests for the StaticHtmlExtractor and FieldRule engine.
"""

import pytest

from web_data_forge.core.exceptions import (
    ExtractionError,
    InvalidSelectorError,
)
from web_data_forge.extraction import FieldRule, StaticHtmlExtractor


def test_field_rule_validation():
    """Verify FieldRule initialization and parameter checks."""
    rule = FieldRule(name="title", selector="h1")
    assert rule.name == "title"
    assert rule.extract == "text"
    assert rule.required is False

    with pytest.raises(ValueError, match="Invalid extract mode"):
        FieldRule(name="title", selector="h1", extract="unsupported_mode")

    with pytest.raises(ValueError, match="attr_name must be provided"):
        FieldRule(name="link", selector="a", extract="attr", attr_name=None)


def test_extract_page_level_item(sample_product_html):
    """Verify extracting page-level metadata from the fixture."""
    extractor = StaticHtmlExtractor()
    rules = [
        FieldRule(name="page_title", selector="title"),
        FieldRule(name="heading", selector="header h1"),
        FieldRule(name="subtitle", selector="header .subtitle"),
    ]

    result = extractor.extract_item(sample_product_html, rules)

    assert result["page_title"] == "TechForge Store - Audio & Peripherals"
    assert result["heading"] == "Featured Tech Products"
    assert "Curated catalog for testing" in result["subtitle"]


def test_extract_collection_from_fixture(sample_product_html):
    """
    Verify extracting product cards from the HTML fixture, including
    edge cases (missing price, missing rating, attribute extraction, regex).
    """
    extractor = StaticHtmlExtractor()
    rules = [
        FieldRule(
            name="product_id",
            selector=".",
            extract="attr",
            attr_name="data-product-id",
        ),
        FieldRule(name="title", selector="h2.product-title"),
        FieldRule(
            name="price",
            selector=".product-price",
            regex=r"\$([\d.]+)",
        ),
        FieldRule(name="rating", selector=".product-rating"),
        FieldRule(
            name="review_count",
            selector=".review-count",
            regex=r"\((\d[\d,]*)\s+reviews\)",
        ),
        FieldRule(
            name="link",
            selector="a.product-link",
            extract="attr",
            attr_name="href",
        ),
        FieldRule(
            name="out_of_stock",
            selector=".stock-badge.out-of-stock",
            default=None,
        ),
    ]

    products = extractor.extract_collection(
        sample_product_html, ".product-card", rules
    )

    assert len(products) == 4

    # Product 1: Complete fields
    p1 = products[0]
    assert p1["product_id"] == "prod-101"
    assert p1["title"] == "Wireless Noise-Canceling Headphones"
    assert p1["price"] == "199.99"
    assert p1["rating"] == "4.7"
    assert p1["review_count"] == "1,240"
    assert p1["link"] == "/products/wireless-headphones"
    assert p1["out_of_stock"] is None

    # Product 2: Complete fields
    p2 = products[1]
    assert p2["product_id"] == "prod-102"
    assert p2["title"] == "Mechanical RGB Gaming Keyboard"
    assert p2["price"] == "89.50"
    assert p2["rating"] == "4.3"
    assert p2["review_count"] == "412"

    # Product 3: Edge Case - Missing rating/reviews
    p3 = products[2]
    assert p3["product_id"] == "prod-103"
    assert p3["title"] == "Ultra-Wide 34-Inch Curved Monitor"
    assert p3["price"] == "499.00"
    assert p3["rating"] is None
    assert p3["review_count"] is None
    assert p3["link"] == "https://example.com/products/ultrawide-monitor"

    # Product 4: Edge Case - Out of stock, missing price
    p4 = products[3]
    assert p4["product_id"] == "prod-104"
    assert p4["title"] == "Ergonomic Mesh Office Chair"
    assert p4["price"] is None
    assert p4["rating"] == "3.9"
    assert p4["review_count"] == "88"
    assert p4["out_of_stock"] == "Currently Out of Stock"


def test_required_field_missing_raises_extraction_error():
    """Verify that a missing required field raises ExtractionError."""
    html = "<div class='item'><span>Only some text</span></div>"
    extractor = StaticHtmlExtractor()

    rules = [
        FieldRule(name="mandatory_tag", selector=".missing-tag", required=True)
    ]

    with pytest.raises(ExtractionError, match="Required field 'mandatory_tag' not found"):
        extractor.extract_item(html, rules)


def test_optional_field_missing_uses_default():
    """Verify that a missing optional field returns the configured default."""
    html = "<div class='item'><span>Content</span></div>"
    extractor = StaticHtmlExtractor()

    rules = [
        FieldRule(
            name="optional_field",
            selector=".does-not-exist",
            default="DEFAULT_VALUE",
        )
    ]

    result = extractor.extract_item(html, rules)
    assert result["optional_field"] == "DEFAULT_VALUE"


def test_invalid_css_selector_raises_invalid_selector_error():
    """Verify that syntactically invalid CSS selectors raise InvalidSelectorError."""
    html = "<div><span>Text</span></div>"
    extractor = StaticHtmlExtractor()

    rules = [FieldRule(name="bad_field", selector="div:::invalid")]

    with pytest.raises(InvalidSelectorError, match="Invalid CSS selector"):
        extractor.extract_item(html, rules)


def test_invalid_container_selector_raises_invalid_selector_error():
    """Verify invalid container selector raises InvalidSelectorError."""
    html = "<div><span>Text</span></div>"
    extractor = StaticHtmlExtractor()
    rules = [FieldRule(name="name", selector="span")]

    with pytest.raises(InvalidSelectorError, match="Invalid container selector"):
        extractor.extract_collection(html, "div:::invalid", rules)


def test_html_mode_extraction():
    """Verify raw HTML extraction when extract='html'."""
    html = "<div class='badge'><strong>Special</strong> Offer</div>"
    extractor = StaticHtmlExtractor()
    rules = [FieldRule(name="badge_markup", selector=".badge", extract="html")]

    result = extractor.extract_item(html, rules)
    assert "<strong>Special</strong> Offer" in result["badge_markup"]


def test_whitespace_normalization():
    """Verify multiline and erratic whitespace is collapsed cleanly."""
    html = """
    <div class="desc">
        Line 1
            Line 2 \t\t with
        tabs and    spaces.
    </div>
    """
    extractor = StaticHtmlExtractor()
    rules = [FieldRule(name="desc", selector=".desc")]

    result = extractor.extract_item(html, rules)
    assert result["desc"] == "Line 1 Line 2 with tabs and spaces."


def test_invalid_input_type_raises_extraction_error():
    """Verify non-string/non-soup inputs raise ExtractionError."""
    extractor = StaticHtmlExtractor()
    with pytest.raises(ExtractionError, match="Expected HTML string"):
        extractor.extract_item(12345, [FieldRule(name="t", selector="h1")])
