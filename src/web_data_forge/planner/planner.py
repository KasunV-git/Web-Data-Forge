"""
Main AI Extraction Planner orchestrator for Web Data Forge.
Coordinates HTML pruning, Gemini API generation, validation, and heuristic fallbacks.
"""

from typing import Optional

from web_data_forge.core.exceptions import (
    MissingApiKeyError,
    PlannerApiError,
    PlannerError,
    PlannerSchemaError,
)
from web_data_forge.models.contracts import ExtractionPlan
from web_data_forge.planner.dom_pruner import prune_html_for_llm
from web_data_forge.planner.fallback import generate_heuristic_plan
from web_data_forge.planner.gemini_client import GeminiPlannerClient
from web_data_forge.security.network_guard import fetch_html


class AiPlanner:
    """
    Translates natural-language extraction instructions and target HTML into
    typed ExtractionPlans using Google Gemini, with automatic fallback handling.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        client: Optional[GeminiPlannerClient] = None,
    ) -> None:
        self.client = client or GeminiPlannerClient(api_key=api_key, model_name=model_name)

    def plan_from_html(
        self,
        user_instruction: str,
        html: str,
        target_url: str,
        container_hint: Optional[str] = None,
        allow_fallback: bool = False,
    ) -> ExtractionPlan:
        """
        Generate an ExtractionPlan from an HTML string and user instruction.

        Args:
            user_instruction: Natural language extraction request.
            html: Raw HTML content.
            target_url: The URL corresponding to the page.
            container_hint: Optional CSS selector hint for container.
            allow_fallback: Whether to use heuristic fallback if Gemini is unavailable.

        Returns:
            Validated ExtractionPlan.

        Raises:
            PlannerError: If generation fails and allow_fallback is False.
        """
        pruned_dom = prune_html_for_llm(html)

        try:
            return self.client.generate_plan(
                user_instruction=user_instruction,
                pruned_html=pruned_dom,
                target_url=target_url,
                container_hint=container_hint,
            )
        except (MissingApiKeyError, PlannerApiError, PlannerSchemaError) as exc:
            if allow_fallback:
                return generate_heuristic_plan(
                    html=html,
                    target_url=target_url,
                    user_instruction=user_instruction,
                )
            raise exc

    def plan_from_url(
        self,
        user_instruction: str,
        target_url: str,
        container_hint: Optional[str] = None,
        verify_dns: bool = True,
        allow_fallback: bool = False,
    ) -> ExtractionPlan:
        """
        Safely fetch HTML from target URL and generate an ExtractionPlan.

        Args:
            user_instruction: Natural language extraction request.
            target_url: Target URL to inspect and plan for.
            container_hint: Optional container CSS selector hint.
            verify_dns: Whether to enforce DNS and SSRF safety checks.
            allow_fallback: Whether to use heuristic fallback if Gemini is unavailable.

        Returns:
            Validated ExtractionPlan.
        """
        html_content, final_url, _ = fetch_html(target_url, verify_dns=verify_dns)
        return self.plan_from_html(
            user_instruction=user_instruction,
            html=html_content,
            target_url=final_url,
            container_hint=container_hint,
            allow_fallback=allow_fallback,
        )

