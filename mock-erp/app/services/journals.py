import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from app.db.models import Account, JournalEntry, JournalLine
from app.domain.schemas import JournalEntryCreate, JournalEntryOut, JournalLineOut


def payload_hash(body: JournalEntryCreate) -> str:
    canonical = {
        "external_reference": body.external_reference,
        "entry_date": body.entry_date.isoformat(),
        "description": body.description,
        "source_system": body.source_system,
        "reverses_external_reference": body.reverses_external_reference,
        "lines": [
            {
                "account_external_reference": ln.account_external_reference,
                "debit": str(ln.debit),
                "credit": str(ln.credit),
            }
            for ln in sorted(body.lines, key=lambda x: x.account_external_reference)
        ],
    }
    raw = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def to_out(entry: JournalEntry) -> JournalEntryOut:
    lines_out: list[JournalLineOut] = []
    total_dr = Decimal("0")
    total_cr = Decimal("0")
    for ln in entry.lines:
        lines_out.append(
            JournalLineOut(
                account_external_reference=ln.account.external_reference,
                account_code=ln.account.code,
                debit=ln.debit,
                credit=ln.credit,
            )
        )
        total_dr += ln.debit
        total_cr += ln.credit
    reverses_ref = None
    if entry.reverses_id and entry.reverses:
        reverses_ref = entry.reverses.external_reference
    return JournalEntryOut(
        id=entry.id,
        external_reference=entry.external_reference,
        entry_date=entry.entry_date,
        description=entry.description,
        source_system=entry.source_system,
        reverses_external_reference=reverses_ref,
        payload_hash=entry.payload_hash,
        created_at=entry.created_at,
        lines=lines_out,
        total_debit=total_dr,
        total_credit=total_cr,
    )


def create_or_idempotent(db: Session, body: JournalEntryCreate) -> tuple[JournalEntryOut, int]:
    """Returns (entry, status_code) — 201 create, 200 identical replay, 409 conflict."""
    digest = payload_hash(body)
    existing = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account), joinedload(JournalEntry.reverses))
        .filter(JournalEntry.external_reference == body.external_reference)
        .first()
    )
    if existing:
        if existing.payload_hash == digest:
            return to_out(existing), 200
        raise HTTPException(
            status_code=409,
            detail={
                "code": "error.msg.journal.external.reference.conflict",
                "message": f"Journal with external_reference {body.external_reference} exists with a different payload",
            },
        )

    reverses_id = None
    if body.reverses_external_reference:
        orig = db.query(JournalEntry).filter(JournalEntry.external_reference == body.reverses_external_reference).first()
        if not orig:
            raise HTTPException(status_code=404, detail="original journal to reverse not found")
        reverses_id = orig.id

    entry = JournalEntry(
        external_reference=body.external_reference,
        entry_date=body.entry_date,
        description=body.description,
        source_system=body.source_system,
        reverses_id=reverses_id,
        payload_hash=digest,
    )
    db.add(entry)
    db.flush()

    for ln in body.lines:
        account = db.query(Account).filter(Account.external_reference == ln.account_external_reference).first()
        if not account:
            raise HTTPException(status_code=400, detail=f"unknown account {ln.account_external_reference}")
        db.add(
            JournalLine(
                entry_id=entry.id,
                account_id=account.id,
                debit=ln.debit,
                credit=ln.credit,
            )
        )
    db.commit()
    entry = (
        db.query(JournalEntry)
        .options(joinedload(JournalEntry.lines).joinedload(JournalLine.account), joinedload(JournalEntry.reverses))
        .filter(JournalEntry.id == entry.id)
        .one()
    )
    return to_out(entry), 201
