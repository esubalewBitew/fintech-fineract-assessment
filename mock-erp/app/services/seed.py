"""Seed 9 RWF accounts + 1 USD account for the RWF gate demo."""

from sqlalchemy.orm import Session

from app.db.models import Account, FaultConfig

SEED_ACCOUNTS = [
    ("ERP-CASH", "1000", "Cash at Bank", "ASSET", "RWF"),
    ("ERP-LOAN-PORT", "1100", "Loan Portfolio", "ASSET", "RWF"),
    ("ERP-INT-REC", "1200", "Interest Receivable", "ASSET", "RWF"),
    ("ERP-OVERPAY", "2100", "Overpayment Liability", "LIABILITY", "RWF"),
    ("ERP-CLIENT-DEP", "2200", "Client Deposits", "LIABILITY", "RWF"),
    ("ERP-EQUITY", "3000", "Equity", "EQUITY", "RWF"),
    ("ERP-FEE-INC", "4001", "Fee Income", "INCOME", "RWF"),
    ("ERP-INT-INC", "4002", "Interest Income", "INCOME", "RWF"),
    ("ERP-OP-EXP", "5001", "Operating Expense", "EXPENSE", "RWF"),
    ("ERP-USD-CASH", "1900", "USD Cash (non-RWF seed)", "ASSET", "USD"),
]


def seed_if_empty(db: Session) -> None:
    if db.query(Account).count() == 0:
        for ref, code, name, typ, currency in SEED_ACCOUNTS:
            db.add(
                Account(
                    external_reference=ref,
                    code=code,
                    name=name,
                    type=typ,
                    usage="DETAIL",
                    currency=currency,
                    description=name,
                    manual_entries_allowed=True,
                )
            )
    if db.query(FaultConfig).count() == 0:
        db.add(FaultConfig(mode="none"))
    db.commit()
