from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.fineract_fault import get_fault_mode, set_fault_mode
from app.api.deps import get_cbs, get_coa, get_ledger, require_api_key
from app.db.models import LoanMap
from app.db.session import get_db
from app.ports.core_banking import CoreBankingPort
from app.ports.coa_provider import CoAProviderPort
from app.ports.ledger import LedgerPort
from app.recovery.sweep import list_needs_reconciliation, recover_needs_reconciliation
from app.usecases import money, onboarding
from app.usecases.reconcile import reconcile_fineract_erp
from app.usecases.sync_coa import sync_chart_of_accounts

router = APIRouter()

_TERMINAL = frozenset({"COMPLETED", "FAILED"})


def _money_response(body: dict[str, Any]) -> JSONResponse | dict[str, Any]:
    """Idempotent replay while still in-flight → 202; completed/failed → 200."""
    if body.get("idempotent_replay") and body.get("state") not in _TERMINAL:
        return JSONResponse(content=body, status_code=202)
    return body


class ClientIn(BaseModel):
    client_uid: str
    firstname: str
    lastname: str
    office_id: Optional[int] = None
    activation_date: Optional[date] = None


class LoanApplyIn(BaseModel):
    loan_reference: str
    client_uid: str
    principal: Decimal
    product_id: Optional[int] = None
    product_external_id: Optional[str] = None
    submitted_on_date: Optional[date] = None
    expected_disbursement_date: Optional[date] = None


class LoanApproveIn(BaseModel):
    approved_on_date: Optional[date] = None
    expected_disbursement_date: Optional[date] = None


class LoanMapIn(BaseModel):
    loan_reference: str
    fineract_loan_id: int
    client_uid: Optional[str] = None


class MoneyIn(BaseModel):
    external_reference: str
    loan_reference: str
    amount: Decimal
    currency: str = "RWF"
    transaction_date: Optional[date] = None
    rail: str = "offline"
    principal: Optional[Decimal] = None
    interest: Optional[Decimal] = None


class ReverseIn(BaseModel):
    external_reference: str
    original_external_reference: str
    transaction_date: Optional[date] = None


class FaultIn(BaseModel):
    mode: str  # none | timeout_after_write | down


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "integration-service"}


@router.post("/sync/coa", dependencies=[Depends(require_api_key)])
def sync_coa(
    db: Session = Depends(get_db),
    coa: CoAProviderPort = Depends(get_coa),
    cbs: CoreBankingPort = Depends(get_cbs),
) -> dict:
    results = sync_chart_of_accounts(db, coa=coa, cbs=cbs)
    return {"count": len(results), "results": results}


@router.post("/clients", dependencies=[Depends(require_api_key)])
def create_client(
    body: ClientIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
) -> dict:
    return onboarding.create_or_get_client(
        db,
        cbs=cbs,
        client_uid=body.client_uid,
        firstname=body.firstname,
        lastname=body.lastname,
        office_id=body.office_id,
        activation_date=(body.activation_date or date.today()).isoformat(),
    )


@router.post("/loans/apply", dependencies=[Depends(require_api_key)])
def apply_loan(
    body: LoanApplyIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
) -> dict:
    today = date.today()
    return onboarding.apply_or_get_loan(
        db,
        cbs=cbs,
        loan_reference=body.loan_reference,
        client_uid=body.client_uid,
        principal=body.principal,
        product_id=body.product_id,
        product_external_id=body.product_external_id,
        submitted_on_date=(body.submitted_on_date or today).isoformat(),
        expected_disbursement_date=(body.expected_disbursement_date or today).isoformat(),
    )


@router.post("/loans/{loan_reference}/approve", dependencies=[Depends(require_api_key)])
def approve_loan(
    loan_reference: str,
    body: LoanApproveIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
) -> dict:
    today = date.today()
    return onboarding.approve_loan(
        db,
        cbs=cbs,
        loan_reference=loan_reference,
        approved_on_date=(body.approved_on_date or today).isoformat(),
        expected_disbursement_date=(body.expected_disbursement_date or today).isoformat(),
    )


