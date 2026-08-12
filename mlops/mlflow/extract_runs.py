"""
extract_runs.py

Milestone 7's bridge between MLflow and the existing data platform.

Reads every run in the configured MLflow experiment via the MLflow
tracking client and converts each one into a dict shaped exactly like
`database.schemas.ExperimentRecord` — the same shape the Milestone 2
synthetic generator produces. That dict is written to
`raw_data/mlflow_runs_raw.json` in the same format
(`generator.generate_experiments.write_records` uses), so the existing
`etl.extract_raw_records` / `etl.validate_records` / `etl.clean_records`
stages work on it completely unmodified — this deliberately does NOT
create a second/parallel ETL pipeline.

Usage:
    python -m mlops.mlflow.extract_runs
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

import mlflow
from mlflow.entities import Run, ViewType
from mlflow.tracking import MlflowClient

from config.config_loader import load_config
from mlops.mlflow.tracking import get_tracking_uri

logger = logging.getLogger(__name__)

# MLflow run status -> ExperimentStatus (database/schemas.py). MLflow's
# FINISHED maps to our "success"; everything else lines up directly or
# falls back to "running" for statuses our schema doesn't model (SCHEDULED).
_STATUS_MAP = {
    "FINISHED": "success",
    "FAILED": "failed",
    "KILLED": "killed",
    "RUNNING": "running",
    "SCHEDULED": "running",
}


def _param(run: Run, key: str, default: Any = None) -> Any:
    return run.data.params.get(key, default)


def _metric(run: Run, key: str, default: float = 0.0) -> float:
    value = run.data.metrics.get(key)
    return float(value) if value is not None else default


def run_to_experiment_record(run: Run, experiment_name: str) -> Dict[str, Any]:
    """Map one MLflow Run to an ExperimentRecord-shaped dict."""
    start_time = (
        datetime.fromtimestamp(run.info.start_time / 1000, tz=timezone.utc)
        if run.info.start_time
        else datetime.now(tz=timezone.utc)
    )
    status = _STATUS_MAP.get(run.info.status, "running")

    # Metrics for RUNNING/KILLED runs may genuinely be absent (matches the
    # Optional-metrics design already documented in database/schemas.py).
    has_metrics = status in ("success", "failed")

    record: Dict[str, Any] = {
        "experiment_id": f"mlflow_{run.info.run_id[:16]}",
        "model_name": _param(run, "model_name", "unknown_model"),
        "dataset": _param(run, "dataset", "unknown_dataset"),
        "framework": _param(run, "framework", "PyTorch"),
        "researcher": _param(run, "researcher", "unknown"),
        "optimizer": _param(run, "optimizer", "Adam"),
        "scheduler": _param(run, "scheduler", "Constant"),
        "learning_rate": float(_param(run, "learning_rate", 0.001)),
        "batch_size": int(float(_param(run, "batch_size", 32))),
        "epochs": int(float(_param(run, "epochs", 1))),
        "gpu": _param(run, "sys_gpu_name", "none"),
        "cpu": _param(run, "sys_cpu_name", "unknown"),
        "ram_gb": float(_param(run, "sys_ram_gb", 0.0)),
        "training_time_sec": _metric(run, "training_duration_sec", 0.0) or 0.001,
        "inference_time_ms": _metric(run, "inference_latency_ms", 0.0) or 0.001,
        "model_size_mb": _metric(run, "model_size_mb", 0.0) or 0.001,
        # Energy draw isn't measured for CPU-only runs in this milestone
        # (no power-metering hardware access) - left at 0.0 rather than
        # estimated, consistent with "don't invent metrics we didn't measure."
        "energy_consumption_kwh": 0.0,
        "accuracy": _metric(run, "accuracy") if has_metrics else None,
        "precision": _metric(run, "precision") if has_metrics else None,
        "recall": _metric(run, "recall") if has_metrics else None,
        "f1_score": _metric(run, "f1") if has_metrics else None,
        "loss": _metric(run, "training_loss") if has_metrics else None,
        "validation_loss": _metric(run, "validation_loss") if has_metrics else None,
        "timestamp": start_time.isoformat(),
        "status": status,
        "source": "mlflow",
        "mlflow_run_id": run.info.run_id,
        "mlflow_experiment_name": experiment_name,
    }
    return record


def extract_runs(config: dict) -> List[Dict[str, Any]]:
    """Fetch every run in the configured MLflow experiment as ExperimentRecord dicts."""
    mlflow.set_tracking_uri(get_tracking_uri(config))
    client = MlflowClient()

    experiment_name = config["mlops"]["experiment_name"]
    experiment = client.get_experiment_by_name(experiment_name)
    if experiment is None:
        logger.warning(
            "No MLflow experiment named '%s' found - has any training run "
            "been executed yet? Returning an empty list.",
            experiment_name,
        )
        return []

    runs = client.search_runs(
        experiment_ids=[experiment.experiment_id],
        run_view_type=ViewType.ALL,
    )
    logger.info("Found %d MLflow run(s) in experiment '%s'", len(runs), experiment_name)

    return [run_to_experiment_record(r, experiment_name) for r in runs]


def write_records(records: List[Dict[str, Any]], output_path: str) -> None:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)
    logger.info("Wrote %d MLflow run records to %s", len(records), out_path)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    config = load_config()
    records = extract_runs(config)
    write_records(records, config["mlops"]["mlflow_raw_output_path"])


if __name__ == "__main__":
    main()
