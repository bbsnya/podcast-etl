"""DAG конвейера подкастов: extract_data → transform_data → quality_check → load_data."""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.models.param import Param
from airflow.operators.python import PythonOperator

from src import config, pipeline
from src.notifications import dag_success_callback, task_failure_callback

default_args = {
    "owner": "student",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 3,                           # NFR-5: автоматический перезапуск при сбое
    "retry_delay": timedelta(minutes=2),
    "retry_exponential_backoff": True,
    "max_retry_delay": timedelta(minutes=30),
    "execution_timeout": timedelta(minutes=30),
    "on_failure_callback": task_failure_callback,   # уведомление после исчерпания retries
}


def run_extract(ds, params, **_):
    return pipeline.stage_extract(ds, params["search_term"], int(params["limit"]))


def run_transform(ds, ti, **_):
    return pipeline.stage_transform(ds, ti.xcom_pull(task_ids="extract_data"))


def run_quality(ds, ti, **_):
    return pipeline.stage_quality(ds, ti.xcom_pull(task_ids="transform_data"))


def run_load(ds, ti, params, **_):
    return pipeline.stage_load(ds, ti.xcom_pull(task_ids="transform_data"), mode=params["load_mode"])


with DAG(
    dag_id="podcast_etl_pipeline",
    default_args=default_args,
    description="ETL-конвейер для анализа данных о подкастах",
    schedule="@daily",                       # FR-4.1; ручной запуск (FR-4.2) — «Trigger DAG w/ config»
    start_date=datetime(2026, 1, 1),
    catchup=False,
    max_active_runs=1,
    dagrun_timeout=timedelta(hours=2),
    on_success_callback=dag_success_callback,
    params={
        "search_term": Param(config.SEARCH_TERM, type="string"),
        "limit": Param(config.LIMIT, type="integer", minimum=1, maximum=200),
        "load_mode": Param(config.LOAD_MODE, type="string", enum=["incremental", "full"]),
    },
    tags=["etl", "podcasts"],
    doc_md=__doc__,
) as dag:
    extract_task = PythonOperator(task_id="extract_data", python_callable=run_extract)
    transform_task = PythonOperator(task_id="transform_data", python_callable=run_transform)
    quality_task = PythonOperator(task_id="quality_check", python_callable=run_quality)
    load_task = PythonOperator(task_id="load_data", python_callable=run_load)

    extract_task >> transform_task >> quality_task >> load_task   # FR-4.3
