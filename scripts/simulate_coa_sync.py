#!/usr/bin/env python3
"""Step 11 — CoA sync twice; second run should be mostly already_mapped / skipped_currency.

Writes evidence/11-coa-sync-1.json and evidence/11-coa-sync-2.json (+ summary).
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT1 = ROOT / "evidence" / "11-coa-sync-1.json"
OUT2 = ROOT / "evidence" / "11-coa-sync-2.json"
SUMMARY = ROOT / "evidence" / "11-coa-sync-summary.json"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
HEADERS = {"X-Api-Key": KEY}


def _counts(payload: dict) -> dict:
    statuses = [r.get("status") for r in payload.get("results") or []]
    return dict(Counter(statuses))


def main() -> int:
    with httpx.Client(timeout=120.0) as client:
        r1 = client.post(f"{INT}/sync/coa", headers=HEADERS)
        r1.raise_for_status()
        b1 = r1.json()
        r2 = client.post(f"{INT}/sync/coa", headers=HEADERS)
        r2.raise_for_status()
        b2 = r2.json()

    c1, c2 = _counts(b1), _counts(b2)
    # Second run: no fresh creates expected (already_mapped / skipped_currency / conflict ok)
    created_second = c2.get("created", 0)
    ok = created_second == 0 and b2.get("count", 0) >= 1
    summary = {
        "run1_counts": c1,
        "run2_counts": c2,
        "pass": ok,
        "rule": "second sync must not create new GL mappings (already_mapped / skipped_currency)",
    }
    OUT1.parent.mkdir(parents=True, exist_ok=True)
    OUT1.write_text(json.dumps(b1, indent=2, default=str) + "\n")
    OUT2.write_text(json.dumps(b2, indent=2, default=str) + "\n")
    SUMMARY.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"wrote": [str(OUT1), str(OUT2), str(SUMMARY)], "pass": ok, "summary": summary}, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
