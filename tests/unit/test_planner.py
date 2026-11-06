"""
Unit tests for AI Planner and Gemini API adapter.
"""

from pathlib import Path
from unittest.mock import MagicMock
import pytest

from web_data_forge.core.exceptions import (
    MissingApiKeyError,
    PlannerApiError,
    PlannerSchemaError,
)
from web_data_forge.models.contracts import DataType, ExtractionPlan
from web_data_forge.planner.fallback import generate_heuristic_plan
from web_data_forge.planner.gemini_client import GeminiPlannerClient
from web_data_forge.planner.planner import AiPlanner


SAMPLE_HTML = """
<html>
    <body>
        <div class="product-grid">
            <article class="product-card">
                <h2 class="product-title">Headphones</h2>
                <span class="product-price">$99.00</span>
                <a href="/products/headphones">View</a>
            </article>
            <article class="product-card">
                <h2 class="product-title">Keyboard</h2>
                <span class="product-price">$49.00</span>
                <a href="/products/keyboard">View</a>
            </article>
        </div>
    </body>
</html>
"""

VALID_PLAN_JSON = """
{
    "target_url": "https://example.com/store",
    "container_selector": "article.product-card",
    "fields": [
        {
            "name": "title",
            "selector": "h2.product-title",
            "extract": "text",
            "data_type": "string",
            "required": true
        },
        {
            "name": "price",
            "selector": "span.product-price",
            "extract": "text",
            "data_type": "string",
            "required": false
        },
        {
            "name": "product_url",
            "selector": "a",
            "extract": "attr",
            "attr_name": "href",
            "data_type": "url",
            "required": false
        }
    ]
}
"""


class TestGeminiPlannerClient:
    """Test suite for GeminiPlannerClient."""

    def test_missing_api_key_raises_error(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        client = GeminiPlannerClient(api_key=None)
        with pytest.raises(MissingApiKeyError, match="Gemini API key is required"):
            client.generate_plan(
                user_instruction="Extract title and price",
                pruned_html=SAMPLE_HTML,
                target_url="https://example.com/store",
            )

    def test_generate_plan_success_with_mock_client(self):
        mock_response = MagicMock()
        mock_response.text = VALID_PLAN_JSON

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.return_value = mock_response

        client = GeminiPlannerClient(api_key="fake-test-key")
        client._client = mock_genai_client

        plan = client.generate_plan(
            user_instruction="Extract title, price, and link",
            pruned_html=SAMPLE_HTML,
            target_url="https://example.com/store",
        )

        assert isinstance(plan, ExtractionPlan)
        assert plan.target_url == "https://example.com/store"
        assert plan.container_selector == "article.product-card"
        assert len(plan.fields) == 3
        assert plan.fields[0].name == "title"
        assert plan.fields[0].data_type == DataType.STRING
        assert plan.fields[2].attr_name == "href"

    def test_invalid_json_raises_schema_error(self):
        mock_response = MagicMock()
        mock_response.text = "This is not valid JSON content"

        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.return_value = mock_response

        client = GeminiPlannerClient(api_key="fake-test-key")
        client._client = mock_genai_client

        with pytest.raises(PlannerSchemaError, match="failed validation"):
            client.generate_plan(
                user_instruction="Extract products",
                pruned_html=SAMPLE_HTML,
                target_url="https://example.com/store",
            )

    def test_api_failure_raises_planner_api_error(self):
        mock_genai_client = MagicMock()
        mock_genai_client.models.generate_content.side_effect = Exception("API Quota exceeded")

        client = GeminiPlannerClient(api_key="fake-test-key")
        client._client = mock_genai_client

        with pytest.raises(PlannerApiError, match="Failed to communicate with Gemini API"):
            client.generate_plan(
                user_instruction="Extract products",
                pruned_html=SAMPLE_HTML,
                target_url="https://example.com/store",
            )


class TestAiPlanner:
    """Test suite for high-level AiPlanner orchestrator."""

    def test_plan_with_fallback_when_api_key_missing(self, monkeypatch):
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GOOGLE_API_KEY", raising=False)

        planner = AiPlanner(api_key=None)
        # Without fallback, raises error
        with pytest.raises(MissingApiKeyError):
            planner.plan_from_html(
                user_instruction="Extract title and price",
                html=SAMPLE_HTML,
                target_url="https://example.com/store",
                allow_fallback=False,
            )

        # With fallback, returns heuristic plan
        fallback_plan = planner.plan_from_html(
            user_instruction="Extract title and price",
            html=SAMPLE_HTML,
            target_url="https://example.com/store",
            allow_fallback=True,
        )
        assert isinstance(fallback_plan, ExtractionPlan)
        assert fallback_plan.container_selector == "article.product-card"
        assert len(fallback_plan.fields) >= 2


class TestHeuristicPlanGenerator:
    """Test suite for heuristic fallback plan generator."""

    def test_heuristic_detects_product_fixture(self):
        fixture_path = Path("tests/fixtures/sample_product_page.html")
        html_content = fixture_path.read_text(encoding="utf-8")

        plan = generate_heuristic_plan(html_content, target_url="https://example.com/products")
        assert plan.container_selector == "article.product-card"
        field_names = [f.name for f in plan.fields]
        assert "title" in field_names
        assert "price" in field_names
        assert "link" in field_names

    def test_heuristic_detects_table(self):
        table_html = """
        <html>
            <body>
                <table>
                    <tbody>
                        <tr><td>Row 1 Col 1</td><td>Row 1 Col 2</td></tr>
                        <tr><td>Row 2 Col 1</td><td>Row 2 Col 2</td></tr>
                    </tbody>
                </table>
            </body>
        </html>
        """
        plan = generate_heuristic_plan(table_html, target_url="https://example.com/table")
        assert plan.container_selector == "table tbody tr"
        assert len(plan.fields) == 2

