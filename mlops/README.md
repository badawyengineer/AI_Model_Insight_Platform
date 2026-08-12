# mlops/ — Milestone 7: Real ML Experiments & MLOps Integration

- `experiments/` — the training workload: model, data loading, metrics,
  and `train.py`, the config-driven entrypoint. Configs live in
  `experiments/configs/*.yaml`.
- `mlflow/` — `tracking.py` (MLflow init + system/resource metadata
  capture) and `extract_runs.py` (MLflow → `ExperimentRecord`-shaped JSON,
  which feeds the existing `etl/` pipeline unmodified).
- `pipeline/` — `run_mlops_pipeline.py`, the end-to-end orchestrator that
  chains training → extraction → the existing ETL/staging/warehouse steps.

See the repo root `README.md`'s "Milestone 7" section for exact commands.
