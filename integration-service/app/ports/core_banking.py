from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional, Protocol

from app.domain.models import FineractGlCreate


class CoreBankingPort(Protocol):
    def create_gl_account(self, payload: FineractGlCreate) -> dict[str, Any]:
        """POST /glaccounts — raises ConflictError on 409."""

    def create_client(
        self,
        *,
        office_id: int,
        firstname: str,
        lastname: str,
        external_id: str,
        activation_date: str,
    ) -> dict[str, Any]: ...

    def get_client_by_external_id(self, external_id: str) -> Optional[dict[str, Any]]: ...

    def apply_loan(
        self,
        *,
        client_id: int,
        product_id: int,
        external_id: str,
        principal: Decimal,
        submitted_on_date: str,
        expected_disbursement_date: str,
        number_of_repayments: int = 12,
        interest_rate_per_period: Decimal = Decimal("18"),
    ) -> dict[str, Any]: ...

    def get_loan_by_external_id(self, external_id: str) -> Optional[dict[str, Any]]: ...

    def get_loan(self, loan_id: int) -> dict[str, Any]: ...

    def approve_loan(self, *, loan_id: int, approved_on_date: str, expected_disbursement_date: str) -> dict[str, Any]: ...

    def disburse_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
        loan_external_id: Optional[str] = None,
    ) -> dict[str, Any]: ...

    def repay_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
        loan_external_id: Optional[str] = None,
    ) -> dict[str, Any]: ...

    def undo_loan_transaction(self, *, loan_id: int, transaction_id: int) -> dict[str, Any]: ...

    def get_loan_transaction_by_external_id(
        self, *, loan_external_id: str, txn_external_id: str
    ) -> Optional[dict[str, Any]]: ...

    def list_loan_transactions(self, *, loan_id: int) -> list[dict]: ...

    def find_loan_product_id(self, *, name: Optional[str] = None, external_id: Optional[str] = None) -> Optional[int]: ...


class ConflictError(Exception):
    def __init__(self, message: str, body: Any = None):
        super().__init__(message)
        self.body = body


class CurrencyRejected(Exception):
    pass


class FineractTimeoutError(Exception):
    """Raised when Fineract HTTP times out; caller must lookup by externalId (no blind retry)."""

    def __init__(self, message: str, *, loan_external_id: str, txn_external_id: str):
        super().__init__(message)
        self.loan_external_id = loan_external_id
        self.txn_external_id = txn_external_id
