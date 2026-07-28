"""
build_dim_date.py

Populates warehouse.dim_date with a full, pre-populated calendar range
(configured via warehouse.date_range_start / date_range_end in
config.yaml) rather than only dates that appear in experiment data.
This is standard data warehouse practice and lets Power BI filter by
date ranges that may extend beyond current experiment history.

Idempotent: safe to re-run, uses INSERT ... ON CONFLICT DO NOTHING on
the unique full_date column.

Usage:
    python -m warehouse.build_dim_date
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text

from config.config_loader import load_config
from database.db_connection import get_engine

logger = logging.getLogger(__name__)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]
DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def build_date_range_df(start_date: str, end_date: str) -> pd.DataFrame:
    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    rows = []
    current = start
    while current <= end:
        dow = current.weekday()  # 0 = Monday
        rows.append(
            {
                "date_key": int(current.strftime("%Y%m%d")),
                "full_date": current,
                "year": current.year,
                "quarter": (current.month - 1) // 3 + 1,
                "month": current.month,
                "month_name": MONTH_NAMES[current.month - 1],
                "day": current.day,
                "day_of_week": dow,
                "day_name": DAY_NAMES[dow],
                "is_weekend": dow >= 5,
            }
        )
        current += timedelta(days=1)

    return pd.DataFrame(rows)


def load_dim_date(engine, df: pd.DataFrame, schema_name: str) -> int:
    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        conn.commit()

    # Load into a temp staging table then upsert, so re-runs don't fail
    # on the unique full_date constraint.
    df.to_sql(
        "_dim_date_tmp",
        con=engine,
        schema=schema_name,
        if_exists="replace",
        index=False,
    )

    with engine.connect() as conn:
        conn.execute(
            text(
                f"""
                INSERT INTO {schema_name}.dim_date
                SELECT * FROM {schema_name}._dim_date_tmp
                ON CONFLICT (date_key) DO NOTHING
                """
            )
        )
        conn.execute(text(f"DROP TABLE {schema_name}._dim_date_tmp"))
        conn.commit()

    return len(df)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    config = load_config()

    from warehouse.warehouse_models import Base

    schema_name = config["database"]["warehouse_schema"]
    engine = get_engine(config)

    with engine.connect() as conn:
        conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
        conn.commit()
    Base.metadata.create_all(engine)

    wh_cfg = config["warehouse"]
    df = build_date_range_df(wh_cfg["date_range_start"], wh_cfg["date_range_end"])
    logger.info("Built calendar with %d dates (%s to %s)", len(df), wh_cfg["date_range_start"], wh_cfg["date_range_end"])

    count = load_dim_date(engine, df, schema_name)
    logger.info("=== DIM_DATE LOAD COMPLETE: %d dates processed ===", count)


if __name__ == "__main__":
    run()
