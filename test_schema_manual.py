"""
Quick manual sanity check for Milestone 1 — NOT the real test suite.
Run with: python test_schema_manual.py

This just proves:
  1. A valid experiment record passes validation.
  2. An invalid one (bad accuracy, bad framework) is correctly rejected.

Real unit tests (pytest, in tests/) come in a later milestone.
"""

from datetime import datetime
from pydantic import ValidationError

from database.schemas import ExperimentRecord, ExperimentStatus


def test_valid_record():
    record = ExperimentRecord(
        experiment_id="exp_0001",
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
    print("VALID RECORD PASSED:")
    print(record.model_dump())


def test_invalid_record():
    try:
        ExperimentRecord(
            experiment_id="exp_0002",
            model_name="resnet50",
            dataset="imagenet_subset",
            framework="Keras",  # invalid: not in Literal["PyTorch","TensorFlow","JAX"]
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
            accuracy=1.5,  # invalid: must be <= 1
            timestamp=datetime.now(),
            status=ExperimentStatus.SUCCESS,
        )
        print("ERROR: invalid record should have failed but didn't!")
    except ValidationError as e:
        print("INVALID RECORD CORRECTLY REJECTED:")
        print(e)


if __name__ == "__main__":
    test_valid_record()
    print("\n" + "=" * 60 + "\n")
    test_invalid_record()
