"""Проверка DAG: импортируется без ошибок, задачи и зависимости соответствуют требованиям."""
from pathlib import Path

import pytest

pytest.importorskip("airflow")
pytest.importorskip("sqlalchemy")

from airflow.models import DagBag  # noqa: E402


@pytest.fixture(scope="module")
def dag():
    bag = DagBag(dag_folder=str(Path(__file__).resolve().parents[1] / "dags"), include_examples=False)
    assert not bag.import_errors, bag.import_errors
    return bag.get_dag("podcast_etl_pipeline")


def test_tasks_and_dependencies(dag):
    assert [t.task_id for t in dag.topological_sort()] == ["extract_data", "transform_data", "quality_check", "load_data"]
    assert dag.get_task("quality_check").downstream_task_ids == {"load_data"}   # FR-4.3: load только после DQ


def test_retries_schedule_and_callbacks(dag):
    assert dag.default_args["retries"] >= 1                                     # NFR-5
    assert dag.schedule_interval == "@daily"                                    # FR-4.1
    assert dag.catchup is False and dag.max_active_runs == 1
    assert dag.on_success_callback is not None
    assert dag.default_args["on_failure_callback"] is not None                  # уведомления


def test_params_allow_manual_override(dag):
    assert {"search_term", "limit", "load_mode"} <= set(dag.params)             # FR-4.2
