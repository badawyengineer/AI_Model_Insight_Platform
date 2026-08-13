"""
test_apply_analytics.py

Tests warehouse/apply_analytics.py's SQL-statement splitting against the
real analytics.sql file. Requires a live PostgreSQL connection (same as
the existing warehouse/staging tests) - set DB_PASSWORD and make sure
config.yaml's database section points at a reachable Postgres instance.

This specifically guards against comment-header statements (every
CREATE VIEW block in analytics.sql is preceded by a multi-line `--`
comment) being silently dropped by a naive "skip lines starting with
--" filter - which happened during development and dropped every view
while indexes (which have no comment header) kept working silently.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from config.config_loader import load_config
from database.db_connection import get_engine
from warehouse.apply_analytics import ANALYTICS_SQL_PATH, apply_analytics_sql

EXPECTED_VIEWS = {
    "vw_dataset_comparison",
    "vw_executive_kpis",
    "vw_experiment_source_breakdown",
    "vw_framework_comparison",
    "vw_gpu_performance",
    "vw_hyperparameter_analysis",
    "vw_model_leaderboard",
    "vw_training_timeline",
}


@pytest.fixture
def db_engine():
    try:
        config = load_config()
        engine = get_engine(config)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No reachable PostgreSQL database configured: {exc}")
    return engine


def test_analytics_sql_file_has_both_indexes_and_views():
    """Sanity check on the fixture file itself - would catch someone
    accidentally emptying analytics.sql."""
    sql_text = ANALYTICS_SQL_PATH.read_text()
    assert sql_text.count("CREATE INDEX") >= 7
    assert sql_text.count("CREATE OR REPLACE VIEW") >= 7


def test_apply_analytics_sql_creates_every_view(db_engine):
    apply_analytics_sql(db_engine)

    with db_engine.connect() as conn:
        result = conn.execute(
            text(
                "SELECT table_name FROM information_schema.views "
                "WHERE table_schema = 'warehouse'"
            )
        )
        actual_views = {row[0] for row in result}

    missing = EXPECTED_VIEWS - actual_views
    assert not missing, (
        f"apply_analytics_sql failed to create: {missing}. "
        "This is the exact bug a comment-stripping regression would cause "
        "(every CREATE VIEW block has a comment header and would be "
        "silently dropped while CREATE INDEX statements keep working)."
    )


def test_apply_analytics_sql_is_idempotent(db_engine):
    """Running it twice in a row must not raise (CREATE INDEX IF NOT
    EXISTS / CREATE OR REPLACE VIEW)."""
    apply_analytics_sql(db_engine)
    apply_analytics_sql(db_engine)  # should not raise
