#!/usr/bin/env python3
"""Part B — bootstrap Fineract tenant for the assessment.

Creates (idempotent):
  - Currency RWF (keeps existing e.g. USD)
  - Office "Kigali" (externalId=KIGALI)
  - Loan product "SME Asset Finance" (18% p.a., 12 months, cash GL mappings)
  - Role assessment-api + user assessment.api (least-privilege)

Prereq: CoA GLs present (run Integration POST /sync/coa first).

Usage:
  python scripts/fineract_setup_part_b.py
  python scripts/fineract_setup_part_b.py --out evidence/01-part-b-setup.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fineract_setup.client import FineractHttpClient  # noqa: E402
from fineract_setup.setup import run_part_b_setup  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Part B Fineract tenant setup")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "FINERACT_BASE_URL",
            "https://localhost:8443/fineract-provider/api/v1",
        ),
    )
    parser.add_argument("--username", default=os.environ.get("FINERACT_USERNAME", "mifos"))
    parser.add_argument("--password", default=os.environ.get("FINERACT_PASSWORD", "password"))
    parser.add_argument("--tenant", default=os.environ.get("FINERACT_TENANT", "default"))
    parser.add_argument("--out", type=Path, default=None, help="Write JSON evidence file")
    parser.add_argument("--skip-login-check", action="store_true")
    args = parser.parse_args()

    with FineractHttpClient(
        args.base_url,
        username=args.username,
        password=args.password,
        tenant=args.tenant,
        verify_ssl=False,
    ) as client:
        result = run_part_b_setup(client, verify_login=not args.skip_login_check)

    payload = result.to_dict()
    text = json.dumps(payload, indent=2)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text + "\n")
        print(f"Wrote {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
