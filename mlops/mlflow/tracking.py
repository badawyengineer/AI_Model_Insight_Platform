"""
tracking.py

Thin wrapper around MLflow so `mlops/experiments/train.py` doesn't need
to know MLflow's API directly, and so tracking setup (URI, experiment
name) is config-driven like every other module in this project.

Also the single source of truth for capturing system/resource metadata
(CPU, RAM, GPU, Python/PyTorch versions) that gets logged as MLflow
tags/params on every run, per Milestone 7's requirements.
"""

from __future__ import annotations

import logging
import os
import platform
import sys
from typing import Any, Dict

import mlflow
import psutil
import torch

logger = logging.getLogger(__name__)


def get_tracking_uri(config: dict) -> str:
    """
    MLFLOW_TRACKING_URI environment variable wins if set (so CI/other
    machines can point at a different tracking server without editing
    config.yaml); otherwise falls back to config["mlops"]["tracking_uri"]
    (defaults to a local `file:./mlruns` store, which needs no server).
    """
    return os.environ.get("MLFLOW_TRACKING_URI") or config["mlops"]["tracking_uri"]


def init_mlflow(config: dict) -> str:
    """Point MLflow at the configured tracking URI/experiment and return the URI used."""
    tracking_uri = get_tracking_uri(config)
    mlflow.set_tracking_uri(tracking_uri)
    mlflow.set_experiment(config["mlops"]["experiment_name"])
    logger.info(
        "MLflow tracking initialized (uri=%s, experiment=%s)",
        tracking_uri,
        config["mlops"]["experiment_name"],
    )
    return tracking_uri


def get_device() -> torch.device:
    """CUDA if available, else CPU. GPU is never required (Milestone 7 rule)."""
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_system_metadata() -> Dict[str, Any]:
    """
    Collect CPU/RAM/GPU/software version info for MLflow logging.

    Every value is best-effort: on a machine where a particular piece of
    info isn't available (e.g. no GPU), that field is set to a clear
    sentinel ("none" / False / 0) rather than raising.
    """
    device = get_device()
    gpu_available = torch.cuda.is_available()

    metadata: Dict[str, Any] = {
        "python_version": sys.version.split()[0],
        "torch_version": torch.__version__,
        "platform": platform.platform(),
        "cpu_name": platform.processor() or platform.machine() or "unknown",
        "cpu_count_logical": psutil.cpu_count(logical=True) or 0,
        "cpu_count_physical": psutil.cpu_count(logical=False) or 0,
        "ram_gb": round(psutil.virtual_memory().total / (1024 ** 3), 2),
        "device": device.type,
        "gpu_available": gpu_available,
        "gpu_name": "none",
        "gpu_utilization_pct": 0.0,
    }

    if gpu_available:
        try:
            metadata["gpu_name"] = torch.cuda.get_device_name(0)
            # torch has no built-in utilization reader; nvidia-smi/pynvml
            # would be needed for a live % figure. Left at 0.0 (documented
            # limitation) rather than faked, per the "don't invent
            # attributions" principle applied to metrics as well.
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read GPU device name: %s", exc)

    return metadata


def log_system_metadata(metadata: Dict[str, Any] | None = None) -> None:
    """Log system metadata as MLflow params (queryable) with a matching tag set."""
    metadata = metadata or get_system_metadata()
    mlflow.log_params({f"sys_{k}": v for k, v in metadata.items()})
    mlflow.set_tags({f"sys_{k}": str(v) for k, v in metadata.items()})
