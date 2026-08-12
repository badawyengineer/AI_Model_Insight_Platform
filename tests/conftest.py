"""
conftest.py

Shared fixtures for the Milestone 7 test suite. All tests here run on
CPU with tiny data subsets and use an isolated per-test MLflow tracking
store (sqlite file in tmp_path) so they never touch or pollute the
project's real mlflow.db / mlruns.
"""

from __future__ import annotations

import copy

import pytest

from config.config_loader import load_config


@pytest.fixture
def tiny_experiment_config() -> dict:
    """A minimal, fast experiment config: tiny subsets, 1 epoch, small model."""
    return {
        "name": "pytest_tiny_run",
        "model_name": "SimpleCNN",
        "learning_rate": 0.001,
        "batch_size": 8,
        "epochs": 1,
        "optimizer": "Adam",
        "scheduler": "Constant",
        "base_channels": 4,
        "dropout": 0.1,
        "random_seed": 42,
        "train_subset_size": 32,
        "val_subset_size": 16,
    }


@pytest.fixture
def isolated_project_config(tmp_path) -> dict:
    """
    A real config.yaml, deep-copied and pointed at tmp_path for
    everything MLflow/data/output related, so tests never touch the
    repo's real mlflow.db, mlruns, or raw_data files.
    """
    config = copy.deepcopy(load_config())
    config["mlops"]["tracking_uri"] = f"sqlite:///{tmp_path / 'test_mlflow.db'}"
    config["mlops"]["experiment_name"] = "pytest-experiment"
    config["mlops"]["data_dir"] = str(tmp_path / "torch_datasets")
    config["mlops"]["mlflow_raw_output_path"] = str(tmp_path / "mlflow_runs_raw.json")
    return config
