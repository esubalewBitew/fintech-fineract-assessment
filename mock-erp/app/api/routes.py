from __future__ import annotations

import time
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from sqlalchemy.orm import Session, joinedload

from app.config import settings
from app.db.models import Account, FaultConfig, JournalEntry, JournalLine
from app.db.session import get_db
from app.domain.schemas import (
    AccountCreate,
    AccountOut,
    FaultRequest,
    JournalEntryCreate,
    JournalEntryOut,
)
from app.services.journals import create_or_idempotent, to_out

router = APIRouter()


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if x_api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="invalid api key")


def apply_faults(db: Session) -> None:
    fault = db.query(FaultConfig).order_by(FaultConfig.id).first()
    if not fault:
        return
    if fault.mode == "down":
        raise HTTPException(status_code=503, detail="fault: down")
    if fault.mode == "slow":
        time.sleep(3)


@router.get("/health")
def health():
    return {"status": "ok", "service": "mock-erp"}


@router.post("/accounts", response_model=AccountOut, status_code=201, dependencies=[Depends(require_api_key)])
def create_account(body: AccountCreate, db: Session = Depends(get_db)):
    apply_faults(db)
    existing = db.query(Account).filter(Account.external_reference == body.external_reference).first()
    if existing:
        raise HTTPException(status_code=409, detail="account external_reference already exists")
    if db.query(Account).filter(Account.code == body.code).first():
        raise HTTPException(status_code=409, detail="account code already exists")
    account = Account(**body.model_dump())
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.get("/accounts", response_model=List[AccountOut], dependencies=[Depends(require_api_key)])
def list_accounts(db: Session = Depends(get_db)):
    apply_faults(db)
    return db.query(Account).order_by(Account.code).all()


@router.get("/accounts/{ref}", response_model=AccountOut, dependencies=[Depends(require_api_key)])
def get_account(ref: str, db: Session = Depends(get_db)):
    apply_faults(db)
    account = db.query(Account).filter(Account.external_reference == ref).first()
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    return account


@router.post("/journal-entries", response_model=JournalEntryOut, dependencies=[Depends(require_api_key)])
def post_journal(body: JournalEntryCreate, response: Response, db: Session = Depends(get_db)):
    apply_faults(db)
    out, status = create_or_idempotent(db, body)
    response.status_code = status
    fault = db.query(FaultConfig).order_by(FaultConfig.id).first()
    if fault and fault.mode == "timeout_after_write" and status == 201:
        time.sleep(30)
    return out


@router.get("/journal-entries", response_model=List[JournalEntryOut], dependencies=[Depends(require_api_key)])
def list_journals(
    external_reference: Optional[str] = None,
    since: Optional[date] = Query(default=None),
    db: Session = Depends(get_db),
):
    apply_faults(db)
    q = db.query(JournalEntry).options(
        joinedload(JournalEntry.lines).joinedload(JournalLine.account),
        joinedload(JournalEntry.reverses),
    )
    if external_reference:
        q = q.filter(JournalEntry.external_reference == external_reference)
    if since:
        q = q.filter(JournalEntry.entry_date >= since)
    return [to_out(e) for e in q.order_by(JournalEntry.id).all()]


@router.get("/journal-entries/{ref}", response_model=JournalEntryOut, dependencies=[Depends(require_api_key)])
def get_journal(ref: str, db: Session = Depends(get_db)):
    apply_faults(db)
    entry = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account), joinedload(JournalEntry.reverses))
        .filter(JournalEntry.external_reference == ref)
        .first()
    )
    if not entry:
        raise HTTPException(status_code=404, detail="journal not found")
    return to_out(entry)


@router.post("/admin/faults", dependencies=[Depends(require_api_key)])
def set_fault(body: FaultRequest, db: Session = Depends(get_db)):
    allowed = {"none", "down", "timeout_after_write", "slow"}
    if body.mode not in allowed:
        raise HTTPException(status_code=400, detail=f"mode must be one of {sorted(allowed)}")
    fault = db.query(FaultConfig).order_by(FaultConfig.id).first()
    if not fault:
        fault = FaultConfig(mode=body.mode)
        db.add(fault)
    else:
        fault.mode = body.mode
    db.commit()
    return {"mode": body.mode}
