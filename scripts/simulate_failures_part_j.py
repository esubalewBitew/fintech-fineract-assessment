#!/usr/bin/env python3
"""Part J — remaining failure/recovery proofs (beyond timeout→lookup).

Scenarios:
  j2 ERP down after Fineract write → NEEDS_RECONCILIATION (no ERP journal yet)
  j3 POST /admin/recover → ERP posted, COMPLETED
  j4 Fineract fault=down → no success invented (502 / NEEDS_RECON)

Timeout→LOOKUP remains make simulate-timeout (evidence/08-*).

Writes evidence/08-j-suite.json
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
EVIDENCE = ROOT / "evidence" / "08-j-suite.json"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
ERP = os.environ.get("MOCK_ERP_URL", "http://localhost:8081")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
ERP_KEY = os.environ.get("MOCK_ERP_API_KEY", "mock-erp-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}
ERP_HEADERS = {"X-Api-Key": ERP_KEY, "Content-Type": "application/json"}


def _prepare_loan(client: httpx.Client, suffix: str, principal: Decimal) -> str:
    today = date.today().isoformat()
    client_uid = f"CLI-JF-{suffix}"
    loan_ref = f"LOAN-JF-{suffix}"
    client.post(
        f"{INT}/clients",
        headers=HEADERS,
        json={"client_uid": client_uid, "firstname": "JFault", "lastname": suffix, "activation_date": today},
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
    return loan_ref


def main() -> int:
    today = date.today().isoformat()
    run_id = uuid.uuid4().hex[:8]
    principal = Decimal("400000")
    report: dict = {"run_id": run_id, "cases": {}}

    with httpx.Client(timeout=120.0) as client:
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()
        client.post(f"{ERP}/admin/faults", headers=ERP_HEADERS, json={"mode": "none"})
        client.post(f"{INT}/admin/fineract-fault", headers=HEADERS, json={"mode": "none"})

        # --- j2: ERP down after Fineract ---
        loan_erp = _prepare_loan(client, f"{run_id}e", principal)
        ref_erp = f"DISB-J-ERPDOWN-{run_id}"
        client.post(f"{ERP}/admin/faults", headers=ERP_HEADERS, json={"mode": "down"}).raise_for_status()
        r2 = client.post(
            f"{INT}/loans/disburse",
            headers=HEADERS,
            json={
                "external_reference": ref_erp,
                "loan_reference": loan_erp,
                "amount": str(principal),
                "currency": "RWF",
                "transaction_date": today,
            },
        )
        body2 = r2.json() if r2.content else {}
        client.post(f"{ERP}/admin/faults", headers=ERP_HEADERS, json={"mode": "none"})
        listed = client.get(f"{INT}/admin/recover", headers=HEADERS)
        listed.raise_for_status()
        listed_body = listed.json()
        in_list = any(t.get("external_reference") == ref_erp for t in listed_body.get("transactions") or [])
        erp_before = client.get(
            f"{ERP}/journal-entries",
            headers=ERP_HEADERS,
            params={"external_reference": ref_erp},
        )
        erp_before.raise_for_status()
        journals_before = erp_before.json() if isinstance(erp_before.json(), list) else []
        j2_pass = (
            r2.status_code in (200, 502)
            and (body2.get("state") == "NEEDS_RECONCILIATION" or in_list)
            and len(journals_before) == 0
        )
        report["cases"]["j2_erp_down_after_fineract"] = {
            "external_reference": ref_erp,
            "http_status": r2.status_code,
            "response": body2,
            "in_recover_list": in_list,
            "erp_journal_count_before_recover": len(journals_before),
            "pass": j2_pass,
        }

        # --- j3: recover ---
        rec = client.post(f"{INT}/admin/recover", headers=HEADERS)
        rec.raise_for_status()
        rec_body = rec.json()
        erp_after = client.get(
            f"{ERP}/journal-entries",
            headers=ERP_HEADERS,
            params={"external_reference": ref_erp},
        )
        erp_after.raise_for_status()
        journals_after = erp_after.json() if isinstance(erp_after.json(), list) else []
        recovered_row = next(
            (x for x in (rec_body.get("results") or []) if x.get("external_reference") == ref_erp),
            None,
        )
        j3_pass = (
            recovered_row is not None
            and recovered_row.get("after_state") == "COMPLETED"
            and len(journals_after) == 1
        )
        report["cases"]["j3_restart_recover"] = {
            "recover_response": rec_body,
            "recovered_row": recovered_row,
            "erp_journal_count_after": len(journals_after),
            "pass": j3_pass,
        }

        # --- j4: Fineract down ---
        loan_down = _prepare_loan(client, f"{run_id}d", principal)
        ref_down = f"DISB-J-FINDOWN-{run_id}"
        client.post(f"{INT}/admin/fineract-fault", headers=HEADERS, json={"mode": "down"}).raise_for_status()
        r4 = client.post(
            f"{INT}/loans/disburse",
            headers=HEADERS,
            json={
                "external_reference": ref_down,
                "loan_reference": loan_down,
                "amount": str(principal),
                "currency": "RWF",
                "transaction_date": today,
            },
        )
        body4 = r4.json() if r4.content else {}
        client.post(f"{INT}/admin/fineract-fault", headers=HEADERS, json={"mode": "none"})
        erp_down = client.get(
            f"{ERP}/journal-entries",
            headers=ERP_HEADERS,
            params={"external_reference": ref_down},
        )
        erp_down.raise_for_status()
        journals_down = erp_down.json() if isinstance(erp_down.json(), list) else []
        # Must not invent COMPLETED / must not post ERP
        j4_pass = r4.status_code >= 400 and body4.get("state") != "COMPLETED" and len(journals_down) == 0
        report["cases"]["j4_fineract_down"] = {
            "external_reference": ref_down,
            "http_status": r4.status_code,
            "response": body4,
            "erp_journal_count": len(journals_down),
            "pass": j4_pass,
        }

        report["note"] = "j1 timeout→LOOKUP_BY_EXTERNAL_ID: see evidence/08-timeout-lookup.json (make simulate-timeout)"
        report["pass"] = j2_pass and j3_pass and j4_pass

    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE.write_text(json.dumps(report, indent=2, default=str) + "\n")
    print(json.dumps({"wrote": str(EVIDENCE), "pass": report["pass"], "cases": {k: v.get("pass") for k, v in report["cases"].items()}}, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
