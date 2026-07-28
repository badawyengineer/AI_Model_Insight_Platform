"""
distributions.py

Sampling helpers that turn the static pools in config_pools.py into a
single, internally-consistent experiment record's worth of numbers.

The guiding principle: fields should not be independently random. A
run's accuracy should depend on its model, its epochs, and its status;
its energy consumption should depend on its training time and GPU;
etc. This is what makes the dataset look like real experiment logs
instead of uniform noise, which matters for the analytical/dashboard
milestones later (e.g. "GPU performance" or "hyperparameter analysis"
charts are meaningless over pure noise).

All sampling takes an explicit `random.Random` instance so the whole
generator can be seeded for reproducibility (see config.yaml `seed`).
"""

from __future__ import annotations

import random
from typing import Optional

from generator.config_pools import (
    BATCH_SIZES,
    CPUS,
    DATASETS,
    FRAMEWORKS,
    GPU_PROFILES,
    MODEL_PROFILES,
    OPTIMIZERS,
    RESEARCHERS,
    SCHEDULERS,
)


def sample_status(rng: random.Random, status_distribution: dict[str, float]) -> str:
    """Weighted sample of experiment status from config-driven probabilities."""
    statuses = list(status_distribution.keys())
    weights = list(status_distribution.values())
    return rng.choices(statuses, weights=weights, k=1)[0]


def sample_learning_rate(rng: random.Random) -> float:
    """Log-uniform sample between 1e-5 and 1e-1 (learning rates span orders of magnitude)."""
    exponent = rng.uniform(-5, -1)
    return round(10 ** exponent, 6)


def sample_model_and_dataset(rng: random.Random) -> tuple[str, dict[str, float], str]:
    model_name = rng.choice(list(MODEL_PROFILES.keys()))
    profile = MODEL_PROFILES[model_name]
    dataset = rng.choice(DATASETS)
    return model_name, profile, dataset


def sample_hardware(rng: random.Random) -> tuple[str, dict[str, float], str, float]:
    gpu_name = rng.choice(list(GPU_PROFILES.keys()))
    gpu_profile = GPU_PROFILES[gpu_name]
    cpu_name = rng.choice(CPUS)
    ram_gb = float(rng.choice([16, 32, 64, 128, 256]))
    return gpu_name, gpu_profile, cpu_name, ram_gb


def sample_epochs(rng: random.Random) -> int:
    return rng.randint(5, 100)


def sample_training_time_sec(
    rng: random.Random, epochs: int, batch_size: int, gpu_speed_factor: float
) -> float:
    """
    Rough proxy: more epochs and smaller batch sizes take longer; faster
    GPUs (higher speed_factor) reduce time. Noise term keeps it non-deterministic.
    """
    base = (epochs * 45.0) * (64.0 / batch_size)
    time_sec = base / gpu_speed_factor
    noise = rng.uniform(0.85, 1.2)
    return round(time_sec * noise, 2)


def sample_energy_consumption_kwh(
    rng: random.Random, training_time_sec: float, gpu_power_watts: float
) -> float:
    """Energy = power (kW) * time (hours), plus small overhead noise."""
    hours = training_time_sec / 3600.0
    kwh = (gpu_power_watts / 1000.0) * hours
    noise = rng.uniform(1.0, 1.15)  # cooling/overhead
    return round(kwh * noise, 4)


def sample_model_size_mb(rng: random.Random, base_size_mb: float) -> float:
    noise = rng.uniform(0.97, 1.03)
    return round(base_size_mb * noise, 2)


def sample_inference_time_ms(rng: random.Random, model_size_mb: float) -> float:
    """Bigger models tend to have higher inference latency."""
    base = 2.0 + (model_size_mb / 50.0)
    noise = rng.uniform(0.8, 1.3)
    return round(base * noise, 3)


def sample_metrics(
    rng: random.Random,
    status: str,
    epochs: int,
    base_accuracy: float,
    learning_rate: float,
) -> dict[str, Optional[float]]:
    """
    Produce accuracy/precision/recall/f1/loss/validation_loss, or None
    values for statuses that wouldn't have final metrics yet.

    Accuracy model: approaches `base_accuracy` asymptotically with more
    epochs (diminishing returns curve), penalized if learning_rate is
    poorly chosen (too high => instability => lower accuracy), plus noise.
    FAILED runs get a low/degenerate accuracy. RUNNING/KILLED runs have
    no final metrics (still training / terminated early).
    """
    if status in ("running", "killed"):
        return {
            "accuracy": None,
            "precision": None,
            "recall": None,
            "f1_score": None,
            "loss": None,
            "validation_loss": None,
        }

    if status == "failed":
        # Degenerate run: near-random accuracy, high loss
        accuracy = round(rng.uniform(0.05, 0.35), 4)
        loss = round(rng.uniform(3.0, 8.0), 4)
        validation_loss = round(loss * rng.uniform(1.0, 1.3), 4)
        precision = round(max(0.0, accuracy - rng.uniform(0.0, 0.05)), 4)
        recall = round(max(0.0, accuracy - rng.uniform(0.0, 0.05)), 4)
        f1 = round(2 * precision * recall / (precision + recall + 1e-9), 4)
        return {
            "accuracy": accuracy,
            "precision": precision,
            "recall": recall,
            "f1_score": f1,
            "loss": loss,
            "validation_loss": validation_loss,
        }

    # status == "success"
    diminishing_returns = 1 - (1 / (1 + epochs / 20.0))
    lr_penalty = 0.0
    if learning_rate > 0.02:
        # Too-high learning rates hurt final accuracy a bit
        lr_penalty = min(0.15, (learning_rate - 0.02) * 2.0)

    accuracy = base_accuracy * diminishing_returns - lr_penalty
    accuracy += rng.uniform(-0.02, 0.02)
    accuracy = round(min(max(accuracy, 0.4), 0.995), 4)

    precision = round(min(max(accuracy + rng.uniform(-0.03, 0.02), 0.0), 1.0), 4)
    recall = round(min(max(accuracy + rng.uniform(-0.03, 0.02), 0.0), 1.0), 4)
    f1 = round(2 * precision * recall / (precision + recall + 1e-9), 4)

    loss = round(max(0.01, (1 - accuracy) * rng.uniform(1.5, 2.5)), 4)
    validation_loss = round(loss * rng.uniform(1.0, 1.25), 4)

    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1_score": f1,
        "loss": loss,
        "validation_loss": validation_loss,
    }
