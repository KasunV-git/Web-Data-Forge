"""
Data Quality package for Web Data Forge.
Provides multi-dimensional quality assessment (Completeness, Validity, Uniqueness).
"""

from web_data_forge.quality.evaluator import (
    QualityAssessment,
    compute_quality_grade,
    evaluate_quality,
)

__all__ = [
    "QualityAssessment",
    "compute_quality_grade",
    "evaluate_quality",
]

