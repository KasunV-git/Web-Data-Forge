"""
Unit tests for Pydantic data contracts, schemas, and quality calculations.
"""

import pytest
from pydantic import ValidationError

from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
    PipelineResult,
    PipelineTelemetry,
    QualityReport,
    RecordAudit,
)


def test_field_contract_valid():
    """Verify standard valid FieldContract creation."""
    field = FieldContract(
        name="product_title",
        selector="h2.title",
        data_type=DataType.STRING,
        required=True,
    )
    assert field.name == "product_title"
    assert field.data_type == DataType.STRING
    assert field.required is True

    # Conversion to extraction FieldRule
    rule = field.to_field_rule()
    assert rule.name == "product_title"
    assert rule.selector == "h2.title"
    assert rule.required is True


def test_field_contract_invalid_name():
    """Verify field name must be a valid alphanumeric/underscore identifier."""
    with pytest.raises(ValidationError, match="must be a valid identifier"):
        FieldContract(name="123invalid", selector="h1")

    with pytest.raises(ValidationError, match="must be a valid identifier"):
        FieldContract(name="product title with spaces", selector="h1")


def test_field_contract_attr_requires_attr_name():
    """Verify extract='attr' requires attr_name."""
    with pytest.raises(ValidationError, match="attr_name must be provided"):
        FieldContract(name="link", selector="a", extract="attr", attr_name=None)


def test_field_contract_invalid_regex():
    """Verify invalid regex syntax is caught at initialization."""
    with pytest.raises(ValidationError, match="Invalid regex pattern"):
        FieldContract(name="code", selector="span", regex=r"([a-z++")


def test_field_contract_coercion_string():
    """Verify string type coercion."""
    field = FieldContract(name="title", selector="h1", data_type=DataType.STRING)
    assert field.coerce_value("Hello World") == "Hello World"
    assert field.coerce_value(12345) == "12345"
    assert field.coerce_value(None) is None


def test_field_contract_coercion_integer():
    """Verify integer parsing and currency/comma stripping."""
    field = FieldContract(name="reviews", selector="span", data_type=DataType.INTEGER)
    assert field.coerce_value("1,240") == 1240
    assert field.coerce_value("$150") == 150
    assert field.coerce_value(42) == 42
    assert field.coerce_value(None) is None

    # Required field missing raises ValueError
    req_field = FieldContract(name="count", selector="span", data_type=DataType.INTEGER, required=True)
    with pytest.raises(ValueError, match="Required field 'count' is missing"):
        req_field.coerce_value(None)


def test_field_contract_coercion_float():
    """Verify float parsing with currency signs."""
    field = FieldContract(name="price", selector="span", data_type=DataType.FLOAT)
    assert field.coerce_value("$199.99") == 199.99
    assert field.coerce_value("  89.50  ") == 89.50
    assert field.coerce_value(None) is None


def test_field_contract_coercion_boolean():
    """Verify boolean truthy and falsy string recognition."""
    field = FieldContract(name="in_stock", selector="span", data_type=DataType.BOOLEAN)
    assert field.coerce_value("In Stock") is True
    assert field.coerce_value("available") is True
    assert field.coerce_value("1") is True
    assert field.coerce_value("true") is True
    assert field.coerce_value("Currently Out of Stock") is False
    assert field.coerce_value("0") is False
    assert field.coerce_value("no") is False


def test_extraction_plan_valid():
    """Verify valid ExtractionPlan creation with multiple fields."""
    plan = ExtractionPlan(
        target_url="https://example.com/products",
        container_selector=".product-card",
        fields=[
            FieldContract(name="title", selector="h2"),
            FieldContract(name="price", selector=".price", data_type=DataType.FLOAT),
        ],
    )
    assert plan.target_url == "https://example.com/products"
    assert plan.container_selector == ".product-card"
    assert len(plan.fields) == 2
    assert plan.timeout == 10.0


