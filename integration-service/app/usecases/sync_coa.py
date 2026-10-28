from __future__ import annotations

from dataclasses import asdict

from sqlalchemy.orm import Session

from app.db.models import GlAccountMap
from app.domain.models import CoAAccount
from app.mapping.fineract_gl import to_fineract_gl
from app.policy.currency import assert_allowed_currency
from app.ports.coa_provider import CoAProviderPort
from app.ports.core_banking import ConflictError, CoreBankingPort, CurrencyRejected


def sync_chart_of_accounts(
    db: Session,
    *,
    coa: CoAProviderPort,
    cbs: CoreBankingPort,
) -> list[dict]:
    results: list[dict] = []
    for account in coa.list_accounts():
        results.append(_sync_one(db, account=account, source_system=coa.source_system, cbs=cbs))
    db.commit()
    return results


def _sync_one(db: Session, *, account: CoAAccount, source_system: str, cbs: CoreBankingPort) -> dict:
    base = {
        "external_reference": account.external_reference,
        "code": account.code,
        "currency": account.currency,
        "source_system": source_system,
    }
    try:
        assert_allowed_currency(account.currency)
    except CurrencyRejected as exc:
        return {**base, "status": "skipped_currency", "detail": str(exc)}

    existing = (
        db.query(GlAccountMap)
        .filter(
            GlAccountMap.source_system == source_system,
            GlAccountMap.external_reference == account.external_reference,
        )
        .first()
    )
    if existing:
        return {**base, "status": "already_mapped", "fineract_gl_id": existing.fineract_gl_id}

    try:
        resp = cbs.create_gl_account(to_fineract_gl(account))
        gl_id = int(resp.get("resourceId") or resp.get("glAccountId"))
        db.add(
            GlAccountMap(
                source_system=source_system,
                external_reference=account.external_reference,
                fineract_gl_id=gl_id,
                sync_state="SYNCED",
            )
        )
        return {**base, "status": "created", "fineract_gl_id": gl_id}
    except ConflictError as exc:
        return {**base, "status": "conflict", "detail": str(exc), "body": getattr(exc, "body", None)}
    except Exception as exc:  # noqa: BLE001 — surface per-item errors in sync report
        return {**base, "status": "error", "detail": str(exc)}
