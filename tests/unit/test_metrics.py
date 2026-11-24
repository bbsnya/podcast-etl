import pytest

from src import metrics


def capture(monkeypatch):
    calls = []
    monkeypatch.setattr(metrics, "push_metrics", lambda task, values, gateway=None: calls.append((task, dict(values))))
    return calls


def test_task_metrics_success(monkeypatch):
    calls = capture(monkeypatch)
    with metrics.task_metrics("extract") as m:
        m.set("podcasts_extracted", 42)
    task, values = calls[0]
    assert task == "extract"
    assert values["task_status"] == 1.0
    assert values["podcasts_extracted"] == 42.0
    assert values["task_duration_seconds"] >= 0
    assert "task_last_success_timestamp_seconds" in values


def test_task_metrics_failure_reports_and_reraises(monkeypatch):
    calls = capture(monkeypatch)
    with pytest.raises(RuntimeError):
        with metrics.task_metrics("load"):
            raise RuntimeError("boom")
    values = calls[0][1]
    assert values["task_status"] == 0.0
    assert "task_last_success_timestamp_seconds" not in values     # не затираем прошлый успех


def test_push_noop_without_gateway(monkeypatch):
    monkeypatch.setattr("src.config.PUSHGATEWAY_URL", "")
    assert metrics.push_metrics("x", {"a": 1}) is False


def test_push_failure_is_swallowed():
    pytest.importorskip("prometheus_client")
    assert metrics.push_metrics("x", {"a": 1}, gateway="127.0.0.1:1") is False
