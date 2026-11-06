"""
Unit tests for SQLAlchemy Storage and JobRepository using in-memory SQLite.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from web_data_forge.models.contracts import (
    DataType,
    ExtractionPlan,
    FieldContract,
    PipelineResult,
    PipelineTelemetry,
    QualityReport,
    RecordAudit,
)
from web_data_forge.quality.evaluator import evaluate_quality
from web_data_forge.storage.database import Base
from web_data_forge.storage.models import JobModel, RecordModel
from web_data_forge.storage.repository import JobRepository


@pytest.fixture
def in_memory_session():
    """Create an isolated in-memory SQLite database session for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()


@pytest.fixture
def sample_result():
    plan = ExtractionPlan(
        target_url="https://example.com/products",
        container_selector=".card",
        fields=[
            FieldContract(name="title", selector="h2", data_type=DataType.STRING, required=True),
            FieldContract(name="price", selector=".price", data_type=DataType.FLOAT, required=False),
        ],
    )
    telemetry = PipelineTelemetry(
        target_url="https://example.com/products",
        resolved_ip="93.184.216.34",
        status_code=200,
        bytes_downloaded=4096,
        latency_seconds=0.25,
        success=True,
    )
    audits = [
        RecordAudit(
            raw_data={"title": "Widget A", "price": "$12.50"},
            coerced_data={"title": "Widget A", "price": 12.50},
            missing_fields=[],
            is_valid=True,
            validation_errors={},
        ),
        RecordAudit(
            raw_data={"title": "Widget B", "price": "$25.00"},
            coerced_data={"title": "Widget B", "price": 25.00},
            missing_fields=[],
            is_valid=True,
            validation_errors={},
        ),
    ]
    quality = QualityReport.calculate(audits, plan.fields)
    return PipelineResult(
        plan=plan,
        telemetry=telemetry,
        records=[a.coerced_data for a in audits],
        record_audits=audits,
        quality_report=quality,
    )


def test_save_and_get_job(in_memory_session, sample_result):
    repo = JobRepository(in_memory_session)
    job = repo.save_job(sample_result)
    in_memory_session.commit()

    assert job.id is not None
    assert job.target_url == "https://example.com/products"
    assert job.total_records == 2
    assert job.valid_records == 2
    assert job.quality_score == 100.0
    assert job.quality_grade == "A"
    assert job.status == "SUCCESS"

    fetched = repo.get_job(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert len(fetched.records) == 2


def test_get_job_records(in_memory_session, sample_result):
    repo = JobRepository(in_memory_session)
    job = repo.save_job(sample_result)
    in_memory_session.commit()

    records = repo.get_job_records(job.id)
    assert len(records) == 2
    assert records[0]["title"] == "Widget A"
    assert records[0]["price"] == 12.50
    assert records[1]["title"] == "Widget B"


def test_list_jobs(in_memory_session, sample_result):
    repo = JobRepository(in_memory_session)
    job1 = repo.save_job(sample_result)
    job2 = repo.save_job(sample_result)
    in_memory_session.commit()

    jobs = repo.list_jobs(limit=10)
    assert len(jobs) == 2
    job_ids = [j.id for j in jobs]
    assert job1.id in job_ids
    assert job2.id in job_ids


def test_delete_job_cascades_records(in_memory_session, sample_result):
    repo = JobRepository(in_memory_session)
    job = repo.save_job(sample_result)
    in_memory_session.commit()

    job_id = job.id
    assert repo.get_job(job_id) is not None
    assert len(repo.get_job_records(job_id)) == 2

    # Delete job
    deleted = repo.delete_job(job_id)
    in_memory_session.commit()

    assert deleted is True
    assert repo.get_job(job_id) is None
    assert len(repo.get_job_records(job_id)) == 0
