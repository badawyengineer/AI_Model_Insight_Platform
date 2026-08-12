"""
test_etl_mlflow_integration.py

Tests etl/run_etl.py's Milestone 7 extension: merging an extra raw
source (MLflow-extracted records) in alongside the synthetic
generator's output, via `run_etl(extra_sources=[...])`. Confirms:
  - default behavior (no extra_sources) is unchanged from Milestone 1-6
  - both sources merge, validate, and clean together through the
    *same* unmodified validate/clean stages
  - a missing extra source file is skipped with a warning, not a crash
    (important since a fresh clone won't have mlflow_runs_raw.json yet)
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from etl.run_etl import run_etl


def _write_json(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, default=str)


def _synthetic_record(experiment_id: str) -> dict:
    return {
        "experiment_id": experiment_id,
        "model_name": "resnet50",
        "dataset": "imagenet_subset",
        "framework": "PyTorch",
        "researcher": "Abdelrahman",
        "optimizer": "Adam",
        "scheduler": "CosineAnnealing",
        "learning_rate": 0.001,
        "batch_size": 32,
        "epochs": 10,
        "gpu": "RTX 3090",
        "cpu": "i9-12900K",
        "ram_gb": 32.0,
        "training_time_sec": 3600.5,
        "inference_time_ms": 12.3,
        "model_size_mb": 98.4,
        "energy_consumption_kwh": 1.2,
        "accuracy": 0.94,
        "precision": 0.92,
        "recall": 0.91,
        "f1_score": 0.915,
        "loss": 0.08,
        "validation_loss": 0.11,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "success",
    }


def _mlflow_record(run_id: str) -> dict:
    record = _synthetic_record(f"mlflow_{run_id}")
    record.update(
        {
            "source": "mlflow",
            "mlflow_run_id": run_id,
            "mlflow_experiment_name": "ai-model-insight-platform",
        }
    )
    return record


def test_run_etl_merges_extra_sources(tmp_path, monkeypatch):
    synthetic_path = tmp_path / "synthetic_raw.json"
    mlflow_path = tmp_path / "mlflow_raw.json"
    clean_path = tmp_path / "clean.csv"

    _write_json(synthetic_path, [_synthetic_record("exp_00001"), _synthetic_record("exp_00002")])
    _write_json(mlflow_path, [_mlflow_record("run_aaa"), _mlflow_record("run_bbb")])

    fake_config = {
        "generator": {"output_path": str(synthetic_path)},
        "etl": {"clean_output_path": str(clean_path), "missing_value_strategy": "median"},
        "logging": {"level": "INFO", "log_file": str(tmp_path / "pipeline.log")},
    }
    monkeypatch.setattr("etl.run_etl.load_config", lambda: fake_config)

    run_etl(extra_sources=[mlflow_path])

    import pandas as pd

    result = pd.read_csv(clean_path)
    assert len(result) == 4
    assert set(result["source"]) == {"synthetic", "mlflow"}
    assert (result["source"] == "mlflow").sum() == 2


def test_run_etl_default_behavior_unchanged_without_extra_sources(tmp_path, monkeypatch):
    """No extra_sources -> exact Milestone 1-6 behavior (synthetic only)."""
    synthetic_path = tmp_path / "synthetic_raw.json"
    clean_path = tmp_path / "clean.csv"
    _write_json(synthetic_path, [_synthetic_record("exp_00001")])

    fake_config = {
        "generator": {"output_path": str(synthetic_path)},
        "etl": {"clean_output_path": str(clean_path), "missing_value_strategy": "median"},
        "logging": {"level": "INFO", "log_file": str(tmp_path / "pipeline.log")},
    }
    monkeypatch.setattr("etl.run_etl.load_config", lambda: fake_config)

    run_etl()  # no extra_sources argument at all

    import pandas as pd

    result = pd.read_csv(clean_path)
    assert len(result) == 1
    assert result.iloc[0]["source"] == "synthetic"


def test_run_etl_skips_missing_extra_source_gracefully(tmp_path, monkeypatch):
    synthetic_path = tmp_path / "synthetic_raw.json"
    clean_path = tmp_path / "clean.csv"
    missing_mlflow_path = tmp_path / "does_not_exist.json"
    _write_json(synthetic_path, [_synthetic_record("exp_00001")])

    fake_config = {
        "generator": {"output_path": str(synthetic_path)},
        "etl": {"clean_output_path": str(clean_path), "missing_value_strategy": "median"},
        "logging": {"level": "INFO", "log_file": str(tmp_path / "pipeline.log")},
    }
    monkeypatch.setattr("etl.run_etl.load_config", lambda: fake_config)

    run_etl(extra_sources=[missing_mlflow_path])  # should not raise

    import pandas as pd

    result = pd.read_csv(clean_path)
    assert len(result) == 1
