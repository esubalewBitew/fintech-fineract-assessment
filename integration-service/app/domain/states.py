"""Single transition table for integration transaction states."""

from __future__ import annotations

ALLOWED: dict[str, set[str]] = {
    "RECEIVED": {"RAIL_PENDING", "RAIL_CONFIRMED", "FAILED"},
    "RAIL_PENDING": {"RAIL_CONFIRMED", "FAILED", "NEEDS_RECONCILIATION"},
    "RAIL_CONFIRMED": {"FINERACT_PENDING", "FAILED", "NEEDS_RECONCILIATION"},
    "FINERACT_PENDING": {"FINERACT_DONE", "FAILED", "NEEDS_RECONCILIATION"},
    "FINERACT_DONE": {"ERP_PENDING", "NEEDS_RECONCILIATION"},
    "ERP_PENDING": {"COMPLETED", "NEEDS_RECONCILIATION", "FAILED"},
    "COMPLETED": set(),
    "FAILED": set(),
    "NEEDS_RECONCILIATION": {"COMPLETED", "FAILED"},
}


class InvalidTransition(Exception):
    pass


def transition(current: str, new: str) -> str:
    allowed = ALLOWED.get(current, set())
    if new not in allowed:
        raise InvalidTransition(f"cannot transition {current} → {new}")
    return new
