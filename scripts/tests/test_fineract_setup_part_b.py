"""Unit tests for Part B create-or-get helpers (no live Fineract)."""

from __future__ import annotations

import json

import httpx
import pytest

from fineract_setup.client import FineractHttpClient
from fineract_setup.setup import (
    API_USERNAME,
    OFFICE_NAME,
    PRODUCT_NAME,
    ROLE_NAME,
    ensure_api_user,
    ensure_currencies,
    ensure_loan_product,
    ensure_office,
    ensure_role,
    resolve_gl_accounts,
    run_part_b_setup,
)


def _router(handler):
    transport = httpx.MockTransport(handler)
    return FineractHttpClient(
        "https://fineract.test/fineract-provider/api/v1",
        username="mifos",
        password="password",
        transport=transport,
    )


def test_ensure_currencies_updates_when_rwf_missing():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "GET" and request.url.path.endswith("/currencies"):
            return httpx.Response(
                200,
                json={"selectedCurrencyOptions": [{"code": "USD"}], "currencyOptions": []},
            )
        if request.method == "PUT" and request.url.path.endswith("/currencies"):
            body = json.loads(request.content)
            assert "RWF" in body["currencies"]
            assert "USD" in body["currencies"]
            return httpx.Response(200, json={"currencies": body["currencies"]})
        return httpx.Response(404, json={"error": "unexpected"})

    with _router(handler) as client:
        out = ensure_currencies(client, keep=["USD"])
    assert out.status == "updated"
    assert "RWF" in out.detail["currencies"]


def test_ensure_office_idempotent_by_name():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/offices"):
            return httpx.Response(
                200,
                json=[
                    {"id": 1, "name": "Head Office", "externalId": "1"},
                    {"id": 2, "name": OFFICE_NAME, "externalId": "KIGALI"},
                ],
            )
        return httpx.Response(500, json={"error": "should not create"})

    with _router(handler) as client:
        out = ensure_office(client)
    assert out.status == "exists"
    assert out.detail["office_id"] == 2


def test_ensure_office_creates_when_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/offices"):
            return httpx.Response(200, json=[{"id": 1, "name": "Head Office", "externalId": "1"}])
        if request.method == "POST" and request.url.path.endswith("/offices"):
            body = json.loads(request.content)
            assert body["name"] == OFFICE_NAME
            assert body["externalId"] == "KIGALI"
            assert body["parentId"] == 1
            return httpx.Response(200, json={"resourceId": 9})
        return httpx.Response(404)

    with _router(handler) as client:
        out = ensure_office(client)
    assert out.status == "created"
    assert out.detail["office_id"] == 9


def test_resolve_gl_accounts_fails_with_hint_when_missing():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1, "glCode": "9999", "name": "Only"}])

    with _router(handler) as client:
        out = resolve_gl_accounts(client)
    assert out.status == "failed"
    assert "1000" in out.detail["missing_gl_codes"]
    assert "sync/coa" in out.detail["hint"]


