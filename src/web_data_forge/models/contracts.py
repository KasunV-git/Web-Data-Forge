"""
Pydantic v2 data contracts, schema definitions, and validation models
for Web Data Forge.
"""

from enum import Enum
import re
from typing import Any, Dict, List, Literal, Optional
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from web_data_forge.extraction.static_extractor import FieldRule


class DataType(str, Enum):
    """Supported data types for extracted fields."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    URL = "url"


class FieldContract(BaseModel):
    """
    Contract defining a field to extract, including CSS selector,
    target attribute, extraction mode, data type, and validation rules.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., description="Unique name/key for this field", min_length=1)
    selector: str = Field(..., description="CSS selector for locating the element")
    extract: Literal["text", "attr", "html"] = Field(
        default="text",
        description="Extraction mode: 'text', 'attr', or 'html'",
    )
    attr_name: Optional[str] = Field(
        default=None,
        description="Target attribute name (required when extract='attr')",
    )
    regex: Optional[str] = Field(
        default=None,
        description="Optional regex pattern to apply to extracted raw string",
    )
    data_type: DataType = Field(
        default=DataType.STRING,
        description="Target typed representation for the value",
    )
    required: bool = Field(
        default=False,
        description="Whether the field is strictly required to be present",
    )
    default: Optional[Any] = Field(
        default=None,
        description="Default fallback value if selector is not found",
    )
    strip_whitespace: bool = Field(
        default=True,
        description="Whether to strip and normalize excessive whitespace",
    )

    @field_validator("name")
    @classmethod
    def validate_name_identifier(cls, v: str) -> str:
        cleaned = v.strip()
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", cleaned):
            raise ValueError(
                f"Field name '{v}' must be a valid identifier (alphanumeric and underscores, not starting with digit)."
            )
        return cleaned

    @model_validator(mode="after")
    def validate_attr_mode(self) -> "FieldContract":
        if self.extract == "attr" and not self.attr_name:
            raise ValueError("attr_name must be provided when extract='attr'.")
        if self.regex:
            try:
                re.compile(self.regex)
            except re.error as exc:
                raise ValueError(f"Invalid regex pattern '{self.regex}': {exc}") from exc
        return self

    def to_field_rule(self, enforce_required: bool = True) -> FieldRule:
        """Convert this contract to a FieldRule for the extraction engine."""
        return FieldRule(
            name=self.name,
            selector=self.selector,
            extract=self.extract,
            attr_name=self.attr_name,
            regex=self.regex,
            default=self.default,
            required=self.required if enforce_required else False,
            strip_whitespace=self.strip_whitespace,
        )

    def coerce_value(self, raw_value: Any) -> Any:
        """
        Coerce a raw extracted value into the configured DataType.
        Raises ValueError if coercion fails and field is required.
        """
        if raw_value is None or raw_value == "":
            if self.required:
                raise ValueError(f"Required field '{self.name}' is missing.")
            return self.default

        if self.data_type == DataType.STRING:
            return str(raw_value)

        if self.data_type == DataType.INTEGER:
            str_val = str(raw_value).strip()
            # Clean common formatting like commas or currency: "$1,240" -> "1240"
            cleaned = re.sub(r"[^\d\-]", "", str_val)
            if not cleaned or cleaned == "-":
                if self.required:
                    raise ValueError(f"Cannot coerce '{raw_value}' to integer for required field '{self.name}'.")
                return self.default
            return int(cleaned)

        if self.data_type == DataType.FLOAT:
            str_val = str(raw_value).strip()
            # Clean currency symbols and commas: "$199.99" -> "199.99"
            cleaned = re.sub(r"[^\d.\-]", "", str_val)
            try:
                return float(cleaned)
            except ValueError:
                if self.required:
                    raise ValueError(f"Cannot coerce '{raw_value}' to float for required field '{self.name}'.")
                return self.default

        if self.data_type == DataType.BOOLEAN:
            str_val = str(raw_value).strip().lower()
            falsy_keywords = {"false", "0", "no", "out of stock", "unavailable", "n", "none"}
            truthy_keywords = {"true", "1", "yes", "in stock", "available", "y"}

            if str_val in truthy_keywords:
                return True
            if str_val in falsy_keywords:
                return False
            if any(k in str_val for k in falsy_keywords):
                return False
            if any(k in str_val for k in truthy_keywords):
                return True
            return bool(raw_value)


        if self.data_type == DataType.URL:
            str_val = str(raw_value).strip()
            return str_val

        return raw_value


