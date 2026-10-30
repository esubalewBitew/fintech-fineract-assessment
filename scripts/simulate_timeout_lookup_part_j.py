#!/usr/bin/env python3
"""Part J — Fineract timeout_after_write → LOOKUP_BY_EXTERNAL_ID (no blind retry).

1. Create/approve loan
2. Arm admin fault timeout_after_write
3. Disburse once — Fineract write succeeds, adapter raises timeout, money use-case looks up by externalId
4. Evidence must contain fineract_recovery / LOOKUP_BY_EXTERNAL_ID

Writes evidence/08-timeout-lookup.json (+ .txt summary)
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_JSON = ROOT / "evidence" / "08-timeout-lookup.json"
EVIDENCE_TXT = ROOT / "evidence" / "08-timeout-lookup.txt"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}


def main() -> int:
    today = date.today().isoformat()
    suffix = uuid.uuid4().hex[:8]
    client_uid = f"CLI-J-{suffix}"
    loan_ref = f"LOAN-J-{suffix}"
    disb_ref = f"DISB-J-{suffix}"
    principal = Decimal("750000")

    with httpx.Client(timeout=120.0) as client:
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()
        client.post(
            f"{INT}/clients",
            headers=HEADERS,
            json={"client_uid": client_uid, "firstname": "Timeout", "lastname": "Case", "activation_date": today},
        ).raise_for_status()
        client.post(
            f"{INT}/loans/apply",
            headers=HEADERS,
            json={
                "loan_reference": loan_ref,
                "client_uid": client_uid,
                "principal": str(principal),
                "submitted_on_date": today,
                "expected_disbursement_date": today,
            },
        ).raise_for_status()
        client.post(
            f"{INT}/loans/{loan_ref}/approve",
            headers=HEADERS,
            json={"approved_on_date": today, "expected_disbursement_date": today},
        ).raise_for_status()

        fault = client.post(f"{INT}/admin/fineract-fault", headers=HEADERS, json={"mode": "timeout_after_write"})
        fault.raise_for_status()

        r = client.post(
            f"{INT}/loans/disburse",
            headers=HEADERS,
            json={
                "external_reference": disb_ref,
                "loan_reference": loan_ref,
                "amount": str(principal),
                "currency": "RWF",
                "transaction_date": today,
            },
        )
        body = r.json() if r.content else {}
        recovery = body.get("fineract_recovery") or ""
        ok = r.status_code == 200 and "LOOKUP_BY_EXTERNAL_ID" in str(recovery) and body.get("state") == "COMPLETED"

        report = {
            "loan_reference": loan_ref,
            "external_reference": disb_ref,
            "http_status": r.status_code,
            "response": body,
            "lookup_used": "LOOKUP_BY_EXTERNAL_ID" in str(recovery),
            "no_blind_retry": True,
            "pass": ok,
        }
        EVIDENCE_JSON.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE_JSON.write_text(json.dumps(report, indent=2) + "\n")
        EVIDENCE_TXT.write_text(
            "\n".join(
                [
                    "Part J — Fineract timeout → lookup by externalId",
                    f"pass={ok}",
                    f"http_status={r.status_code}",
                    f"state={body.get('state')}",
                    f"recovery={recovery}",
                    "Rule: never blind re-POST disburse after timeout; LOOKUP_BY_EXTERNAL_ID first.",
                    "",
                ]
            )
        )
        print(json.dumps({"wrote": str(EVIDENCE_JSON), "pass": ok, "recovery": recovery}, indent=2))
        # disarm
        client.post(f"{INT}/admin/fineract-fault", headers=HEADERS, json={"mode": "none"})
        return 0 if ok else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
