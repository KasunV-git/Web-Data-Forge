"""
Storage Repository for Web Data Forge extraction jobs and records.
Provides clean CRUD access across database engines.
"""

import json
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from web_data_forge.models.contracts import PipelineResult
from web_data_forge.quality.evaluator import QualityAssessment, evaluate_quality
from web_data_forge.storage.models import JobModel, RecordModel


class JobRepository:
    """
    Data access repository for persisting and querying extraction jobs and records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def save_job(
        self,
        result: PipelineResult,
        quality: Optional[QualityAssessment] = None,
    ) -> JobModel:
        """
        Persist a PipelineResult and its QualityAssessment into the database.

        Args:
            result: Executed PipelineResult instance.
            quality: Optional QualityAssessment (computed automatically if omitted).

        Returns:
            Saved JobModel instance.
        """
        # Calculate quality assessment if not provided explicitly
        if quality is None:
            quality = evaluate_quality(result.record_audits, result.plan.fields)

        job_id = str(uuid.uuid4())
        status = "SUCCESS" if result.telemetry.success else "FAILED"
        if result.telemetry.success and quality.valid_records < quality.total_records:
            status = "PARTIAL"

        job = JobModel(
            id=job_id,
            target_url=result.plan.target_url,
            status=status,
            total_records=quality.total_records,
            valid_records=quality.valid_records,
            duplicate_records=quality.duplicate_records,
            quality_score=quality.quality_score,
            quality_grade=quality.quality_grade,
            plan_json=result.plan.model_dump_json(),
            telemetry_json=result.telemetry.model_dump_json(),
            quality_report_json=quality.model_dump_json(),
        )
        self.session.add(job)

        # Create record entities
        for idx, audit in enumerate(result.record_audits):
            record_entity = RecordModel(
                job_id=job_id,
                record_index=idx,
                data_json=json.dumps(audit.coerced_data),
                raw_json=json.dumps(audit.raw_data),
                is_valid=audit.is_valid,
                errors_json=json.dumps(audit.validation_errors),
            )
            self.session.add(record_entity)

        self.session.flush()
        return job

    def get_job(self, job_id: str) -> Optional[JobModel]:
        """Retrieve a single job by its UUID."""
        stmt = select(JobModel).where(JobModel.id == job_id)
        return self.session.execute(stmt).scalar_one_or_none()

    def list_jobs(self, limit: int = 50, offset: int = 0) -> List[JobModel]:
        """List extraction jobs ordered by creation date descending."""
        stmt = (
            select(JobModel)
            .order_by(desc(JobModel.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.execute(stmt).scalars().all())

    def get_job_records(self, job_id: str) -> List[Dict[str, Any]]:
        """Retrieve the list of coerced record dictionaries for a specific job."""
        stmt = (
            select(RecordModel)
            .where(RecordModel.job_id == job_id)
            .order_by(RecordModel.record_index)
        )
        records = self.session.execute(stmt).scalars().all()
        return [json.loads(r.data_json) for r in records]

    def delete_job(self, job_id: str) -> bool:
        """Delete an extraction job and all its associated records (cascade delete)."""
        job = self.get_job(job_id)
        if not job:
            return False
        self.session.delete(job)
        self.session.flush()
        return True

