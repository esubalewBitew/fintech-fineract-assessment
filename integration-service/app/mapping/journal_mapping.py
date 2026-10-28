"""Pure mapping: Fineract-oriented money events → ERP journal lines; reverse() swaps DR/CR."""

from decimal import Decimal

from app.domain.models import JournalDraft, JournalLine

# Seed ERP account refs used by mock-erp
CASH = "ERP-CASH"
LOAN_PORTFOLIO = "ERP-LOAN-PORT"
INTEREST_INCOME = "ERP-INT-INC"


def disburse_journal(*, external_reference: str, entry_date: str, amount: Decimal) -> JournalDraft:
    return JournalDraft(
        external_reference=external_reference,
        entry_date=entry_date,
        description="Loan disbursement",
        lines=[
            JournalLine(account_external_reference=LOAN_PORTFOLIO, debit=amount, credit=Decimal("0")),
            JournalLine(account_external_reference=CASH, debit=Decimal("0"), credit=amount),
        ],
    )


def repay_journal(*, external_reference: str, entry_date: str, principal: Decimal, interest: Decimal = Decimal("0")) -> JournalDraft:
    lines = [
        JournalLine(account_external_reference=CASH, debit=principal + interest, credit=Decimal("0")),
        JournalLine(account_external_reference=LOAN_PORTFOLIO, debit=Decimal("0"), credit=principal),
    ]
    if interest > 0:
        lines.append(JournalLine(account_external_reference=INTEREST_INCOME, debit=Decimal("0"), credit=interest))
    return JournalDraft(
        external_reference=external_reference,
        entry_date=entry_date,
        description="Loan repayment",
        lines=lines,
    )


def reverse(lines: list[JournalLine]) -> list[JournalLine]:
    """Swap debit and credit — trivially testable (brief H)."""
    return [
        JournalLine(
            account_external_reference=ln.account_external_reference,
            debit=ln.credit,
            credit=ln.debit,
        )
        for ln in lines
    ]


def reversing_journal(*, original: JournalDraft, reverse_external_reference: str) -> JournalDraft:
    return JournalDraft(
        external_reference=reverse_external_reference,
        entry_date=original.entry_date,
        description=f"Reversal of {original.external_reference}",
        lines=reverse(original.lines),
        reverses_external_reference=original.external_reference,
    )
