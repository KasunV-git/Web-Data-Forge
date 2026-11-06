"""
SQLAlchemy ORM models for job execution tracking and record storage.
"""

from datetime import datetime, timezone
import uuid
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from web_data_forge.storage.database import Base


class JobModel(Base):
    """
    Persistent entity representing an extraction job run,
    including plan snapshot, execution telemetry, and quality evaluation.
    """

    __tablename__ = "extraction_jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    target_url = Column(String(2048), nullable=False)
    status = Column(String(50), nullable=False, default="SUCCESS", index=True)

    total_records = Column(Integer, nullable=False, default=0)
    valid_records = Column(Integer, nullable=False, default=0)
    duplicate_records = Column(Integer, nullable=False, default=0)

    quality_score = Column(Float, nullable=False, default=0.0)
    quality_grade = Column(String(5), nullable=False, default="F")

    # Serialized JSON representations
    plan_json = Column(Text, nullable=False)
    telemetry_json = Column(Text, nullable=False)
    quality_report_json = Column(Text, nullable=False)

    records = relationship(
        "RecordModel",
        back_populates="job",
        cascade="all, delete-orphan",
        order_by="RecordModel.record_index",
    )


class RecordModel(Base):
    """
    Persistent entity representing an individual extracted record within a job.
    """

    __tablename__ = "extracted_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(
        String(36),
        ForeignKey("extraction_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    record_index = Column(Integer, nullable=False)

    data_json = Column(Text, nullable=False)
    raw_json = Column(Text, nullable=False)
    is_valid = Column(Boolean, nullable=False, default=True)
    errors_json = Column(Text, nullable=False, default="{}")

    job = relationship("JobModel", back_populates="records")