@router.get("/loans/{loan_reference}", dependencies=[Depends(require_api_key)])
def get_loan(
    loan_reference: str,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
) -> dict:
    return onboarding.loan_snapshot(db, cbs=cbs, loan_reference=loan_reference)


@router.post("/loans/map", dependencies=[Depends(require_api_key)])
def map_loan(body: LoanMapIn, db: Session = Depends(get_db)) -> dict:
    """Admin escape hatch — primary path is POST /clients + /loans/apply."""
    existing = db.query(LoanMap).filter(LoanMap.loan_reference == body.loan_reference).first()
    if existing:
        existing.fineract_loan_id = body.fineract_loan_id
        existing.client_uid = body.client_uid
    else:
        db.add(
            LoanMap(
                loan_reference=body.loan_reference,
                fineract_loan_id=body.fineract_loan_id,
                client_uid=body.client_uid,
            )
        )
    db.commit()
    return {"loan_reference": body.loan_reference, "fineract_loan_id": body.fineract_loan_id}


@router.post("/loans/disburse", dependencies=[Depends(require_api_key)])
def disburse_loan(
    body: MoneyIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
    ledger: LedgerPort = Depends(get_ledger),
    x_correlation_id: Optional[str] = Header(default=None),
):
    return _money_response(
        money.disburse(
            db,
            cbs=cbs,
            ledger=ledger,
            external_reference=body.external_reference,
            loan_reference=body.loan_reference,
            amount=body.amount,
            currency=body.currency,
            transaction_date=(body.transaction_date or date.today()).isoformat(),
            rail_name=body.rail,
            correlation_id=x_correlation_id,
        )
    )


@router.post("/loans/repay", dependencies=[Depends(require_api_key)])
def repay_loan(
    body: MoneyIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
    ledger: LedgerPort = Depends(get_ledger),
    x_correlation_id: Optional[str] = Header(default=None),
):
    return _money_response(
        money.repay(
            db,
            cbs=cbs,
            ledger=ledger,
            external_reference=body.external_reference,
            loan_reference=body.loan_reference,
            amount=body.amount,
            currency=body.currency,
            transaction_date=(body.transaction_date or date.today()).isoformat(),
            principal=body.principal,
            interest=body.interest,
            rail_name=body.rail,
            correlation_id=x_correlation_id,
        )
    )


@router.post("/transactions/reverse-repayment", dependencies=[Depends(require_api_key)])
def reverse_repayment(
    body: ReverseIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
    ledger: LedgerPort = Depends(get_ledger),
    x_correlation_id: Optional[str] = Header(default=None),
):
    return _money_response(
        money.reverse_repayment(
            db,
            cbs=cbs,
            ledger=ledger,
            external_reference=body.external_reference,
            original_external_reference=body.original_external_reference,
            transaction_date=(body.transaction_date or date.today()).isoformat(),
            correlation_id=x_correlation_id,
        )
    )


@router.get("/reconcile/fineract-erp", dependencies=[Depends(require_api_key)])
def reconcile(
    since: Optional[str] = None,
    db: Session = Depends(get_db),
    ledger: LedgerPort = Depends(get_ledger),
) -> dict:
    rows = reconcile_fineract_erp(db, ledger, since=since)
    return {"count": len(rows), "results": rows}


@router.get("/admin/recover", dependencies=[Depends(require_api_key)])
def recover_list(db: Session = Depends(get_db)) -> dict:
    rows = list_needs_reconciliation(db)
    return {"count": len(rows), "transactions": rows}


@router.post("/admin/recover", dependencies=[Depends(require_api_key)])
def recover_run(db: Session = Depends(get_db), ledger: LedgerPort = Depends(get_ledger)) -> dict:
    """Part J restart recovery: post missing ERP journals for NEEDS_RECONCILIATION + CBS CONFIRMED."""
    results = recover_needs_reconciliation(db, ledger)
    return {"count": len(results), "results": results}


@router.post("/admin/fineract-fault", dependencies=[Depends(require_api_key)])
def fineract_fault(body: FaultIn) -> dict:
    """Part J: inject timeout_after_write (LOOKUP_BY_EXTERNAL_ID) or down (no CBS write)."""
    try:
        mode = set_fault_mode(body.mode)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"mode": mode, "current": get_fault_mode()}
