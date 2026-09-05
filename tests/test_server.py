from unittest.mock import Mock

from fastapi.testclient import TestClient

from holmes_console.server import create_app


def test_webhook_requires_bearer_authentication():
    client = TestClient(create_app(Mock(), "secret"))
    response = client.post("/api/v1/alerts", json={"alerts": []})
    assert response.status_code == 401


def test_valid_alert_is_queued_and_processed():
    healer = Mock()
    healer.submit.return_value = ("job-1", True)
    client = TestClient(create_app(healer, "secret"))
    payload = {
        "commonLabels": {"namespace": "staging"},
        "alerts": [{"status": "firing", "labels": {"pod": "web-abc"}}],
    }
    response = client.post(
        "/api/v1/alerts",
        json=payload,
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 202
    assert response.json()["jobs"][0]["id"] == "job-1"
    healer.process.assert_called_once_with("job-1")


def test_webhook_limits_alert_batch_size():
    client = TestClient(create_app(Mock(), "secret"))
    response = client.post(
        "/api/v1/alerts",
        json={"alerts": [{}] * 21},
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 413
