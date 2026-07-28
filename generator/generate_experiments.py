"""
generate_experiments.py

Main entry point for Milestone 2. Generates `num_experiments` synthetic
but internally-consistent AI training experiment records (per the
ExperimentRecord schema in database/schemas.py) and writes them to
`raw_data/experiments_raw.json`.

Usage:
    python -m generator.generate_experiments

All tunable parameters (count, seed, output path, status distribution)
come from config/config.yaml — nothing is hardcoded here, per the
project's coding rules.
"""

from __future__ import annotations

import json
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path

from config.config_loader import load_config
from database.schemas import ExperimentRecord, ExperimentStatus
from generator.config_pools import (
    BATCH_SIZES,
    FRAMEWORKS,
    OPTIMIZERS,
    RESEARCHERS,
    SCHEDULERS,
)
from generator.distributions import (
    sample_energy_consumption_kwh,
    sample_epochs,
    sample_hardware,
    sample_inference_time_ms,
    sample_learning_rate,
    sample_metrics,
    sample_model_and_dataset,
    sample_model_size_mb,
    sample_status,
    sample_training_time_sec,
)

logger = logging.getLogger(__name__)


def _setup_logging(level: str, log_file: str) -> None:
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[
            logging.FileHandler(log_path, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _random_timestamp(rng: random.Random, days_back: int = 180) -> datetime:
    """Random timestamp within the last `days_back` days, for a realistic experiment history."""
    now = datetime.now()
    offset_seconds = rng.randint(0, days_back * 24 * 3600)
    return now - timedelta(seconds=offset_seconds)


def generate_one_experiment(
    rng: random.Random, index: int, status_distribution: dict[str, float]
) -> ExperimentRecord:
    """Build a single internally-consistent, schema-valid experiment record."""
    status = sample_status(rng, status_distribution)

    model_name, model_profile, dataset = sample_model_and_dataset(rng)
    gpu_name, gpu_profile, cpu_name, ram_gb = sample_hardware(rng)

    framework = rng.choice(FRAMEWORKS)
    optimizer = rng.choice(OPTIMIZERS)
    scheduler = rng.choice(SCHEDULERS)
    researcher = rng.choice(RESEARCHERS)

    learning_rate = sample_learning_rate(rng)
    batch_size = rng.choice(BATCH_SIZES)
    epochs = sample_epochs(rng)

    training_time_sec = sample_training_time_sec(
        rng, epochs, batch_size, gpu_profile["speed_factor"]
    )
    energy_consumption_kwh = sample_energy_consumption_kwh(
        rng, training_time_sec, gpu_profile["power_watts"]
    )
    model_size_mb = sample_model_size_mb(rng, model_profile["base_size_mb"])
    inference_time_ms = sample_inference_time_ms(rng, model_size_mb)

    metrics = sample_metrics(
        rng,
        status=status,
        epochs=epochs,
        base_accuracy=model_profile["base_accuracy"],
        learning_rate=learning_rate,
    )

    record = ExperimentRecord(
        experiment_id=f"exp_{index:05d}",
        model_name=model_name,
        dataset=dataset,
        framework=framework,
        researcher=researcher,
        optimizer=optimizer,
        scheduler=scheduler,
        learning_rate=learning_rate,
        batch_size=batch_size,
        epochs=epochs,
        gpu=gpu_name,
        cpu=cpu_name,
        ram_gb=ram_gb,
        training_time_sec=training_time_sec,
        inference_time_ms=inference_time_ms,
        model_size_mb=model_size_mb,
        energy_consumption_kwh=energy_consumption_kwh,
        accuracy=metrics["accuracy"],
        precision=metrics["precision"],
        recall=metrics["recall"],
        f1_score=metrics["f1_score"],
        loss=metrics["loss"],
        validation_loss=metrics["validation_loss"],
        timestamp=_random_timestamp(rng),
        status=ExperimentStatus(status),
    )
    return record


def generate_experiments(config: dict) -> list[ExperimentRecord]:
    gen_cfg = config["generator"]
    num_experiments = gen_cfg["num_experiments"]
    seed = gen_cfg["seed"]
    status_distribution = gen_cfg["status_distribution"]

    rng = random.Random(seed)

    logger.info(
        "Generating %d synthetic experiment records (seed=%d)", num_experiments, seed
    )

    records: list[ExperimentRecord] = []
    for i in range(1, num_experiments + 1):
        record = generate_one_experiment(rng, i, status_distribution)
        records.append(record)
        if i % 1000 == 0:
            logger.info("Generated %d/%d records", i, num_experiments)

    logger.info("Finished generating %d records", len(records))
    return records


def write_records(records: list[ExperimentRecord], output_path: str) -> None:
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    payload = [json.loads(r.model_dump_json()) for r in records]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d records to %s", len(records), out_path)


def main() -> None:
    config = load_config()
    _setup_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("log_file", "logs/pipeline.log"),
    )

    records = generate_experiments(config)
    write_records(records, config["generator"]["output_path"])

    # Quick summary for a sanity glance at the console
    status_counts: dict[str, int] = {}
    for r in records:
        status_counts[r.status.value] = status_counts.get(r.status.value, 0) + 1
    logger.info("Status breakdown: %s", status_counts)


if __name__ == "__main__":
    main()
