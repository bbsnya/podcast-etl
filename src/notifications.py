"""Уведомления об успехе/ошибке выполнения DAG (Telegram)."""
import logging
from typing import Any, Dict

import requests

from src import config

logger = logging.getLogger(__name__)


def send_notification(text: str) -> bool:
    """Отправляет уведомление в Telegram, если настроены параметры подключения."""
    token, chat_id = config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID
    if not (token and chat_id):
        logger.info("[уведомление, Telegram не настроен] %s", text)
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text},
            timeout=10,
        )
        response.raise_for_status()
        return True
    except Exception as exc:  # noqa: BLE001
        # В тексте исключения requests может быть URL с токеном — логируем только тип
        logger.warning("Не удалось отправить уведомление: %s", type(exc).__name__)
        return False


def task_failure_callback(context: Dict[str, Any]) -> None:
    """Отправляет уведомление об ошибке задачи."""
    ti = context.get("task_instance")
    task_id = getattr(ti, "task_id", "?")
    dag_id = getattr(ti, "dag_id", "?")
    exc = context.get("exception")
    send_notification(
        f"❌ {dag_id}: задача {task_id} завершилась ошибкой\n"
        f"run: {context.get('run_id')}\n"
        f"{type(exc).__name__ if exc else ''}: {str(exc)[:300] if exc else ''}"
    )


def dag_success_callback(context: Dict[str, Any]) -> None:
    """Отправляет уведомление об успешном завершении конвейера."""
    dag = context.get("dag")
    send_notification(f"✅ {getattr(dag, 'dag_id', '?')}: запуск {context.get('run_id')} выполнен успешно")
