"""
test_monitoring_dag.py

Structural tests for orchestration/dags/monitoring_pipeline_dag.py -
same pattern as test_airflow_dag.py, covering the second DAG added in
Milestone 11. Skipped entirely if apache-airflow isn't installed.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytest.importorskip("airflow", reason="apache-airflow is an optional dependency - see orchestration/README.md")

DAG_PATH = Path(__file__).parents[1] / "orchestration" / "dags" / "monitoring_pipeline_dag.py"


@pytest.fixture(scope="module")
def dag():
    spec = importlib.util.spec_from_file_location("monitoring_pipeline_dag", DAG_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.dag


def test_dag_loads_without_import_errors(dag):
    assert dag.dag_id == "ai_model_insight_monitoring"


def test_dag_has_no_cycles(dag):
    task_ids = [t.task_id for t in dag.topological_sort()]
    assert set(task_ids) == set(dag.task_dict.keys())


def test_dag_has_consume_and_at_least_one_drift_check_task(dag):
    task_ids = set(dag.task_dict.keys())
    assert "consume_prediction_events" in task_ids

    drift_tasks = [t for t in task_ids if t.startswith("check_drift_")]
    assert len(drift_tasks) >= 1


def test_every_drift_check_depends_on_consume(dag):
    consume = dag.get_task("consume_prediction_events")
    drift_task_ids = {t for t in dag.task_dict if t.startswith("check_drift_")}

    for task_id in drift_task_ids:
        task = dag.get_task(task_id)
        assert "consume_prediction_events" in task.upstream_task_ids

    assert not consume.upstream_task_ids  # nothing runs before it


def test_dag_schedule_is_more_frequent_than_daily_pipeline(dag):
    """Milestone 11's whole point is not waiting for the next daily
    batch run - confirm the schedule is actually tighter than @daily."""
    assert dag.schedule_interval != "@daily"
    assert dag.schedule_interval == "*/15 * * * *"
