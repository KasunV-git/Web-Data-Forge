"""
Core extraction pipeline orchestrator.
Coordinates URL safety validation, network retrieval, HTML extraction,
and data contract validation into a single execution flow.
"""

import time
from typing import List, Optional
from urllib.parse import urlsplit

from web_data_forge.core.exceptions import (
    NetworkError,
    ResponseTooLargeError,
    SecurityError,
    UrlValidationError,
    WebDataForgeError,
)
from web_data_forge.extraction.static_extractor import StaticHtmlExtractor
from web_data_forge.inspection.url_validator import (
    resolve_hostname_ips,
    validate_url,
)
from web_data_forge.models.contracts import (
    ExtractionPlan,
    PipelineResult,
    PipelineTelemetry,
    QualityReport,
    RecordAudit,
)
from web_data_forge.security.network_guard import (
    DEFAULT_USER_AGENT,
    SafeFetcher,
)


class ExtractionPipeline:
    """
    Coordinates end-to-end execution of an ExtractionPlan:
    URL safety -> Safe HTTP retrieval -> Rule extraction -> Data contracts & Quality audit.
    """

    def __init__(
        self,
        extractor: Optional[StaticHtmlExtractor] = None,
    ) -> None:
        self.extractor = extractor or StaticHtmlExtractor()

    def process_markup(
        self,
        html_content: str,
        plan: ExtractionPlan,
    ) -> List[RecordAudit]:
        """
        Extract and coerce fields from HTML content according to the plan's field contracts.
        """
        rules = [field.to_field_rule(enforce_required=False) for field in plan.fields]

        if plan.container_selector:
            raw_records = self.extractor.extract_collection(
                html_content, plan.container_selector, rules
            )
        else:
            raw_records = [self.extractor.extract_item(html_content, rules)]

        audits: List[RecordAudit] = []

        for raw in raw_records:
            coerced: dict = {}
            missing: List[str] = []
            errors: dict = {}
            is_valid = True

            for field in plan.fields:
                raw_val = raw.get(field.name)
                try:
                    coerced_val = field.coerce_value(raw_val)
                    coerced[field.name] = coerced_val
                    if coerced_val is None or coerced_val == "":
                        missing.append(field.name)
                except Exception as exc:
                    is_valid = False
                    errors[field.name] = str(exc)
                    coerced[field.name] = field.default
                    missing.append(field.name)

            audits.append(
                RecordAudit(
                    raw_data=raw,
                    coerced_data=coerced,
                    missing_fields=missing,
                    is_valid=is_valid,
                    validation_errors=errors,
                )
            )

        return audits

    def run_offline(
        self,
        plan: ExtractionPlan,
        html_content: str,
    ) -> PipelineResult:
        """
        Execute an extraction plan against an offline HTML string without making network calls.
        Useful for fixture validation, local mock runs, and regression tests.
        """
        start_time = time.perf_counter()

        audits = self.process_markup(html_content, plan)
        quality = QualityReport.calculate(audits, plan.fields)
        latency = round(time.perf_counter() - start_time, 4)

        telemetry = PipelineTelemetry(
            target_url=plan.target_url,
            resolved_ip="127.0.0.1 (offline fixture)",
            status_code=200,
            bytes_downloaded=len(html_content.encode("utf-8")),
            latency_seconds=latency,
            success=True,
        )

        return PipelineResult(
            plan=plan,
            telemetry=telemetry,
            records=[a.coerced_data for a in audits],
            record_audits=audits,
            quality_report=quality,
        )

    def run(
        self,
        plan: ExtractionPlan,
        verify_dns: bool = True,
        raise_on_error: bool = False,
    ) -> PipelineResult:
        """
        Execute the full extraction pipeline:
        1. Validate URL destination against SSRF policies.
        2. Fetch HTML via bounded SafeFetcher.
        3. Parse elements and extract raw fields.
        4. Validate, coerce, and audit data quality.
        5. Return comprehensive PipelineResult.
        """
        start_time = time.perf_counter()
        target_url = plan.target_url
        resolved_ip: Optional[str] = None

        try:
            # 1. URL Safety and DNS Resolution
            validated_url = validate_url(target_url, verify_dns=verify_dns)
            hostname = urlsplit(validated_url).hostname
            if hostname:
                try:
                    ips = resolve_hostname_ips(hostname)
                    resolved_ip = ips[0] if ips else None
                except Exception:
                    pass

            # 2. Safe Network Retrieval
            fetcher = SafeFetcher(
                timeout=plan.timeout,
                max_bytes=plan.max_bytes,
                max_redirects=plan.max_redirects,
                user_agent=plan.user_agent or DEFAULT_USER_AGENT,
            )
            html_content, final_url, status_code = fetcher.fetch(
                validated_url, verify_dns=verify_dns
            )

            # 3. Extraction & Quality Audit
            audits = self.process_markup(html_content, plan)
            quality = QualityReport.calculate(audits, plan.fields)
            latency = round(time.perf_counter() - start_time, 4)

            telemetry = PipelineTelemetry(
                target_url=final_url,
                resolved_ip=resolved_ip,
                status_code=status_code,
                bytes_downloaded=len(html_content.encode("utf-8")),
                latency_seconds=latency,
                success=True,
            )

            return PipelineResult(
                plan=plan,
                telemetry=telemetry,
                records=[a.coerced_data for a in audits],
                record_audits=audits,
                quality_report=quality,
            )

        except (WebDataForgeError, Exception) as exc:
            latency = round(time.perf_counter() - start_time, 4)
            if raise_on_error:
                raise

            error_msg = str(exc)
            telemetry = PipelineTelemetry(
                target_url=target_url,
                resolved_ip=resolved_ip,
                status_code=None,
                bytes_downloaded=0,
                latency_seconds=latency,
                success=False,
                error_message=error_msg,
            )

            empty_quality = QualityReport.calculate([], plan.fields)

            return PipelineResult(
                plan=plan,
                telemetry=telemetry,
                records=[],
                record_audits=[],
                quality_report=empty_quality,
            )
