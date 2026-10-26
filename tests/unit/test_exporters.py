"""
Unit tests for safe dataset exporters and OWASP formula injection defenses.
"""

import csv
import json
from web_data_forge.export import (
    export_csv,
    export_csv_to_file,
    export_json,
    export_json_to_file,
    export_result_csv,
    export_result_json,
    sanitize_csv_value,
)
from web_data_forge.models.contracts import (
    ExtractionPlan,
    FieldContract,
    PipelineResult,
    PipelineTelemetry,
    QualityReport,
    RecordAudit,
)


def test_sanitize_csv_value_dangerous_formulae():
    """Verify formula injection triggers are escaped with a leading single quote."""
    assert sanitize_csv_value("=1+1") == "'=1+1"
    assert sanitize_csv_value("=cmd|' /C calc'!A0") == "'=cmd|' /C calc'!A0"
    assert sanitize_csv_value("@SUM(A1:A10)") == "'@SUM(A1:A10)"
    assert sanitize_csv_value("+cmd|' /C'!") == "'+cmd|' /C'!"
    assert sanitize_csv_value("-2+3*4") == "'-2+3*4"
    assert sanitize_csv_value("\ttab_attack") == "'\ttab_attack"
    assert sanitize_csv_value("\rreturn_attack") == "'\rreturn_attack"


def test_sanitize_csv_value_benign_values():
    """Verify ordinary text, booleans, and pure numbers are not unnecessarily escaped."""
    assert sanitize_csv_value("Wireless Headphones") == "Wireless Headphones"
    assert sanitize_csv_value(199.99) == 199.99
    assert sanitize_csv_value(-42) == -42
    assert sanitize_csv_value("-42") == "-42"
    assert sanitize_csv_value("-3.14") == "-3.14"
    assert sanitize_csv_value("+100") == "+100"
    assert sanitize_csv_value(True) is True
    assert sanitize_csv_value(None) == ""


def test_export_csv_formula_sanitization():
    """Verify CSV export serializes rows and neutralizes dangerous content."""
    records = [
        {"title": "Headphones", "price": 199.99, "notes": "=HYPERLINK(\"http://evil.com\")"},
        {"title": "Monitor", "price": 499.00, "notes": "@IMPORT(\"leak\")"},
        {"title": "Keyboard", "price": 89.50, "notes": "Normal note"},
    ]

    csv_output = export_csv(records)
    reader = list(csv.reader(csv_output.splitlines()))

    assert reader[0] == ["title", "price", "notes"]
    assert reader[1] == ["Headphones", "199.99", "'=HYPERLINK(\"http://evil.com\")"]
    assert reader[2] == ["Monitor", "499.0", "'@IMPORT(\"leak\")"]
    assert reader[3] == ["Keyboard", "89.5", "Normal note"]


def test_export_csv_empty_records():
    """Verify CSV handles empty records gracefully."""
    assert export_csv([]) == ""
    assert export_csv([], fieldnames=["a", "b"]) == "a,b\n"


def test_export_json():
    """Verify JSON export generates valid JSON matching data structure."""
    records = [
        {"id": "prod-101", "name": "Headphones", "in_stock": True},
        {"id": "prod-102", "name": "Keyboard", "in_stock": False},
    ]

    json_str = export_json(records)
    parsed = json.loads(json_str)

    assert len(parsed) == 2
    assert parsed[0]["name"] == "Headphones"
    assert parsed[1]["in_stock"] is False


def test_file_export(tmp_path):
    """Verify writing CSV and JSON directly to file paths."""
    records = [{"item": "Chair", "price": 120.0}]

    csv_file = tmp_path / "exports" / "test.csv"
    json_file = tmp_path / "exports" / "test.json"

    export_csv_to_file(records, csv_file)
    export_json_to_file(records, json_file)

    assert csv_file.exists()
    assert "Chair,120.0" in csv_file.read_text(encoding="utf-8")

    assert json_file.exists()
    parsed = json.loads(json_file.read_text(encoding="utf-8"))
    assert parsed[0]["item"] == "Chair"


def test_export_pipeline_result():
    """Verify helper functions correctly export a PipelineResult."""
    plan = ExtractionPlan(
        target_url="https://example.com",
        fields=[FieldContract(name="title", selector="h1")],
    )
    telemetry = PipelineTelemetry(
        target_url=plan.target_url,
        resolved_ip="93.184.216.34",
        status_code=200,
        bytes_downloaded=5000,
        latency_seconds=0.2,
    )
    records = [{"title": "Sample Title"}]
    audits = [
        RecordAudit(
            raw_data={"title": "Sample Title"},
            coerced_data={"title": "Sample Title"},
            missing_fields=[],
            is_valid=True,
        )
    ]
    report = QualityReport.calculate(audits, plan.fields)

    result = PipelineResult(
        plan=plan,
        telemetry=telemetry,
        records=records,
        record_audits=audits,
        quality_report=report,
    )

    # Test CSV helper
    csv_str = export_result_csv(result)
    assert "title" in csv_str
    assert "Sample Title" in csv_str

    # Test JSON helper with metadata
    json_str = export_result_json(result, include_metadata=True)
    parsed = json.loads(json_str)
    assert "telemetry" in parsed
    assert "quality_report" in parsed
    assert parsed["records"][0]["title"] == "Sample Title"
