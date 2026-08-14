"""
monitoring_models.py

Milestone 11: SQLAlchemy model for real-time prediction events consumed
from the Redis stream (streaming/consumer.py) into their own
`monitoring` schema - deliberately separate from `staging`/`warehouse`.

These are live inference events from a (simulated) deployed model, not
training-experiment records, so they don't belong in the star schema
built for experiment metadata (Milestones 5-7). A production version of
this platform would eventually aggregate prediction_events into its own
small warehouse (e.g. daily accuracy/latency rollups) the same way
Milestone 5 built one for training runs, but that's future work -
monitoring/drift_detection.py queries this table directly for now.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PredictionEvent(Base):
    """One real-time inference event, as consumed off the Redis stream."""

    __tablename__ = "prediction_events"
    __table_args__ = {"schema": "monitoring"}

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Redis stream entry ID (e.g. "1699999999999-0") - lets us trace any
    # row back to exactly where it came from in the stream, and doubles
    # as a natural dedup key if a batch is ever reprocessed.
    stream_entry_id: Mapped[str] = mapped_column(String(32), nullable=False, unique=True)

    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)

    prediction: Mapped[float] = mapped_column(Float, nullable=False)
    # Ground truth often arrives later than the prediction itself (label
    # lag is normal in production ML) - nullable, filled in by a
    # separate correction event in a real system. Drift detection here
    # only uses `prediction`/`latency_ms`, which are always available
    # immediately, so it isn't blocked on ground truth ever arriving.
    ground_truth: Mapped[float | None] = mapped_column(Float, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)