def test_extraction_plan_invalid_scheme():
    """Verify non-HTTP schemes are rejected."""
    with pytest.raises(ValidationError, match="Invalid target URL scheme"):
        ExtractionPlan(
            target_url="ftp://ftp.example.com",
            fields=[FieldContract(name="title", selector="h1")],
        )


def test_extraction_plan_duplicate_field_names():
    """Verify duplicate field names are rejected."""
    with pytest.raises(ValidationError, match="Duplicate field name 'title'"):
        ExtractionPlan(
            target_url="https://example.com",
            fields=[
                FieldContract(name="title", selector="h1"),
                FieldContract(name="title", selector="h2"),
            ],
        )


def test_extraction_plan_bounds():
    """Verify runtime limits have enforced ranges."""
    with pytest.raises(ValidationError):
        ExtractionPlan(
            target_url="https://example.com",
            fields=[FieldContract(name="title", selector="h1")],
            timeout=0.5,  # min is 1.0
        )


def test_quality_report_calculation():
    """Verify QualityReport properly aggregates record audits."""
    fields = [
        FieldContract(name="title", selector="h2", required=True),
        FieldContract(name="price", selector=".price"),
        FieldContract(name="rating", selector=".rating"),
    ]

    audits = [
        RecordAudit(
            raw_data={"title": "Item 1", "price": "$10", "rating": "4.5"},
            coerced_data={"title": "Item 1", "price": 10.0, "rating": 4.5},
            missing_fields=[],
            is_valid=True,
        ),
        RecordAudit(
            raw_data={"title": "Item 2", "price": None, "rating": "4.0"},
            coerced_data={"title": "Item 2", "price": None, "rating": 4.0},
            missing_fields=["price"],
            is_valid=True,
        ),
        RecordAudit(
            raw_data={"title": "Item 3", "price": "$30", "rating": None},
            coerced_data={"title": "Item 3", "price": 30.0, "rating": None},
            missing_fields=["rating"],
            is_valid=True,
        ),
        RecordAudit(
            raw_data={"title": None, "price": "$40", "rating": "3.8"},
            coerced_data={"title": None, "price": 40.0, "rating": 3.8},
            missing_fields=["title"],
            is_valid=False,
            validation_errors={"title": "Required field missing"},
        ),
    ]

    report = QualityReport.calculate(audits, fields)

    assert report.total_records == 4
    assert report.valid_records == 3
    assert report.total_fields_expected == 12  # 4 records * 3 fields
    assert report.total_fields_collected == 9   # 12 - 3 missing
    assert report.completeness_score == 75.0
    assert report.missing_fields_summary == {
        "title": 1,
        "price": 1,
        "rating": 1,
    }


def test_quality_report_zero_records():
    """Verify QualityReport handles empty runs without ZeroDivisionError."""
    fields = [FieldContract(name="title", selector="h1")]
    report = QualityReport.calculate([], fields)
    assert report.total_records == 0
    assert report.completeness_score == 0.0


def test_pipeline_result_structure():
    """Verify full PipelineResult data structure."""
    plan = ExtractionPlan(
        target_url="https://example.com/items",
        fields=[FieldContract(name="title", selector="h1")],
    )
    telemetry = PipelineTelemetry(
        target_url=plan.target_url,
        resolved_ip="93.184.216.34",
        status_code=200,
        bytes_downloaded=12400,
        latency_seconds=0.45,
        success=True,
    )
    audit = RecordAudit(
        raw_data={"title": "Sample"},
        coerced_data={"title": "Sample"},
        missing_fields=[],
        is_valid=True,
    )
    report = QualityReport.calculate([audit], plan.fields)

    result = PipelineResult(
        plan=plan,
        telemetry=telemetry,
        records=[{"title": "Sample"}],
        record_audits=[audit],
        quality_report=report,
    )

    assert result.telemetry.status_code == 200
    assert result.quality_report.completeness_score == 100.0
    assert len(result.records) == 1
