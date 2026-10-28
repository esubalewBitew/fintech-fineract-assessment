from __future__ import annotations

import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.adapters.rails import RAILS
from app.db.models import IntegrationTransaction, LoanMap, TransactionLeg
from app.domain.models import Beneficiary, LegState, LegType, OperationType, Payer, RailStatus
from app.domain.states import InvalidTransition, transition
from app.idempotency.claim import claim_or_get, payload_hash
from app.mapping import journal_mapping as jm
from app.policy.currency import assert_allowed_currency
from app.ports.core_banking import CoreBankingPort, CurrencyRejected
from app.ports.ledger import LedgerPort


def _leg(db: Session, txn: IntegrationTransaction, leg_type: str, provider: str) -> TransactionLeg:
    leg = (
        db.query(TransactionLeg)
        .filter(TransactionLeg.txn_id == txn.id, TransactionLeg.leg_type == leg_type)
        .first()
    )
    if not leg:
        leg = TransactionLeg(txn_id=txn.id, leg_type=leg_type, provider=provider, state=LegState.PENDING.value)
        db.add(leg)
        db.flush()
    return leg


def _set_state(txn: IntegrationTransaction, new: str) -> None:
    txn.state = transition(txn.state, new)


def _idempotent_response(txn: IntegrationTransaction) -> dict:
    return {
        "integration_txn_id": txn.id,
        "external_reference": txn.external_reference,
        "state": txn.state,
        "idempotent_replay": True,
    }


def disburse(
    db: Session,
    *,
    cbs: CoreBankingPort,
    ledger: LedgerPort,
    external_reference: str,
    loan_reference: str,
    amount: Decimal,
    currency: str,
    transaction_date: str,
    rail_name: str = "offline",
    correlation_id: str | None = None,
) -> dict:
    try:
        assert_allowed_currency(currency)
    except CurrencyRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    payload = {
        "external_reference": external_reference,
        "loan_reference": loan_reference,
        "amount": str(amount),
        "currency": currency,
        "transaction_date": transaction_date,
        "rail": rail_name,
    }
    txn, created = claim_or_get(
        db,
        operation_type=OperationType.DISBURSEMENT.value,
        external_reference=external_reference,
        payload=payload,
        loan_reference=loan_reference,
        amount=amount,
        currency=currency,
        rail=rail_name,
        correlation_id=correlation_id,
    )
    if not created:
        if txn.payload_hash != payload_hash(payload):
            raise HTTPException(status_code=409, detail="idempotency conflict: same external_reference different payload")
        return _idempotent_response(txn)

    loan = db.query(LoanMap).filter(LoanMap.loan_reference == loan_reference).first()
    if not loan:
        raise HTTPException(status_code=400, detail=f"unknown loan_reference {loan_reference}; register via POST /loans/map")
    if loan.disbursed_txn_id:
        raise HTTPException(status_code=409, detail="loan already has a disbursement")

    rail = RAILS[rail_name]
    try:
        _set_state(txn, "RAIL_PENDING")
        rail_leg = _leg(db, txn, LegType.RAIL.value, rail.name)
        rail_leg.attempts += 1
        result = rail.initiate_payout(
            idempotency_key=external_reference,
            amount=amount,
            currency=currency,
            beneficiary=Beneficiary(account_ref=loan_reference),
        )
        rail_leg.provider_reference = result.rail_reference
        rail_leg.response_json = json.dumps({"status": result.status.value})
        if result.status == RailStatus.FAILED:
            rail_leg.state = LegState.FAILED.value
            _set_state(txn, "FAILED")
            db.commit()
            return {"integration_txn_id": txn.id, "state": txn.state}
        if result.status == RailStatus.PENDING:
            rail_leg.state = LegState.SENT.value
            db.commit()
            return {"integration_txn_id": txn.id, "state": txn.state, "rail_reference": result.rail_reference}
        rail_leg.state = LegState.CONFIRMED.value
        _set_state(txn, "RAIL_CONFIRMED")

        _set_state(txn, "FINERACT_PENDING")
        cbs_leg = _leg(db, txn, LegType.CORE_BANKING.value, "fineract")
        cbs_leg.attempts += 1
        cbs_resp = cbs.disburse_loan(
            loan_id=loan.fineract_loan_id,
            amount=amount,
            external_id=external_reference,
            transaction_date=transaction_date,
        )
        cbs_leg.provider_reference = str(cbs_resp.get("resourceId") or cbs_resp.get("transactionId") or "")
        cbs_leg.response_json = json.dumps(cbs_resp, default=str)
        cbs_leg.state = LegState.CONFIRMED.value
        _set_state(txn, "FINERACT_DONE")

        _set_state(txn, "ERP_PENDING")
        led_leg = _leg(db, txn, LegType.LEDGER.value, "mock-erp")
        led_leg.attempts += 1
        draft = jm.disburse_journal(external_reference=external_reference, entry_date=transaction_date, amount=amount)
        status, body = ledger.post_journal(draft)
        led_leg.response_json = json.dumps(body, default=str)
        if status == 409:
            led_leg.state = LegState.FAILED.value
            _set_state(txn, "NEEDS_RECONCILIATION")
        else:
            led_leg.provider_reference = str(body.get("id") or "")
            led_leg.state = LegState.CONFIRMED.value
            _set_state(txn, "COMPLETED")
            loan.disbursed_txn_id = txn.id

        db.commit()
        return {"integration_txn_id": txn.id, "external_reference": external_reference, "state": txn.state}
    except InvalidTransition as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        try:
            _set_state(txn, "NEEDS_RECONCILIATION")
        except InvalidTransition:
            txn.state = "NEEDS_RECONCILIATION"
        db.commit()
        raise HTTPException(status_code=502, detail=f"disburse failed: {exc}") from exc


