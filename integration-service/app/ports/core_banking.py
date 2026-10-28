from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol

from app.domain.models import FineractGlCreate


class CoreBankingPort(Protocol):
    def create_gl_account(self, payload: FineractGlCreate) -> dict[str, Any]:
        """POST /glaccounts — raises ConflictError on 409."""

    def disburse_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
    ) -> dict[str, Any]: ...

    def repay_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
    ) -> dict[str, Any]: ...

    def undo_loan_transaction(self, *, loan_id: int, transaction_id: int) -> dict[str, Any]: ...

    def get_loan_transaction_by_external_id(self, *, loan_external_id: str, txn_external_id: str) -> dict | None: ...

    def list_loan_transactions(self, *, loan_id: int) -> list[dict]: ...


class ConflictError(Exception):
    def __init__(self, message: str, body: Any = None):
        super().__init__(message)
        self.body = body


class CurrencyRejected(Exception):
    pass
