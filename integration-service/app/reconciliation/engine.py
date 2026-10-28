from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class Record:
    external_reference: str
    amount: Decimal
    kind: str = ""  # optional: DISBURSEMENT/REPAYMENT/REVERSAL


@dataclass
class ReconcileResult:
    external_reference: str
    outcome: str
    left_amount: Decimal | None = None
    right_amount: Decimal | None = None


def reconcile(left: Iterable[Record], right: Iterable[Record]) -> list[ReconcileResult]:
    """Generic join on external_reference.

    Outcomes: MATCHED | MISSING_IN_RIGHT | MISSING_IN_LEFT | AMOUNT_MISMATCH
    (Fineract↔ERP: RIGHT=ERP → MISSING_IN_ERP / MISSING_IN_FINERACT aliases applied by caller.)
    """
    left_map = {r.external_reference: r for r in left}
    right_map = {r.external_reference: r for r in right}
    keys = sorted(set(left_map) | set(right_map))
    out: list[ReconcileResult] = []
    for key in keys:
        l = left_map.get(key)
        r = right_map.get(key)
        if l and not r:
            out.append(ReconcileResult(key, "MISSING_IN_RIGHT", l.amount, None))
        elif r and not l:
            out.append(ReconcileResult(key, "MISSING_IN_LEFT", None, r.amount))
        elif l and r:
            if l.amount == r.amount:
                out.append(ReconcileResult(key, "MATCHED", l.amount, r.amount))
            else:
                out.append(ReconcileResult(key, "AMOUNT_MISMATCH", l.amount, r.amount))
    return out


def fineract_erp_labels(results: list[ReconcileResult]) -> list[dict]:
    rename = {
        "MISSING_IN_RIGHT": "MISSING_IN_ERP",
        "MISSING_IN_LEFT": "MISSING_IN_FINERACT",
    }
    return [
        {
            "external_reference": r.external_reference,
            "outcome": rename.get(r.outcome, r.outcome),
            "fineract_amount": str(r.left_amount) if r.left_amount is not None else None,
            "erp_amount": str(r.right_amount) if r.right_amount is not None else None,
        }
        for r in results
    ]
