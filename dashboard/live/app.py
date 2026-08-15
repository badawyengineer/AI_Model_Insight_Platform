"""
dashboard/live/app.py

Milestone 12: a live monitoring dashboard showing real-time prediction
volume, latency, and drift status for every model flowing through the
Milestone 11 streaming pipeline. Auto-refreshes on an interval so it
reflects new events without a manual reload - this is the "live" half
of Milestone 12's live streaming request.

Deliberately Streamlit (not a full custom frontend): every other custom
UI in this project (the analytical SQL layer, Power BI assets) already
targets a BI-tool audience; this dashboard's job is to show what's
*currently* happening in the streaming/monitoring layer, which is a
different, more operational audience a lightweight Python-only tool
serves well without adding a JS build step to the project.

Usage:
    streamlit run dashboard/live/app.py
"""

from __future__ import annotations

import time

import pandas as pd
import plotly.express as px
import streamlit as st

from config.config_loader import load_config
from dashboard.live.data import (
    get_drift_status,
    get_latency_summary,
    get_monitored_models,
    get_recent_predictions,
)
from database.db_connection import get_engine

st.set_page_config(page_title="AI Model Insight — Live Monitoring", layout="wide")


@st.cache_resource
def _get_engine():
    return get_engine(load_config())


def _psi_badge(psi: float, threshold: float) -> str:
    if psi > threshold:
        return f"🔴 DRIFT DETECTED (PSI={psi:.4f}, threshold={threshold})"
    return f"🟢 Stable (PSI={psi:.4f}, threshold={threshold})"


def render() -> None:
    st.title("Live Model Monitoring")
    st.caption(
        "Real-time prediction events consumed from the Redis stream (Milestone 11) "
        "into PostgreSQL. Auto-refreshes every 10 seconds."
    )

    config = load_config()
    engine = _get_engine()
    psi_threshold = config["monitoring"]["psi_drift_threshold"]

    models_df = get_monitored_models(engine)

    if models_df.empty:
        st.info(
            "No prediction events yet. Publish some with:\n\n"
            "`python -m streaming.producer --simulate 400 --drift-after 200`\n\n"
            "then consume them with:\n\n"
            "`python -m streaming.consumer --once`"
        )
        return

    st.subheader("Monitored models")
    st.dataframe(models_df, use_container_width=True, hide_index=True)

    st.divider()

    minutes_window = st.slider("Time window (minutes)", min_value=5, max_value=1440, value=60, step=5)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Prediction volume")
        recent_df = get_recent_predictions(engine, minutes=minutes_window)
        if recent_df.empty:
            st.write("No events in this window.")
        else:
            recent_df["event_timestamp"] = pd.to_datetime(recent_df["event_timestamp"])
            volume = (
                recent_df.set_index("event_timestamp")
                .groupby([pd.Grouper(freq="1min"), "model_name"])
                .size()
                .reset_index(name="count")
            )
            fig = px.line(volume, x="event_timestamp", y="count", color="model_name", markers=True)
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Latency (p50 / p95)")
        latency_df = get_latency_summary(engine, minutes=minutes_window)
        if latency_df.empty:
            st.write("No events in this window.")
        else:
            st.dataframe(latency_df, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Drift status")

    for _, row in models_df.iterrows():
        status = get_drift_status(engine, row["model_name"], row["model_version"])
        label = f"{row['model_name']} / {row['model_version']}"
        if not status["has_enough_data"]:
            st.write(
                f"**{label}**: not enough events yet for a drift check "
                f"({status['event_count']}/{status['events_needed']})"
            )
        else:
            st.write(f"**{label}**: {_psi_badge(status['psi'], psi_threshold)}")

    st.divider()
    st.caption(f"Last refreshed: {pd.Timestamp.now(tz='UTC').strftime('%Y-%m-%d %H:%M:%S UTC')}")


render()
time.sleep(10)
st.rerun()