def test_ensure_loan_product_creates_with_cash_mappings():
    gl_map = {
        "fund_source": 2,
        "loan_portfolio": 3,
        "transfers_suspense": 4,
        "interest_income": 9,
        "fee_income": 8,
        "write_off": 10,
        "overpayment": 5,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path.endswith("/loanproducts"):
            return httpx.Response(200, json=[])
        if request.method == "POST" and request.url.path.endswith("/loanproducts"):
            body = json.loads(request.content)
            assert body["name"] == PRODUCT_NAME
            assert body["currencyCode"] == "RWF"
            assert body["interestRatePerPeriod"] == 18
            assert body["numberOfRepayments"] == 12
            assert body["accountingRule"] == 2
            assert body["fundSourceAccountId"] == 2
            assert body["loanPortfolioAccountId"] == 3
            return httpx.Response(200, json={"resourceId": 42})
        return httpx.Response(404)

    with _router(handler) as client:
        out = ensure_loan_product(client, gl_map)
    assert out.status == "created"
    assert out.detail["product_id"] == 42


def test_ensure_role_and_user_create_or_get():
    state = {"roles": [], "users": []}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path.endswith("/roles"):
            return httpx.Response(200, json=state["roles"])
        if request.method == "POST" and path.endswith("/roles"):
            state["roles"].append({"id": 7, "name": ROLE_NAME})
            return httpx.Response(200, json={"resourceId": 7})
        if request.method == "PUT" and "/roles/7/permissions" in path:
            return httpx.Response(200, json={"resourceId": 7})
        if request.method == "GET" and path.endswith("/users"):
            return httpx.Response(200, json=state["users"])
        if request.method == "POST" and path.endswith("/users"):
            body = json.loads(request.content)
            assert body["username"] == API_USERNAME
            assert body["roles"] == [7]
            state["users"].append({"id": 11, "username": API_USERNAME})
            return httpx.Response(200, json={"resourceId": 11})
        return httpx.Response(404, text=path)

    with _router(handler) as client:
        role = ensure_role(client)
        assert role.status == "created"
        user = ensure_api_user(client, role_id=7, office_id=2)
        assert user.status == "created"
        # idempotent second pass
        role2 = ensure_role(client)
        user2 = ensure_api_user(client, role_id=7, office_id=2)
        assert role2.status == "exists"
        assert user2.status == "exists"


def test_run_part_b_setup_happy_path_end_to_end_mock():
    gls = [
        {"id": 2, "glCode": "1000"},
        {"id": 3, "glCode": "1100"},
        {"id": 4, "glCode": "1200"},
        {"id": 5, "glCode": "2100"},
        {"id": 8, "glCode": "4001"},
        {"id": 9, "glCode": "4002"},
        {"id": 10, "glCode": "5001"},
    ]
    state = {
        "currencies": ["USD"],
        "offices": [{"id": 1, "name": "Head Office", "externalId": "1"}],
        "products": [],
        "roles": [],
        "users": [],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        auth = request.headers.get("Authorization", "")

        if request.method == "GET" and path.endswith("/offices"):
            return httpx.Response(200, json=state["offices"])
        if request.method == "GET" and path.endswith("/currencies"):
            return httpx.Response(
                200,
                json={"selectedCurrencyOptions": [{"code": c} for c in state["currencies"]]},
            )
        if request.method == "PUT" and path.endswith("/currencies"):
            body = json.loads(request.content)
            state["currencies"] = body["currencies"]
            return httpx.Response(200, json=body)
        if request.method == "POST" and path.endswith("/offices"):
            state["offices"].append({"id": 2, "name": OFFICE_NAME, "externalId": "KIGALI"})
            return httpx.Response(200, json={"resourceId": 2})
        if request.method == "GET" and path.endswith("/glaccounts"):
            return httpx.Response(200, json=gls)
        if request.method == "GET" and path.endswith("/loanproducts"):
            return httpx.Response(200, json=state["products"])
        if request.method == "POST" and path.endswith("/loanproducts"):
            state["products"].append({"id": 42, "name": PRODUCT_NAME, "externalId": "SME-ASSET-FINANCE"})
            return httpx.Response(200, json={"resourceId": 42})
        if request.method == "GET" and path.endswith("/roles"):
            return httpx.Response(200, json=state["roles"])
        if request.method == "POST" and path.endswith("/roles"):
            state["roles"].append({"id": 7, "name": ROLE_NAME})
            return httpx.Response(200, json={"resourceId": 7})
        if request.method == "PUT" and "/permissions" in path:
            return httpx.Response(200, json={})
        if request.method == "GET" and path.endswith("/users"):
            return httpx.Response(200, json=state["users"])
        if request.method == "POST" and path.endswith("/users"):
            state["users"].append({"id": 11, "username": API_USERNAME})
            return httpx.Response(200, json={"resourceId": 11})
        return httpx.Response(404, text=f"{request.method} {path} auth={auth[:20]}")

    transport = httpx.MockTransport(handler)
    with FineractHttpClient(
        "https://fineract.test/fineract-provider/api/v1",
        username="mifos",
        password="password",
        transport=transport,
    ) as client:
        result = run_part_b_setup(client, verify_login=True, login_transport=transport)

    assert result.office_id == 2
    assert result.product_id == 42
    assert result.role_id == 7
    assert result.user_id == 11
    assert "RWF" in result.currencies
    assert result.steps[-1].step == "api_user_login"
    assert result.steps[-1].status == "ok"
