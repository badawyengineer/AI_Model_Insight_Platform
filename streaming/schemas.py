"""
streaming/schemas.py

Milestone 11: the shape of one real-time prediction event, published to
the Redis stream by streaming/producer.py and consumed into
database.monitoring_models.PredictionEvent by streaming/consumer.py.

Deliberately much smaller than database.schemas.ExperimentRecord - a
live inference event carries only what a model-serving layer would
actually know at request time (not hyperparameters, not final metrics).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PredictionEvent(BaseModel):
    model_name: str
    model_version: str
    prediction: float
    ground_truth: float | None = None
    latency_ms: float = Field(ge=0)
    event_timestamp: datetime
