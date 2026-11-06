"""
Multi-dimensional Data Quality Evaluator for Web Data Forge.
Assesses extracted datasets across Completeness, Validity, and Uniqueness
to produce a weighted composite score and letter grade (A-F).
"""

import json
from typing import Any, Dict, List, Set
from pydantic import BaseModel, Field

from web_data_forge.models.contracts import FieldContract, RecordAudit


class QualityAssessment(BaseModel):
    """
    Comprehensive multi-dimensional quality report for an extraction dataset.
    """

    total_records: int
    valid_records: int
    duplicate_records: int
    total_fields_expected: int
    total_fields_collected: int

    completeness_score: float = Field(
        ..., description="Percentage of non-empty collected values (0.0 to 100.0)"
    )
    validity_score: float = Field(
        ..., description="Percentage of records meeting schema & type contracts (0.0 to 100.0)"
    )
    uniqueness_score: float = Field(
        ..., description="Percentage of unique records without duplicates (0.0 to 100.0)"
    )
    quality_score: float = Field(
        ..., description="Weighted composite score: 40% Completeness + 40% Validity + 20% Uniqueness"
    )
    quality_grade: str = Field(
        ..., description="Letter grade: A (>=90), B (>=80), C (>=70), D (>=60), F (<60)"
    )

    field_completeness: Dict[str, float] = Field(
        default_factory=dict, description="Completeness percentage per field"
    )
    missing_fields_summary: Dict[str, int] = Field(
        default_factory=dict, description="Count of missing instances per field"
    )
    critical_missing_fields: List[str] = Field(
        default_factory=list, description="Fields with > 30% missing rate"
    )
    error_summary: Dict[str, int] = Field(
        default_factory=dict, description="Count of validation errors per field"
    )


def compute_quality_grade(score: float) -> str:
    """Map a 0-100 quality score to a letter grade."""
    if score >= 90.0:
        return "A"
    if score >= 80.0:
        return "B"
    if score >= 70.0:
        return "C"
    if score >= 60.0:
        return "D"
    return "F"


def evaluate_quality(
    audits: List[RecordAudit],
    fields: List[FieldContract],
) -> QualityAssessment:
    """
    Evaluate extraction dataset quality across Completeness, Validity, and Uniqueness.

    Args:
        audits: List of RecordAudit instances from the pipeline run.
        fields: List of FieldContracts defined in the extraction plan.

    Returns:
        QualityAssessment containing dimensional metrics, composite score, and grade.
    """
    total_records = len(audits)
    field_count = len(fields)
    total_fields_expected = total_records * field_count

    if total_records == 0:
        return QualityAssessment(
            total_records=0,
            valid_records=0,
            duplicate_records=0,
            total_fields_expected=0,
            total_fields_collected=0,
            completeness_score=0.0,
            validity_score=0.0,
            uniqueness_score=100.0,
            quality_score=0.0,
            quality_grade="F",
            field_completeness={f.name: 0.0 for f in fields},
            missing_fields_summary={f.name: 0 for f in fields},
            critical_missing_fields=[f.name for f in fields],
            error_summary={},
        )

    # 1. Validity calculation
    valid_records = sum(1 for a in audits if a.is_valid)
    validity_score = round((valid_records / total_records) * 100.0, 2)

    # 2. Missing fields and completeness calculation
    missing_counts: Dict[str, int] = {f.name: 0 for f in fields}
    error_counts: Dict[str, int] = {}

    for audit in audits:
        for missing_f in audit.missing_fields:
            if missing_f in missing_counts:
                missing_counts[missing_f] += 1
        for err_f in audit.validation_errors:
            error_counts[err_f] = error_counts.get(err_f, 0) + 1

    total_missing = sum(missing_counts.values())
    total_fields_collected = max(0, total_fields_expected - total_missing)

    completeness_score = (
        round((total_fields_collected / total_fields_expected) * 100.0, 2)
        if total_fields_expected > 0
        else 0.0
    )

    field_completeness: Dict[str, float] = {}
    critical_missing: List[str] = []
    for f in fields:
        miss = missing_counts.get(f.name, 0)
        col = total_records - miss
        rate = round((col / total_records) * 100.0, 2)
        field_completeness[f.name] = rate
        if (miss / total_records) > 0.30:
            critical_missing.append(f.name)

    # 3. Uniqueness and duplicate detection
    seen_hashes: Set[str] = set()
    duplicate_records = 0

    for audit in audits:
        # Canonical string representation of coerced record
        try:
            record_key = json.dumps(audit.coerced_data, sort_keys=True, default=str)
        except Exception:
            record_key = str(sorted(audit.coerced_data.items()))

        if record_key in seen_hashes:
            duplicate_records += 1
        else:
            seen_hashes.add(record_key)

    uniqueness_score = round(
        max(0.0, (1.0 - (duplicate_records / total_records)) * 100.0), 2
    )

    # 4. Composite Quality Score (40% Completeness + 40% Validity + 20% Uniqueness)
    quality_score = round(
        (0.40 * completeness_score)
        + (0.40 * validity_score)
        + (0.20 * uniqueness_score),
        2,
    )

    quality_grade = compute_quality_grade(quality_score)

    return QualityAssessment(
        total_records=total_records,
        valid_records=valid_records,
        duplicate_records=duplicate_records,
        total_fields_expected=total_fields_expected,
        total_fields_collected=total_fields_collected,
        completeness_score=completeness_score,
        validity_score=validity_score,
        uniqueness_score=uniqueness_score,
        quality_score=quality_score,
        quality_grade=quality_grade,
        field_completeness=field_completeness,
        missing_fields_summary=missing_counts,
        critical_missing_fields=critical_missing,
        error_summary=error_counts,
    )

