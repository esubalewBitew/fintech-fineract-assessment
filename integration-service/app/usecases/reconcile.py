from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models import IntegrationTransaction, TransactionLeg
from app.domain.models import LegType, OperationType
from app.ports.ledger import LedgerPort
from app.reconciliation.engine import Record, fineract_erp_labels, reconcile


def reconcile_fineract_erp(db: Session, ledger: LedgerPort, *, since: str | None = None) -> list[dict]:
    """Build Fineract-side amounts from completed integration txns; ERP from journal list."""
    left: list[Record] = []
    txns = (
        db.query(IntegrationTransaction)
        .filter(IntegrationTransaction.state.in_(["COMPLETED", "NEEDS_RECONCILIATION"]))
        .filter(
            IntegrationTransaction.operation_type.in_(
                [
                    OperationType.DISBURSEMENT.value,
                    OperationType.REPAYMENT.value,
                    OperationType.REVERSAL.value,
                ]
            )
        )
        .all()
    )
    # Net by external_reference: reversals negate original amount under their own REF; compare journals 1:1 by ref
    for txn in txns:
        cbs_leg = (
            db.query(TransactionLeg)
            .filter(TransactionLeg.txn_id == txn.id, TransactionLeg.leg_type == LegType.CORE_BANKING.value)
            .first()
        )
        if not cbs_leg or cbs_leg.state != "CONFIRMED":
            continue
        amt = txn.amount
        if txn.operation_type == OperationType.REVERSAL.value:
            amt = -amt
        left.append(Record(external_reference=txn.external_reference, amount=amt, kind=txn.operation_type))

    right: list[Record] = []
    for j in ledger.list_journals(since=since):
        total = Decimal(str(j.get("total_debit") or 0))
        # reversing journals: still positive totals; use sign from reverses field
        if j.get("reverses_external_reference"):
            total = -total
        right.append(Record(external_reference=j["external_reference"], amount=total))

    return fineract_erp_labels(reconcile(left, right))
