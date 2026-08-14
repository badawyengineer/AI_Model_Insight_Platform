"""
monitoring_pipeline_dag.py

Milestone 11: consumes prediction events off the Redis stream into
PostgreSQL, then checks each monitored model for drift - on its own,
much shorter schedule (every 15 minutes) than
ai_model_insight_pipeline_dag's daily batch pipeline, since real-time
monitoring is exactly the kind of thing that shouldn't wait for the
next daily run.

Kept as a separate DAG file (not more tasks bolted onto the daily one)
because it has a fundamentally different cadence and failure domain: a
stalled/failed monitoring run shouldn't block or get blocked by the
training/warehouse pipeline, and vice versa.
"""

from __future__ import annotations

import os
from datetime import datetime

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator

PROJECT_DIR = Variable.get(
    "ai_model_insight_project_dir",
    default_var=os.environ.get("AI_MODEL_INSIGHT_PROJECT_DIR", "/opt/ai_model_insight_platform"),
)
PYTHON_BIN = Variable.get(
    "ai_model_insight_python_bin",
    default_var=os.environ.get("AI_MODEL_INSIGHT_PYTHON_BIN", "python3"),
)

# Comma-separated "model_name:model_version" pairs to check for drift
# each run. Defaults match streaming/producer.py's simulated models, so
# this DAG works out of the box against `python -m streaming.producer
# --simulate ...` output without extra setup - point
# monitored_models at your real deployed models in production.
MONITORED_MODELS = Variable.get(
    "ai_model_insight_monitored_models",
    default_var="fraud-detector:v3,churn-predictor:v1",
).split(",")

_RUN_MODULE = (
    'cd "{project_dir}" && PYTHONPATH="{project_dir}" "{python_bin}" -m {{module}}'
).format(project_dir=PROJECT_DIR, python_bin=PYTHON_BIN)

default_args = {
    "owner": "badawy",
    "retries": 2,
    "retry_delay": 60,
}

with DAG(
    dag_id="ai_model_insight_monitoring",
    description="Milestone 11: consume prediction events -> check each monitored model for drift",
    default_args=default_args,
    schedule="*/15 * * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ai-model-insight-platform", "mlops", "milestone-11"],
) as dag:

    consume_prediction_events = BashOperator(
        task_id="consume_prediction_events",
        bash_command=_RUN_MODULE.format(module="streaming.consumer --once"),
    )

    for pair in MONITORED_MODELS:
        pair = pair.strip()
        if not pair or ":" not in pair:
            continue
        model_name, model_version = pair.split(":", 1)
        # task_id can't contain most punctuation - sanitize to underscores
        safe_id = f"{model_name}_{model_version}".replace("-", "_").replace(".", "_")

        check_drift = BashOperator(
            task_id=f"check_drift_{safe_id}",
            bash_command=_RUN_MODULE.format(
                module=f"monitoring.drift_detection --model-name {model_name} --model-version {model_version}"
            ),
        )
        consume_prediction_events >> check_drift
