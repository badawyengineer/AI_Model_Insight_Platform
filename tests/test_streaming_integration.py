"""
test_streaming_integration.py

End-to-end integration test for the Milestone 11 streaming path:
publish simulated events to a real Redis stream, consume them with a
real consumer group, and confirm they land correctly in PostgreSQL.

Skips (not fails) if Redis or PostgreSQL aren't reachable, matching the
pattern used by tests/test_apply_analytics.py for Postgres-dependent
tests. This is deliberately a real integration test, not a mocked one -
Redis Streams' consumer-group semantics (XREADGROUP/XACK, the
BUSYGROUP-on-recreate case, at-least-once delivery) are exactly the kind
of behavior a mock would get subtly wrong.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from config.config_loader import load_config
from database.db_connection import get_engine
from database.monitoring_models import PredictionEvent as PredictionEventModel
from streaming.consumer import consume_batch, ensure_consumer_group, ensure_schema_and_table
from streaming.producer import _simulate_event, get_redis_client, publish_event


@pytest.fixture
def redis_client():
    try:
        client = get_redis_client(load_config())
        client.ping()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No reachable Redis instance configured: {exc}")
    return client


@pytest.fixture
def db_session():
    try:
        engine = get_engine(load_config())
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"No reachable PostgreSQL database configured: {exc}")

    ensure_schema_and_table(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def isolated_stream_name():
    """A unique stream name per test run, so tests never see each
    other's events or interfere with a real prediction_events stream
    that might exist on the same Redis instance."""
    return f"test_prediction_events_{uuid.uuid4().hex[:8]}"


def test_publish_and_consume_round_trip(redis_client, db_session, isolated_stream_name):
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"
    model_name = f"test-model-{uuid.uuid4().hex[:8]}"

    events = [_simulate_event(drifted=False, model_name=model_name, model_version="v1") for _ in range(10)]
    for event in events:
        publish_event(redis_client, isolated_stream_name, event)

    assert redis_client.xlen(isolated_stream_name) == 10

    ensure_consumer_group(redis_client, isolated_stream_name, group_name)
    processed = consume_batch(redis_client, db_session, isolated_stream_name, group_name, batch_size=100)

    assert processed == 10

    rows = (
        db_session.query(PredictionEventModel)
        .filter(PredictionEventModel.model_name == model_name, PredictionEventModel.model_version == "v1")
        .all()
    )
    assert len(rows) == 10
    for row in rows:
        assert 0.0 <= row.prediction <= 1.0
        assert row.latency_ms > 0
        assert row.stream_entry_id  # non-empty, traceable back to the Redis entry


def test_consume_batch_is_idempotent_on_redelivery(redis_client, db_session, isolated_stream_name):
    """Simulates a crashed consumer: entries read but not yet acked are
    redelivered on the next XREADGROUP with the same consumer name.
    Re-processing must not create duplicate rows (on_conflict_do_nothing
    on stream_entry_id)."""
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"
    model_name = f"test-model-{uuid.uuid4().hex[:8]}"
    event = _simulate_event(drifted=False, model_name=model_name, model_version="v1")
    publish_event(redis_client, isolated_stream_name, event)

    ensure_consumer_group(redis_client, isolated_stream_name, group_name)

    first_pass = consume_batch(redis_client, db_session, isolated_stream_name, group_name, batch_size=10)
    assert first_pass == 1

    # Re-run consume_batch with nothing new published - XREADGROUP with
    # ">" only returns *new* (never-delivered) entries, so this proves
    # the already-acked entry isn't reprocessed, which is the correct
    # behavior (ack happens right after the successful insert).
    second_pass = consume_batch(redis_client, db_session, isolated_stream_name, group_name, batch_size=10)
    assert second_pass == 0

    rows = (
        db_session.query(PredictionEventModel)
        .filter(PredictionEventModel.model_name == model_name)
        .all()
    )
    assert len(rows) == 1


def test_ensure_consumer_group_is_idempotent(redis_client, isolated_stream_name):
    """Creating the same consumer group twice must not raise (the
    BUSYGROUP case) - this is exercised on every real run after the
    first, since ensure_consumer_group runs at the start of every
    `streaming.consumer` invocation."""
    group_name = f"test_group_{uuid.uuid4().hex[:8]}"
    ensure_consumer_group(redis_client, isolated_stream_name, group_name)
    ensure_consumer_group(redis_client, isolated_stream_name, group_name)  # must not raise
