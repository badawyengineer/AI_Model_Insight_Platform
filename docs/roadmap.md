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

## 🔜 Milestone 8 — Orchestration (Airflow)
Schedule and monitor the generator/ETL/staging/warehouse/MLOps pipeline as
a DAG instead of manually-run scripts.

## 🔜 Milestone 9 — Containerization (Docker)
Package the platform (app + Postgres + MLflow) as Docker/Compose services
for one-command local spin-up.

## 🔜 Milestone 10 — Cloud Deployment
Move staging/warehouse to a managed Postgres service and MLflow to a
remote tracking server with cloud artifact storage.

## 🔜 Milestone 11 — Streaming & Advanced Monitoring
Real-time experiment/prediction-log ingestion, drift detection, and
alerting on top of the batch pipeline built in Milestones 1-7.
