from __future__ import annotations

from typing import Protocol

from app.domain.models import JournalDraft


class LedgerPort(Protocol):
    def post_journal(self, draft: JournalDraft) -> tuple[int, dict]:
        """Returns (http_status, body)."""

    def list_journals(self, *, since: str | None = None) -> list[dict]: ...

    def get_journal(self, external_reference: str) -> dict | None: ...
