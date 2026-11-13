from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
import pandas as pd

from src.extract import fetch_podcasts_from_itunes, parse_rss_feed
from src.transform import transform_podcasts, transform_episodes
from src.load import load_podcasts, load_episodes
from src.quality import validate_podcasts, validate_episodes
from src.config import SEARCH_TERM, LIMIT

default_args = {
    "owner": "student",
    "depends_on_past": False,
    "email_on_failure": False,
    "retries": 3,
    "retry_delay": timedelta(minutes=5),
}

def run_extract(**context):
    raw_podcasts = fetch_podcasts_from_itunes(SEARCH_TERM, LIMIT)
    context["ti"].xcom_push(key="raw_podcasts", value=raw_podcasts)
    
    all_episodes = []
    for p in raw_podcasts:
        rss_url = p.get("feedUrl")
        if rss_url:
            episodes = parse_rss_feed(rss_url)
            for ep in episodes:
                ep["podcast_id"] = p.get("collectionId")
            all_episodes.extend(episodes)
    
    context["ti"].xcom_push(key="raw_episodes", value=all_episodes)

def run_transform(**context):
    raw_podcasts = context["ti"].xcom_pull(key="raw_podcasts")
    raw_episodes = context["ti"].xcom_pull(key="raw_episodes")
    
    df_podcasts = transform_podcasts(raw_podcasts)
    
    episodes_by_podcast = {}
    for ep in raw_episodes:
        pid = ep.get("podcast_id")
        episodes_by_podcast.setdefault(pid, []).append(ep)
    
    dfs_episodes = []
    for pid, eps in episodes_by_podcast.items():
        dfs_episodes.append(transform_episodes(eps, pid))
    
    df_episodes = pd.concat(dfs_episodes, ignore_index=True) if dfs_episodes else pd.DataFrame()

    if not df_episodes.empty and "pub_date" in df_episodes.columns:
        df_episodes["pub_date"] = df_episodes["pub_date"].astype(str)

    context["ti"].xcom_push(key="df_podcasts", value=df_podcasts.to_dict("records"))
    context["ti"].xcom_push(key="df_episodes", value=df_episodes.to_dict("records"))

def run_quality(**context):
    df_podcasts = pd.DataFrame(context["ti"].xcom_pull(key="df_podcasts"))
    df_episodes = pd.DataFrame(context["ti"].xcom_pull(key="df_episodes"))
    
    if not validate_podcasts(df_podcasts):
        raise ValueError("Валидация подкастов не пройдена!")
    if not validate_episodes(df_episodes):
        raise ValueError("Валидация выпусков не пройдена!")

def run_load(**context):
    df_podcasts = pd.DataFrame(context["ti"].xcom_pull(key="df_podcasts"))
    df_episodes = pd.DataFrame(context["ti"].xcom_pull(key="df_episodes"))
    
    load_podcasts(df_podcasts)
    load_episodes(df_episodes)

with DAG(
    dag_id="podcast_etl_pipeline",
    default_args=default_args,
    description="ETL-конвейер для анализа данных о подкастах",
    schedule_interval="@daily",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["etl", "podcasts"],
) as dag:

    extract_task = PythonOperator(task_id="extract_data", python_callable=run_extract)
    transform_task = PythonOperator(task_id="transform_data", python_callable=run_transform)
    quality_task = PythonOperator(task_id="quality_check", python_callable=run_quality)
    load_task = PythonOperator(task_id="load_data", python_callable=run_load)

    extract_task >> transform_task >> quality_task >> load_task
