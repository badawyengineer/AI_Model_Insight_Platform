# orchestration/ — Milestone 8: Airflow Orchestration

Schedules and monitors the full pipeline (generate/train → MLflow → ETL →
staging → warehouse → analytics) as an Airflow DAG instead of running each
Milestone 1-7 stage as a separate manual command.

> **Why this folder isn't named `airflow/`:** a folder literally named
> `airflow/` at the repo root shadows the real installed `airflow` package
> for any code (including `pytest`) run with the repo root on `sys.path`.
> This bit us during development — every `import airflow` silently resolved
> to our own empty folder instead of the real package. `orchestration/`
> avoids the collision entirely.

## Design

Every task in `dags/ai_model_insight_pipeline_dag.py` is a `BashOperator`
that shells out to a Python interpreter with this project's dependencies
installed (`torch`, `mlflow`, `sqlalchemy`, ...) — **not** the Airflow
worker's own environment. This means:

- Airflow itself only needs a plain `pip install apache-airflow` — it never
  imports torch/mlflow/pandas directly, so the orchestrator stays small and
  fast to set up.
- The project's own venv (from the repo root `requirements.txt`) can be
  managed completely independently of Airflow's.

This mirrors how ML training is usually run under Airflow in production
(a dedicated venv/container per job) rather than baking heavy ML
dependencies into the scheduler's own environment.

## Pipeline

```
generate_synthetic_data
        |
        v
[train_exp01_baseline, train_exp02_high_lr, ...]   (one task per YAML config)
        |
        v
extract_mlflow_metadata
        |
        v
run_etl  (--include-mlflow: merges synthetic + mlflow raw sources)
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
```

## Setup

Airflow has its own, fairly strict dependency pinning, so install it in a
**separate venv** from the project's main one (`requirements.txt` doesn't
include `apache-airflow` for this reason):

```bash
python -m venv airflow_venv
source airflow_venv/bin/activate   # airflow_venv\Scripts\activate on Windows

AIRFLOW_VERSION=2.10.5
PYTHON_VERSION="$(python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
CONSTRAINT_URL="https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"
pip install "apache-airflow==${AIRFLOW_VERSION}" --constraint "${CONSTRAINT_URL}"
```

Point Airflow at this project's DAG and initialize its metadata DB:

```bash
export AIRFLOW_HOME=~/airflow_home     # anywhere you like
mkdir -p "$AIRFLOW_HOME/dags"
cp orchestration/dags/ai_model_insight_pipeline_dag.py "$AIRFLOW_HOME/dags/"
airflow db migrate
airflow users create --username admin --password admin --firstname A --lastname B --role Admin --email admin@example.com
```

Set the two Airflow Variables the DAG needs (path to this repo, and the
path to the *project's own* venv's Python — not Airflow's):

```bash
airflow variables set ai_model_insight_project_dir /absolute/path/to/AI_Model_Insight_Platform
airflow variables set ai_model_insight_python_bin /absolute/path/to/AI_Model_Insight_Platform/venv/bin/python
```

Make sure `DB_PASSWORD` (and `MLFLOW_TRACKING_URI`, if you're not using the
default local SQLite store) are set in whatever environment the Airflow
**worker/scheduler** process runs under — the tasks inherit that
environment when they shell out.

Start Airflow (standalone mode, good for local development):

```bash
airflow standalone
```

Then open the UI (usually `http://localhost:8080`), find
`ai_model_insight_pipeline`, and trigger it — or just wait for its daily
schedule.

## Running a single task manually (no scheduler needed)

Useful for testing one stage in isolation:

```bash
airflow tasks test ai_model_insight_pipeline generate_synthetic_data 2026-01-01
airflow tasks test ai_model_insight_pipeline train_exp01_baseline 2026-01-01
airflow tasks test ai_model_insight_pipeline run_etl 2026-01-01
```

## Tests

`tests/test_airflow_dag.py` checks the DAG's structure (no cycles, correct
task dependency chain, every task is a `BashOperator`). It automatically
skips (not fails) if `apache-airflow` isn't installed in whatever venv is
running pytest, since it's an optional dependency of the core project:

```bash
# from the airflow_venv (has apache-airflow installed)
pytest ../AI_Model_Insight_Platform/tests/test_airflow_dag.py -v
```
