from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any, Optional


class OperationType(str, Enum):
    DISBURSEMENT = "DISBURSEMENT"
    REPAYMENT = "REPAYMENT"
    REVERSAL = "REVERSAL"
    REFUND = "REFUND"


class LegType(str, Enum):
    RAIL = "RAIL"
    CORE_BANKING = "CORE_BANKING"
    LEDGER = "LEDGER"


class LegState(str, Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class RailStatus(str, Enum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    FAILED = "FAILED"


@dataclass
class Beneficiary:
    account_ref: str
    name: str = ""


@dataclass
class Payer:
    account_ref: str
    name: str = ""


@dataclass
class RailResult:
    status: RailStatus
    rail_reference: str
    raw: Optional[dict] = None


@dataclass
class RailEvent:
    rail_reference: str
    status: RailStatus
    external_reference: Optional[str] = None
    raw: Optional[dict] = None


@dataclass
class CoAAccount:
    external_reference: str
    code: str
    name: str
    type: str
    usage: str
    currency: str
    description: Optional[str] = None
    manual_entries_allowed: bool = True


@dataclass
class JournalLine:
    account_external_reference: str
    debit: Decimal
    credit: Decimal


@dataclass
class JournalDraft:
    external_reference: str
    entry_date: str
    description: Optional[str]
    lines: list
    reverses_external_reference: Optional[str] = None


@dataclass
class FineractGlCreate:
    external_reference: str
    gl_code: str
    name: str
    type: int
    usage: int
    description: Optional[str]
    manual_entries_allowed: bool


TYPE_TO_FINERACT = {"ASSET": 1, "LIABILITY": 2, "EQUITY": 3, "INCOME": 4, "EXPENSE": 5}
USAGE_TO_FINERACT = {"DETAIL": 1, "HEADER": 2}
