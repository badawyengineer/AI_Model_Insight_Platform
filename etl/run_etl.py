"""
run_etl.py

Orchestrates the full ETL pipeline: extract -> validate -> clean -> load
(to clean_data/experiments_clean.csv). Rejected records (failed schema
validation) are written to logs/rejected_records.json for audit rather
than silently discarded.

Usage:
    python -m etl.run_etl
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from config.config_loader import load_config
from etl.clean import clean_records
from etl.extract import extract_raw_records
from etl.validate import validate_records

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
        force=True,  # allow re-running in the same process (e.g. tests) cleanly
    )


def write_rejected_records(rejected: list[dict], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rejected, f, indent=2, ensure_ascii=False, default=str)
    if rejected:
        logger.info("Wrote %d rejected records to %s", len(rejected), path)


def run_etl() -> None:
    config = load_config()
    _setup_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("log_file", "logs/pipeline.log"),
    )

    generator_cfg = config["generator"]
    etl_cfg = config["etl"]

    logger.info("=== ETL PIPELINE START ===")

    # --- Extract ---
    raw_records = extract_raw_records(generator_cfg["output_path"])

    # --- Validate ---
    valid_records, rejected_records = validate_records(raw_records)
    write_rejected_records(rejected_records, "logs/rejected_records.json")

    if not valid_records:
        logger.error("No valid records survived validation. Aborting ETL.")
        return

    # --- Clean ---
    clean_df = clean_records(valid_records, etl_cfg["missing_value_strategy"])

    # --- Load (to clean_data/) ---
    output_path = Path(etl_cfg["clean_output_path"])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_df.to_csv(output_path, index=False)
    logger.info("Wrote %d clean records to %s", len(clean_df), output_path)

    logger.info(
        "=== ETL PIPELINE COMPLETE: %d raw -> %d valid -> %d rejected -> %d clean ===",
        len(raw_records),
        len(valid_records),
        len(rejected_records),
        len(clean_df),
    )


if __name__ == "__main__":
    run_etl()
