from __future__ import annotations

import hashlib
import json
from typing import Any, Optional, Tuple

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from ulid import ULID

from app.db.models import IntegrationTransaction


def payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(raw.encode()).hexdigest()


def claim_or_get(
    db: Session,
    *,
    operation_type: str,
    external_reference: str,
    payload: dict[str, Any],
    loan_reference: Optional[str],
    amount: Any,
    currency: str,
    rail: str,
    correlation_id: Optional[str],
) -> Tuple[IntegrationTransaction, bool]:
    """Returns (txn, created). If same hash exists → replay. Different hash → IntegrityError/conflict handled by caller."""
    digest = payload_hash(payload)
    existing = (
        db.query(IntegrationTransaction)
        .filter(
            IntegrationTransaction.operation_type == operation_type,
            IntegrationTransaction.external_reference == external_reference,
        )
        .first()
    )
    if existing:
        return existing, False

    txn = IntegrationTransaction(
        id=str(ULID()),
        operation_type=operation_type,
        external_reference=external_reference,
        loan_reference=loan_reference,
        amount=amount,
        currency=currency,
        rail=rail,
        payload_hash=digest,
        state="RECEIVED",
        correlation_id=correlation_id,
    )
    db.add(txn)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(IntegrationTransaction)
            .filter(
                IntegrationTransaction.operation_type == operation_type,
                IntegrationTransaction.external_reference == external_reference,
            )
            .one()
        )
        return existing, False
    db.refresh(txn)
    return txn, True
