from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import IntegrationTransaction


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
