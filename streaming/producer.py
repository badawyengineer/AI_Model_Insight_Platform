"""
streaming/producer.py

Milestone 11: publishes prediction events onto a Redis stream, in place
of a real model-serving layer. Redis Streams (XADD/XREADGROUP), not
Kafka: it's genuinely lightweight to run for a project this size
(a single `apt install redis-server`, no ZooKeeper/KRaft cluster,
no JVM), while still giving the same core properties this milestone
needs - an append-only, replayable, consumer-group-based log. Kafka is
the right call at a scale this project doesn't operate at; the
producer/consumer split here is written the same way either technology
would use it, so swapping in `kafka-python` later would only touch
this file and consumer.py, not any downstream consumer of
PredictionEvent or database.monitoring_models.

Usage:
    python -m streaming.producer --simulate 200
    python -m streaming.producer --simulate 200 --drift-after 100   # inject a distribution shift partway through, for testing drift detection
"""

from __future__ import annotations

import argparse
import logging
import random
from datetime import datetime, timezone

import redis

from config.config_loader import load_config
from streaming.schemas import PredictionEvent

logger = logging.getLogger(__name__)


def get_redis_client(config: dict | None = None) -> redis.Redis:
    config = config or load_config()
    import os

    redis_url = os.environ.get("REDIS_URL", config["streaming"]["redis_url"])
    return redis.Redis.from_url(redis_url, decode_responses=True)


def publish_event(client: redis.Redis, stream_name: str, event: PredictionEvent) -> str:
    """Publish one event to the stream. Returns the Redis-assigned stream entry ID."""
    payload = {k: str(v) for k, v in event.model_dump(mode="json").items()}
    entry_id = client.xadd(stream_name, payload)
    return entry_id


def _simulate_event(drifted: bool, model_name: str = "fraud-detector", model_version: str = "v3") -> PredictionEvent:
    """
    Generates one synthetic prediction event.

    `drifted=True` shifts both the prediction distribution and latency
    upward, so streaming.producer --drift-after can produce a stream
    with a clear, detectable distribution shift partway through - useful
    for exercising monitoring.drift_detection without waiting for a real
    production incident.
    """
    if drifted:
        prediction = max(0.0, min(1.0, random.gauss(0.75, 0.15)))
        latency_ms = max(1.0, random.gauss(180, 40))
    else:
        prediction = max(0.0, min(1.0, random.gauss(0.3, 0.1)))
        latency_ms = max(1.0, random.gauss(45, 10))

    ground_truth = 1.0 if random.random() < prediction else 0.0

    return PredictionEvent(
        model_name=model_name,
        model_version=model_version,
        prediction=round(prediction, 4),
        ground_truth=ground_truth,
        latency_ms=round(latency_ms, 2),
        event_timestamp=datetime.now(timezone.utc),
    )


def simulate(n_events: int, drift_after: int | None, config: dict | None = None) -> int:
    """Publish n_events simulated PredictionEvents. Returns the count published."""
    config = config or load_config()
    client = get_redis_client(config)
    stream_name = config["streaming"]["stream_name"]

    published = 0
    for i in range(n_events):
        drifted = drift_after is not None and i >= drift_after
        event = _simulate_event(drifted=drifted)
        publish_event(client, stream_name, event)
        published += 1

    logger.info(
        "Published %d simulated events to stream '%s'%s",
        published,
        stream_name,
        f" (drift injected after event {drift_after})" if drift_after is not None else "",
    )
    return published


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Publish (simulated) prediction events to the Redis stream.")
    parser.add_argument("--simulate", type=int, required=True, help="Number of synthetic events to publish.")
    parser.add_argument(
        "--drift-after",
        type=int,
        default=None,
        help="Shift the simulated distribution starting at this event index, to exercise drift detection.",
    )
    args = parser.parse_args()
    simulate(args.simulate, args.drift_after)


if __name__ == "__main__":
    main()
