# mlops/mlflow/

- `tracking.py` — `init_mlflow()` (sets tracking URI + experiment name,
  config-driven, `MLFLOW_TRACKING_URI` env var overrides) and
  `get_system_metadata()` (CPU/RAM/GPU/Python/PyTorch version capture,
  used both for MLflow logging and for populating the `gpu`/`cpu`/`ram_gb`
  fields on extracted `ExperimentRecord`s).
- `extract_runs.py` — reads every run in the configured MLflow experiment
  via `MlflowClient` and converts each into an `ExperimentRecord`-shaped
  dict, written to `raw_data/mlflow_runs_raw.json`. This is the *only*
  bridge between MLflow and the rest of the platform — everything
  downstream (`etl/`, `database/`, `warehouse/`) is the existing,
  unmodified Milestone 3-5 code.

Run standalone (after at least one training run has happened):

```bash
python -m mlops.mlflow.extract_runs
```
