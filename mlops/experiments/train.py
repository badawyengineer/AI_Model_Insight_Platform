"""
train.py

Milestone 7's real ML training workload: a small CNN trained on
CIFAR-10 (or a same-shaped fallback dataset — see data.py) with
PyTorch, fully config-driven, and tracked end-to-end in MLflow.

Usage:
    python -m mlops.experiments.train --config mlops/experiments/configs/exp01_baseline.yaml
    python -m mlops.experiments.train --config mlops/experiments/configs/exp01_baseline.yaml --epochs 1  # override

Every run:
  - sets Python/NumPy/PyTorch seeds from the config (reproducible)
  - logs all hyperparameters as MLflow params
  - logs per-epoch + final metrics (loss, val loss, accuracy, precision,
    recall, F1, training duration, inference latency)
  - logs system/resource metadata (CPU, RAM, GPU, versions)
  - logs artifacts: model checkpoint, a copy of the config, a metrics
    JSON summary, and (if matplotlib is available) a training-curve PNG
  - works on CPU; CUDA is used opportunistically, never required
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict

import mlflow
import numpy as np
import torch
import yaml
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # repo root, for sibling imports

from config.config_loader import load_config
from mlops.experiments.data import get_dataloaders
from mlops.experiments.metrics import macro_precision_recall_f1
from mlops.experiments.model import SimpleCNN, model_size_mb
from mlops.mlflow.tracking import get_device, get_system_metadata, init_mlflow

logger = logging.getLogger(__name__)


def set_seed(seed: int) -> None:
    """Seed Python, NumPy, and PyTorch (CPU + CUDA) for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def build_optimizer(name: str, params, learning_rate: float) -> torch.optim.Optimizer:
    optimizers = {
        "Adam": torch.optim.Adam,
        "AdamW": torch.optim.AdamW,
        "SGD": lambda p, lr: torch.optim.SGD(p, lr=lr, momentum=0.9),
        "RMSprop": torch.optim.RMSprop,
    }
    if name not in optimizers:
        raise ValueError(f"Unknown optimizer '{name}'. Expected one of {list(optimizers)}.")
    return optimizers[name](params, lr=learning_rate)


