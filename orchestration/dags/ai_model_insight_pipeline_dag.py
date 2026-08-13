"""
ai_model_insight_pipeline_dag.py

Milestone 8: orchestrates the full AI Model Insight Platform pipeline as
an Airflow DAG, instead of running each Milestone 1-7 stage as a
separate manual command.

Design choice - BashOperator, not PythonOperator:
Every task shells out to a Python interpreter (configurable via the
`ai_model_insight_python_bin` Airflow Variable) that already has this
project's dependencies (torch, mlflow, sqlalchemy, ...) installed. The
Airflow *worker* environment itself only needs plain Airflow - it never
imports torch/mlflow/pandas directly. This mirrors how production
Airflow deployments usually run heavy ML workloads (a dedicated
venv/container per job, not baked into the orchestrator's own
environment) and keeps the Airflow install itself small and fast to
set up. See orchestration/README.md for the two Variables this DAG needs.

Pipeline:
    generate_synthetic_data
            |
            v
    [train_exp01, train_exp02, ..., train_expNN]   (one task per YAML config)
            |
            v
    extract_mlflow_metadata
            |
            v
    run_etl (merges synthetic + mlflow raw sources)
            |
            v
    load_staging
            |
            v
    build_dim_date
            |
            v
    transform_load
            |
            v
    apply_analytics_sql
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.models import Variable
from airflow.operators.bash import BashOperator

# --- Configuration ---
# Both are Airflow Variables (Admin -> Variables in the UI, or `airflow
# variables set`) so this DAG file never hardcodes a machine-specific
# path. Sensible local-dev defaults are provided as fallbacks.
PROJECT_DIR = Variable.get(
    "ai_model_insight_project_dir",
    default_var=os.environ.get("AI_MODEL_INSIGHT_PROJECT_DIR", "/opt/ai_model_insight_platform"),
)
PYTHON_BIN = Variable.get(
    "ai_model_insight_python_bin",
    default_var=os.environ.get("AI_MODEL_INSIGHT_PYTHON_BIN", "python3"),
)

CONFIGS_DIR = Path(PROJECT_DIR) / "mlops" / "experiments" / "configs"

# BashOperator's bash_command; {module} runs as `python -m <module>` with
# the project dir as both the cwd (relative paths like config/config.yaml,
# raw_data/... resolve correctly) and on PYTHONPATH (so `import config`,
# `import etl`, etc. work without the project being pip-installed).
_RUN_MODULE = (
    'cd "{project_dir}" && PYTHONPATH="{project_dir}" "{python_bin}" -m {{module}}'
).format(project_dir=PROJECT_DIR, python_bin=PYTHON_BIN)

default_args = {
    "owner": "badawy",
    "retries": 1,
    "retry_delay": 300,  # seconds
}

with DAG(
    dag_id="ai_model_insight_pipeline",
    description="Milestone 8: generate/train -> MLflow -> ETL -> staging -> warehouse -> analytics",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    tags=["ai-model-insight-platform", "mlops", "milestone-8"],
) as dag:

    generate_synthetic_data = BashOperator(
        task_id="generate_synthetic_data",
        bash_command=_RUN_MODULE.format(module="generator.generate_experiments"),
    )

    # One task per experiment config file, so the DAG graph shows each
    # experiment individually (retries/failures are isolated per run)
    # rather than one opaque "train everything" task. Configs are static
    # files checked into the repo, so building this list at DAG-parse
    # time is safe and simpler than Airflow's dynamic task mapping.
    training_tasks = []
    if CONFIGS_DIR.exists():
        for config_file in sorted(CONFIGS_DIR.glob("*.yaml")):
            task = BashOperator(
                task_id=f"train_{config_file.stem}",
                bash_command=_RUN_MODULE.format(
                    module=f"mlops.experiments.train --config mlops/experiments/configs/{config_file.name}"
                ),
            )
            training_tasks.append(task)

    extract_mlflow_metadata = BashOperator(
        task_id="extract_mlflow_metadata",
        bash_command=_RUN_MODULE.format(module="mlops.mlflow.extract_runs"),
    )

    run_etl = BashOperator(
        task_id="run_etl",
        bash_command=_RUN_MODULE.format(module="etl.run_etl --include-mlflow"),
    )

    load_staging = BashOperator(
        task_id="load_staging",
        bash_command=_RUN_MODULE.format(module="database.load_staging"),
    )

    build_dim_date = BashOperator(
        task_id="build_dim_date",
        bash_command=_RUN_MODULE.format(module="warehouse.build_dim_date"),
    )

    transform_load = BashOperator(
        task_id="transform_load",
        bash_command=_RUN_MODULE.format(module="warehouse.transform_load"),
    )

    apply_analytics_sql = BashOperator(
        task_id="apply_analytics_sql",
        bash_command=_RUN_MODULE.format(module="warehouse.apply_analytics"),
    )

    if training_tasks:
        generate_synthetic_data >> training_tasks >> extract_mlflow_metadata
    else:
        generate_synthetic_data >> extract_mlflow_metadata

    (
        extract_mlflow_metadata
        >> run_etl
        >> load_staging
        >> build_dim_date
        >> transform_load
        >> apply_analytics_sql
    )
