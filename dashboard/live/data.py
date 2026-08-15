"""
dashboard/live/data.py

Milestone 12: query functions backing the live monitoring dashboard
(dashboard/live/app.py). Deliberately separated from the Streamlit UI
code - these are plain functions returning pandas DataFrames/dicts, so
they're testable with ordinary pytest against a real database, without
needing to drive a Streamlit server to verify the data is correct.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
from sqlalchemy import text
from sqlalchemy.engine import Engine

from monitoring.drift_detection import compute_psi


def get_recent_predictions(engine: Engine, minutes: int = 60, limit: int = 5000) -> pd.DataFrame:
    """Prediction events from the last `minutes` minutes, newest first."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    query = text(
        """
        SELECT model_name, model_version, prediction, ground_truth,
               latency_ms, event_timestamp, ingested_at
        FROM monitoring.prediction_events
        WHERE event_timestamp >= :cutoff
        ORDER BY event_timestamp DESC
        LIMIT :limit
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"cutoff": cutoff, "limit": limit})


def get_monitored_models(engine: Engine) -> pd.DataFrame:
    """Distinct model_name/model_version pairs seen in prediction_events, with event counts."""
    query = text(
        """
        SELECT model_name, model_version, COUNT(*) AS event_count,
               MAX(event_timestamp) AS latest_event
        FROM monitoring.prediction_events
        GROUP BY model_name, model_version
        ORDER BY latest_event DESC
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn)


def get_drift_status(engine: Engine, model_name: str, model_version: str, window_size: int = 200) -> dict:
    """
    Same baseline-vs-recent PSI comparison as monitoring.drift_detection,
    reused directly (not reimplemented) so the dashboard can never show
    a different drift number than what actually triggers an alert.
    Returns a dict rather than the dataclass so it serializes cleanly
    for Streamlit's caching.
    """
    query = text(
        """
        SELECT prediction, event_timestamp FROM monitoring.prediction_events
        WHERE model_name = :model_name AND model_version = :model_version
        ORDER BY event_timestamp ASC
        """
    )
    with engine.connect() as conn:
        df = pd.read_sql(
            query, conn, params={"model_name": model_name, "model_version": model_version}
        )

    if len(df) < window_size * 2:
        return {
            "has_enough_data": False,
            "event_count": len(df),
            "events_needed": window_size * 2,
        }

    baseline = df["prediction"].values[:window_size]
    recent = df["prediction"].values[-window_size:]
    psi = compute_psi(np.array(baseline), np.array(recent))

    return {
        "has_enough_data": True,
        "psi": round(float(psi), 4),
        "baseline_n": window_size,
        "recent_n": window_size,
        "event_count": len(df),
    }


def get_latency_summary(engine: Engine, minutes: int = 60) -> pd.DataFrame:
    """Per-model p50/p95/avg latency over the last `minutes` minutes."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=minutes)
    query = text(
        """
        SELECT
            model_name,
            model_version,
            COUNT(*) AS event_count,
            AVG(latency_ms) AS avg_latency_ms,
            PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50_latency_ms,
            PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95_latency_ms
        FROM monitoring.prediction_events
        WHERE event_timestamp >= :cutoff
        GROUP BY model_name, model_version
        ORDER BY model_name, model_version
        """
    )
    with engine.connect() as conn:
        return pd.read_sql(query, conn, params={"cutoff": cutoff})
