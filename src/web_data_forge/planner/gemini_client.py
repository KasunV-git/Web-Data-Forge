"""
Gemini Client adapter for AI extraction planning using google-genai SDK.
"""

import os
from typing import Optional
from google import genai
from google.genai import types
from pydantic import ValidationError

from web_data_forge.core.exceptions import (
    MissingApiKeyError,
    PlannerApiError,
    PlannerSchemaError,
)
from web_data_forge.models.contracts import ExtractionPlan
from web_data_forge.planner.prompts import SYSTEM_PROMPT, build_user_prompt

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiPlannerClient:
    """
    Adapter for communicating with the Gemini API to generate structured ExtractionPlans.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
        )
        self.model_name = (
            model_name
            or os.environ.get("GEMINI_MODEL")
            or DEFAULT_MODEL
        )

        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        """Lazily initialize and return the GenAI client."""
        if not self.api_key or self.api_key.strip() in ("", "your_gemini_api_key_here"):
            raise MissingApiKeyError(
                "Gemini API key is required for AI extraction planning. "
                "Set GEMINI_API_KEY in your .env file or supply it via settings."
            )

        if self._client is None:
            self._client = genai.Client(api_key=self.api_key)

        return self._client

    def generate_plan(
        self,
        user_instruction: str,
        pruned_html: str,
        target_url: str,
        container_hint: Optional[str] = None,
    ) -> ExtractionPlan:
        """
        Request Gemini to generate a structured ExtractionPlan based on user instruction
        and the pruned HTML DOM.

        Args:
            user_instruction: Natural language extraction request.
            pruned_html: Sanitized HTML string within untrusted context tags.
            target_url: The URL of the target web page.
            container_hint: Optional hint for container selector.

        Returns:
            Validated ExtractionPlan instance.

        Raises:
            MissingApiKeyError: If API key is not supplied.
            PlannerApiError: If API call fails.
            PlannerSchemaError: If response cannot be parsed into an ExtractionPlan.
        """
        client = self._get_client()

        user_content = build_user_prompt(
            user_instruction=user_instruction,
            pruned_html=pruned_html,
            target_url=target_url,
            container_hint=container_hint,
        )

        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=ExtractionPlan,
            temperature=0.1,  # Low temperature for deterministic selector extraction
        )

        try:
            response = client.models.generate_content(
                model=self.model_name,
                contents=user_content,
                config=config,
            )
        except Exception as exc:
            raise PlannerApiError(
                f"Failed to communicate with Gemini API ({self.model_name}): {exc}"
            ) from exc

        raw_text = getattr(response, "text", "")
        if not raw_text or not raw_text.strip():
            raise PlannerSchemaError("Gemini API returned an empty response.")

        try:
            plan = ExtractionPlan.model_validate_json(raw_text)
            # Ensure target_url is populated accurately even if LLM omitted or altered it
            if not plan.target_url or plan.target_url.strip() != target_url.strip():
                plan = plan.model_copy(update={"target_url": target_url})
            return plan
        except ValidationError as exc:
            raise PlannerSchemaError(
                f"Generated extraction plan failed validation: {exc}",
                details={"raw_response": raw_text},
            ) from exc

