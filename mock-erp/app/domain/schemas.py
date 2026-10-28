from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel, Field, model_validator


class AccountCreate(BaseModel):
    external_reference: str
    code: str
    name: str
    type: str
    usage: str = "DETAIL"
    currency: str = "RWF"
    description: Optional[str] = None
    manual_entries_allowed: bool = True


class AccountOut(BaseModel):
    id: int
    external_reference: str
    code: str
    name: str
    type: str
    usage: str
    currency: str
    description: Optional[str]
    manual_entries_allowed: bool

    model_config = {"from_attributes": True}


class JournalLineIn(BaseModel):
    account_external_reference: str
    debit: Decimal = Field(default=Decimal("0"))
    credit: Decimal = Field(default=Decimal("0"))

    @model_validator(mode="after")
    def one_side(self) -> "JournalLineIn":
        if self.debit < 0 or self.credit < 0:
            raise ValueError("debit and credit must be non-negative")
        if (self.debit > 0 and self.credit > 0) or (self.debit == 0 and self.credit == 0):
            raise ValueError("each line must have either debit or credit, not both/neither")
        return self


class JournalEntryCreate(BaseModel):
    external_reference: str
    entry_date: date
    description: Optional[str] = None
    source_system: str = "integration"
    reverses_external_reference: Optional[str] = None
    lines: List[JournalLineIn]

    @model_validator(mode="after")
    def balanced(self) -> "JournalEntryCreate":
        if len(self.lines) < 2:
            raise ValueError("journal must have at least 2 lines")
        total_dr = sum((ln.debit for ln in self.lines), Decimal("0"))
        total_cr = sum((ln.credit for ln in self.lines), Decimal("0"))
        if total_dr != total_cr:
            raise ValueError(f"unbalanced journal: debit={total_dr} credit={total_cr}")
        return self


class JournalLineOut(BaseModel):
    account_external_reference: str
    account_code: str
    debit: Decimal
    credit: Decimal


class JournalEntryOut(BaseModel):
    id: int
    external_reference: str
    entry_date: date
    description: Optional[str]
    source_system: str
    reverses_external_reference: Optional[str] = None
    payload_hash: str
    created_at: datetime
    lines: List[JournalLineOut]
    total_debit: Decimal
    total_credit: Decimal


class FaultRequest(BaseModel):
    mode: str
