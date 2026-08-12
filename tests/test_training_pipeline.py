"""
test_training_pipeline.py

Exercises the real training loop (mlops/experiments/train.py) end to
end on a tiny config, against an isolated tmp MLflow store. No GPU
required; no network required (data.py falls back to a same-shaped
synthetic dataset automatically if CIFAR-10 can't be downloaded).
"""

from __future__ import annotations

import mlflow
from mlflow.tracking import MlflowClient

from mlops.experiments.train import set_seed, train_one_config
from mlops.mlflow.tracking import init_mlflow


def test_set_seed_is_reproducible():
    import random

    set_seed(123)
    a = [random.random() for _ in range(5)]
    set_seed(123)
    b = [random.random() for _ in range(5)]
    assert a == b


def test_train_one_config_runs_and_logs_to_mlflow(tiny_experiment_config, isolated_project_config):
    init_mlflow(isolated_project_config)

    run_id = train_one_config(tiny_experiment_config, isolated_project_config)
    assert run_id

    client = MlflowClient()
    run = client.get_run(run_id)

    # Required params (Milestone 7 spec section 3)
    for param in ("learning_rate", "batch_size", "epochs", "optimizer", "model_name", "dataset", "random_seed"):
        assert param in run.data.params, f"missing logged param: {param}"

    # Required metrics
    for metric in ("training_loss", "validation_loss", "accuracy", "precision", "recall", "f1"):
        assert metric in run.data.metrics, f"missing logged metric: {metric}"
    for metric in ("training_duration_sec", "inference_latency_ms", "model_size_mb"):
        assert metric in run.data.metrics, f"missing logged metric: {metric}"

    # System/resource metadata
    for param in ("sys_python_version", "sys_torch_version", "sys_device", "sys_cpu_name", "sys_ram_gb"):
        assert param in run.data.params, f"missing system metadata param: {param}"

    # Artifacts: checkpoint, config, metrics
    artifact_paths = {a.path for a in client.list_artifacts(run_id)}
    assert "checkpoint" in artifact_paths
    assert "config" in artifact_paths
    assert "metrics" in artifact_paths

    assert run.info.status == "FINISHED"


def test_training_metrics_are_in_valid_ranges(tiny_experiment_config, isolated_project_config):
    init_mlflow(isolated_project_config)
    run_id = train_one_config(tiny_experiment_config, isolated_project_config)

    client = MlflowClient()
    run = client.get_run(run_id)

    assert 0.0 <= run.data.metrics["accuracy"] <= 1.0
    assert 0.0 <= run.data.metrics["precision"] <= 1.0
    assert 0.0 <= run.data.metrics["recall"] <= 1.0
    assert 0.0 <= run.data.metrics["f1"] <= 1.0
    assert run.data.metrics["training_loss"] >= 0.0
    assert run.data.metrics["training_duration_sec"] > 0.0
