from __future__ import annotations

from typing import Any

import httpx

from app.config import settings
from app.domain.models import CoAAccount, JournalDraft


class MockErpCoAProvider:
    source_system = settings.coa_source_system

    def __init__(self, base_url: str | None = None, api_key: str | None = None, client: httpx.Client | None = None):
        self.base_url = (base_url or settings.mock_erp_url).rstrip("/")
        self.api_key = api_key or settings.mock_erp_api_key
        self._client = client or httpx.Client(timeout=30.0)

    def list_accounts(self) -> list[CoAAccount]:
        r = self._client.get(f"{self.base_url}/accounts", headers={"X-Api-Key": self.api_key})
        r.raise_for_status()
        out: list[CoAAccount] = []
        for row in r.json():
            out.append(
                CoAAccount(
                    external_reference=row["external_reference"],
                    code=row["code"],
                    name=row["name"],
                    type=row["type"],
                    usage=row.get("usage") or "DETAIL",
                    currency=row["currency"],
                    description=row.get("description"),
                    manual_entries_allowed=row.get("manual_entries_allowed", True),
                )
            )
        return out


class MockErpLedger:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, client: httpx.Client | None = None):
        self.base_url = (base_url or settings.mock_erp_url).rstrip("/")
        self.api_key = api_key or settings.mock_erp_api_key
        self._client = client or httpx.Client(timeout=30.0)

    def post_journal(self, draft: JournalDraft) -> tuple[int, dict]:
        body: dict[str, Any] = {
            "external_reference": draft.external_reference,
            "entry_date": draft.entry_date,
            "description": draft.description,
            "source_system": "integration",
            "reverses_external_reference": draft.reverses_external_reference,
            "lines": [
                {
                    "account_external_reference": ln.account_external_reference,
                    "debit": str(ln.debit),
                    "credit": str(ln.credit),
                }
                for ln in draft.lines
            ],
        }
        r = self._client.post(f"{self.base_url}/journal-entries", headers={"X-Api-Key": self.api_key}, json=body)
        data = r.json() if r.content else {}
        if r.status_code not in (200, 201, 409):
            r.raise_for_status()
        return r.status_code, data

    def list_journals(self, *, since: str | None = None) -> list[dict]:
        params = {}
        if since:
            params["since"] = since
        r = self._client.get(f"{self.base_url}/journal-entries", headers={"X-Api-Key": self.api_key}, params=params)
        r.raise_for_status()
        return list(r.json())

    def get_journal(self, external_reference: str) -> dict | None:
        r = self._client.get(
            f"{self.base_url}/journal-entries/{external_reference}",
            headers={"X-Api-Key": self.api_key},
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
