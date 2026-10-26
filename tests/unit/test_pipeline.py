"""
Unit and integration tests for the ExtractionPipeline orchestrator.
"""

from unittest.mock import patch
import pytest

from web_data_forge.core.exceptions import UrlValidationError
from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
)
from web_data_forge.orchestrator.pipeline import ExtractionPipeline


def test_pipeline_run_offline_collection(sample_product_html):
    """
    Verify full offline execution on sample product fixture:
    collection extraction, type coercion, auditing, and quality report.
    """
    plan = ExtractionPlan(
        target_url="https://example.com/store/products",
        container_selector=".product-card",
        fields=[
            FieldContract(
                name="product_id",
                selector=".",
                extract="attr",
                attr_name="data-product-id",
                data_type=DataType.STRING,
                required=True,
            ),
            FieldContract(
                name="title",
                selector="h2.product-title",
                data_type=DataType.STRING,
                required=True,
            ),
            FieldContract(
                name="price",
                selector=".product-price",
                regex=r"\$([\d.]+)",
                data_type=DataType.FLOAT,
            ),
            FieldContract(
                name="rating",
                selector=".product-rating",
                data_type=DataType.FLOAT,
            ),
            FieldContract(
                name="review_count",
                selector=".review-count",
                regex=r"\((\d[\d,]*)\s+reviews\)",
                data_type=DataType.INTEGER,
            ),
            FieldContract(
                name="in_stock",
                selector=".stock-badge.out-of-stock",
                data_type=DataType.BOOLEAN,
                default=True,
            ),
        ],
    )

    pipeline = ExtractionPipeline()
    result = pipeline.run_offline(plan, sample_product_html)

    # 1. Telemetry checks
    assert result.telemetry.success is True
    assert result.telemetry.status_code == 200
    assert result.telemetry.bytes_downloaded > 0

    # 2. Record checks
    records = result.records
    assert len(records) == 4

    # Prod 1: Complete item
    assert records[0]["product_id"] == "prod-101"
    assert records[0]["title"] == "Wireless Noise-Canceling Headphones"
    assert records[0]["price"] == 199.99
    assert records[0]["rating"] == 4.7
    assert records[0]["review_count"] == 1240
    assert records[0]["in_stock"] is True

    # Prod 3: Edge Case - missing rating and reviews
    assert records[2]["product_id"] == "prod-103"
    assert records[2]["price"] == 499.00
    assert records[2]["rating"] is None
    assert records[2]["review_count"] is None

    # Prod 4: Edge Case - out of stock, missing price
    assert records[3]["product_id"] == "prod-104"
    assert records[3]["price"] is None
    assert records[3]["in_stock"] is False

    # 3. Quality report checks
    quality = result.quality_report
    assert quality.total_records == 4
    assert quality.valid_records == 4
    assert quality.total_fields_expected == 24  # 4 records * 6 fields
    # Missing: 1 price (prod 4), 1 rating (prod 3), 1 review_count (prod 3) = 3 missing
    assert quality.total_fields_collected == 21
    assert quality.completeness_score == 87.5
    assert quality.missing_fields_summary["price"] == 1
    assert quality.missing_fields_summary["rating"] == 1
    assert quality.missing_fields_summary["review_count"] == 1


def test_pipeline_run_offline_single_item(sample_product_html):
    """Verify single-record extraction when container_selector is None."""
    plan = ExtractionPlan(
        target_url="https://example.com/store",
        fields=[
            FieldContract(name="heading", selector="header h1"),
            FieldContract(name="title", selector="title"),
        ],
    )

    pipeline = ExtractionPipeline()
    result = pipeline.run_offline(plan, sample_product_html)

    assert result.telemetry.success is True
    assert len(result.records) == 1
    assert result.records[0]["heading"] == "Featured Tech Products"
    assert result.quality_report.completeness_score == 100.0


def test_pipeline_required_field_missing_marks_record_invalid():
    """Verify missing required field flags the record as invalid."""
    html = "<div class='item'><span class='opt'>Only optional</span></div>"
    plan = ExtractionPlan(
        target_url="https://example.com/item",
        container_selector=".item",
        fields=[
            FieldContract(name="mandatory", selector=".missing-tag", required=True),
            FieldContract(name="optional", selector=".opt"),
        ],
    )

    pipeline = ExtractionPipeline()
    result = pipeline.run_offline(plan, html)

    assert len(result.record_audits) == 1
    audit = result.record_audits[0]
    assert audit.is_valid is False
    assert "mandatory" in audit.validation_errors
    assert result.quality_report.valid_records == 0


def test_pipeline_run_ssrf_blocked():
    """Verify pipeline intercepts SSRF targets safely without crashing."""
    plan = ExtractionPlan(
        target_url="http://127.0.0.1:8000/internal-data",
        fields=[FieldContract(name="data", selector="body")],
    )

    pipeline = ExtractionPipeline()

    # When raise_on_error is False (default)
    result = pipeline.run(plan, raise_on_error=False)
    assert result.telemetry.success is False
    assert "SSRF" in (result.telemetry.error_message or "")
    assert len(result.records) == 0

    # When raise_on_error is True
    with pytest.raises(UrlValidationError):
        pipeline.run(plan, raise_on_error=True)



def test_pipeline_mocked_network_run():
    """Verify end-to-end pipeline with mocked HTTP network call."""
    mock_html = "<div class='card'><h1>Mocked Item</h1><span class='price'>$25.50</span></div>"

    plan = ExtractionPlan(
        target_url="https://example.com/mock-page",
        container_selector=".card",
        fields=[
            FieldContract(name="title", selector="h1"),
            FieldContract(
                name="price",
                selector=".price",
                regex=r"\$([\d.]+)",
                data_type=DataType.FLOAT,
            ),
        ],
    )

    pipeline = ExtractionPipeline()

    with patch("web_data_forge.security.network_guard.SafeFetcher.fetch") as mock_fetch:
        mock_fetch.return_value = (mock_html, "https://example.com/mock-page", 200)

        result = pipeline.run(plan, verify_dns=False)

        assert result.telemetry.success is True
        assert result.telemetry.status_code == 200
        assert len(result.records) == 1
        assert result.records[0]["title"] == "Mocked Item"
        assert result.records[0]["price"] == 25.50
