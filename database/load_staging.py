"""
load_staging.py

Loads clean_data/experiments_clean.csv into the PostgreSQL
staging.experiments table:
  1. Creates the `staging` schema and `experiments` table if they
     don't exist (idempotent, safe to re-run).
  2. Truncates the table (staging is meant to be re-runnable/disposable).
  3. Bulk-loads the clean CSV via pandas.to_sql.

Usage:
    python -m database.load_staging
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd
from sqlalchemy import text

from config.config_loader import load_config
from database.db_connection import get_engine
from database.staging_models import Base

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
        force=True,
    )


def ensure_schema_and_table(engine, schema_name: str) -> None:
    """Create the staging schema (if missing) and all tables defined on Base."""
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        conn.commit()
    Base.metadata.create_all(engine)
    logger.info("Ensured schema '%s' and staging tables exist", schema_name)


def truncate_staging_table(engine, schema_name: str, table_name: str) -> None:
    with engine.connect() as conn:
        conn.execute(text(f"TRUNCATE TABLE {schema_name}.{table_name} RESTART IDENTITY"))
        conn.commit()
    logger.info("Truncated %s.%s", schema_name, table_name)


def load_clean_csv_to_staging(engine, csv_path: str, schema_name: str, table_name: str) -> int:
    df = pd.read_csv(csv_path, parse_dates=["timestamp"])
    row_count = len(df)

    df.to_sql(
        table_name,
        con=engine,
        schema=schema_name,
        if_exists="append",
        index=False,
        method="multi",
        chunksize=1000,
    )
    logger.info("Loaded %d rows into %s.%s", row_count, schema_name, table_name)
    return row_count


def run() -> None:
    config = load_config()
    _setup_logging(
        level=config.get("logging", {}).get("level", "INFO"),
        log_file=config.get("logging", {}).get("log_file", "logs/pipeline.log"),
    )

    db_cfg = config["database"]
    schema_name = db_cfg["staging_schema"]
    csv_path = config["etl"]["clean_output_path"]

    logger.info("=== STAGING LOAD START ===")

    engine = get_engine(config)
    ensure_schema_and_table(engine, schema_name)
    truncate_staging_table(engine, schema_name, "experiments")
    row_count = load_clean_csv_to_staging(engine, csv_path, schema_name, "experiments")

    logger.info("=== STAGING LOAD COMPLETE: %d rows loaded ===", row_count)


if __name__ == "__main__":
    run()
