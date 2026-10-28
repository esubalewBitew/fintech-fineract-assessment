from decimal import Decimal

from app.reconciliation.engine import Record, fineract_erp_labels, reconcile


def test_four_outcomes():
    left = [
        Record("A", Decimal("100")),
        Record("B", Decimal("50")),
        Record("C", Decimal("10")),
    ]
    right = [
        Record("A", Decimal("100")),
        Record("B", Decimal("40")),
        Record("D", Decimal("5")),
    ]
    results = fineract_erp_labels(reconcile(left, right))
    by_ref = {r["outcome"] + ":" + r["external_reference"]: r for r in results}
    assert any(r["outcome"] == "MATCHED" and r["external_reference"] == "A" for r in results)
    assert any(r["outcome"] == "AMOUNT_MISMATCH" and r["external_reference"] == "B" for r in results)
    assert any(r["outcome"] == "MISSING_IN_ERP" and r["external_reference"] == "C" for r in results)
    assert any(r["outcome"] == "MISSING_IN_FINERACT" and r["external_reference"] == "D" for r in results)
    assert len(by_ref) == 4
