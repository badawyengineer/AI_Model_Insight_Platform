"""
test_ml_config.py

Unit tests for Milestone 7's experiment configuration: config.yaml's
new `mlops` section, and every YAML file under
mlops/experiments/configs/. No GPU, no DB, no network required.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from config.config_loader import load_config

REQUIRED_EXPERIMENT_KEYS = {
    "name",
    "learning_rate",
    "batch_size",
    "epochs",
    "optimizer",
    "scheduler",
    "random_seed",
}
VALID_OPTIMIZERS = {"Adam", "AdamW", "SGD", "RMSprop"}
VALID_SCHEDULERS = {"CosineAnnealing", "StepLR", "OneCycle", "Constant"}


def test_config_has_mlops_section():
    config = load_config()
    assert "mlops" in config
    for key in (
        "tracking_uri",
        "experiment_name",
        "mlflow_raw_output_path",
        "configs_dir",
        "data_dir",
        "researcher",
    ):
        assert key in config["mlops"], f"config['mlops'] missing '{key}'"


def _experiment_config_files() -> list[Path]:
    config = load_config()
    configs_dir = Path(config["mlops"]["configs_dir"])
    files = sorted(configs_dir.glob("*.yaml"))
    assert files, f"No experiment config YAML files found under {configs_dir}"
    return files


@pytest.mark.parametrize("config_path", _experiment_config_files())
def test_experiment_config_is_well_formed(config_path: Path):
    with open(config_path, "r", encoding="utf-8") as f:
        exp_config = yaml.safe_load(f)

    missing = REQUIRED_EXPERIMENT_KEYS - exp_config.keys()
    assert not missing, f"{config_path.name} missing keys: {missing}"

    assert exp_config["optimizer"] in VALID_OPTIMIZERS, (
        f"{config_path.name}: optimizer '{exp_config['optimizer']}' not in {VALID_OPTIMIZERS} "
        "(must match database.schemas.ExperimentRecord's Literal)"
    )
    assert exp_config["scheduler"] in VALID_SCHEDULERS, (
        f"{config_path.name}: scheduler '{exp_config['scheduler']}' not in {VALID_SCHEDULERS} "
        "(must match database.schemas.ExperimentRecord's Literal)"
    )
    assert 0 < exp_config["learning_rate"] < 1
    assert exp_config["batch_size"] > 0
    assert exp_config["epochs"] > 0


def test_at_least_five_experiment_configs_exist():
    """Milestone 7 acceptance criteria: at least 5 reproducible experiments."""
    assert len(_experiment_config_files()) >= 5
