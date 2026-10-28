from __future__ import annotations

import base64
from decimal import Decimal
from typing import Any

import httpx

from app.config import settings
from app.domain.models import FineractGlCreate
from app.ports.core_banking import ConflictError


class FineractAdapter:
    def __init__(
        self,
        base_url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        tenant: str | None = None,
        verify_ssl: bool | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = (base_url or settings.fineract_base_url).rstrip("/")
        self.tenant = tenant or settings.fineract_tenant
        user = username or settings.fineract_username
        pwd = password or settings.fineract_password
        token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
        self._headers = {
            "Authorization": f"Basic {token}",
            "Fineract-Platform-TenantId": self.tenant,
            "Content-Type": "application/json",
        }
        self._client = client or httpx.Client(verify=verify_ssl if verify_ssl is not None else settings.fineract_verify_ssl, timeout=60.0)

    def create_gl_account(self, payload: FineractGlCreate) -> dict[str, Any]:
        body = {
            "name": payload.name,
            "glCode": payload.gl_code,
            "type": payload.type,
            "usage": payload.usage,
            "manualEntriesAllowed": payload.manual_entries_allowed,
            "description": payload.description or payload.name,
            "externalReference": payload.external_reference,
        }
        r = self._client.post(f"{self.base_url}/glaccounts", headers=self._headers, json=body)
        if r.status_code == 409:
            raise ConflictError("GL externalReference conflict", r.json() if r.content else None)
        r.raise_for_status()
        return r.json()

    def disburse_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
    ) -> dict[str, Any]:
        body = {
            "actualDisbursementDate": transaction_date,
            "transactionAmount": float(amount),
            "externalId": external_id,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        r = self._client.post(
            f"{self.base_url}/loans/{loan_id}?command=disburse",
            headers=self._headers,
            json=body,
        )
        r.raise_for_status()
        return r.json()

    def repay_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
    ) -> dict[str, Any]:
        body = {
            "transactionDate": transaction_date,
            "transactionAmount": float(amount),
            "externalId": external_id,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
            "paymentTypeId": 1,
        }
        r = self._client.post(
            f"{self.base_url}/loans/{loan_id}/transactions?command=repayment",
            headers=self._headers,
            json=body,
        )
        r.raise_for_status()
        return r.json()

    def undo_loan_transaction(self, *, loan_id: int, transaction_id: int) -> dict[str, Any]:
        r = self._client.post(
            f"{self.base_url}/loans/{loan_id}/transactions/{transaction_id}?command=undo",
            headers=self._headers,
            json={},
        )
        r.raise_for_status()
        return r.json() if r.content else {}

    def get_loan_transaction_by_external_id(self, *, loan_external_id: str, txn_external_id: str) -> dict | None:
        r = self._client.get(
            f"{self.base_url}/loans/external-id/{loan_external_id}/transactions/external-id/{txn_external_id}",
            headers=self._headers,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def list_loan_transactions(self, *, loan_id: int) -> list[dict]:
        r = self._client.get(
            f"{self.base_url}/loans/{loan_id}?associations=transactions",
            headers=self._headers,
        )
        r.raise_for_status()
        data = r.json()
        return list(data.get("transactions") or [])
