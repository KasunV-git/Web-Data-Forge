"""
Unit tests for Multi-Dimensional Data Quality Evaluator.
"""

import pytest

from web_data_forge.models.contracts import DataType, FieldContract, RecordAudit
from web_data_forge.quality.evaluator import (
    compute_quality_grade,
    evaluate_quality,
)


@pytest.fixture
def sample_fields():
    return [
        FieldContract(name="title", selector="h1", data_type=DataType.STRING, required=True),
        FieldContract(name="price", selector=".price", data_type=DataType.FLOAT, required=True),
        FieldContract(name="rating", selector=".rating", data_type=DataType.FLOAT, required=False),
    ]


def test_empty_dataset_quality(sample_fields):
    assessment = evaluate_quality([], sample_fields)
    assert assessment.total_records == 0
    assert assessment.quality_score == 0.0
    assert assessment.quality_grade == "F"
    assert len(assessment.critical_missing_fields) == len(sample_fields)


def test_perfect_dataset_quality(sample_fields):
    audits = [
        RecordAudit(
            raw_data={"title": "Item 1", "price": "$10.0", "rating": "4.5"},
            coerced_data={"title": "Item 1", "price": 10.0, "rating": 4.5},
            missing_fields=[],
            is_valid=True,
            validation_errors={},
        ),
        RecordAudit(
            raw_data={"title": "Item 2", "price": "$20.0", "rating": "4.8"},
            coerced_data={"title": "Item 2", "price": 20.0, "rating": 4.8},
            missing_fields=[],
            is_valid=True,
            validation_errors={},
        ),
    ]

    assessment = evaluate_quality(audits, sample_fields)
    assert assessment.total_records == 2
    assert assessment.valid_records == 2
    assert assessment.duplicate_records == 0
    assert assessment.completeness_score == 100.0
    assert assessment.validity_score == 100.0
    assert assessment.uniqueness_score == 100.0
    assert assessment.quality_score == 100.0
    assert assessment.quality_grade == "A"
    assert len(assessment.critical_missing_fields) == 0


def test_missing_fields_and_critical_detection(sample_fields):
    audits = [
        RecordAudit(
            raw_data={"title": "Item 1", "price": "10.0", "rating": None},
            coerced_data={"title": "Item 1", "price": 10.0, "rating": None},
            missing_fields=["rating"],
            is_valid=True,
            validation_errors={},
        ),
        RecordAudit(
            raw_data={"title": "Item 2", "price": "20.0", "rating": None},
            coerced_data={"title": "Item 2", "price": 20.0, "rating": None},
            missing_fields=["rating"],
            is_valid=True,
            validation_errors={},
        ),
    ]

    assessment = evaluate_quality(audits, sample_fields)
    # Total fields expected: 2 records * 3 fields = 6
    # Missing rating in both: 2 missing out of 6 -> 4 collected out of 6 = 66.67%
    assert assessment.completeness_score == 66.67
    assert assessment.field_completeness["rating"] == 0.0
    assert "rating" in assessment.critical_missing_fields


def test_duplicate_records_lower_uniqueness(sample_fields):
    identical_record = RecordAudit(
        raw_data={"title": "Duplicate", "price": "15.0", "rating": "4.0"},
        coerced_data={"title": "Duplicate", "price": 15.0, "rating": 4.0},
        missing_fields=[],
        is_valid=True,
        validation_errors={},
    )
    audits = [identical_record, identical_record, identical_record, identical_record]

    assessment = evaluate_quality(audits, sample_fields)
    assert assessment.total_records == 4
    assert assessment.duplicate_records == 3
    # 1 unique out of 4 -> uniqueness score = 25.0%
    assert assessment.uniqueness_score == 25.0


def test_grade_mapping():
    assert compute_quality_grade(95.0) == "A"
    assert compute_quality_grade(85.0) == "B"
    assert compute_quality_grade(75.0) == "C"
    assert compute_quality_grade(65.0) == "D"
    assert compute_quality_grade(45.0) == "F"
