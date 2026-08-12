"""
test_schema_compatibility.py

Confirms the Milestone 7 schema extension (source / mlflow_run_id /
mlflow_experiment_name on ExperimentRecord) is purely additive:
  - old-style records (no provenance fields, exactly what Milestone 2's
    generator has always produced) still validate, defaulting to
    source="synthetic"
  - new mlflow-shaped records validate too
This directly backs the "schema compatibility" and "existing warehouse
architecture remains intact" acceptance criteria.
"""

from __future__ import annotations

from datetime import datetime

from database.schemas import ExperimentRecord, ExperimentStatus

_BASE_KWARGS = dict(
    experiment_id="exp_00001",
    model_name="resnet50",
    dataset="imagenet_subset",
    framework="PyTorch",
    researcher="Abdelrahman",
    optimizer="Adam",
    scheduler="CosineAnnealing",
    learning_rate=0.001,
    batch_size=32,
    epochs=10,
    gpu="RTX 3090",
    cpu="i9-12900K",
    ram_gb=32.0,
    training_time_sec=3600.5,
    inference_time_ms=12.3,
    model_size_mb=98.4,
    energy_consumption_kwh=1.2,
    accuracy=0.94,
    precision=0.92,
    recall=0.91,
    f1_score=0.915,
    loss=0.08,
    validation_loss=0.11,
    timestamp=datetime.now(),
    status=ExperimentStatus.SUCCESS,
)


def test_pre_milestone_7_record_still_validates_and_defaults_source():
    """A record shaped exactly like Milestone 2's generator output (no provenance fields)."""
    record = ExperimentRecord(**_BASE_KWARGS)
    assert record.source == "synthetic"
    assert record.mlflow_run_id is None
    assert record.mlflow_experiment_name is None


def test_mlflow_shaped_record_validates():
    record = ExperimentRecord(
        **_BASE_KWARGS,
        source="mlflow",
        mlflow_run_id="a" * 32,
        mlflow_experiment_name="ai-model-insight-platform",
    )
    assert record.source == "mlflow"
    assert record.mlflow_run_id == "a" * 32


def test_serialized_record_round_trips_through_json():
    """Same round trip the generator/ETL relies on (model_dump_json -> ExperimentRecord)."""
    import json

    record = ExperimentRecord(**_BASE_KWARGS)
    payload = json.loads(record.model_dump_json())
    rebuilt = ExperimentRecord(**payload)
    assert rebuilt == record
