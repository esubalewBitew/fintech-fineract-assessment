from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.models import GlAccountMap
from app.db.session import Base
from app.domain.models import CoAAccount, FineractGlCreate
from app.policy.currency import assert_allowed_currency
from app.ports.core_banking import ConflictError, CurrencyRejected
from app.usecases.sync_coa import sync_chart_of_accounts


def test_currency_gate():
    assert_allowed_currency("RWF")
    with pytest.raises(CurrencyRejected):
        assert_allowed_currency("USD")


def test_sync_skips_usd_and_creates_rwf():
    engine = create_engine("sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    db = Session()

    class FakeCoA:
        source_system = "mock-erp"

        def list_accounts(self):
            return [
                CoAAccount("ERP-CASH", "1000", "Cash", "ASSET", "DETAIL", "RWF"),
                CoAAccount("ERP-USD", "1900", "USD", "ASSET", "DETAIL", "USD"),
            ]

    class FakeCbs:
        def create_gl_account(self, payload: FineractGlCreate):
            return {"resourceId": 42}

    results = sync_chart_of_accounts(db, coa=FakeCoA(), cbs=FakeCbs())
    statuses = {r["external_reference"]: r["status"] for r in results}
    assert statuses["ERP-CASH"] == "created"
    assert statuses["ERP-USD"] == "skipped_currency"
    assert db.query(GlAccountMap).count() == 1
