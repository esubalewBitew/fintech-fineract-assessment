from __future__ import annotations

import base64
import logging
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.adapters.fineract_fault import get_fault_mode, set_fault_mode
from app.config import settings
from app.domain.models import FineractGlCreate
from app.ports.core_banking import ConflictError, FineractTimeoutError

logger = logging.getLogger(__name__)


class FineractAdapter:
    def __init__(
        self,
        base_url: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        tenant: Optional[str] = None,
        verify_ssl: Optional[bool] = None,
        client: Optional[httpx.Client] = None,
        fault_mode: Optional[str] = None,
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
        self._client = client or httpx.Client(
            verify=verify_ssl if verify_ssl is not None else settings.fineract_verify_ssl,
            timeout=60.0,
        )
        # none | timeout_after_write (one-shot: succeed then pretend timeout)
        if fault_mode is not None:
            self.fault_mode = fault_mode
        elif settings.fineract_fault_mode != "none":
            self.fault_mode = settings.fineract_fault_mode
        else:
            self.fault_mode = get_fault_mode()

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

    def create_client(
        self,
        *,
        office_id: int,
        firstname: str,
        lastname: str,
        external_id: str,
        activation_date: str,
    ) -> dict[str, Any]:
        body = {
            "officeId": office_id,
            "firstname": firstname,
            "lastname": lastname,
            "externalId": external_id,
            "active": True,
            "activationDate": activation_date,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
            "legalFormId": 1,
        }
        r = self._client.post(f"{self.base_url}/clients", headers=self._headers, json=body)
        r.raise_for_status()
        return r.json()

    def get_client_by_external_id(self, external_id: str) -> Optional[dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/clients/external-id/{external_id}", headers=self._headers)
        if r.status_code in (404, 400):
            return None
        if r.status_code >= 500:
            return None
        r.raise_for_status()
        return r.json()

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
    ) -> dict[str, Any]:
        body = {
            "clientId": client_id,
            "productId": product_id,
            "externalId": external_id,
            "principal": float(principal),
            "loanTermFrequency": number_of_repayments,
            "loanTermFrequencyType": 2,
            "numberOfRepayments": number_of_repayments,
            "repaymentEvery": 1,
            "repaymentFrequencyType": 2,
            "interestRatePerPeriod": float(interest_rate_per_period),
            "amortizationType": 1,
            "interestType": 0,
            "interestCalculationPeriodType": 1,
            "transactionProcessingStrategyCode": "mifos-standard-strategy",
            "expectedDisbursementDate": expected_disbursement_date,
            "submittedOnDate": submitted_on_date,
            "loanType": "individual",
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        r = self._client.post(f"{self.base_url}/loans", headers=self._headers, json=body)
        r.raise_for_status()
        return r.json()

    def get_loan_by_external_id(self, external_id: str) -> Optional[dict[str, Any]]:
        r = self._client.get(f"{self.base_url}/loans/external-id/{external_id}", headers=self._headers)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()

    def get_loan(self, loan_id: int) -> dict[str, Any]:
        r = self._client.get(
            f"{self.base_url}/loans/{loan_id}?associations=all",
            headers=self._headers,
        )
        r.raise_for_status()
        return r.json()

    def approve_loan(self, *, loan_id: int, approved_on_date: str, expected_disbursement_date: str) -> dict[str, Any]:
        body = {
            "approvedOnDate": approved_on_date,
            "expectedDisbursementDate": expected_disbursement_date,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        r = self._client.post(
            f"{self.base_url}/loans/{loan_id}?command=approve",
            headers=self._headers,
            json=body,
        )
        r.raise_for_status()
        return r.json()

    def disburse_loan(
        self,
        *,
        loan_id: int,
        amount: Decimal,
        external_id: str,
        transaction_date: str,
        loan_external_id: Optional[str] = None,
    ) -> dict[str, Any]:
        body = {
            "actualDisbursementDate": transaction_date,
            "transactionAmount": float(amount),
            "externalId": external_id,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
        }
        try:
            r = self._client.post(
                f"{self.base_url}/loans/{loan_id}?command=disburse",
                headers=self._headers,
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise FineractTimeoutError(
                f"fineract timeout on disburse: {exc}",
                loan_external_id=loan_external_id or str(loan_id),
                txn_external_id=external_id,
            ) from exc

        active_fault = self.fault_mode if self.fault_mode != "none" else get_fault_mode()
        if active_fault == "timeout_after_write" and r.status_code < 300:
            # One-shot: write succeeded; caller must LOOKUP BY externalId — never blind re-POST.
            self.fault_mode = "none"
            set_fault_mode("none")
            logger.warning(
                "FINERACT_FAULT timeout_after_write: write ok; LOOKUP_BY_EXTERNAL_ID required (txn=%s loan=%s)",
                external_id,
                loan_external_id,
            )
            raise FineractTimeoutError(
                "simulated timeout after successful Fineract write",
                loan_external_id=loan_external_id or str(loan_id),
                txn_external_id=external_id,
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
        loan_external_id: Optional[str] = None,
    ) -> dict[str, Any]:
        body = {
            "transactionDate": transaction_date,
            "transactionAmount": float(amount),
            "externalId": external_id,
            "dateFormat": "yyyy-MM-dd",
            "locale": "en",
            "paymentTypeId": 1,
        }
        try:
            r = self._client.post(
                f"{self.base_url}/loans/{loan_id}/transactions?command=repayment",
                headers=self._headers,
                json=body,
            )
        except httpx.TimeoutException as exc:
            raise FineractTimeoutError(
                f"fineract timeout on repay: {exc}",
                loan_external_id=loan_external_id or str(loan_id),
                txn_external_id=external_id,
            ) from exc
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

    def get_loan_transaction_by_external_id(
        self, *, loan_external_id: str, txn_external_id: str
    ) -> Optional[dict[str, Any]]:
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

    def find_loan_product_id(self, *, name: Optional[str] = None, external_id: Optional[str] = None) -> Optional[int]:
        r = self._client.get(f"{self.base_url}/loanproducts", headers=self._headers)
        r.raise_for_status()
        for p in r.json() or []:
            if external_id and p.get("externalId") == external_id:
                return int(p["id"])
            if name and p.get("name") == name:
                return int(p["id"])
        return None
