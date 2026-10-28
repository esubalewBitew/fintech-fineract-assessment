from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import router
from app.config import settings
from app.db.session import Base, get_db
from app.services.seed import seed_if_empty


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(bind=engine)
    db = TestingSession()
    seed_if_empty(db)

    app = FastAPI()
    app.include_router(router)

    def _override():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        c.headers.update({"X-Api-Key": settings.api_key})
        yield c
    app.dependency_overrides.clear()
    db.close()


def test_rejects_unbalanced(client: TestClient):
    r = client.post(
        "/journal-entries",
        json={
            "external_reference": "J1",
            "entry_date": str(date.today()),
            "lines": [
                {"account_external_reference": "ERP-CASH", "debit": "100", "credit": "0"},
                {"account_external_reference": "ERP-FEE-INC", "debit": "0", "credit": "50"},
            ],
        },
    )
    assert r.status_code == 422


def test_create_and_idempotent_replay(client: TestClient):
    body = {
        "external_reference": "FIN-2026-000001",
        "entry_date": str(date.today()),
        "description": "repay",
        "lines": [
            {"account_external_reference": "ERP-CASH", "debit": "1000", "credit": "0"},
            {"account_external_reference": "ERP-LOAN-PORT", "debit": "0", "credit": "1000"},
        ],
    }
    r1 = client.post("/journal-entries", json=body)
    assert r1.status_code == 201
    r2 = client.post("/journal-entries", json=body)
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]


def test_conflict_different_payload(client: TestClient):
    body1 = {
        "external_reference": "FIN-CONFLICT",
        "entry_date": str(date.today()),
        "lines": [
            {"account_external_reference": "ERP-CASH", "debit": "100", "credit": "0"},
            {"account_external_reference": "ERP-FEE-INC", "debit": "0", "credit": "100"},
        ],
    }
    body2 = {
        **body1,
        "lines": [
            {"account_external_reference": "ERP-CASH", "debit": "200", "credit": "0"},
            {"account_external_reference": "ERP-FEE-INC", "debit": "0", "credit": "200"},
        ],
    }
    assert client.post("/journal-entries", json=body1).status_code == 201
    r = client.post("/journal-entries", json=body2)
    assert r.status_code == 409


def test_list_accounts_includes_usd_seed(client: TestClient):
    accounts = client.get("/accounts").json()
    currencies = {a["currency"] for a in accounts}
    assert "RWF" in currencies
    assert "USD" in currencies
    assert len(accounts) == 10
