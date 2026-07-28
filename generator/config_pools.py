"""
config_pools.py

Static pools of realistic reference values used by the synthetic data
generator. Keeping these as plain data (not logic) makes it trivial to
extend the generator's vocabulary later (e.g. add a new GPU) without
touching sampling logic in distributions.py.

Each model/GPU entry carries small "profile" numbers (base accuracy
ceiling, base size, power draw, etc.) that distributions.py uses to
produce internally-consistent records, rather than every field being
independently random noise.
"""

from __future__ import annotations

# model_name -> (base_model_size_mb, base_accuracy_ceiling)
# base_accuracy_ceiling = the asymptotic accuracy a well-trained run
# of this model architecture tends to approach.
MODEL_PROFILES: dict[str, dict[str, float]] = {
    "resnet18": {"base_size_mb": 45.0, "base_accuracy": 0.90},
    "resnet50": {"base_size_mb": 98.0, "base_accuracy": 0.94},
    "resnet101": {"base_size_mb": 170.0, "base_accuracy": 0.95},
    "vit_base": {"base_size_mb": 330.0, "base_accuracy": 0.96},
    "vit_large": {"base_size_mb": 1150.0, "base_accuracy": 0.97},
    "bert_base": {"base_size_mb": 420.0, "base_accuracy": 0.91},
    "bert_large": {"base_size_mb": 1340.0, "base_accuracy": 0.93},
    "gpt2_small": {"base_size_mb": 500.0, "base_accuracy": 0.88},
    "efficientnet_b0": {"base_size_mb": 20.0, "base_accuracy": 0.89},
    "efficientnet_b7": {"base_size_mb": 256.0, "base_accuracy": 0.95},
    "mobilenet_v3": {"base_size_mb": 12.0, "base_accuracy": 0.85},
    "yolo_v8": {"base_size_mb": 50.0, "base_accuracy": 0.92},
}

DATASETS: list[str] = [
    "imagenet_subset",
    "cifar100",
    "coco_detection",
    "squad_v2",
    "glue_mnli",
    "librispeech",
    "wikitext103",
    "openwebtext_subset",
    "voc2012",
    "ade20k",
    "arabic_news_corpus",
    "cidar_instruction",
]

# gpu_name -> (relative_speed_factor, power_draw_watts)
# relative_speed_factor: higher = faster training (reduces training_time_sec)
GPU_PROFILES: dict[str, dict[str, float]] = {
    "NVIDIA T4": {"speed_factor": 1.0, "power_watts": 70},
    "NVIDIA RTX 3090": {"speed_factor": 2.2, "power_watts": 350},
    "NVIDIA RTX 4090": {"speed_factor": 3.0, "power_watts": 450},
    "NVIDIA V100": {"speed_factor": 2.5, "power_watts": 300},
    "NVIDIA A100": {"speed_factor": 4.0, "power_watts": 400},
    "NVIDIA H100": {"speed_factor": 6.0, "power_watts": 700},
}

CPUS: list[str] = [
    "Intel Xeon Gold 6248",
    "Intel i9-12900K",
    "AMD EPYC 7742",
    "AMD Ryzen 9 7950X",
    "Intel i7-13700K",
    "AMD Threadripper 3970X",
]

FRAMEWORKS: list[str] = ["PyTorch", "TensorFlow", "JAX"]

OPTIMIZERS: list[str] = ["Adam", "AdamW", "SGD", "RMSprop"]

SCHEDULERS: list[str] = ["CosineAnnealing", "StepLR", "OneCycle", "Constant"]

RESEARCHERS: list[str] = [
    "Abdelrahman Badawy",
    "Sara Mostafa",
    "Youssef Ali",
    "Mona Hassan",
    "Ahmed Fathy",
    "Nourhan Ibrahim",
    "Karim Salah",
    "Laila Adel",
    "Omar Tarek",
    "Dina Farouk",
]

BATCH_SIZES: list[int] = [8, 16, 32, 64, 128, 256]
