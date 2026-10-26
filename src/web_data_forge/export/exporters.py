"""
Safe dataset exporters for CSV and JSON serialization.
Enforces OWASP formula-injection defenses for spreadsheet compatibility.
"""

import csv
import io
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Union

from web_data_forge.models.contracts import PipelineResult

DANGEROUS_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def is_pure_number(value: str) -> bool:
    """Check if a string represents a plain decimal or integer (e.g., '-42', '3.14')."""
    return bool(re.match(r"^-?\d+(\.\d+)?$", value.strip()))


def sanitize_csv_value(value: Any, sanitize: bool = True) -> Any:
    """
    Sanitize a single cell value for CSV export according to OWASP formula injection controls.
    Prepends a single quote (') if the value starts with dangerous formula operators (=, +, -, @, \\t, \\r)
    unless the value is a plain numeric literal.
    """
    if value is None:
        return ""

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    str_val = str(value)
    if not sanitize or not str_val:
        return str_val

    # If it starts with a dangerous trigger character
    if str_val.startswith(DANGEROUS_FORMULA_PREFIXES):
        # Do not escape benign pure negative numbers (e.g. '-10', '-3.5')
        if str_val.startswith("-") and is_pure_number(str_val):
            return str_val
        if str_val.startswith("+") and is_pure_number(str_val[1:]):
            return str_val
        return f"'{str_val}"

    return str_val


def export_csv(
    records: List[Dict[str, Any]],
    fieldnames: Optional[List[str]] = None,
    sanitize_formulas: bool = True,
) -> str:
    """
    Serialize a list of record dictionaries into an RFC 4180 CSV string with formula sanitization.

    Args:
        records: List of key-value dictionaries.
        fieldnames: Optional explicit list of columns and their ordering.
        sanitize_formulas: Whether to sanitize formula injection characters.

    Returns:
        CSV formatted string.
    """
    if not records:
        if fieldnames:
            buffer = io.StringIO()
            writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
            writer.writeheader()
            return buffer.getvalue()
        return ""

    # Derive fieldnames if not specified
    if not fieldnames:
        unique_keys: List[str] = []
        for r in records:
            for k in r.keys():
                if k not in unique_keys:
                    unique_keys.append(k)
        fieldnames = unique_keys

    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer,
        fieldnames=fieldnames,
        lineterminator="\n",
        quoting=csv.QUOTE_MINIMAL,
    )
    writer.writeheader()

    for r in records:
        sanitized_row = {
            k: sanitize_csv_value(r.get(k), sanitize=sanitize_formulas)
            for k in fieldnames
        }
        writer.writerow(sanitized_row)

    return buffer.getvalue()


def export_csv_to_file(
    records: List[Dict[str, Any]],
    file_path: Union[str, Path],
    fieldnames: Optional[List[str]] = None,
    sanitize_formulas: bool = True,
) -> Path:
    """Write sanitized CSV records to a file path."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = export_csv(records, fieldnames=fieldnames, sanitize_formulas=sanitize_formulas)
    path.write_text(content, encoding="utf-8")
    return path


def export_json(
    records: List[Dict[str, Any]],
    indent: int = 2,
) -> str:
    """
    Serialize records to formatted JSON.

    Args:
        records: List of dictionaries.
        indent: Indentation spaces for pretty printing.

    Returns:
        JSON string.
    """
    return json.dumps(records, indent=indent, ensure_ascii=False)


def export_json_to_file(
    records: List[Dict[str, Any]],
    file_path: Union[str, Path],
    indent: int = 2,
) -> Path:
    """Write formatted JSON records to a file path."""
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = export_json(records, indent=indent)
    path.write_text(content, encoding="utf-8")
    return path


def export_result_csv(
    result: PipelineResult,
    file_path: Optional[Union[str, Path]] = None,
    sanitize_formulas: bool = True,
) -> str:
    """Export the records from a PipelineResult to CSV string or file."""
    fieldnames = [f.name for f in result.plan.fields]
    csv_str = export_csv(
        result.records,
        fieldnames=fieldnames,
        sanitize_formulas=sanitize_formulas,
    )
    if file_path:
        Path(file_path).write_text(csv_str, encoding="utf-8")
    return csv_str


def export_result_json(
    result: PipelineResult,
    file_path: Optional[Union[str, Path]] = None,
    indent: int = 2,
    include_metadata: bool = True,
) -> str:
    """
    Export PipelineResult to JSON string or file.
    If include_metadata is True, wraps dataset with telemetry and quality report.
    """
    if include_metadata:
        payload = {
            "telemetry": result.telemetry.model_dump(),
            "quality_report": result.quality_report.model_dump(),
            "records": result.records,
        }
    else:
        payload = result.records  # type: ignore

    json_str = json.dumps(payload, indent=indent, ensure_ascii=False)
    if file_path:
        Path(file_path).write_text(json_str, encoding="utf-8")
    return json_str
