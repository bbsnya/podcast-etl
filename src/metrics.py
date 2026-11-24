"""Сбор и отправка метрик выполнения конвейера."""
import logging
import time
from contextlib import contextmanager
from typing import Dict, Iterator, Optional

from src import config

logger = logging.getLogger(__name__)

JOB_NAME = "podcast_etl"


def push_metrics(task: str, values: Dict[str, float], gateway: Optional[str] = None) -> bool:
    """Отправляет метрики задачи в Pushgateway."""
    gateway = config.PUSHGATEWAY_URL if gateway is None else gateway
    if not gateway:
        return False
    try:
        from prometheus_client import CollectorRegistry, Gauge, pushadd_to_gateway

        registry = CollectorRegistry()
        for name, value in values.items():
            Gauge(f"etl_{name}", f"ETL metric: {name}", registry=registry).set(float(value))
        pushadd_to_gateway(gateway, job=JOB_NAME, registry=registry, grouping_key={"task": task}, timeout=5)
        return True
    except Exception as exc:  # noqa: BLE001 - мониторинг не критичен
        logger.warning("Не удалось отправить метрики (%s): %s", task, type(exc).__name__)
        return False


class TaskMetrics:
    def __init__(self, task: str):
        self.task = task
        self.values: Dict[str, float] = {}

    def set(self, name: str, value: float) -> None:
        self.values[name] = float(value)


@contextmanager
def task_metrics(task: str, gateway: Optional[str] = None) -> Iterator[TaskMetrics]:
    """Собирает длительность и результат выполнения задачи."""
    tm = TaskMetrics(task)
    started = time.monotonic()
    ok = False
    try:
        yield tm
        ok = True
    finally:
        now = time.time()
        tm.values["task_duration_seconds"] = time.monotonic() - started
        tm.values["task_status"] = 1.0 if ok else 0.0
        tm.values["task_last_run_timestamp_seconds"] = now
        if ok:
            tm.values["task_last_success_timestamp_seconds"] = now
        push_metrics(task, tm.values, gateway)
