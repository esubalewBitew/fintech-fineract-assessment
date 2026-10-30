#!/usr/bin/env python3
"""Part K seed — engineer four external_reference cases for reconcile evidence.

Synthetic left-side rows for MISSING_IN_ERP / AMOUNT_MISMATCH are intentional:
reviewers can see this script. MATCHED uses the full disburse path; MISSING_IN_FINERACT
is ERP-only.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]

INT = os.environ.get("INTEGRATION_URL", "http://localhost:8082")
ERP = os.environ.get("MOCK_ERP_URL", "http://localhost:8081")
KEY = os.environ.get("INTEGRATION_API_KEY", "integration-key")
ERP_KEY = os.environ.get("MOCK_ERP_API_KEY", "mock-erp-key")
HEADERS = {"X-Api-Key": KEY, "Content-Type": "application/json"}
ERP_HEADERS = {"X-Api-Key": ERP_KEY, "Content-Type": "application/json"}

AMOUNT = Decimal("100000.00")
MISMATCH_ERP = Decimal("50000.00")


def _sql_integration(sql: str) -> None:
    """Run SQL against the compose Postgres integration DB (avoids host :5432 clash)."""
    env_url = os.environ.get("INTEGRATION_DATABASE_URL")
    if env_url and "psycopg2" not in env_url:
        # Optional direct DSN for CI: postgresql://integration:...@host:port/integration
        import psycopg2

        with psycopg2.connect(env_url) as conn:
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute(sql)
        return

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
        raise RuntimeError(f"integration SQL failed: {proc.stderr or proc.stdout}")


def _insert_left_only(*, txn_id: str, external_reference: str, amount: Decimal, loan_reference: str) -> None:
    digest = hashlib.sha256(f"seed-k:{external_reference}".encode()).hexdigest()
    sql = f"""
INSERT INTO integration_transaction (
  id, operation_type, external_reference, loan_reference, amount, currency,
  rail, payload_hash, state, response_status, correlation_id
) VALUES (
  '{txn_id}', 'DISBURSEMENT', '{external_reference}', '{loan_reference}',
  {amount}, 'RWF', 'offline', '{digest}', 'COMPLETED', 200, 'seed-k'
)
ON CONFLICT DO NOTHING;

INSERT INTO transaction_leg (
  txn_id, leg_type, provider, provider_reference, state, attempts
)
SELECT '{txn_id}', 'CORE_BANKING', 'fineract', 'seed-k', 'CONFIRMED', 1
WHERE NOT EXISTS (
  SELECT 1 FROM transaction_leg WHERE txn_id = '{txn_id}' AND leg_type = 'CORE_BANKING'
);
"""
    _sql_integration(sql)


def _post_erp_journal(client: httpx.Client, *, external_reference: str, amount: Decimal, today: str) -> dict[str, Any]:
    body = {
        "external_reference": external_reference,
        "entry_date": today,
        "description": f"Part K seed {external_reference}",
        "source_system": "seed-k",
        "lines": [
            {"account_external_reference": "ERP-LOAN-PORT", "debit": str(amount), "credit": "0"},
            {"account_external_reference": "ERP-CASH", "debit": "0", "credit": str(amount)},
        ],
    }
    r = client.post(f"{ERP}/journal-entries", headers=ERP_HEADERS, json=body)
    if r.status_code not in (200, 201, 409):
        r.raise_for_status()
    return {"status_code": r.status_code, "body": r.json() if r.content else {}}


def _prepare_loan(client: httpx.Client, suffix: str, principal: Decimal) -> str:
    today = date.today().isoformat()
    client_uid = f"CLI-K-{suffix}"
    loan_ref = f"LOAN-K-{suffix}"
    client.post(
        f"{INT}/clients",
        headers=HEADERS,
        json={"client_uid": client_uid, "firstname": "Reconcile", "lastname": suffix, "activation_date": today},
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


def seed(*, run_id: str | None = None) -> dict[str, Any]:
    run_id = run_id or uuid.uuid4().hex[:8]
    today = date.today().isoformat()
    refs = {
        "MATCHED": f"K-SEED-MATCH-{run_id}",
        "MISSING_IN_ERP": f"K-SEED-MISS-ERP-{run_id}",
        "MISSING_IN_FINERACT": f"K-SEED-MISS-FIN-{run_id}",
        "AMOUNT_MISMATCH": f"K-SEED-MISMATCH-{run_id}",
    }
    out: dict[str, Any] = {"run_id": run_id, "refs": refs, "cases": {}}

    with httpx.Client(timeout=120.0) as client:
        client.post(f"{INT}/sync/coa", headers=HEADERS).raise_for_status()
        # Ensure ERP faults off (list_journals also applies faults)
        client.post(f"{ERP}/admin/faults", headers=ERP_HEADERS, json={"mode": "none"})

        # 1) MATCHED — full disburse path
        loan_match = _prepare_loan(client, f"{run_id}m", AMOUNT)
        r = client.post(
            f"{INT}/loans/disburse",
            headers=HEADERS,
            json={
                "external_reference": refs["MATCHED"],
                "loan_reference": loan_match,
                "amount": str(AMOUNT),
                "currency": "RWF",
                "transaction_date": today,
            },
        )
        r.raise_for_status()
        out["cases"]["MATCHED"] = {
            "method": "POST /loans/disburse",
            "loan_reference": loan_match,
            "response": r.json(),
        }

        # 2) MISSING_IN_ERP — integration left only (no ERP journal)
        miss_erp_id = uuid.uuid4().hex[:26]
        _insert_left_only(
            txn_id=miss_erp_id,
            external_reference=refs["MISSING_IN_ERP"],
            amount=AMOUNT,
            loan_reference=f"LOAN-K-SYNTH-ERP-{run_id}",
        )
        out["cases"]["MISSING_IN_ERP"] = {
            "method": "SQL integration_transaction + CORE_BANKING CONFIRMED (no ERP journal)",
            "integration_txn_id": miss_erp_id,
        }

        # 3) MISSING_IN_FINERACT — ERP journal only
        erp_only = _post_erp_journal(
            client, external_reference=refs["MISSING_IN_FINERACT"], amount=AMOUNT, today=today
        )
        out["cases"]["MISSING_IN_FINERACT"] = {
            "method": "POST mock-erp /journal-entries only",
            "erp": erp_only,
        }

        # 4) AMOUNT_MISMATCH — left 100000, ERP 50000, same ref
        mismatch_id = uuid.uuid4().hex[:26]
        _insert_left_only(
            txn_id=mismatch_id,
            external_reference=refs["AMOUNT_MISMATCH"],
            amount=AMOUNT,
            loan_reference=f"LOAN-K-SYNTH-MM-{run_id}",
        )
        erp_mm = _post_erp_journal(
            client, external_reference=refs["AMOUNT_MISMATCH"], amount=MISMATCH_ERP, today=today
        )
        out["cases"]["AMOUNT_MISMATCH"] = {
            "method": "SQL left amount 100000 + ERP journal total_debit 50000",
            "integration_txn_id": mismatch_id,
            "erp": erp_mm,
        }

    return out


if __name__ == "__main__":
    import json
    import sys

    try:
        print(json.dumps(seed(), indent=2))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
