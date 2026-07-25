"""
schemas.py

Single source of truth for the shape of an AI training experiment record.
This Pydantic model is used by:
  - the synthetic data generator (to emit valid records)
  - the ETL layer (to validate/clean raw records)
  - documentation (as the canonical field reference)

Design note on Optional metrics:
Experiments with status RUNNING or KILLED may not have final metrics yet
(mirrors real experiment trackers like MLflow / Weights & Biases). All
metric fields are therefore Optional. SUCCESS/FAILED runs are expected to
have metrics populated; the ETL validation layer (Milestone 3) will flag
SUCCESS records with missing metrics as data quality issues rather than
silently accepting them.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ExperimentStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    RUNNING = "running"
    KILLED = "killed"


class ExperimentRecord(BaseModel):
    # --- Identity ---
    experiment_id: str
    model_name: str
    dataset: str
    framework: Literal["PyTorch", "TensorFlow", "JAX"]
    researcher: str

    # --- Hyperparameters ---
    optimizer: Literal["Adam", "AdamW", "SGD", "RMSprop"]
    scheduler: Literal["CosineAnnealing", "StepLR", "OneCycle", "Constant"]
    learning_rate: float = Field(gt=0, lt=1)
    batch_size: int = Field(gt=0)
    epochs: int = Field(gt=0)

    # --- Hardware ---
    gpu: str
    cpu: str
    ram_gb: float = Field(gt=0)

    # --- Performance / cost ---
    training_time_sec: float = Field(gt=0)
    inference_time_ms: float = Field(gt=0)
    model_size_mb: float = Field(gt=0)
    energy_consumption_kwh: float = Field(ge=0)

    # --- Metrics (Optional: see module docstring) ---
    accuracy: Optional[float] = Field(default=None, ge=0, le=1)
    precision: Optional[float] = Field(default=None, ge=0, le=1)
    recall: Optional[float] = Field(default=None, ge=0, le=1)
    f1_score: Optional[float] = Field(default=None, ge=0, le=1)
    loss: Optional[float] = Field(default=None, ge=0)
    validation_loss: Optional[float] = Field(default=None, ge=0)

    # --- Metadata ---
    timestamp: datetime
    status: ExperimentStatus
