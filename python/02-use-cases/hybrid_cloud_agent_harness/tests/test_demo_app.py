from fastapi.testclient import TestClient

from demo_app import app


def test_demo_health_and_harness_chat() -> None:
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "healthy", "mode": "demo"}
    response = client.post(
        "/api/chat",
        json={
            "message": "退款规则是什么？",
            "tenant_id": "demo-bank",
            "user_id": "user-001",
            "session_id": "demo-smoke",
        },
    )

    assert response.status_code == 200
    events = [event["name"] for event in response.json()["events"]]
    assert events[0] == "harness.request.accept"
    assert events[-1] == "harness.telemetry.export"
