from __future__ import annotations


def test_readiness_reports_ready_when_provider_is_reachable(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"api": "ready", "localstack": "ready", "overall": "ready"}


def test_readiness_never_errors_even_when_provider_is_unreachable(client, monkeypatch):
    from app.api import routes_health

    # Same shape as a cold LocalStack: the probe fails, but the endpoint
    # itself must still answer 200 — a splash screen can't distinguish a
    # 503 from "the API is actually down".
    monkeypatch.setattr(routes_health, "_probe_localstack", lambda provider: "starting")

    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"api": "ready", "localstack": "starting", "overall": "starting"}
