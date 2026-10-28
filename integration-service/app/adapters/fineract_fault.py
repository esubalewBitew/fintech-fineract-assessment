"""Process-local Fineract fault injection for Part J simulations."""

from __future__ import annotations

_FAULT_MODE = "none"


def get_fault_mode() -> str:
    return _FAULT_MODE


def set_fault_mode(mode: str) -> str:
    global _FAULT_MODE
    if mode not in ("none", "timeout_after_write", "down"):
        raise ValueError("mode must be none|timeout_after_write|down")
    _FAULT_MODE = mode
    return _FAULT_MODE
