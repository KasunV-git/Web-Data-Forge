"""
Comprehensive Benchmark Corpus Test Suite for Web Data Forge.
Validates extraction latency, data contract enforcement, multi-dimensional quality scoring,
and formula injection sanitization across 4 realistic web page archetypes.
"""

from pathlib import Path
import time
import pytest

from web_data_forge.export import export_csv, export_json
from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
    PipelineResult,
)
from web_data_forge.orchestrator.pipeline import ExtractionPipeline
from web_data_forge.quality import QualityAssessment, evaluate_quality


BENCHMARK_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "benchmark"


def load_fixture(filename: str) -> str:
    path = BENCHMARK_DIR / filename
    assert path.exists(), f"Benchmark fixture {filename} not found at {path}"
    return path.read_text(encoding="utf-8")


class TestBenchmarkCorpus:
    """Benchmark evaluation across diverse web page archetypes."""

    def test_ecommerce_catalog_archetype(self):
        """Archetype 1: E-Commerce Product Catalog."""
        html = load_fixture("ecommerce_catalog.html")

        plan = ExtractionPlan(
            target_url="https://example.com/store/tech-hardware",
            container_selector="article.product-item",
            fields=[
                FieldContract(name="sku", selector=".", extract="attr", attr_name="data-sku", required=True),
                FieldContract(name="title", selector="h3.item-name", required=True),
                FieldContract(name="price", selector="span.price-val", required=True),
                FieldContract(name="rating", selector="span.stars", data_type=DataType.FLOAT, required=False),
                FieldContract(name="reviews", selector="span.review-total", regex=r"\((\d[\d,]*)\s+reviews\)", data_type=DataType.INTEGER, required=False),
                FieldContract(name="stock", selector="span.stock-status", required=True),
                FieldContract(name="product_url", selector="a.product-link", extract="attr", attr_name="href", data_type=DataType.URL, required=False),
            ],
        )

        pipeline = ExtractionPipeline()
        start = time.perf_counter()
        result = pipeline.run_offline(plan, html)
        elapsed = time.perf_counter() - start

        # Performance & throughput assertions
        assert elapsed < 0.25, f"Extraction took {elapsed:.4f}s, expected < 250ms"
        assert len(result.records) == 6
        assert result.telemetry.success is True

        # Quality assertions
        quality: QualityAssessment = result.quality_assessment
        assert quality.valid_records == 6
        assert quality.completeness_score == 100.0
        assert quality.uniqueness_score == 100.0
        assert quality.quality_score == 100.0
        assert quality.quality_grade == "A"

        # Field validation
        first = result.records[0]
        assert first["sku"] == "SKU-001"
        assert first["title"] == "Pro Mechanical Keyboard RGB"
        assert first["rating"] == 4.8
        assert first["reviews"] == 850
        assert first["stock"] == "In Stock"

    def test_news_publication_archetype(self):
        """Archetype 2: Editorial & News Publication."""
        html = load_fixture("news_publication.html")

        plan = ExtractionPlan(
            target_url="https://techchronicle.example.com/feed",
            container_selector="article.news-entry",
            fields=[
                FieldContract(name="headline", selector="h2.headline a", required=True),
                FieldContract(name="link", selector="h2.headline a", extract="attr", attr_name="href", data_type=DataType.URL, required=True),
                FieldContract(name="author", selector="span.author-name", required=True),
                FieldContract(name="date", selector="time.pub-date", required=True),
                FieldContract(name="summary", selector="p.summary", required=False),
            ],
        )

        pipeline = ExtractionPipeline()
        result = pipeline.run_offline(plan, html)

        assert len(result.records) == 3
        quality: QualityAssessment = result.quality_assessment
        assert quality.quality_grade == "A"
        assert result.records[0]["author"] == "Dr. Elena Rostova"
        assert result.records[1]["headline"] == "Hardening Cloud Infrastructure Against SSRF Attack Vectors"
        assert result.records[2]["date"] == "October 22, 2026"

    def test_financial_table_archetype(self):
        """Archetype 3: Tabular Financial Performance Data."""
        html = load_fixture("financial_table.html")

        plan = ExtractionPlan(
            target_url="https://example.com/investors/q4-report",
            container_selector="table#earnings-matrix tbody tr.row-data",
            fields=[
                FieldContract(name="quarter", selector="td.col-q", required=True),
                FieldContract(name="revenue", selector="td.col-rev", data_type=DataType.FLOAT, required=True),
                FieldContract(name="operating_margin", selector="td.col-margin", data_type=DataType.FLOAT, required=True),
                FieldContract(name="eps", selector="td.col-eps", data_type=DataType.FLOAT, required=True),
                FieldContract(name="status", selector="td.col-status", required=True),
            ],
        )

        pipeline = ExtractionPipeline()
        result = pipeline.run_offline(plan, html)

        assert len(result.records) == 4
        # Numeric conversions validated
        assert result.records[0]["quarter"] == "Q1 2026"
        assert result.records[0]["revenue"] == 425.50
        assert result.records[0]["operating_margin"] == 24.2
        assert result.records[0]["eps"] == 1.85
        assert result.records[3]["revenue"] == 550.00
        assert result.quality_assessment.quality_grade == "A"

    def test_adversarial_and_formula_injection_archetype(self):
        """Archetype 4: Adversarial Input, Edge Cases & OWASP Formula Injection Neutralization."""
        html = load_fixture("adversarial_edge_cases.html")

        plan = ExtractionPlan(
            target_url="https://example.com/untrusted/feed",
            container_selector="article.edge-item",
            fields=[
                FieldContract(name="name", selector="span.name", required=True),
                FieldContract(name="value", selector="span.value", required=False),
                FieldContract(name="comment", selector="span.comment", required=False),
            ],
        )

        pipeline = ExtractionPipeline()
        result = pipeline.run_offline(plan, html)

        assert len(result.records) == 4

        # Verify missing field recorded explicitly in Item 3
        assert result.records[2]["value"] is None
        assert "value" in result.record_audits[2].missing_fields

        # Quality score reflects missing field
        assert result.quality_assessment.completeness_score < 100.0

        # CRITICAL SECURITY CHECK: Export CSV and verify OWASP formula sanitization
        csv_text = export_csv(result.records, sanitize_formulas=True)

        # Danger formula triggers (=, @) must be escaped with leading single quote
        assert "'=1+1; cmd.exe /c calc" in csv_text
        assert "'@SUM(A1:A100)" in csv_text
        assert "'@HYPERLINK(" in csv_text
        # Benign numeric values are preserved cleanly
        assert "+12345" in csv_text
        assert "-99.95" in csv_text
        # Normal strings must NOT be escaped
        assert "Safe normal comment" in csv_text
