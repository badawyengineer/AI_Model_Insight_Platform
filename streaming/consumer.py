"""
streaming/consumer.py

Milestone 11: consumes prediction events off the Redis stream (see
streaming/producer.py for why Redis Streams rather than Kafka) using a
consumer group - XREADGROUP + XACK - so consumption is at-least-once
and resumable (a crashed consumer's unacked entries are still claimable
by the next run), the same guarantee a Kafka consumer group gives.
Writes batches into database.monitoring_models.PredictionEvent.

Usage:
    python -m streaming.consumer --once             # drain what's currently available, then exit (used by tests/CI)
    python -m streaming.consumer                     # run continuously (Ctrl+C to stop)
"""

from __future__ import annotations

import argparse
import logging
from datetime import datetime, timezone

import redis
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from config.config_loader import load_config
from database.db_connection import get_engine
from database.monitoring_models import Base, PredictionEvent
from streaming.producer import get_redis_client
from streaming.schemas import PredictionEvent as PredictionEventSchema

logger = logging.getLogger(__name__)

CONSUMER_NAME = "consumer-1"  # single-consumer for this project's scale; a real deployment would use one name per process


def ensure_consumer_group(client: redis.Redis, stream_name: str, group_name: str) -> None:
    try:
        client.xgroup_create(stream_name, group_name, id="0", mkstream=True)
        logger.info("Created consumer group '%s' on stream '%s'", group_name, stream_name)
    except redis.ResponseError as exc:
        if "BUSYGROUP" in str(exc):
            pass  # group already exists - fine, this is expected on every run after the first
        else:
            raise


def _parse_entry(entry_id: str, fields: dict) -> PredictionEvent:
    schema_event = PredictionEventSchema(**fields)
    return PredictionEvent(
        stream_entry_id=entry_id,
        model_name=schema_event.model_name,
        model_version=schema_event.model_version,
        prediction=schema_event.prediction,
        ground_truth=schema_event.ground_truth,
        latency_ms=schema_event.latency_ms,
        event_timestamp=schema_event.event_timestamp,
        ingested_at=datetime.now(timezone.utc),
    )


def consume_batch(
    client: redis.Redis,
    session: Session,
    stream_name: str,
    group_name: str,
    batch_size: int,
) -> int:
    """
    Read up to batch_size pending entries, insert them (upsert on
    stream_entry_id so a redelivered/replayed entry is a no-op, not a
    duplicate row), and XACK only the ones that made it into Postgres.
    Returns the number of entries processed.
    """
    response = client.xreadgroup(
        group_name, CONSUMER_NAME, {stream_name: ">"}, count=batch_size, block=1000
    )
    if not response:
        return 0

    entries = response[0][1]  # [(stream_name, [(entry_id, fields), ...])]
    rows = [_parse_entry(entry_id, fields) for entry_id, fields in entries]

    if rows:
        stmt = pg_insert(PredictionEvent).values(
            [
                {
                    "stream_entry_id": r.stream_entry_id,
                    "model_name": r.model_name,
                    "model_version": r.model_version,
                    "prediction": r.prediction,
                    "ground_truth": r.ground_truth,
                    "latency_ms": r.latency_ms,
                    "event_timestamp": r.event_timestamp,
                    "ingested_at": r.ingested_at,
                }
                for r in rows
            ]
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["stream_entry_id"])
        session.execute(stmt)
        session.commit()

    entry_ids = [entry_id for entry_id, _ in entries]
    client.xack(stream_name, group_name, *entry_ids)

    return len(rows)


def ensure_schema_and_table(engine) -> None:
    """Create the monitoring schema (if missing) and all tables defined
    on Base - same pattern as database.load_staging.ensure_schema_and_table."""
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS monitoring"))
        conn.commit()
    Base.metadata.create_all(engine, checkfirst=True)


def run(once: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    config = load_config()
    client = get_redis_client(config)
    engine = get_engine(config)
    ensure_schema_and_table(engine)

    stream_cfg = config["streaming"]
    stream_name = stream_cfg["stream_name"]
    group_name = stream_cfg["consumer_group"]
    batch_size = stream_cfg["consumer_batch_size"]

    ensure_consumer_group(client, stream_name, group_name)

    total = 0
    with Session(engine) as session:
        while True:
            n = consume_batch(client, session, stream_name, group_name, batch_size)
            total += n
            if once and n == 0:
                break
            if once:
                continue  # drain everything currently pending, then the next 0-read breaks the loop
            if n == 0:
                continue  # continuous mode: XREADGROUP's block=1000 already paced this, just keep polling

    logger.info("Consumed %d prediction event(s) into PostgreSQL", total)
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Consume prediction events from the Redis stream into PostgreSQL.")
    parser.add_argument(
        "--once", action="store_true", help="Drain what's currently available, then exit (used by tests/CI)."
    )
    args = parser.parse_args()
    run(once=args.once)


if __name__ == "__main__":
    main()
