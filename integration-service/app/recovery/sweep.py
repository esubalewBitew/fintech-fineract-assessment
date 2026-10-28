from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import IntegrationTransaction, LoanMap, TransactionLeg
from app.domain.models import LegState, LegType, OperationType
from app.domain.states import InvalidTransition, transition
from app.mapping import journal_mapping as jm
from app.ports.ledger import LedgerPort


def list_needs_reconciliation(db: Session) -> list[dict]:
    rows = db.query(IntegrationTransaction).filter(IntegrationTransaction.state == "NEEDS_RECONCILIATION").all()
    return [
        {
            "integration_txn_id": t.id,
            "operation_type": t.operation_type,
            "external_reference": t.external_reference,
            "loan_reference": t.loan_reference,
            "state": t.state,
        }
        for t in rows
    ]


def recover_needs_reconciliation(db: Session, ledger: LedgerPort) -> list[dict]:
    """Retry ERP journal for NEEDS_RECONCILIATION txns that already have CBS CONFIRMED.

    Covers Part J crash-after-Fineract / ERP-down: Fineract booked; ledger leg unfinished.
    """
    out: list[dict] = []
    rows = (
        db.query(IntegrationTransaction)
        .filter(IntegrationTransaction.state == "NEEDS_RECONCILIATION")
        .order_by(IntegrationTransaction.created_at)
        .all()
    )
    for txn in rows:
        item: dict = {
            "integration_txn_id": txn.id,
            "external_reference": txn.external_reference,
            "operation_type": txn.operation_type,
            "before_state": txn.state,
        }
        cbs = (
            db.query(TransactionLeg)
            .filter(TransactionLeg.txn_id == txn.id, TransactionLeg.leg_type == LegType.CORE_BANKING.value)
            .first()
        )
        if not cbs or cbs.state != LegState.CONFIRMED.value:
            item["action"] = "skipped"
            item["reason"] = "CORE_BANKING not CONFIRMED"
            out.append(item)
            continue

        led = (
            db.query(TransactionLeg)
            .filter(TransactionLeg.txn_id == txn.id, TransactionLeg.leg_type == LegType.LEDGER.value)
            .first()
        )
        if led and led.state == LegState.CONFIRMED.value:
            try:
                txn.state = transition(txn.state, "COMPLETED")
            except InvalidTransition:
                txn.state = "COMPLETED"
            if txn.operation_type == OperationType.DISBURSEMENT.value and txn.loan_reference:
                loan = db.query(LoanMap).filter(LoanMap.loan_reference == txn.loan_reference).first()
                if loan and not loan.disbursed_txn_id:
                    loan.disbursed_txn_id = txn.id
            db.commit()
            item["action"] = "completed_ledger_already_confirmed"
            item["after_state"] = txn.state
            out.append(item)
            continue

        if txn.operation_type not in (OperationType.DISBURSEMENT.value, OperationType.REPAYMENT.value):
            item["action"] = "skipped"
            item["reason"] = f"unsupported op {txn.operation_type} (recover disburse/repay ERP leg only)"
            out.append(item)
            continue

        if not led:
            led = TransactionLeg(
                txn_id=txn.id,
                leg_type=LegType.LEDGER.value,
                provider="mock-erp",
                state=LegState.PENDING.value,
            )
            db.add(led)
            db.flush()

        entry_date = (txn.created_at.date().isoformat() if txn.created_at else None) or "2026-01-01"
        if txn.operation_type == OperationType.DISBURSEMENT.value:
            draft = jm.disburse_journal(
                external_reference=txn.external_reference,
                entry_date=entry_date,
                amount=Decimal(txn.amount),
            )
        else:
            draft = jm.repay_journal(
                external_reference=txn.external_reference,
                entry_date=entry_date,
                principal=Decimal(txn.amount),
            )

        led.attempts += 1
        try:
            status, body = ledger.post_journal(draft)
        except Exception as exc:  # noqa: BLE001
            led.last_error = str(exc)
            db.commit()
            item["action"] = "failed"
            item["reason"] = str(exc)
            item["after_state"] = txn.state
            out.append(item)
            continue

        led.response_json = json.dumps(body, default=str)
        if status in (200, 201, 409):
            # 409 = already posted under this external_reference → treat as confirmed
            led.state = LegState.CONFIRMED.value
            led.provider_reference = str(body.get("id") or led.provider_reference or "")
            try:
                txn.state = transition(txn.state, "COMPLETED")
            except InvalidTransition:
                txn.state = "COMPLETED"
            if txn.operation_type == OperationType.DISBURSEMENT.value and txn.loan_reference:
                loan = db.query(LoanMap).filter(LoanMap.loan_reference == txn.loan_reference).first()
                if loan and not loan.disbursed_txn_id:
                    loan.disbursed_txn_id = txn.id
            db.commit()
            item["action"] = "erp_posted" if status != 409 else "erp_already_present"
            item["http_status"] = status
            item["after_state"] = txn.state
        else:
            led.state = LegState.FAILED.value
            led.last_error = f"unexpected status {status}"
            db.commit()
            item["action"] = "failed"
            item["http_status"] = status
            item["after_state"] = txn.state
        out.append(item)
    return out
