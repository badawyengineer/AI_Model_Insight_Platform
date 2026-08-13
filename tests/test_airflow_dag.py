"""
test_airflow_dag.py

Structural tests for orchestration/dags/ai_model_insight_pipeline_dag.py:
that it parses without import errors, has no cycles, and wires the
expected task dependency chain. Skipped entirely if apache-airflow
isn't installed in the current environment (it's an optional,
separately-installed dependency - see orchestration/README.md - not
part of requirements.txt, to keep the core project's install
lightweight).

Note: this pipeline's own top-level folder is named `orchestration/`,
not `airflow/`, specifically so it can never shadow the real installed
`airflow` package on sys.path (a folder literally named `airflow/` at
the repo root does exactly that whenever the repo root is importable -
e.g. during `pytest` collection from the repo root - and silently
breaks `import airflow` for everyone, with or without apache-airflow
installed).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow", reason="apache-airflow is an optional dependency - see orchestration/README.md")

DAG_PATH = Path(__file__).parents[1] / "orchestration" / "dags" / "ai_model_insight_pipeline_dag.py"


@pytest.fixture(scope="module")
def dag():
    spec = importlib.util.spec_from_file_location("ai_model_insight_pipeline_dag", DAG_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.dag


def test_dag_loads_without_import_errors(dag):
    assert dag.dag_id == "ai_model_insight_pipeline"


def test_dag_has_no_cycles(dag):
    # DAG construction itself raises AirflowDagCycleException on a cycle,
    # but topological_sort is a direct, explicit check that also
    # confirms every task is reachable in dependency order.
    task_ids = [t.task_id for t in dag.topological_sort()]
    assert set(task_ids) == set(dag.task_dict.keys())


def test_dag_has_expected_pipeline_stages(dag):
    task_ids = set(dag.task_dict.keys())
    expected_fixed_stages = {
        "generate_synthetic_data",
        "extract_mlflow_metadata",
        "run_etl",
        "load_staging",
        "build_dim_date",
        "transform_load",
        "apply_analytics_sql",
    }
    assert expected_fixed_stages.issubset(task_ids)

    training_tasks = [t for t in task_ids if t.startswith("train_")]
    assert len(training_tasks) >= 5, "Milestone 7 requires >=5 experiment configs"


def test_generate_precedes_training_precedes_extraction(dag):
    generate = dag.get_task("generate_synthetic_data")
    extract = dag.get_task("extract_mlflow_metadata")

    training_task_ids = {t for t in dag.task_dict if t.startswith("train_")}

    # generate_synthetic_data has no upstream dependencies
    assert not generate.upstream_task_ids

    # every training task depends (directly) on generate_synthetic_data
    for task_id in training_task_ids:
        task = dag.get_task(task_id)
        assert "generate_synthetic_data" in task.upstream_task_ids

    # extract_mlflow_metadata depends on every training task
    assert training_task_ids == extract.upstream_task_ids


def test_downstream_chain_order(dag):
    """run_etl -> load_staging -> build_dim_date -> transform_load -> apply_analytics_sql"""
    chain = ["run_etl", "load_staging", "build_dim_date", "transform_load", "apply_analytics_sql"]
    for upstream_id, downstream_id in zip(chain, chain[1:]):
        downstream_task = dag.get_task(downstream_id)
        assert upstream_id in downstream_task.upstream_task_ids


def test_all_tasks_use_bash_operator_against_project_python(dag):
    """Every task should shell out via BashOperator (see module docstring
    for why: keeps torch/mlflow out of the Airflow worker's own env)."""
    from airflow.operators.bash import BashOperator

    for task in dag.tasks:
        assert isinstance(task, BashOperator)
        assert "python" in task.bash_command.lower()
