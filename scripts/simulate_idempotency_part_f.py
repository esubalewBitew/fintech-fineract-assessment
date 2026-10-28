#!/usr/bin/env python3
"""Part F — idempotency matrix evidence.

H5.1 Identical retry after COMPLETED → 200 + same integration_txn_id + idempotent_replay
H5.3 Same external_reference, different payload → 409
H5.2 Retry while in-progress → 202 + current state (seeded RAIL_PENDING via SQL)

Writes evidence/05-idempotency.json (+ .txt summary)
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_JSON = ROOT / "evidence" / "05-idempotency.json"
EVIDENCE_TXT = ROOT / "evidence" / "05-idempotency.txt"

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}


def _sql_integration(sql: str) -> None:
    proc = subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "db",
            "psql",
            "-U",
            "integration",
            "-d",
            "integration",
            "-v",
            "ON_ERROR_STOP=1",
        ],
        input=sql,
        text=True,
        cwd=str(ROOT),
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or proc.stdout)


def _prepare_loan(client: httpx.Client, suffix: str, principal: Decimal) -> str:
    today = date.today().isoformat()
    client_uid = f"CLI-F-{suffix}"
    loan_ref = f"LOAN-F-{suffix}"
    client.post(
        f"{INT}/clients",
        headers=HEADERS,
        json={"client_uid": client_uid, "firstname": "Idem", "lastname": suffix, "activation_date": today},
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
    principal = Decimal("300000")
    report: dict = {"run_id": run_id, "cases": {}}

    with httpx.Client(timeout=120.0) as client:
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()

        # H5.1 replay after COMPLETED
        loan = _prepare_loan(client, f"{run_id}a", principal)
        ref = f"DISB-F-REPLAY-{run_id}"
        payload = {
            "external_reference": ref,
            "loan_reference": loan,
            "amount": str(principal),
            "currency": "RWF",
            "transaction_date": today,
        }
        r1 = client.post(f"{INT}/loans/disburse", headers=HEADERS, json=payload)
        r1.raise_for_status()
        b1 = r1.json()
        r2 = client.post(f"{INT}/loans/disburse", headers=HEADERS, json=payload)
        b2 = r2.json()
        h51 = (
            r1.status_code == 200
            and b1.get("state") == "COMPLETED"
            and r2.status_code == 200
            and b2.get("idempotent_replay") is True
            and b2.get("integration_txn_id") == b1.get("integration_txn_id")
        )
        report["cases"]["H5.1_completed_replay"] = {
            "first": {"status": r1.status_code, "body": b1},
            "second": {"status": r2.status_code, "body": b2},
            "pass": h51,
        }

        # H5.3 same ref different payload → 409
        bad = dict(payload)
        bad["amount"] = str(principal + Decimal("1"))
        r3 = client.post(f"{INT}/loans/disburse", headers=HEADERS, json=bad)
        b3 = r3.json() if r3.content else {}
        h53 = r3.status_code == 409
        report["cases"]["H5.3_payload_mismatch_409"] = {
            "status": r3.status_code,
            "body": b3,
            "pass": h53,
        }

        # H5.2 in-progress → 202
        pending_ref = f"DISB-F-PENDING-{run_id}"
        txn_id = uuid.uuid4().hex[:26]
        payload_pending = {
            "external_reference": pending_ref,
            "loan_reference": f"LOAN-F-PENDING-{run_id}",
            "amount": str(principal),
            "currency": "RWF",
            "transaction_date": today,
            "rail": "offline",
        }
        digest = hashlib.sha256(
            json.dumps(payload_pending, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        # claim_or_get hashes the same keys as money.disburse payload
        money_payload = {
            "external_reference": pending_ref,
            "loan_reference": payload_pending["loan_reference"],
            "amount": str(principal),
            "currency": "RWF",
            "transaction_date": today,
            "rail": "offline",
        }
        digest = hashlib.sha256(
            json.dumps(money_payload, sort_keys=True, default=str, separators=(",", ":")).encode()
        ).hexdigest()
        _sql_integration(
            f"""
INSERT INTO integration_transaction (
  id, operation_type, external_reference, loan_reference, amount, currency,
  rail, payload_hash, state
) VALUES (
  '{txn_id}', 'DISBURSEMENT', '{pending_ref}', '{payload_pending["loan_reference"]}',
  {principal}, 'RWF', 'offline', '{digest}', 'RAIL_PENDING'
);
"""
        )
        r4 = client.post(
            f"{INT}/loans/disburse",
            headers=HEADERS,
            json={
                "external_reference": pending_ref,
                "loan_reference": payload_pending["loan_reference"],
                "amount": str(principal),
                "currency": "RWF",
                "transaction_date": today,
                "rail": "offline",
            },
        )
        b4 = r4.json() if r4.content else {}
        h52 = r4.status_code == 202 and b4.get("idempotent_replay") is True and b4.get("state") == "RAIL_PENDING"
        report["cases"]["H5.2_in_progress_202"] = {
            "status": r4.status_code,
            "body": b4,
            "seeded_txn_id": txn_id,
            "pass": h52,
        }

        report["pass"] = h51 and h53 and h52

    EVIDENCE_JSON.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_JSON.write_text(json.dumps(report, indent=2, default=str) + "\n")
    EVIDENCE_TXT.write_text(
        "\n".join(
            [
                "Part F — Idempotency matrix",
                f"pass={report['pass']}",
                f"H5.1 completed replay 200 same txn: {h51}",
                f"H5.3 payload mismatch 409: {h53}",
                f"H5.2 in-progress 202: {h52}",
                "Also see Part I parallel identical ref (evidence/07-concurrency.json).",
                "",
            ]
        )
    )
    print(json.dumps({"wrote": str(EVIDENCE_JSON), "pass": report["pass"]}, indent=2))
    return 0 if report["pass"] else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
