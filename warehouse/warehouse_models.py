"""
warehouse_models.py

SQLAlchemy declarative models for the star schema data warehouse.
Grain of FactTrainingRun: one row per training experiment.

Dimension design notes:
  - DimFramework bundles framework + optimizer + scheduler into a single
    dimension (rather than 3 separate tables) because these attributes
    are always chosen together per run — this is intentional
    denormalization to avoid an overly "snowflaked" schema, not an
    oversight.
  - DimHardware similarly bundles gpu + cpu + ram_gb into one hardware
    "profile" dimension for the same reason.
  - DimExperiment holds the hyperparameters that are properties of the
    experiment itself (learning_rate, batch_size, epochs) plus the
    natural key (experiment_id).
  - DimDate is a fully pre-populated calendar table (not just dates that
    appear in the data), which is standard data warehouse practice and
    supports date-range filtering in Power BI even for dates with no
    experiments yet.

All surrogate keys are auto-incrementing integers, per warehouse best
practice — dimension natural keys (model_name, dataset_name, etc.) are
never used directly as join keys in the fact table.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

SCHEMA = "warehouse"


class Base(DeclarativeBase):
    pass


class DimModel(Base):
    __tablename__ = "dim_model"
    __table_args__ = ({"schema": SCHEMA},)

    model_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class DimDataset(Base):
    __tablename__ = "dim_dataset"
    __table_args__ = ({"schema": SCHEMA},)

    dataset_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dataset_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class DimHardware(Base):
    __tablename__ = "dim_hardware"
    __table_args__ = (
        UniqueConstraint("gpu", "cpu", "ram_gb", name="uq_hardware_profile"),
        {"schema": SCHEMA},
    )

    hardware_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gpu: Mapped[str] = mapped_column(String(100), nullable=False)
    cpu: Mapped[str] = mapped_column(String(100), nullable=False)
    ram_gb: Mapped[float] = mapped_column(Float, nullable=False)


class DimFramework(Base):
    __tablename__ = "dim_framework"
    __table_args__ = (
        UniqueConstraint("framework", "optimizer", "scheduler", name="uq_framework_profile"),
        {"schema": SCHEMA},
    )

    framework_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    framework: Mapped[str] = mapped_column(String(50), nullable=False)
    optimizer: Mapped[str] = mapped_column(String(50), nullable=False)
    scheduler: Mapped[str] = mapped_column(String(50), nullable=False)


class DimResearcher(Base):
    __tablename__ = "dim_researcher"
    __table_args__ = ({"schema": SCHEMA},)

    researcher_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    researcher_name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)


class DimExperiment(Base):
    __tablename__ = "dim_experiment"
    __table_args__ = ({"schema": SCHEMA},)

    experiment_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    experiment_id: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    learning_rate: Mapped[float] = mapped_column(Float, nullable=False)
    batch_size: Mapped[int] = mapped_column(Integer, nullable=False)
    epochs: Mapped[int] = mapped_column(Integer, nullable=False)


class DimDate(Base):
    __tablename__ = "dim_date"
    __table_args__ = ({"schema": SCHEMA},)

    # date_key format: YYYYMMDD as integer, standard DW convention
    date_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    full_date: Mapped[date] = mapped_column(Date, nullable=False, unique=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    quarter: Mapped[int] = mapped_column(Integer, nullable=False)
    month: Mapped[int] = mapped_column(Integer, nullable=False)
    month_name: Mapped[str] = mapped_column(String(20), nullable=False)
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday
    day_name: Mapped[str] = mapped_column(String(20), nullable=False)
    is_weekend: Mapped[bool] = mapped_column(Boolean, nullable=False)


class FactTrainingRun(Base):
    __tablename__ = "fact_training_run"
    __table_args__ = ({"schema": SCHEMA},)

    fact_key: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    experiment_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_experiment.experiment_key"), nullable=False
    )
    model_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_model.model_key"), nullable=False
    )
    dataset_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_dataset.dataset_key"), nullable=False
    )
    hardware_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_hardware.hardware_key"), nullable=False
    )
    framework_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_framework.framework_key"), nullable=False
    )
    researcher_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_researcher.researcher_key"), nullable=False
    )
    date_key: Mapped[int] = mapped_column(
        ForeignKey(f"{SCHEMA}.dim_date.date_key"), nullable=False
    )

    # Measures
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
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    run_timestamp: Mapped[datetime] = mapped_column(DateTime, nullable=False)
