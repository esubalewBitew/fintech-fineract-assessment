#!/usr/bin/env python3
"""Part D — Apply → Approve → Disburse → 3 repayments → payoff → Closed.

Writes evidence/03-lifecycle.json with status + balances each step.
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
EVIDENCE = ROOT / "evidence" / "03-lifecycle.json"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}


def main() -> int:
    today = date.today().isoformat()
    suffix = uuid.uuid4().hex[:8]
    client_uid = f"CLI-LIFE-{suffix}"
    loan_ref = f"LOAN-LIFE-{suffix}"
    principal = Decimal("1000000")
    steps = []

    with httpx.Client(timeout=120.0) as client:
        # Ensure CoA (idempotent)
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()

        r = client.post(
            f"{INT}/clients",
            headers=HEADERS,
            json={
                "client_uid": client_uid,
                "firstname": "Kigali",
                "lastname": "SME",
                "activation_date": today,
            },
        )
        r.raise_for_status()
        steps.append({"step": "create_client", "response": r.json()})

        r = client.post(
            f"{INT}/loans/apply",
            headers=HEADERS,
            json={
                "loan_reference": loan_ref,
                "client_uid": client_uid,
                "principal": str(principal),
                "submitted_on_date": today,
                "expected_disbursement_date": today,
            },
        )
        r.raise_for_status()
        steps.append({"step": "apply", "response": r.json()})

        r = client.post(
            f"{INT}/loans/{loan_ref}/approve",
            headers=HEADERS,
            json={"approved_on_date": today, "expected_disbursement_date": today},
        )
        r.raise_for_status()
        steps.append({"step": "approve", "response": r.json()})

        snap = client.get(f"{INT}/loans/{loan_ref}", headers=HEADERS)
        snap.raise_for_status()
        steps.append({"step": "snapshot_after_approve", "loan": snap.json()})

        disb_ref = f"DISB-{suffix}"
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
        r.raise_for_status()
        steps.append({"step": "disburse", "response": r.json()})
        snap = client.get(f"{INT}/loans/{loan_ref}", headers=HEADERS)
        snap.raise_for_status()
        steps.append({"step": "snapshot_after_disburse", "loan": snap.json()})

        # Three partial principal repayments then payoff remainder
        partials = [Decimal("200000"), Decimal("200000"), Decimal("200000")]
        paid = Decimal("0")
        for i, amt in enumerate(partials, start=1):
            ref = f"REPAY-{suffix}-{i}"
            r = client.post(
                f"{INT}/loans/repay",
                headers=HEADERS,
                json={
                    "external_reference": ref,
                    "loan_reference": loan_ref,
                    "amount": str(amt),
                    "principal": str(amt),
                    "interest": "0",
                    "currency": "RWF",
                    "transaction_date": today,
                },
            )
            r.raise_for_status()
            paid += amt
            snap = client.get(f"{INT}/loans/{loan_ref}", headers=HEADERS)
            snap.raise_for_status()
            steps.append({"step": f"repayment_{i}", "amount": str(amt), "response": r.json(), "loan": snap.json()})

        # Pay whatever Fineract still shows outstanding (principal + interest)
        snap = client.get(f"{INT}/loans/{loan_ref}", headers=HEADERS)
        snap.raise_for_status()
        before_payoff = snap.json()
        outstanding = Decimal(str(before_payoff.get("totalOutstanding") or "0"))
        # Loop small residual interest until closed or outstanding hits 0
        round_i = 0
        while outstanding > 0 and round_i < 5:
            round_i += 1
            ref = f"REPAY-{suffix}-payoff-{round_i}"
            r = client.post(
                f"{INT}/loans/repay",
                headers=HEADERS,
                json={
                    "external_reference": ref,
                    "loan_reference": loan_ref,
                    "amount": str(outstanding),
                    "principal": str(outstanding),
                    "interest": "0",
                    "currency": "RWF",
                    "transaction_date": today,
                },
            )
            r.raise_for_status()
            snap = client.get(f"{INT}/loans/{loan_ref}", headers=HEADERS)
            snap.raise_for_status()
            steps.append(
                {
                    "step": f"payoff_round_{round_i}",
                    "amount": str(outstanding),
                    "response": r.json(),
                    "loan": snap.json(),
                }
            )
            outstanding = Decimal(str(snap.json().get("totalOutstanding") or "0"))

        final = snap.json()
        status = final.get("status") or ""
        outstanding = final.get("totalOutstanding")
        closed_ok = "closed" in str(status).lower() or (
            outstanding is not None and Decimal(str(outstanding)) == 0
        )
        report = {
            "client_uid": client_uid,
            "loan_reference": loan_ref,
            "principal": str(principal),
            "final_status": status,
            "final_totalOutstanding": outstanding,
            "closed_ok": closed_ok,
            "steps": steps,
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"wrote": str(EVIDENCE), "final_status": status, "closed_ok": closed_ok}, indent=2))
        return 0 if closed_ok else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