class ExtractionPlan(BaseModel):
    """
    Blueprint defining the target URL, extraction scope, field contracts,
    and runtime security constraints.
    """

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(..., description="Target URL to inspect and extract")
    container_selector: Optional[str] = Field(
        default=None,
        description="CSS selector for repeated items (e.g. '.product-card'). If None, extracts a single item.",
    )
    fields: List[FieldContract] = Field(
        ..., min_length=1, description="List of field contracts to extract"
    )
    timeout: float = Field(
        default=10.0,
        ge=1.0,
        le=60.0,
        description="Timeout in seconds per network request",
    )
    max_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        le=50 * 1024 * 1024,
        description="Maximum allowed response payload size in bytes",
    )
    max_redirects: int = Field(
        default=5,
        ge=0,
        le=10,
        description="Maximum redirect hops to follow",
    )
    user_agent: Optional[str] = Field(
        default=None,
        description="Optional custom User-Agent string",
    )

    @field_validator("target_url")
    @classmethod
    def validate_url_scheme(cls, v: str) -> str:
        parsed = urlparse(v)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ValueError(f"Invalid target URL scheme '{parsed.scheme}'. Only http and https are allowed.")
        if not parsed.netloc:
            raise ValueError("Target URL must have a valid network host.")
        return v

    @model_validator(mode="after")
    def validate_unique_field_names(self) -> "ExtractionPlan":
        seen = set()
        for f in self.fields:
            if f.name in seen:
                raise ValueError(f"Duplicate field name '{f.name}' in extraction plan.")
            seen.add(f.name)
        return self


class RecordAudit(BaseModel):
    """Audit information for a single extracted record."""

    raw_data: Dict[str, Any]
    coerced_data: Dict[str, Any]
    missing_fields: List[str]
    is_valid: bool
    validation_errors: Dict[str, str] = Field(default_factory=dict)


class QualityReport(BaseModel):
    """Aggregate quality and completeness report for an extraction run."""

    total_records: int
    valid_records: int
    total_fields_expected: int
    total_fields_collected: int
    completeness_score: float = Field(
        ..., description="Percentage of successfully collected fields (0.0 to 100.0)"
    )
    missing_fields_summary: Dict[str, int] = Field(
        default_factory=dict, description="Count of missing occurrences per field"
    )

    @classmethod
    def calculate(
        cls,
        audits: List[RecordAudit],
        fields: List[FieldContract],
    ) -> "QualityReport":
        total_records = len(audits)
        if total_records == 0:
            return cls(
                total_records=0,
                valid_records=0,
                total_fields_expected=0,
                total_fields_collected=0,
                completeness_score=0.0,
                missing_fields_summary={f.name: 0 for f in fields},
            )

        valid_records = sum(1 for a in audits if a.is_valid)
        total_fields_expected = total_records * len(fields)
        missing_counts: Dict[str, int] = {f.name: 0 for f in fields}

        for audit in audits:
            for missing_f in audit.missing_fields:
                if missing_f in missing_counts:
                    missing_counts[missing_f] += 1

        total_missing = sum(missing_counts.values())
        total_collected = max(0, total_fields_expected - total_missing)
        completeness = (
            round((total_collected / total_fields_expected) * 100.0, 2)
            if total_fields_expected > 0
            else 0.0
        )

        return cls(
            total_records=total_records,
            valid_records=valid_records,
            total_fields_expected=total_fields_expected,
            total_fields_collected=total_collected,
            completeness_score=completeness,
            missing_fields_summary=missing_counts,
        )


class PipelineTelemetry(BaseModel):
    """Network, performance, and security telemetry for an extraction run."""

    target_url: str
    resolved_ip: Optional[str] = None
    status_code: Optional[int] = None
    bytes_downloaded: int = 0
    latency_seconds: float = 0.0
    success: bool = True
    error_message: Optional[str] = None


class PipelineResult(BaseModel):
    """Comprehensive output produced by an extraction pipeline run."""

    plan: ExtractionPlan
    telemetry: PipelineTelemetry
    records: List[Dict[str, Any]]
    record_audits: List[RecordAudit]
    quality_report: QualityReport
