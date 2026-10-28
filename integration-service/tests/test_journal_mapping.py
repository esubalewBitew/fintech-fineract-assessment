from decimal import Decimal

from app.mapping.journal_mapping import repay_journal, reverse


def test_reverse_swaps_debit_credit():
    draft = repay_journal(
        external_reference="FIN-1",
        entry_date="2026-01-01",
        principal=Decimal("1000"),
        interest=Decimal("100"),
    )
    rev = reverse(draft.lines)
    assert len(rev) == len(draft.lines)
    for a, b in zip(draft.lines, rev):
        assert a.debit == b.credit
        assert a.credit == b.debit
        assert a.account_external_reference == b.account_external_reference
