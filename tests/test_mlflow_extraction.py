"""
test_mlflow_extraction.py

Tests the MLflow -> ExperimentRecord extraction bridge
(mlops/mlflow/extract_runs.py): runs a tiny real training run into an
isolated tmp MLflow store, extracts it, and validates that the result
both matches the shape extract_runs promises AND passes
database.schemas.ExperimentRecord validation unmodified - proving the
"MLflow metadata can enter the existing ETL architecture" acceptance
criterion end to end.
"""

from __future__ import annotations

from database.schemas import ExperimentRecord
from mlops.experiments.train import train_one_config
from mlops.mlflow.extract_runs import extract_runs
from mlops.mlflow.tracking import init_mlflow


def test_extract_runs_returns_schema_valid_records(tiny_experiment_config, isolated_project_config):
    init_mlflow(isolated_project_config)
    run_id_1 = train_one_config(tiny_experiment_config, isolated_project_config)
    run_id_2 = train_one_config({**tiny_experiment_config, "name": "pytest_tiny_run_2"}, isolated_project_config)

    records = extract_runs(isolated_project_config)
    our_records = [r for r in records if r["mlflow_run_id"] in (run_id_1, run_id_2)]
    assert len(our_records) == 2

    for raw in our_records:
        # This is the exact validation the real ETL pipeline (etl.validate)
        # runs every record through - if this passes, MLflow metadata is
        # confirmed compatible with the existing pipeline end to end.
        record = ExperimentRecord(**raw)
        assert record.source == "mlflow"
        assert record.mlflow_run_id is not None
        assert record.framework == "PyTorch"


def test_extracted_record_experiment_id_is_unique_and_traceable(
    tiny_experiment_config, isolated_project_config
):
    init_mlflow(isolated_project_config)
    run_id = train_one_config(tiny_experiment_config, isolated_project_config)

    records = extract_runs(isolated_project_config)
    matches = [r for r in records if r["mlflow_run_id"] == run_id]
    assert len(matches) == 1
    record = matches[0]

    assert record["experiment_id"] == f"mlflow_{run_id[:16]}"
    assert record["mlflow_experiment_name"] == isolated_project_config["mlops"]["experiment_name"]
    # experiment_id must be unique per run (natural key for dim_experiment)
    assert len({r["experiment_id"] for r in records}) == len(records)


def test_extract_runs_on_nonexistent_experiment_returns_empty(isolated_project_config):
    isolated_project_config["mlops"]["experiment_name"] = "pytest-does-not-exist-experiment-xyz"
    records = extract_runs(isolated_project_config)
    assert records == []