def repay(
    db: Session,
    *,
    cbs: CoreBankingPort,
    ledger: LedgerPort,
    external_reference: str,
    loan_reference: str,
    amount: Decimal,
    currency: str,
    transaction_date: str,
    principal: Decimal | None = None,
    interest: Decimal | None = None,
    rail_name: str = "offline",
    correlation_id: str | None = None,
) -> dict:
    try:
        assert_allowed_currency(currency)
    except CurrencyRejected as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    principal = principal if principal is not None else amount
    interest = interest or Decimal("0")
    payload = {
        "external_reference": external_reference,
        "loan_reference": loan_reference,
        "amount": str(amount),
        "principal": str(principal),
        "interest": str(interest),
        "currency": currency,
        "transaction_date": transaction_date,
        "rail": rail_name,
    }
    txn, created = claim_or_get(
        db,
        operation_type=OperationType.REPAYMENT.value,
        external_reference=external_reference,
        payload=payload,
        loan_reference=loan_reference,
        amount=amount,
        currency=currency,
        rail=rail_name,
        correlation_id=correlation_id,
    )
    if not created:
        if txn.payload_hash != payload_hash(payload):
            raise HTTPException(status_code=409, detail="idempotency conflict")
        return _idempotent_response(txn)

    loan = db.query(LoanMap).filter(LoanMap.loan_reference == loan_reference).first()
    if not loan:
        raise HTTPException(status_code=400, detail=f"unknown loan_reference {loan_reference}")

    rail = RAILS[rail_name]
    try:
        rail_leg = _leg(db, txn, LegType.RAIL.value, rail.name)
        result = rail.initiate_collection(
            idempotency_key=external_reference,
            amount=amount,
            currency=currency,
            payer=Payer(account_ref=loan_reference),
        )
        rail_leg.provider_reference = result.rail_reference
        rail_leg.state = (
            LegState.CONFIRMED.value if result.status == RailStatus.CONFIRMED else LegState.SENT.value
        )
        _set_state(txn, "RAIL_CONFIRMED")

        _set_state(txn, "FINERACT_PENDING")
        cbs_leg = _leg(db, txn, LegType.CORE_BANKING.value, "fineract")
        cbs_resp = cbs.repay_loan(
            loan_id=loan.fineract_loan_id,
            amount=amount,
            external_id=external_reference,
            transaction_date=transaction_date,
        )
        cbs_leg.provider_reference = str(cbs_resp.get("resourceId") or "")
        cbs_leg.response_json = json.dumps(cbs_resp, default=str)
        cbs_leg.state = LegState.CONFIRMED.value
        _set_state(txn, "FINERACT_DONE")

        _set_state(txn, "ERP_PENDING")
        led_leg = _leg(db, txn, LegType.LEDGER.value, "mock-erp")
        draft = jm.repay_journal(
            external_reference=external_reference,
            entry_date=transaction_date,
            principal=principal,
            interest=interest,
        )
        status, body = ledger.post_journal(draft)
        led_leg.response_json = json.dumps(body, default=str)
        if status == 409:
            led_leg.state = LegState.FAILED.value
            _set_state(txn, "NEEDS_RECONCILIATION")
        else:
            led_leg.provider_reference = str(body.get("id") or "")
            led_leg.state = LegState.CONFIRMED.value
            _set_state(txn, "COMPLETED")
        db.commit()
        return {"integration_txn_id": txn.id, "external_reference": external_reference, "state": txn.state}
    except Exception as exc:  # noqa: BLE001
        txn.state = "NEEDS_RECONCILIATION"
        db.commit()
        raise HTTPException(status_code=502, detail=f"repay failed: {exc}") from exc


