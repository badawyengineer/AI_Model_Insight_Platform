"""
data.py

Dataset loading for the Milestone 7 training workload.

Primary path: torchvision's CIFAR-10 (downloaded once into
config["mlops"]["data_dir"] and cached for every later run).

Fallback path: if CIFAR-10 can't be downloaded (offline machine, CI
runner with restricted network egress, first run behind a firewall),
we fall back to torchvision.datasets.FakeData with the exact same
shape (3x32x32 images, 10 classes). This keeps the training/tracking
code fully exercisable and reproducible without a network dependency,
which matters more for this milestone (real MLflow-tracked training
runs) than which exact dataset supplies the pixels. `dataset_name` in
the logged metadata always reflects which one was actually used.
"""

from __future__ import annotations

import logging

import torch
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, transforms

logger = logging.getLogger(__name__)

CIFAR10_MEAN = (0.4914, 0.4822, 0.4465)
CIFAR10_STD = (0.2470, 0.2435, 0.2616)


def _cifar10_transform() -> transforms.Compose:
    return transforms.Compose(
        [transforms.ToTensor(), transforms.Normalize(CIFAR10_MEAN, CIFAR10_STD)]
    )


def _load_cifar10(data_dir: str) -> tuple[torch.utils.data.Dataset, torch.utils.data.Dataset, str]:
    tfm = _cifar10_transform()
    train = datasets.CIFAR10(root=data_dir, train=True, download=True, transform=tfm)
    val = datasets.CIFAR10(root=data_dir, train=False, download=True, transform=tfm)
    return train, val, "CIFAR-10"


def _load_fake_fallback() -> tuple[torch.utils.data.Dataset, torch.utils.data.Dataset, str]:
    tfm = transforms.ToTensor()
    train = datasets.FakeData(
        size=4000, image_size=(3, 32, 32), num_classes=10, transform=tfm
    )
    val = datasets.FakeData(
        size=1000, image_size=(3, 32, 32), num_classes=10, transform=tfm
    )
    return train, val, "FakeData-CIFAR10Shaped"


def get_datasets(data_dir: str) -> tuple[torch.utils.data.Dataset, torch.utils.data.Dataset, str]:
    """
    Returns (train_dataset, val_dataset, dataset_name_actually_used).

    Tries real CIFAR-10 first; falls back to a same-shaped synthetic
    dataset if the download fails for any reason (network, disk, etc).
    """
    try:
        return _load_cifar10(data_dir)
    except Exception as exc:  # noqa: BLE001 - deliberately broad: any download failure
        logger.warning(
            "CIFAR-10 download failed (%s: %s) - falling back to a "
            "same-shaped synthetic dataset so training can still run.",
            type(exc).__name__,
            exc,
        )
        return _load_fake_fallback()


def get_dataloaders(
    data_dir: str,
    batch_size: int,
    seed: int,
    train_subset_size: int | None = None,
    val_subset_size: int | None = None,
    num_workers: int = 0,
) -> tuple[DataLoader, DataLoader, str, int]:
    """
    Build train/val DataLoaders.

    train_subset_size / val_subset_size cap the dataset size (config-driven)
    so a full experiment matrix trains in seconds on CPU instead of
    minutes-per-epoch — this is a reproducibility/config knob, not a
    change to the dataset itself. Pass None to use the full dataset.
    """
    train_ds, val_ds, dataset_name = get_datasets(data_dir)

    generator = torch.Generator().manual_seed(seed)

    if train_subset_size is not None and train_subset_size < len(train_ds):
        idx = torch.randperm(len(train_ds), generator=generator)[:train_subset_size]
        train_ds = Subset(train_ds, idx.tolist())
    if val_subset_size is not None and val_subset_size < len(val_ds):
        idx = torch.randperm(len(val_ds), generator=generator)[:val_subset_size]
        val_ds = Subset(val_ds, idx.tolist())

    train_loader = DataLoader(
        train_ds, batch_size=batch_size, shuffle=True, num_workers=num_workers
    )
    val_loader = DataLoader(
        val_ds, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )
    return train_loader, val_loader, dataset_name, 10
