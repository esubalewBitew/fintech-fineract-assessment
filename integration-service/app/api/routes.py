from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_cbs, get_coa, get_ledger, require_api_key
from app.db.models import LoanMap
from app.db.session import get_db
from app.ports.core_banking import CoreBankingPort
from app.ports.coa_provider import CoAProviderPort
from app.ports.ledger import LedgerPort
from app.recovery.sweep import list_needs_reconciliation
from app.usecases import money
from app.usecases.reconcile import reconcile_fineract_erp
from app.usecases.sync_coa import sync_chart_of_accounts

router = APIRouter()


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


@router.post("/loans/map", dependencies=[Depends(require_api_key)])
def map_loan(body: LoanMapIn, db: Session = Depends(get_db)) -> dict:
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
) -> dict:
    return money.disburse(
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


@router.post("/loans/repay", dependencies=[Depends(require_api_key)])
def repay_loan(
    body: MoneyIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
    ledger: LedgerPort = Depends(get_ledger),
    x_correlation_id: Optional[str] = Header(default=None),
) -> dict:
    return money.repay(
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


@router.post("/transactions/reverse-repayment", dependencies=[Depends(require_api_key)])
def reverse_repayment(
    body: ReverseIn,
    db: Session = Depends(get_db),
    cbs: CoreBankingPort = Depends(get_cbs),
    ledger: LedgerPort = Depends(get_ledger),
    x_correlation_id: Optional[str] = Header(default=None),
) -> dict:
    return money.reverse_repayment(
        db,
        cbs=cbs,
        ledger=ledger,
        external_reference=body.external_reference,
        original_external_reference=body.original_external_reference,
        transaction_date=(body.transaction_date or date.today()).isoformat(),
        correlation_id=x_correlation_id,
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
def recover(db: Session = Depends(get_db)) -> dict:
    rows = list_needs_reconciliation(db)
    return {"count": len(rows), "transactions": rows}
