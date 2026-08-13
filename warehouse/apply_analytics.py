"""
apply_analytics.py

Applies warehouse/analytics.sql (indexes + views) against the warehouse
schema. Previously this was a manual step (`psql -f warehouse/analytics.sql`)
run by hand after transform_load. This gives it the same "python -m"
entry point every other stage has, so it can be scheduled as an Airflow
task (Milestone 8) instead of a manual command.

Idempotent: analytics.sql uses `CREATE INDEX IF NOT EXISTS` and
`CREATE OR REPLACE VIEW`, so re-running this after every warehouse load
is safe and cheap.

Usage:
    python -m warehouse.apply_analytics
"""

from __future__ import annotations

import logging
from pathlib import Path

from sqlalchemy import text

from config.config_loader import load_config
from database.db_connection import get_engine

logger = logging.getLogger(__name__)

ANALYTICS_SQL_PATH = Path(__file__).parent / "analytics.sql"


def apply_analytics_sql(engine, sql_path: Path = ANALYTICS_SQL_PATH) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")

    # Strip full-line SQL comments before splitting, so a statement
    # preceded by a multi-line comment header (every CREATE VIEW block
    # here has one) isn't mistaken for "starts with a comment" and
    # dropped whole. Comments after code on the same line are left
    # alone - none of analytics.sql's statements rely on those.
    lines = [line for line in sql_text.splitlines() if not line.strip().startswith("--")]
    sql_no_comments = "\n".join(lines)

    # analytics.sql contains multiple statements separated by semicolons;
    # psycopg2 can't execute a multi-statement string in one call, so we
    # split on statement-terminating semicolons and run each one that
    # actually has content. Safe here because analytics.sql contains
    # only DDL (CREATE INDEX / CREATE VIEW) with no semicolons inside
    # string literals.
    statements = [s.strip() for s in sql_no_comments.split(";") if s.strip()]

    with engine.connect() as conn:
        for statement in statements:
            conn.execute(text(statement))
        conn.commit()

    logger.info("Applied %d statement(s) from %s", len(statements), sql_path)


def run() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    config = load_config()
    engine = get_engine(config)
    apply_analytics_sql(engine)
    logger.info("=== ANALYTICS SQL APPLY COMPLETE ===")


if __name__ == "__main__":
    run()
