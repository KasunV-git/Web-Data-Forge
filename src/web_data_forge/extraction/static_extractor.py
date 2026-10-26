"""
Static HTML extraction engine powered by BeautifulSoup4.
Provides rule-based field extraction for single pages and collections.
"""

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Optional, Union
from bs4 import BeautifulSoup, Tag
import soupsieve

from web_data_forge.core.exceptions import (
    ExtractionError,
    InvalidSelectorError,
)


@dataclass
class FieldRule:
    """
    Defines how a single data field should be extracted from an HTML element.
    """

    name: str
    selector: str
    extract: str = "text"  # "text", "attr", or "html"
    attr_name: Optional[str] = None
    regex: Optional[str] = None
    default: Optional[Any] = None
    required: bool = False
    strip_whitespace: bool = True

    def __post_init__(self) -> None:
        if self.extract not in {"text", "attr", "html"}:
            raise ValueError(
                f"Invalid extract mode '{self.extract}'. Expected 'text', 'attr', or 'html'."
            )
        if self.extract == "attr" and not self.attr_name:
            raise ValueError("attr_name must be provided when extract='attr'.")


class StaticHtmlExtractor:
    """
    Parses HTML markup and extracts structured records using configurable CSS rules.
    """

    def __init__(self, parser: str = "html.parser") -> None:
        self.parser = parser

    def parse_soup(
        self, html_or_tag: Union[str, Tag, BeautifulSoup]
    ) -> Union[Tag, BeautifulSoup]:
        """Convert input to a BeautifulSoup or Tag object if it is a string."""
        if isinstance(html_or_tag, (Tag, BeautifulSoup)):
            return html_or_tag
        if not isinstance(html_or_tag, str):
            raise ExtractionError(
                f"Expected HTML string or Tag/BeautifulSoup object, got {type(html_or_tag).__name__}"
            )
        return BeautifulSoup(html_or_tag, self.parser)

    def extract_field(
        self, element: Union[Tag, BeautifulSoup], rule: FieldRule
    ) -> Any:
        """
        Extract a single field from an element according to a FieldRule.
        """
        target_el: Optional[Tag] = None

        try:
            selector = rule.selector.strip()
            if selector in {"", ".", "self", ":scope"}:
                if isinstance(element, Tag):
                    target_el = element
                else:
                    target_el = element.find()
            else:
                target_el = element.select_one(selector)
        except (soupsieve.SelectorSyntaxError, Exception) as exc:
            if isinstance(exc, soupsieve.SelectorSyntaxError):
                raise InvalidSelectorError(
                    f"Invalid CSS selector '{rule.selector}' for field '{rule.name}': {exc}"
                ) from exc
            raise

        if target_el is None:
            if rule.required:
                raise ExtractionError(
                    f"Required field '{rule.name}' not found matching selector '{rule.selector}'."
                )
            return rule.default

        # Extract value based on mode
        raw_val: Optional[str] = None
        if rule.extract == "attr" or rule.attr_name is not None:
            attr_key = rule.attr_name or ""
            val = target_el.get(attr_key)
            if val is None:
                if rule.required:
                    raise ExtractionError(
                        f"Required attribute '{attr_key}' on field '{rule.name}' not found."
                    )
                return rule.default
            raw_val = " ".join(val) if isinstance(val, list) else str(val)
        elif rule.extract == "html":
            raw_val = str(target_el)
        else:  # "text"
            raw_val = target_el.get_text(separator=" ", strip=False)

        # Normalize text/whitespace
        if raw_val is not None and rule.strip_whitespace:
            raw_val = re.sub(r"\s+", " ", raw_val).strip()

        # Apply regex pattern if defined
        if raw_val is not None and rule.regex:
            match = re.search(rule.regex, raw_val)
            if match:
                raw_val = match.group(1) if match.groups() else match.group(0)
            else:
                if rule.required:
                    raise ExtractionError(
                        f"Required field '{rule.name}' regex '{rule.regex}' did not match '{raw_val}'."
                    )
                return rule.default

        return raw_val

    def extract_item(
        self,
        html_or_tag: Union[str, Tag, BeautifulSoup],
        rules: List[FieldRule],
    ) -> Dict[str, Any]:
        """
        Extract fields from a single page or element container.
        """
        soup = self.parse_soup(html_or_tag)
        record: Dict[str, Any] = {}

        for rule in rules:
            record[rule.name] = self.extract_field(soup, rule)

        return record

    def extract_collection(
        self,
        html_or_tag: Union[str, Tag, BeautifulSoup],
        container_selector: str,
        rules: List[FieldRule],
    ) -> List[Dict[str, Any]]:
        """
        Extract multiple records from repeating containers matching container_selector.
        """
        soup = self.parse_soup(html_or_tag)

        try:
            containers = soup.select(container_selector)
        except soupsieve.SelectorSyntaxError as exc:
            raise InvalidSelectorError(
                f"Invalid container selector '{container_selector}': {exc}"
            ) from exc

        records: List[Dict[str, Any]] = []
        for container in containers:
            item = self.extract_item(container, rules)
            records.append(item)

        return records
