from typing import Optional

from fastapi import Header, HTTPException

from app.adapters.fineract import FineractAdapter
from app.adapters.mock_erp import MockErpCoAProvider, MockErpLedger
from app.config import settings


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")


def get_cbs() -> FineractAdapter:
    return FineractAdapter()


def get_coa() -> MockErpCoAProvider:
    return MockErpCoAProvider()


def get_ledger() -> MockErpLedger:
    return MockErpLedger()
