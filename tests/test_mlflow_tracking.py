"""
test_mlflow_tracking.py

Unit tests for mlops/mlflow/tracking.py: system metadata capture and
tracking-URI resolution. No GPU or network required.
"""

from __future__ import annotations

import torch

from mlops.mlflow.tracking import get_device, get_system_metadata, get_tracking_uri


def test_get_device_never_requires_gpu():
    device = get_device()
    assert device.type in ("cpu", "cuda")
    if not torch.cuda.is_available():
        assert device.type == "cpu"


def test_get_system_metadata_has_required_fields():
    metadata = get_system_metadata()
    required = {
        "python_version",
        "torch_version",
        "platform",
        "cpu_name",
        "cpu_count_logical",
        "ram_gb",
        "device",
        "gpu_available",
        "gpu_name",
    }
    assert required.issubset(metadata.keys())
    assert metadata["ram_gb"] > 0
    assert isinstance(metadata["gpu_available"], bool)
    if not metadata["gpu_available"]:
        assert metadata["gpu_name"] == "none"


def test_get_tracking_uri_env_var_overrides_config(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "sqlite:///env_override.db")
    config = {"mlops": {"tracking_uri": "sqlite:///config_default.db"}}
    assert get_tracking_uri(config) == "sqlite:///env_override.db"


def test_get_tracking_uri_falls_back_to_config(monkeypatch):
    monkeypatch.delenv("MLFLOW_TRACKING_URI", raising=False)
    config = {"mlops": {"tracking_uri": "sqlite:///config_default.db"}}
    assert get_tracking_uri(config) == "sqlite:///config_default.db"
