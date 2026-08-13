# Roadmap — AI Model Insight Platform

This project evolves in milestones, from a data-warehouse foundation to a
full AI/MLOps observability platform. Each milestone builds on the previous
one's code rather than replacing it.

## ✅ Milestone 1 — Project Foundation & Schema Design
- Config system (`config/config.yaml` + `config_loader.py`)
- `database/schemas.py`: `ExperimentRecord` Pydantic model, the single
  source of truth for the shape of an experiment record

## ✅ Milestone 2 — Synthetic Experiment Data Generator
- `generator/`: Faker-driven synthetic experiment log generator, producing
  internally-consistent `ExperimentRecord`s

## ✅ Milestone 3 — Python ETL Pipeline
- `etl/`: extract → validate → clean stages, with a rejects file for audit

## ✅ Milestone 4 — PostgreSQL Staging Layer
- `database/staging_models.py` + `load_staging.py`: disposable, re-runnable
  staging table loaded from the clean ETL output

## ✅ Milestone 5 — Star Schema Data Warehouse
- `warehouse/warehouse_models.py` + `transform_load.py`: dimensional model
  (`dim_model`, `dim_dataset`, `dim_hardware`, `dim_framework`,
  `dim_researcher`, `dim_experiment`, `dim_date`) and `fact_training_run`

## ✅ Milestone 6 — Analytical SQL Layer
- `warehouse/analytics.sql`: performance indexes + views (executive KPIs,
  model leaderboard, training timeline, etc.) using CTEs and window
  functions, ready for Power BI to query directly

## ✅ Milestone 7 — Real ML Experiment Tracking & MLOps Integration
Evolved the platform from synthetic-data-only into one that also ingests
**real** ML experiments, without touching Milestones 1-6's behavior.

- `mlops/experiments/`: a config-driven PyTorch CNN trained on CIFAR-10
  (with an automatic same-shaped offline fallback dataset so training never
  requires network access), at least 5 reproducible experiment configs
  under `mlops/experiments/configs/*.yaml`
- `mlops/mlflow/tracking.py`: MLflow init + CPU/GPU/RAM/software-version
  system metadata capture (GPU never required)
- `mlops/mlflow/extract_runs.py`: converts MLflow run metadata into the
  exact same `ExperimentRecord` shape the synthetic generator produces, so
  it flows through the **existing, unmodified** ETL → staging → warehouse
  pipeline (no second/parallel pipeline was created)
- `database/schemas.py`, `staging_models.py`, `warehouse_models.py`:
  minimally extended with additive, defaulted `source` /
  `mlflow_run_id` / `mlflow_experiment_name` fields so every
  Milestone 1-6 record and code path keeps working unchanged
- `etl/run_etl.py --include-mlflow`: opt-in merge of MLflow-extracted
  records alongside the synthetic generator's output; default behavior
  (no flag) is byte-for-byte the Milestone 1-6 behavior
- `mlops/pipeline/run_mlops_pipeline.py`: one-command end-to-end
  orchestration (train → extract → ETL → staging → warehouse), built
  entirely out of calls to the existing Milestone 3-5 entry points
- `warehouse/analytics.sql`: added `vw_experiment_source_breakdown`,
  comparing synthetic vs. real MLflow-tracked runs
- `tests/`: pytest suite covering experiment config validity, the real
  training loop's MLflow logging, system metadata capture, MLflow→ETL
  schema compatibility, and the ETL merge logic — no GPU or live
  database required for most tests

**Completion criteria** (see also Milestone 7's acceptance checklist in the
implementation notes):
- [x] Milestones 1-6 still work unmodified
- [x] At least 5 real, reproducible ML experiments run and are tracked
- [x] Parameters, metrics, artifacts, and system metadata are logged to MLflow
- [x] CPU-only execution works (GPU opportunistic, never required)
- [x] MLflow run metadata can be extracted programmatically and validated
      against the existing `ExperimentRecord` schema unmodified
- [x] MLflow-sourced data flows through the existing ETL → PostgreSQL
      staging → star-schema warehouse
- [x] Tests added and passing; `requirements.txt`, README, and this roadmap
      updated; no secrets committed

## ✅ Milestone 8 — Orchestration (Airflow)
Schedules and monitors the full pipeline as a DAG instead of manually-run
scripts, without loading any ML dependencies into the Airflow worker
itself.

- `orchestration/dags/ai_model_insight_pipeline_dag.py`: one `BashOperator`
  task per stage (`generate_synthetic_data` → one task per experiment
  config → `extract_mlflow_metadata` → `run_etl --include-mlflow` →
  `load_staging` → `build_dim_date` → `transform_load` →
  `apply_analytics_sql`), each shelling out to the project's own venv
  (configurable via the `ai_model_insight_project_dir` /
  `ai_model_insight_python_bin` Airflow Variables) rather than requiring
  torch/mlflow inside Airflow's own environment
