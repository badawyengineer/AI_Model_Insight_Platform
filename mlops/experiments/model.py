"""
model.py

A deliberately small CNN for 32x32x3 image classification (CIFAR-10
shaped). Milestone 7's goal is realistic *experiment metadata*, not a
state-of-the-art model, so this is intentionally simple and fast to
train on CPU.

`base_channels` and `dropout` are exposed so experiment configs can
vary model capacity between runs (this is what shows up in MLflow as
the `model_name`/architecture params), without needing a different
model class per experiment.
"""

from __future__ import annotations

import torch
from torch import nn


class SimpleCNN(nn.Module):
    """Two conv blocks + a small classifier head."""

    def __init__(
        self,
        num_classes: int = 10,
        base_channels: int = 32,
        dropout: float = 0.25,
    ) -> None:
        super().__init__()
        self.base_channels = base_channels

        self.features = nn.Sequential(
            nn.Conv2d(3, base_channels, kernel_size=3, padding=1),
            nn.BatchNorm2d(base_channels),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),  # 32 -> 16
            nn.Conv2d(base_channels, base_channels * 2, kernel_size=3, padding=1),
            nn.BatchNorm2d(base_channels * 2),
            nn.ReLU(inplace=True),
            nn.MaxPool2d(2),  # 16 -> 8
        )
        self.classifier = nn.Sequential(
            nn.Flatten(),
            nn.Dropout(dropout),
            nn.Linear(base_channels * 2 * 8 * 8, 128),
            nn.ReLU(inplace=True),
            nn.Dropout(dropout),
            nn.Linear(128, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.features(x)
        return self.classifier(x)


def count_parameters(model: nn.Module) -> int:
    """Total trainable parameter count, used for the `model_size_mb` metric."""
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def model_size_mb(model: nn.Module) -> float:
    """Approximate on-disk size in MB assuming float32 weights (4 bytes/param)."""
    return count_parameters(model) * 4 / (1024 ** 2)
