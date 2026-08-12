"""
staging_models.py

SQLAlchemy declarative model for the staging layer. This table mirrors
the cleaned CSV output of the ETL pipeline almost 1:1 — it is
deliberately NOT the star schema (that comes in Milestone 5's warehouse
layer). Staging exists as a disposable, re-runnable landing zone: it can
be truncated and reloaded at any time without affecting the modeled
warehouse tables that downstream consumers (SQL analytics, Power BI)
actually query.

A surrogate integer primary key (staging_id) is used in addition to the
natural key (experiment_id) because staging tables should never assume
the natural key is unique across reloads/sources — that's an ETL/staging
best practice, even though in our case experiment_id is already unique.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class StagingExperiment(Base):
    __tablename__ = "experiments"
    __table_args__ = {"schema": "staging"}

    staging_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    experiment_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)
    dataset: Mapped[str] = mapped_column(String(100), nullable=False)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    researcher: Mapped[str] = mapped_column(String(100), nullable=False)
    optimizer: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduler: Mapped[str] = mapped_column(String(50), nullable=False)

    learning_rate: Mapped[float] = mapped_column(Float, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)

    gpu: Mapped[str] = mapped_column(String(100), nullable=False)
    cpu: Mapped[str] = mapped_column(String(100), nullable=False)
    ram_gb: Mapped[float] = mapped_column(Float, nullable=False)

    training_time_sec: Mapped[float] = mapped_column(Float, nullable=False)
    inference_time_ms: Mapped[float] = mapped_column(Float, nullable=False)
    model_size_mb: Mapped[float] = mapped_column(Float, nullable=False)
    energy_consumption_kwh: Mapped[float] = mapped_column(Float, nullable=False)

    accuracy: Mapped[float | None] = mapped_column(Float, nullable=True)
    precision: Mapped[float | None] = mapped_column(Float, nullable=True)
    recall: Mapped[float | None] = mapped_column(Float, nullable=True)
    f1_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    validation_loss: Mapped[float | None] = mapped_column(Float, nullable=True)

    timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)

    # --- Provenance (Milestone 7) ---
    # Nullable/defaulted so this stays compatible with any pre-Milestone-7
    # staging rows; new loads always populate `source` via the ETL layer.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="synthetic")
    mlflow_run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mlflow_experiment_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