def build_scheduler(name: str, optimizer: torch.optim.Optimizer, epochs: int):
    if name == "CosineAnnealing":
        return torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(epochs, 1))
    if name == "StepLR":
        return torch.optim.lr_scheduler.StepLR(optimizer, step_size=max(epochs // 2, 1), gamma=0.5)
    if name == "OneCycle":
        return None  # constructed lazily once steps_per_epoch is known; see train_one_config
    if name == "Constant":
        return None
    raise ValueError(f"Unknown scheduler '{name}'.")


def run_epoch(
    model: nn.Module,
    loader,
    device: torch.device,
    criterion,
    optimizer: torch.optim.Optimizer | None = None,
    scheduler=None,
) -> tuple[float, float, float, float, float]:
    """One pass over `loader`. If optimizer is given, trains; else evaluates.

    Returns: (avg_loss, accuracy, precision, recall, f1)
    """
    is_train = optimizer is not None
    model.train(is_train)

    total_loss = 0.0
    all_preds, all_targets = [], []

    with torch.set_grad_enabled(is_train):
        for images, labels in loader:
            images, labels = images.to(device), labels.to(device)

            if is_train:
                optimizer.zero_grad()

            outputs = model(images)
            loss = criterion(outputs, labels)

            if is_train:
                loss.backward()
                optimizer.step()
                if scheduler is not None:
                    scheduler.step()

            total_loss += loss.item() * images.size(0)
            preds = outputs.argmax(dim=1)
            all_preds.append(preds.cpu())
            all_targets.append(labels.cpu())

    all_preds = torch.cat(all_preds)
    all_targets = torch.cat(all_targets)
    accuracy = float((all_preds == all_targets).float().mean())
    precision, recall, f1 = macro_precision_recall_f1(all_targets, all_preds, num_classes=10)
    avg_loss = total_loss / len(loader.dataset)

    return avg_loss, accuracy, precision, recall, f1


def measure_inference_latency_ms(model: nn.Module, loader, device: torch.device) -> float:
    """Average per-batch inference latency in milliseconds, over a few warm batches."""
    model.eval()
    batch = next(iter(loader))[0].to(device)
    # warm-up (first call pays init cost, especially on CPU)
    with torch.no_grad():
        model(batch)

    n_reps = 5
    start = time.perf_counter()
    with torch.no_grad():
        for _ in range(n_reps):
            model(batch)
    elapsed_ms = (time.perf_counter() - start) * 1000 / n_reps
    return elapsed_ms


def maybe_log_training_curve(history: Dict[str, list], out_dir: Path) -> Path | None:
    """Save a training-curve PNG via matplotlib if it's installed; skip gracefully if not."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        logger.info("matplotlib not installed - skipping training curve artifact")
        return None

    fig, ax = plt.subplots()
    ax.plot(history["train_loss"], label="train_loss")
    ax.plot(history["val_loss"], label="val_loss")
    ax.set_xlabel("epoch")
    ax.set_ylabel("loss")
    ax.legend()
    ax.set_title("Training curve")

    out_path = out_dir / "training_curve.png"
    fig.savefig(out_path)
    plt.close(fig)
    return out_path


def train_one_config(exp_config: Dict[str, Any], project_config: Dict[str, Any]) -> str:
    """
    Run one full training experiment described by `exp_config` and log it
    to MLflow. Returns the MLflow run_id.
    """
    seed = exp_config.get("random_seed", 42)
    set_seed(seed)

    device = get_device()
    mlops_cfg = project_config["mlops"]

    train_loader, val_loader, dataset_name, num_classes = get_dataloaders(
        data_dir=mlops_cfg["data_dir"],
        batch_size=exp_config["batch_size"],
        seed=seed,
        train_subset_size=exp_config.get("train_subset_size"),
        val_subset_size=exp_config.get("val_subset_size"),
    )

    model = SimpleCNN(
        num_classes=num_classes,
        base_channels=exp_config.get("base_channels", 32),
        dropout=exp_config.get("dropout", 0.25),
    ).to(device)

    optimizer = build_optimizer(exp_config["optimizer"], model.parameters(), exp_config["learning_rate"])
    scheduler_name = exp_config.get("scheduler", "Constant")
    epochs = exp_config["epochs"]

    if scheduler_name == "OneCycle":
        scheduler = torch.optim.lr_scheduler.OneCycleLR(
            optimizer,
            max_lr=exp_config["learning_rate"],
            steps_per_epoch=len(train_loader),
            epochs=epochs,
        )
    else:
        scheduler = build_scheduler(scheduler_name, optimizer, epochs)

    criterion = nn.CrossEntropyLoss()

    with mlflow.start_run(run_name=exp_config["name"]) as run:
        mlflow.log_params(
            {
                "model_name": exp_config.get("model_name", "SimpleCNN"),
                "dataset": dataset_name,
                "framework": "PyTorch",
                "researcher": mlops_cfg.get("researcher", "unknown"),
                "learning_rate": exp_config["learning_rate"],
                "batch_size": exp_config["batch_size"],
                "epochs": epochs,
                "optimizer": exp_config["optimizer"],
                "scheduler": scheduler_name,
                "random_seed": seed,
                "base_channels": exp_config.get("base_channels", 32),
                "dropout": exp_config.get("dropout", 0.25),
            }
        )

        system_metadata = get_system_metadata()
        mlflow.log_params({f"sys_{k}": v for k, v in system_metadata.items()})

        history: Dict[str, list] = {"train_loss": [], "val_loss": []}
        start_time = time.perf_counter()

        # OneCycle steps per-batch (passed into run_epoch); StepLR/CosineAnnealing
        # step once per epoch (called explicitly after each epoch below).
        per_batch_scheduler = scheduler if scheduler_name == "OneCycle" else None
        per_epoch_scheduler = scheduler if scheduler_name in ("StepLR", "CosineAnnealing") else None

        final_metrics: Dict[str, float] = {}
        for epoch in range(1, epochs + 1):
            train_loss, train_acc, train_prec, train_rec, train_f1 = run_epoch(
                model, train_loader, device, criterion, optimizer,
                scheduler=per_batch_scheduler,
            )
            if per_epoch_scheduler is not None:
                per_epoch_scheduler.step()

            val_loss, val_acc, val_prec, val_rec, val_f1 = run_epoch(
                model, val_loader, device, criterion
            )

            history["train_loss"].append(train_loss)
            history["val_loss"].append(val_loss)

            mlflow.log_metrics(
                {
                    "training_loss": train_loss,
                    "validation_loss": val_loss,
                    "train_accuracy": train_acc,
                    "accuracy": val_acc,
                    "precision": val_prec,
                    "recall": val_rec,
                    "f1": val_f1,
                },
                step=epoch,
            )
            logger.info(
                "[%s] epoch %d/%d train_loss=%.4f val_loss=%.4f val_acc=%.4f",
                exp_config["name"], epoch, epochs, train_loss, val_loss, val_acc,
            )

            final_metrics = {
                "training_loss": train_loss,
                "validation_loss": val_loss,
                "accuracy": val_acc,
                "precision": val_prec,
                "recall": val_rec,
                "f1": val_f1,
            }

        training_duration_sec = time.perf_counter() - start_time
        inference_latency_ms = measure_inference_latency_ms(model, val_loader, device)
        size_mb = model_size_mb(model)

        mlflow.log_metrics(
            {
                "training_duration_sec": training_duration_sec,
                "inference_latency_ms": inference_latency_ms,
                "model_size_mb": size_mb,
            }
        )

        # --- Artifacts ---
        run_dir = Path("models") / run.info.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        checkpoint_path = run_dir / "model.pt"
        torch.save(model.state_dict(), checkpoint_path)
        mlflow.log_artifact(str(checkpoint_path), artifact_path="checkpoint")

        config_copy_path = run_dir / "config.yaml"
        config_copy_path.write_text(yaml.safe_dump(exp_config, sort_keys=False))
        mlflow.log_artifact(str(config_copy_path), artifact_path="config")

        metrics_path = run_dir / "metrics.json"
        metrics_path.write_text(json.dumps(final_metrics, indent=2))
        mlflow.log_artifact(str(metrics_path), artifact_path="metrics")

        curve_path = maybe_log_training_curve(history, run_dir)
        if curve_path is not None:
            mlflow.log_artifact(str(curve_path), artifact_path="metrics")

        logger.info(
            "Run '%s' complete: run_id=%s final_accuracy=%.4f duration=%.1fs",
            exp_config["name"], run.info.run_id, final_metrics["accuracy"], training_duration_sec,
        )
        return run.info.run_id


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def main() -> None:
    _setup_logging()
    parser = argparse.ArgumentParser(description="Run one config-driven ML training experiment.")
    parser.add_argument("--config", required=True, help="Path to an experiment YAML config.")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs from the config.")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        exp_config = yaml.safe_load(f)
    if args.epochs is not None:
        exp_config["epochs"] = args.epochs

    project_config = load_config()
    init_mlflow(project_config)
    train_one_config(exp_config, project_config)


if __name__ == "__main__":
    main()