def reverse_repayment(
    db: Session,
    *,
    cbs: CoreBankingPort,
    ledger: LedgerPort,
    external_reference: str,
    original_external_reference: str,
    transaction_date: str,
    correlation_id: str | None = None,
) -> dict:
    original = (
        db.query(IntegrationTransaction)
        .filter(
            IntegrationTransaction.operation_type == OperationType.REPAYMENT.value,
            IntegrationTransaction.external_reference == original_external_reference,
        )
        .first()
    )
    if not original:
        raise HTTPException(status_code=404, detail="original repayment not found")
    if original.state != "COMPLETED":
        raise HTTPException(status_code=409, detail="original repayment not COMPLETED")

    payload = {
        "external_reference": external_reference,
        "reverses": original_external_reference,
        "transaction_date": transaction_date,
    }
    txn, created = claim_or_get(
        db,
        operation_type=OperationType.REVERSAL.value,
        external_reference=external_reference,
        payload=payload,
        loan_reference=original.loan_reference,
        amount=original.amount,
        currency=original.currency,
        rail=original.rail,
        correlation_id=correlation_id,
    )
    if not created:
        return _idempotent_response(txn)

    txn.reverses_txn_id = original.id
    loan = db.query(LoanMap).filter(LoanMap.loan_reference == original.loan_reference).first()
    if not loan:
        raise HTTPException(status_code=400, detail="loan map missing")

    cbs_leg_orig = (
        db.query(TransactionLeg)
        .filter(TransactionLeg.txn_id == original.id, TransactionLeg.leg_type == LegType.CORE_BANKING.value)
        .first()
    )
    if not cbs_leg_orig or not cbs_leg_orig.provider_reference:
        raise HTTPException(status_code=409, detail="original Fineract transaction id unknown")

    try:
        _set_state(txn, "RAIL_CONFIRMED")  # offline: no rail unwind required for v1
        _set_state(txn, "FINERACT_PENDING")
        cbs_leg = _leg(db, txn, LegType.CORE_BANKING.value, "fineract")
        cbs_resp = cbs.undo_loan_transaction(loan_id=loan.fineract_loan_id, transaction_id=int(cbs_leg_orig.provider_reference))
        cbs_leg.provider_reference = str(cbs_resp.get("resourceId") or cbs_leg_orig.provider_reference)
        cbs_leg.response_json = json.dumps(cbs_resp, default=str)
        cbs_leg.state = LegState.CONFIRMED.value
        _set_state(txn, "FINERACT_DONE")

        _set_state(txn, "ERP_PENDING")
        orig_draft = jm.repay_journal(
            external_reference=original_external_reference,
            entry_date=transaction_date,
            principal=original.amount,
        )
        rev_draft = jm.reversing_journal(original=orig_draft, reverse_external_reference=external_reference)
        led_leg = _leg(db, txn, LegType.LEDGER.value, "mock-erp")
        status, body = ledger.post_journal(rev_draft)
        led_leg.response_json = json.dumps(body, default=str)
        if status == 409:
            led_leg.state = LegState.FAILED.value
            _set_state(txn, "NEEDS_RECONCILIATION")
        else:
            led_leg.provider_reference = str(body.get("id") or "")
            led_leg.state = LegState.CONFIRMED.value
            _set_state(txn, "COMPLETED")
        db.commit()
        return {
            "integration_txn_id": txn.id,
            "external_reference": external_reference,
            "reverses": original_external_reference,
            "state": txn.state,
        }
    except Exception as exc:  # noqa: BLE001
        txn.state = "NEEDS_RECONCILIATION"
        db.commit()
        raise HTTPException(status_code=502, detail=f"reverse failed: {exc}") from exc
