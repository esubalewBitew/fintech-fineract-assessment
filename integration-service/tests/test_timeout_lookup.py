"""Part J: on FineractTimeoutError, lookup by externalId — never blind retry."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.ports.core_banking import FineractTimeoutError
from app.usecases.money import _cbs_call_with_external_id_lookup


def test_timeout_recovers_via_external_id_lookup():
    cbs = MagicMock()
    cbs.get_loan_transaction_by_external_id.return_value = {"resourceId": 99, "id": 99}

    def boom():
        raise FineractTimeoutError(
            "timeout",
            loan_external_id="LOAN-1",
            txn_external_id="DISB-1",
        )

    resp, note = _cbs_call_with_external_id_lookup(
        cbs,
        call_name="disburse",
        loan_reference="LOAN-1",
        external_reference="DISB-1",
        call=boom,
    )
    assert resp["resourceId"] == 99
    assert "LOOKUP_BY_EXTERNAL_ID" in note
    cbs.get_loan_transaction_by_external_id.assert_called_once_with(
        loan_external_id="LOAN-1",
        txn_external_id="DISB-1",
    )


def test_timeout_miss_does_not_retry_call():
    cbs = MagicMock()
    cbs.get_loan_transaction_by_external_id.return_value = None
    calls = {"n": 0}

    def boom():
        calls["n"] += 1
        raise FineractTimeoutError("timeout", loan_external_id="L", txn_external_id="T")

    with pytest.raises(HTTPException) as ei:
        _cbs_call_with_external_id_lookup(
            cbs,
            call_name="disburse",
            loan_reference="L",
            external_reference="T",
            call=boom,
        )
    assert calls["n"] == 1  # no blind retry
    assert ei.value.status_code == 502
    assert "LOOKUP_BY_EXTERNAL_ID" in ei.value.detail
