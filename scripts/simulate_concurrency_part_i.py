#!/usr/bin/env python3
"""Part I — concurrency proofs.

1) 10 parallel identical disbursement refs → 1 Fineract txn + 1 ERP journal
2) 4 sequential disbursements on different loans (sanity)

Writes evidence/07-concurrency.json
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "evidence" / "07-concurrency.json"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
ERP = os.environ.get("MOCK_ERP_URL", "http://localhost:8081")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
ERP_KEY = os.environ.get("MOCK_ERP_API_KEY", "mock-erp-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}


def _prepare_loan(client: httpx.Client, suffix: str, principal: Decimal) -> str:
    today = date.today().isoformat()
    client_uid = f"CLI-CONC-{suffix}"
    loan_ref = f"LOAN-CONC-{suffix}"
    client.post(
        f"{INT}/clients",
        headers=HEADERS,
        json={"client_uid": client_uid, "firstname": "Conc", "lastname": suffix, "activation_date": today},
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
    principal = Decimal("500000")
    run_id = uuid.uuid4().hex[:8]

    with httpx.Client(timeout=120.0) as client:
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()

        # --- Critical: 10 parallel identical external_reference ---
        loan_ref = _prepare_loan(client, f"{run_id}a", principal)
        same_ref = f"DISB-PAR-{run_id}"
        payload = {
            "external_reference": same_ref,
            "loan_reference": loan_ref,
            "amount": str(principal),
            "currency": "RWF",
            "transaction_date": today,
        }

        def one_disburse(_: int) -> dict:
            with httpx.Client(timeout=120.0) as c:
                r = c.post(f"{INT}/loans/disburse", headers=HEADERS, json=payload)
                return {"status_code": r.status_code, "body": r.json() if r.content else {}}

        parallel_results = []
        with ThreadPoolExecutor(max_workers=10) as pool:
            futs = [pool.submit(one_disburse, i) for i in range(10)]
            for f in as_completed(futs):
                parallel_results.append(f.result())

        erp = client.get(
            f"{ERP}/journal-entries",
            headers={"X-Api-Key": ERP_KEY},
            params={"external_reference": same_ref},
        )
        erp.raise_for_status()
        erp_journals = erp.json() if isinstance(erp.json(), list) else erp.json().get("items") or []

        states = [r["body"].get("state") for r in parallel_results]
        txn_ids = {r["body"].get("integration_txn_id") for r in parallel_results if r["body"].get("integration_txn_id")}
        ok_codes = [r["status_code"] for r in parallel_results]
        completed = [r for r in parallel_results if r["body"].get("state") == "COMPLETED"]
        replays = [r for r in parallel_results if r["body"].get("idempotent_replay")]
        # Critical reviewer proof: 10 workers → 1 integration txn → 1 ERP journal
        identical_proof = (
            len(erp_journals) == 1
            and len(txn_ids) == 1
            and any(r["body"].get("state") == "COMPLETED" for r in parallel_results)
        )

        # --- 4 sequential different loans ---
        sequential = []
        for i in range(4):
            lr = _prepare_loan(client, f"{run_id}s{i}", principal)
            ref = f"DISB-SEQ-{run_id}-{i}"
            r = client.post(
                f"{INT}/loans/disburse",
                headers=HEADERS,
                json={
                    "external_reference": ref,
                    "loan_reference": lr,
                    "amount": str(principal),
                    "currency": "RWF",
                    "transaction_date": today,
                },
            )
            sequential.append({"loan_reference": lr, "external_reference": ref, "status_code": r.status_code, "body": r.json()})

        report = {
            "parallel_identical_ref": {
                "external_reference": same_ref,
                "loan_reference": loan_ref,
                "workers": 10,
                "http_status_codes": ok_codes,
                "integration_txn_ids": list(txn_ids),
                "states": states,
                "erp_journal_count": len(erp_journals),
                "completed_count": len(completed),
                "idempotent_replay_count": len(replays),
                "proof_one_fineract_one_erp": identical_proof and len(erp_journals) == 1 and len(txn_ids) == 1,
            },
            "sequential_four_loans": sequential,
            "pass": identical_proof and all(s["status_code"] == 200 and s["body"].get("state") == "COMPLETED" for s in sequential),
        }
        EVIDENCE.parent.mkdir(parents=True, exist_ok=True)
        EVIDENCE.write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"wrote": str(EVIDENCE), "pass": report["pass"], "parallel": report["parallel_identical_ref"]}, indent=2))
        return 0 if report["pass"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
