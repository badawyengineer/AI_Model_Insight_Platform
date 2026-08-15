"""
test_dashboard_data.py

Tests dashboard/live/data.py's query functions against a real
PostgreSQL instance - same skip-if-unreachable pattern as
tests/test_apply_analytics.py and tests/test_streaming_integration.py.
Publishes real events through the actual streaming pipeline (not
hand-inserted rows) so these tests exercise the exact same path a real
dashboard session would see.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.config_loader import load_config
from dashboard.live.data import (
    get_drift_status,
    get_latency_summary,
    get_monitored_models,
    get_recent_predictions,
)
from database.db_connection import get_engine
from streaming.consumer import consume_batch, ensure_consumer_group, ensure_schema_and_table
from streaming.producer import _simulate_event, get_redis_client, publish_event


@pytest.fixture
def engine():
    try:
        eng = get_engine(load_config())
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No reachable PostgreSQL database configured: {exc}")
    ensure_schema_and_table(eng)
    return eng


@pytest.fixture
def redis_client():
    try:
        client = get_redis_client(load_config())
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No reachable Redis instance configured: {exc}")
    return client


@pytest.fixture
def seeded_model(engine, redis_client):
    """Publishes and consumes 20 real events for a unique model name,
    through the actual producer/consumer path, and returns that name."""
    model_name = f"dashtest-{uuid.uuid4().hex[:8]}"
    stream_name = f"test_stream_{uuid.uuid4().hex[:8]}"
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"

    for _ in range(20):
        event = _simulate_event(drifted=False, model_name=model_name, model_version="v1")
        publish_event(redis_client, stream_name, event)

    ensure_consumer_group(redis_client, stream_name, group_name)
    with Session(engine) as session:
        consume_batch(redis_client, session, stream_name, group_name, batch_size=100)

    return model_name


def test_get_monitored_models_includes_seeded_model(engine, seeded_model):
    df = get_monitored_models(engine)
    assert seeded_model in df["model_name"].values

    row = df[df["model_name"] == seeded_model].iloc[0]
    assert row["model_version"] == "v1"
    assert row["event_count"] == 20


def test_get_recent_predictions_returns_seeded_events(engine, seeded_model):
    df = get_recent_predictions(engine, minutes=60)
    model_rows = df[df["model_name"] == seeded_model]
    assert len(model_rows) == 20
    assert (model_rows["prediction"].between(0.0, 1.0)).all()


def test_get_recent_predictions_respects_time_window(engine, seeded_model):
    """A 0-minute window should exclude events published moments ago -
    proves the cutoff filter is actually applied, not just present."""
    df = get_recent_predictions(engine, minutes=0)
    model_rows = df[df["model_name"] == seeded_model]
    assert len(model_rows) == 0


def test_get_latency_summary_computes_percentiles(engine, seeded_model):
    df = get_latency_summary(engine, minutes=60)
    row = df[df["model_name"] == seeded_model].iloc[0]

    assert row["event_count"] == 20
    assert row["avg_latency_ms"] > 0
    # p50 must be <= p95 by definition
    assert row["p50_latency_ms"] <= row["p95_latency_ms"]


def test_get_drift_status_reports_insufficient_data_below_window(engine, seeded_model):
    """20 events is well under the 200-per-window default - must report
    has_enough_data=False rather than computing a misleading PSI."""
    status = get_drift_status(engine, seeded_model, "v1", window_size=200)
    assert status["has_enough_data"] is False
    assert status["event_count"] == 20


def test_get_drift_status_matches_monitoring_drift_detection(engine, redis_client):
    """The dashboard's PSI must be computed the same way
    monitoring.drift_detection computes it for real alerts - this test
    publishes enough events to actually cross the has_enough_data
    threshold and checks the result is internally consistent (a valid
    float, not NaN/None) rather than duplicating drift_detection's own
    false-positive-rate tests here."""
    model_name = f"dashtest-full-{uuid.uuid4().hex[:8]}"
    stream_name = f"test_stream_{uuid.uuid4().hex[:8]}"
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"

    for _ in range(400):
        event = _simulate_event(drifted=False, model_name=model_name, model_version="v1")
        publish_event(redis_client, stream_name, event)

    ensure_consumer_group(redis_client, stream_name, group_name)
    with Session(engine) as session:
        consume_batch(redis_client, session, stream_name, group_name, batch_size=500)

    status = get_drift_status(engine, model_name, "v1", window_size=200)
    assert status["has_enough_data"] is True
    assert isinstance(status["psi"], float)
    assert status["psi"] >= 0.0
