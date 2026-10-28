from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import ClientMap, LoanMap
from app.ports.core_banking import CoreBankingPort


def create_or_get_client(
    db: Session,
    *,
    cbs: CoreBankingPort,
    client_uid: str,
    firstname: str,
    lastname: str,
    office_id: Optional[int] = None,
    activation_date: str,
) -> dict[str, Any]:
    office_id = office_id or settings.default_office_id
    existing = db.query(ClientMap).filter(ClientMap.client_uid == client_uid).first()
    if existing:
        return {
            "client_uid": client_uid,
            "fineract_client_id": existing.fineract_client_id,
            "status": "exists",
        }

    remote = cbs.get_client_by_external_id(client_uid)
    if remote:
        cid = int(remote.get("id") or remote.get("clientId"))
        db.add(ClientMap(client_uid=client_uid, fineract_client_id=cid))
        db.commit()
        return {"client_uid": client_uid, "fineract_client_id": cid, "status": "linked"}

    resp = cbs.create_client(
        office_id=office_id,
        firstname=firstname,
        lastname=lastname,
        external_id=client_uid,
        activation_date=activation_date,
    )
    cid = int(resp.get("clientId") or resp.get("resourceId"))
    db.add(ClientMap(client_uid=client_uid, fineract_client_id=cid))
    db.commit()
    return {"client_uid": client_uid, "fineract_client_id": cid, "status": "created"}


def apply_or_get_loan(
    db: Session,
    *,
    cbs: CoreBankingPort,
    loan_reference: str,
    client_uid: str,
    principal: Decimal,
    submitted_on_date: str,
    expected_disbursement_date: str,
    product_id: Optional[int] = None,
    product_external_id: Optional[str] = None,
) -> dict[str, Any]:
    existing = db.query(LoanMap).filter(LoanMap.loan_reference == loan_reference).first()
    if existing:
        return {
            "loan_reference": loan_reference,
            "fineract_loan_id": existing.fineract_loan_id,
            "client_uid": existing.client_uid,
            "status": "exists",
        }

    remote = cbs.get_loan_by_external_id(loan_reference)
    if remote:
        lid = int(remote.get("id") or remote.get("loanId"))
        db.add(
            LoanMap(
                loan_reference=loan_reference,
                fineract_loan_id=lid,
                client_uid=client_uid,
            )
        )
        db.commit()
        return {
            "loan_reference": loan_reference,
            "fineract_loan_id": lid,
            "client_uid": client_uid,
            "status": "linked",
        }

    client = db.query(ClientMap).filter(ClientMap.client_uid == client_uid).first()
    if not client:
        raise HTTPException(status_code=400, detail=f"unknown client_uid {client_uid}; POST /clients first")

    if product_id is None:
        pid = cbs.find_loan_product_id(
            external_id=product_external_id or settings.default_product_external_id,
            name="SME Asset Finance",
        )
        if pid is None:
            raise HTTPException(status_code=400, detail="loan product not found; run Part B setup")
        product_id = pid

    resp = cbs.apply_loan(
        client_id=client.fineract_client_id,
        product_id=product_id,
        external_id=loan_reference,
        principal=principal,
        submitted_on_date=submitted_on_date,
        expected_disbursement_date=expected_disbursement_date,
    )
    lid = int(resp.get("loanId") or resp.get("resourceId"))
    db.add(
        LoanMap(
            loan_reference=loan_reference,
            fineract_loan_id=lid,
            client_uid=client_uid,
        )
    )
    db.commit()
    return {
        "loan_reference": loan_reference,
        "fineract_loan_id": lid,
        "client_uid": client_uid,
        "product_id": product_id,
        "status": "created",
    }


def approve_loan(
    db: Session,
    *,
    cbs: CoreBankingPort,
    loan_reference: str,
    approved_on_date: str,
    expected_disbursement_date: str,
) -> dict[str, Any]:
    loan = db.query(LoanMap).filter(LoanMap.loan_reference == loan_reference).first()
    if not loan:
        raise HTTPException(status_code=400, detail=f"unknown loan_reference {loan_reference}")
    resp = cbs.approve_loan(
        loan_id=loan.fineract_loan_id,
        approved_on_date=approved_on_date,
        expected_disbursement_date=expected_disbursement_date,
    )
    detail = cbs.get_loan(loan.fineract_loan_id)
    status = (detail.get("status") or {}).get("value") if isinstance(detail.get("status"), dict) else detail.get("status")
    return {
        "loan_reference": loan_reference,
        "fineract_loan_id": loan.fineract_loan_id,
        "status": status,
        "approve_response": resp,
    }


def loan_snapshot(db: Session, *, cbs: CoreBankingPort, loan_reference: str) -> dict[str, Any]:
    loan = db.query(LoanMap).filter(LoanMap.loan_reference == loan_reference).first()
    if not loan:
        raise HTTPException(status_code=404, detail="loan_reference not found")
    detail = cbs.get_loan(loan.fineract_loan_id)
    status = (detail.get("status") or {}).get("value") if isinstance(detail.get("status"), dict) else detail.get("status")
    summary = detail.get("summary") or {}
    return {
        "loan_reference": loan_reference,
        "fineract_loan_id": loan.fineract_loan_id,
        "status": status,
        "principal": summary.get("principal"),
        "principalOutstanding": summary.get("principalOutstanding"),
        "totalOutstanding": summary.get("totalOutstanding"),
        "totalRepayment": summary.get("totalRepayment"),
    }
