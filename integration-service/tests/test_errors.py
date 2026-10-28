from fastapi.testclient import TestClient

from app.main import app


def test_missing_api_key_uses_error_envelope():
    client = TestClient(app)
    r = client.post("/sync/coa")
    assert r.status_code == 401
    body = r.json()
    assert "error" in body
    assert body["error"]["code"] == "unauthorized"
    assert "X-Correlation-Id" in r.headers


def test_correlation_id_echoed():
    client = TestClient(app)
    r = client.get("/health", headers={"X-Correlation-Id": "corr-test-1"})
    assert r.status_code == 200
    assert r.headers.get("X-Correlation-Id") == "corr-test-1"