- `warehouse/apply_analytics.py`: new `python -m` entry point for
  `analytics.sql` (previously a manual `psql -f` step), so the analytics
  layer has the same scriptable interface as every other stage
- `tests/test_airflow_dag.py`: DAG structure tests (no cycles, correct
  dependency chain, every task is a `BashOperator`) — auto-skips if
  `apache-airflow` isn't installed, since it's an optional dependency kept
  out of the core `requirements.txt`
- `tests/test_apply_analytics.py`: regression test against a real bug
  found during development — a naive comment-stripping filter silently
  dropped every `CREATE VIEW` statement (each has a comment header) while
  `CREATE INDEX` statements kept working, so the failure was easy to miss

**Note:** this folder is named `orchestration/`, not `airflow/` — a folder
literally named `airflow/` at the repo root shadows the real installed
`airflow` package for any code (including `pytest`) run with the repo
root on `sys.path`. Caught this exact collision during development.

**Completion criteria:**
- [x] Full pipeline runs as an Airflow DAG (13 tasks: generate + 6 training
      + extract + ETL + staging + build_dim_date + transform_load + analytics)
- [x] Verified end-to-end via `airflow tasks test` against a real Postgres
      instance: every task succeeds, and the resulting warehouse data
      matches what running the stages manually produces
- [x] DAG structure tests added and passing
- [x] Airflow kept as an isolated, optional dependency (own venv, own
      constraints file) — the core project's `requirements.txt` is unchanged

## ✅ Milestone 9 — Containerization (Docker)
Packages the platform as Docker/Compose services for one-command local
spin-up, replacing the manual "install Postgres, create a venv, install
Airflow in a second venv" setup used through Milestone 8.

- `docker/app.Dockerfile`: the project's full code + dependencies
  (torch, mlflow, sqlalchemy, ...). Every pipeline stage runs from this
  one image via `docker compose run --rm app python -m <module>` — no
  per-stage image, no hidden "run everything" entrypoint
- `docker/mlflow.Dockerfile`: a standalone, deliberately lightweight
  MLflow tracking server (no torch) reachable over the network at
  `http://mlflow:5000`, instead of a per-container local sqlite file
- `docker/airflow.Dockerfile`: extends `apache/airflow` with this
  project's `requirements.txt` installed directly into it — inside
  Docker every service is already isolated per-container, so (unlike
  the bare-metal setup in `orchestration/README.md`) there's no reason
  to keep Airflow and the project in separate images
- `docker/postgres/init-airflow-db.sh`: creates a second `airflow`
  database alongside the app's `ai_model_insight` one, so a single
  Postgres container serves both
- `docker-compose.yml`: wires all 6 services (`postgres`, `mlflow`,
  `app`, `airflow-init`, `airflow-webserver`, `airflow-scheduler`)
  together — healthchecks, `depends_on` conditions, a shared YAML
  anchor for the three Airflow services' environment (so they can't
  drift apart), and named volumes for data persistence
- `database/db_connection.py`: added `DB_HOST`/`DB_PORT` environment
  overrides (on top of `config.yaml`'s `localhost` default) — Postgres
  is reachable by its Compose service name, not `localhost`, without
  hardcoding that into `config.yaml`
- `tests/test_docker_compose.py`, `tests/test_db_connection.py`:
  validate the compose file's structure and the new env-var override
  logic without needing container-registry access

**Completion criteria:**
- [x] `docker-compose.yml` + all 3 Dockerfiles validated: YAML parses,
      `docker compose config` fully resolves (env interpolation, the
      shared Airflow anchor, volumes, `depends_on` conditions), and
      every Dockerfile was confirmed syntactically valid by Docker
      itself (each build reached and only failed at the final
      "pull the base image from Docker Hub" step, in a sandboxed dev
      environment whose network policy blocks registry access — not a
      configuration error)
- [x] `DB_HOST`/`DB_PORT` overrides added and tested; bare-metal setups
      that don't set them are unaffected
- [x] Structural tests added and passing
- [ ] Actual `docker compose build`/`up` end-to-end run — needs
      verifying in an environment with real Docker Hub access (see
      `docker/README.md`)

## 🔜 Milestone 10 — Cloud Deployment
Move staging/warehouse to a managed Postgres service and MLflow to a
remote tracking server with cloud artifact storage.

## 🔜 Milestone 11 — Streaming & Advanced Monitoring
Real-time experiment/prediction-log ingestion, drift detection, and
alerting on top of the batch pipeline built in Milestones 1-7.
