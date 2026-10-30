#!/usr/bin/env python3
"""Part K — seed four cases, GET /reconcile/fineract-erp, assert all outcomes.

Writes evidence/09-reconcile-four-outcomes.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

from seed_reconcile_part_k import seed

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "09-reconcile-four-outcomes.json"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
HEADERS = {"X-Api-Key": KEY}

REQUIRED = {"MATCHED", "MISSING_IN_ERP", "MISSING_IN_FINERACT", "AMOUNT_MISMATCH"}


def main() -> int:
    seeded = seed()
    refs = seeded["refs"]
    ref_to_expected = {refs[k]: k for k in REQUIRED}

    with httpx.Client(timeout=60.0) as client:
        r = client.get(f"{INT}/reconcile/fineract-erp", headers=HEADERS)
        r.raise_for_status()
        report = r.json()

    results = report.get("results") or []
    seeded_rows = [row for row in results if row.get("external_reference") in ref_to_expected]
    by_ref = {row["external_reference"]: row.get("outcome") for row in seeded_rows}
    outcomes_found = {by_ref[ref] for ref in refs.values() if ref in by_ref}

    mismatches = []
    for outcome, ref in refs.items():
        got = by_ref.get(ref)
        if got != outcome:
            mismatches.append({"ref": ref, "expected": outcome, "got": got})

    passed = outcomes_found == REQUIRED and not mismatches
    payload = {
        "seed": seeded,
        "report": report,
        "seeded_rows": seeded_rows,
        "outcomes_found": sorted(outcomes_found),
        "mismatches": mismatches,
        "pass": passed,
    }
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(payload, indent=2, default=str) + "\n")
    print(
        json.dumps(
            {
                "wrote": str(EVIDENCE),
                "pass": passed,
                "outcomes_found": sorted(outcomes_found),
                "mismatches": mismatches,
            },
            indent=2,
        )
    )
    return 0 if passed else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
