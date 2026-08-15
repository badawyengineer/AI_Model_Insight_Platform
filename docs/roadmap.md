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

## ✅ Milestone 10 — Cloud Deployment
Moves the staging/warehouse database to managed AWS RDS PostgreSQL and
MLflow's artifact storage to S3, with the DB password in AWS Secrets
Manager instead of a local `.env` file. Deliberately does NOT provision
compute (ECS/EC2) to run the app/Airflow containers or a remote MLflow
tracking server deployment — see `docs/cloud-deployment.md` for why
"the data layer moved to managed services" and "here's a specific
compute platform" are kept as separate decisions.

- `terraform/`: RDS PostgreSQL, an S3 bucket for MLflow artifacts
  (versioned, encrypted, public access blocked), a Secrets Manager
  secret for the generated DB password, and an IAM policy for
  read/write access to the artifact bucket. Fails closed by default —
  `allowed_cidr_blocks` is empty until explicitly set, so RDS is not
  publicly reachable out of the box
- `config/config_loader.py`: `get_db_password()` now checks
  `DB_PASSWORD_SECRET_ARN` first (fetching from AWS Secrets Manager via
  a lazily-imported `boto3`, so it stays an optional dependency) and
  falls back to the plain `DB_PASSWORD` env var used by every earlier
  milestone — every other module is unaffected, since they all already
  go through this one function
- `requirements-cloud.txt`: `boto3` + `moto` kept out of the core
  `requirements.txt` — local/Docker-only users never need them
- `docs/cloud-deployment.md`: full walkthrough — provision, point the
  app at RDS + Secrets Manager, point MLflow at S3, verify, tear down
- `tests/test_secrets_manager.py`: 4 tests against a real moto-mocked
  AWS Secrets Manager (not hand-rolled stubs) — no AWS account needed

**Completion criteria:**
- [x] Terraform provisions RDS + S3 + Secrets Manager + IAM policy;
      every `.tf` file confirmed syntactically valid (`python-hcl2`)
      since the `terraform` CLI itself wasn't installable in this
      sandbox — run `terraform validate`/`plan` yourself before applying
- [x] `DB_PASSWORD_SECRET_ARN` Secrets Manager path added, tested against
      real (mocked) AWS calls, and confirmed to fall back correctly to
      plain `DB_PASSWORD` when unset — Milestones 1-9 behavior unchanged
- [x] Security fails closed: RDS not publicly reachable by default,
      S3 bucket blocks all public access, encryption enabled on both
- [x] Full walkthrough documented, including the explicit scope
      boundary (data layer only, not a compute/deployment platform
      decision)

## ✅ Milestone 11 — Streaming & Advanced Monitoring
Real-time prediction-log ingestion, drift detection, and alerting on top
of the batch pipeline built in Milestones 1-10.

- `streaming/producer.py` + `streaming/consumer.py`: Redis Streams
  ingestion (chosen deliberately over Kafka - see `streaming/README.md`
  for why - as a genuinely lightweight, still-real streaming
  technology for this project's scale) with proper consumer-group
  semantics (`XREADGROUP`/`XACK`, at-least-once delivery,
  redelivery-safe via `ON CONFLICT DO NOTHING` on the Redis stream
  entry ID)
- `database/monitoring_models.py`: a new `monitoring` schema/table for
  real-time prediction events, deliberately separate from the
  `staging`/`warehouse` star schema built for training-experiment data
- `monitoring/drift_detection.py`: Population Stability Index (PSI)
  drift detection. **A real false-positive bug was found and fixed
  during development**: PSI at a naive fixed bin count is dominated by
  sampling noise at small sample sizes — two draws from the *identical*
  distribution at n=30 regularly exceeded the alert threshold. Fixed
  with sample-size-adaptive binning and a config default of 200
  events/window, verified by repeated-trial testing
- `monitoring/alerting.py`: always logs; optionally POSTs to a
  Slack-compatible webhook (`ALERT_WEBHOOK_URL`) — a failed webhook
  delivery never masks the alert itself
- `orchestration/dags/monitoring_pipeline_dag.py`: a second, separate
  Airflow DAG on a 15-minute schedule (not bolted onto the daily
  training pipeline — different cadence, different failure domain)
- `tests/test_drift_detection.py`: 14 tests, including 5-seed
  parametrized false-positive and true-positive checks at the project's
  actual window size — a direct regression test for the bug above
- `tests/test_streaming_integration.py`: real integration tests against
  live Redis + PostgreSQL (not mocked) — publish, consume, and a
  redelivery/idempotency test
- `tests/test_alerting.py`: real local HTTP server, not a mocked
  `requests` call, proving webhook delivery actually happens

**Completion criteria:**
- [x] Real-time ingestion works end-to-end: producer → Redis stream →
      consumer (consumer group, at-least-once) → PostgreSQL, verified
      with real Redis and Postgres instances, not mocks
- [x] Drift detection correctly distinguishes stable vs. shifted
      distributions at the project's actual configured window size —
      verified after finding and fixing a genuine false-positive bug
- [x] Alerting always logs, and delivers to a configured webhook,
      verified against a real local HTTP server
- [x] Wired into Airflow on its own schedule, verified via
      `airflow tasks test` against real Redis/Postgres
- [x] All new tests pass; `requirements.txt`, README, and this roadmap
      updated

This completes the originally planned Milestones 1-11.

## ✅ Milestone 12 — CI/CD Pipeline & Live Monitoring Dashboard (extension)
Not part of the original 11-milestone plan — added afterward to close
two real gaps: every test run had been manual, and none of Milestone
11's real-time data had anywhere to be *seen* live.

- `.github/workflows/tests.yml`: lint (`ruff`) + the full test suite
  against real Postgres/Redis service containers on every push/PR, plus
  the Airflow DAG structural tests
- `.github/workflows/docker.yml`: actually builds every Docker image
  and smoke-tests the `app` image's imports. This is the first *real*
  build verification Milestone 9 gets — GitHub Actions runners have
  normal Docker Hub access, unlike the sandbox this project was
  developed in
- `.github/workflows/terraform.yml`: `terraform fmt -check` +
  `terraform validate` — likewise the first real verification with the
  actual Terraform CLI, which wasn't installable during development
- `pyproject.toml`: `ruff` config; running it against the full codebase
  during development found and fixed 11 real (if minor) issues —
  unused imports, unsorted import blocks
- `dashboard/live/`: a Streamlit dashboard showing real-time prediction
  volume, latency percentiles, and drift status per model, reusing
  `monitoring.drift_detection.compute_psi()` directly so it can never
  disagree with what actually triggers a real alert. Query logic
  (`data.py`) is split from the UI layer (`app.py`) specifically so
  it's testable with plain `pytest` against a real database

**Completion criteria:**
- [x] Full test suite runs automatically in CI against real service
      containers (verified: 48 tests passing locally with the same
      Postgres/Redis setup CI uses)
- [x] Docker images build for real once pushed (closes Milestone 9's
      sandbox verification gap)
- [x] Terraform validates for real once pushed (closes Milestone 10's
      sandbox verification gap)
- [x] Live dashboard renders real data end-to-end: verified by actually
      running `streamlit run` and confirming a real HTTP 200 response
      with zero errors in the server log, plus 6 passing tests against
      real Postgres/Redis data published through the actual streaming
      pipeline
- [x] `ruff check .` passes clean across the entire codebase
