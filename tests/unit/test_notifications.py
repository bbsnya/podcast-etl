from types import SimpleNamespace

import requests

from src import notifications


def test_not_configured_does_not_send(monkeypatch):
    monkeypatch.setattr("src.config.TELEGRAM_BOT_TOKEN", "")
    monkeypatch.setattr("src.config.TELEGRAM_CHAT_ID", "")
    monkeypatch.setattr(requests, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("не должно вызываться")))
    assert notifications.send_notification("hi") is False


def test_sends_to_telegram(monkeypatch):
    sent = {}

    class Resp:
        def raise_for_status(self):
            pass

    def fake_post(url, json=None, timeout=None):
        sent.update(url=url, json=json)
        return Resp()

    monkeypatch.setattr("src.config.TELEGRAM_BOT_TOKEN", "TOKEN")
    monkeypatch.setattr("src.config.TELEGRAM_CHAT_ID", "42")
    monkeypatch.setattr(requests, "post", fake_post)
    assert notifications.send_notification("hello") is True
    assert "botTOKEN" in sent["url"] and sent["json"] == {"chat_id": "42", "text": "hello"}


def test_network_error_swallowed_and_token_not_leaked(monkeypatch):
    def boom(*a, **k):
        raise requests.ConnectionError("https://api.telegram.org/botSECRET/sendMessage failed")

    monkeypatch.setattr("src.config.TELEGRAM_BOT_TOKEN", "SECRET")
    monkeypatch.setattr("src.config.TELEGRAM_CHAT_ID", "1")
    monkeypatch.setattr(requests, "post", boom)
    assert notifications.send_notification("x") is False


def test_callbacks_format_messages(monkeypatch):
    messages = []
    monkeypatch.setattr(notifications, "send_notification", lambda text: messages.append(text) or True)
    ti = SimpleNamespace(task_id="load_data", dag_id="podcast_etl_pipeline")
    notifications.task_failure_callback({"task_instance": ti, "run_id": "r1", "exception": ValueError("bad")})
    notifications.dag_success_callback({"dag": SimpleNamespace(dag_id="podcast_etl_pipeline"), "run_id": "r1"})
    assert "load_data" in messages[0] and "ValueError" in messages[0]
    assert "успешно" in messages[1]
