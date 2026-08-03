import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, UniqueConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import Base


def utcnow():
    return datetime.now(timezone.utc)


class IngestionRun(Base):
    """One execution of `source + endpoint`. Kept so /runs gives operators
    visibility into what happened, and so future runs have something to
    reconcile against (e.g. incremental/watermark strategies)."""

    __tablename__ = "ingestion_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String, nullable=False, index=True)
    endpoint_name = Column(String, nullable=False, index=True)
    status = Column(String, nullable=False, default="running")  # running|success|failed
    started_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at = Column(DateTime(timezone=True), nullable=True)
    pages_fetched = Column(Integer, default=0, nullable=False)
    records_ingested = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)


class RawRecord(Base):
    """Every ingested record is stored as-is (schema-less JSONB), keyed by
    (source, endpoint, external_id). This is what makes the store generic:
    the service never needs to know a source's shape ahead of time, and
    reruns upsert instead of duplicating rows. See README for the tradeoffs
    this implies (no per-source query-ability without a downstream step)."""

    __tablename__ = "raw_records"
    __table_args__ = (
        UniqueConstraint("source_name", "endpoint_name", "external_id", name="uq_raw_record_identity"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_name = Column(String, nullable=False, index=True)
    endpoint_name = Column(String, nullable=False, index=True)
    external_id = Column(String, nullable=False, index=True)
    payload = Column(JSONB, nullable=False)
    run_id = Column(UUID(as_uuid=True), ForeignKey("ingestion_runs.id"), nullable=True)
    fetched_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
