from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .client import FineractHttpClient

OFFICE_NAME = "Kigali"
OFFICE_EXTERNAL_ID = "KIGALI"
PRODUCT_NAME = "SME Asset Finance"
PRODUCT_SHORT_NAME = "SMEA"  # Fineract max length 4
PRODUCT_EXTERNAL_ID = "SME-ASSET-FINANCE"
ROLE_NAME = "assessment-api"
API_USERNAME = "assessment.api"
# Fineract policy: 12–50 chars, upper+lower+digit+special, no spaces, no consecutive repeats.
API_PASSWORD = "Th1sIsA#Pas9x"
CURRENCY = "RWF"

# Cash-based product GL mapping by glCode (aligned with Mock ERP seed / CoA sync).
GL_BY_ROLE = {
    "fund_source": "1000",
    "loan_portfolio": "1100",
    "transfers_suspense": "1200",
    "interest_income": "4002",
    "fee_income": "4001",
    "write_off": "5001",
    "overpayment": "2100",
}

API_ROLE_PERMISSIONS = [
    "READ_OFFICE",
    "READ_CURRENCY",
    "READ_GLACCOUNT",
    "CREATE_GLACCOUNT",
    "UPDATE_GLACCOUNT",
    "READ_LOANPRODUCT",
    "CREATE_CLIENT",
    "READ_CLIENT",
    "UPDATE_CLIENT",
    "ACTIVATE_CLIENT",
    "CREATE_LOAN",
    "READ_LOAN",
    "UPDATE_LOAN",
    "APPROVE_LOAN",
    "APPROVALUNDO_LOAN",
    "REJECT_LOAN",
    "DISBURSE_LOAN",
    "DISBURSALUNDO_LOAN",
    "REPAYMENT_LOAN",
    "ADJUST_LOAN",
    "WAIVEINTERESTPORTION_LOAN",
    "WRITEOFF_LOAN",
    "UNDOWRITEOFF_LOAN",
    "CLOSE_LOAN",
    "CREDITBALANCEREFUND_LOAN",
]


@dataclass
class StepOutcome:
    step: str
    status: str  # created | exists | updated | ok | skipped | failed
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PartBResult:
    steps: List[StepOutcome] = field(default_factory=list)
    office_id: Optional[int] = None
    product_id: Optional[int] = None
    role_id: Optional[int] = None
    user_id: Optional[int] = None
    currencies: List[str] = field(default_factory=list)
    gl_map: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "office_id": self.office_id,
            "product_id": self.product_id,
            "role_id": self.role_id,
            "user_id": self.user_id,
            "currencies": self.currencies,
            "gl_map": self.gl_map,
            "api_user": {"username": API_USERNAME, "role": ROLE_NAME},
            "steps": [asdict(s) for s in self.steps],
        }


def _type_value(gl: dict) -> str:
    t = gl.get("type")
    if isinstance(t, dict):
        return str(t.get("value") or "")
    return str(t or "")


def ensure_currencies(client: FineractHttpClient, *, keep: Optional[List[str]] = None) -> StepOutcome:
    """Enable RWF (and keep existing selected currencies such as USD)."""
    keep = keep or []
    data = client.get_json("/currencies")
    selected = [c["code"] for c in data.get("selectedCurrencyOptions") or []]
    merged = sorted(set(selected) | set(keep) | {CURRENCY})
    if CURRENCY not in selected or set(merged) != set(selected):
        client.put_json("/currencies", {"currencies": merged})
        return StepOutcome("currency", "updated", {"currencies": merged})
    return StepOutcome("currency", "exists", {"currencies": selected})


def ensure_office(client: FineractHttpClient) -> StepOutcome:
    offices = client.get_json("/offices") or []
    for o in offices:
        if o.get("name") == OFFICE_NAME or o.get("externalId") == OFFICE_EXTERNAL_ID:
            return StepOutcome(
                "office",
                "exists",
                {"office_id": o["id"], "name": o.get("name"), "externalId": o.get("externalId")},
            )
    head = next((o for o in offices if o.get("id") == 1), offices[0])
    body = {
        "name": OFFICE_NAME,
        "parentId": head["id"],
        "externalId": OFFICE_EXTERNAL_ID,
        "openingDate": "2010-01-01",
        "dateFormat": "yyyy-MM-dd",
        "locale": "en",
    }
    resp = client.post_json("/offices", body)
    oid = int(resp.get("resourceId") or resp.get("officeId"))
    return StepOutcome("office", "created", {"office_id": oid, "name": OFFICE_NAME, "externalId": OFFICE_EXTERNAL_ID})


def resolve_gl_accounts(client: FineractHttpClient) -> StepOutcome:
    accounts = client.get_json("/glaccounts") or []
    by_code = {a.get("glCode"): int(a["id"]) for a in accounts if a.get("glCode")}
    missing = [code for code in GL_BY_ROLE.values() if code not in by_code]
    if missing:
        return StepOutcome(
            "gl_accounts",
            "failed",
            {
                "missing_gl_codes": missing,
                "hint": "Run CoA sync first: POST http://localhost:8082/sync/coa -H 'X-Api-Key: integration-key'",
                "available": sorted(by_code.keys()),
            },
        )
    gl_map = {role: by_code[code] for role, code in GL_BY_ROLE.items()}
    return StepOutcome("gl_accounts", "ok", {"gl_map": gl_map, "by_code": {c: by_code[c] for c in GL_BY_ROLE.values()}})


def ensure_loan_product(client: FineractHttpClient, gl_map: Dict[str, int]) -> StepOutcome:
    products = client.get_json("/loanproducts") or []
    for p in products:
        if p.get("name") == PRODUCT_NAME or p.get("externalId") == PRODUCT_EXTERNAL_ID:
            return StepOutcome(
                "loan_product",
                "exists",
                {"product_id": p["id"], "name": p.get("name"), "externalId": p.get("externalId")},
            )

    body = {
        "name": PRODUCT_NAME,
        "shortName": PRODUCT_SHORT_NAME,
        "externalId": PRODUCT_EXTERNAL_ID,
        "currencyCode": CURRENCY,
        "digitsAfterDecimal": 0,
        "inMultiplesOf": 1,
        "principal": 1000000,
        "minPrincipal": 100000,
        "maxPrincipal": 50000000,
        "numberOfRepayments": 12,
        "repaymentEvery": 1,
        "repaymentFrequencyType": 2,  # months
        "interestRatePerPeriod": 18,
        "interestRateFrequencyType": 3,  # per year
        "amortizationType": 1,  # equal installments
        "interestType": 0,  # declining balance
        "interestCalculationPeriodType": 1,
        "transactionProcessingStrategyCode": "mifos-standard-strategy",
        "accountingRule": 2,  # cash
        "isInterestRecalculationEnabled": False,
        "daysInYearType": 1,
        "daysInMonthType": 1,
        "locale": "en",
        "dateFormat": "yyyy-MM-dd",
        "fundSourceAccountId": gl_map["fund_source"],
        "loanPortfolioAccountId": gl_map["loan_portfolio"],
        "transfersInSuspenseAccountId": gl_map["transfers_suspense"],
        "interestOnLoanAccountId": gl_map["interest_income"],
        "incomeFromFeeAccountId": gl_map["fee_income"],
        "incomeFromPenaltyAccountId": gl_map["fee_income"],
        "incomeFromRecoveryAccountId": gl_map["fee_income"],
        "writeOffAccountId": gl_map["write_off"],
        "overpaymentLiabilityAccountId": gl_map["overpayment"],
    }
    resp = client.post_json("/loanproducts", body)
    pid = int(resp.get("resourceId") or resp.get("productId"))
    return StepOutcome(
        "loan_product",
        "created",
        {
            "product_id": pid,
            "name": PRODUCT_NAME,
            "externalId": PRODUCT_EXTERNAL_ID,
            "interestRatePerPeriod": 18,
            "numberOfRepayments": 12,
            "currencyCode": CURRENCY,
            "accountingRule": "CASH",
            "gl_map": gl_map,
        },
    )


def ensure_role(client: FineractHttpClient) -> StepOutcome:
    roles = client.get_json("/roles") or []
    for r in roles:
        if r.get("name") == ROLE_NAME:
            return StepOutcome("role", "exists", {"role_id": r["id"], "name": ROLE_NAME})
    resp = client.post_json(
        "/roles",
        {"name": ROLE_NAME, "description": "Least-privilege API role for assessment integration"},
    )
    role_id = int(resp.get("resourceId") or resp.get("roleId"))
    perms = {code: True for code in API_ROLE_PERMISSIONS}
    client.put_json(f"/roles/{role_id}/permissions", {"permissions": perms})
    return StepOutcome(
        "role",
        "created",
        {"role_id": role_id, "name": ROLE_NAME, "permission_count": len(API_ROLE_PERMISSIONS)},
    )


def ensure_api_user(client: FineractHttpClient, *, role_id: int, office_id: int) -> StepOutcome:
    users = client.get_json("/users") or []
    for u in users:
        if u.get("username") == API_USERNAME:
            return StepOutcome(
                "api_user",
                "exists",
                {"user_id": u["id"], "username": API_USERNAME, "office_id": office_id, "role_id": role_id},
            )
    body = {
        "username": API_USERNAME,
        "firstname": "Assessment",
        "lastname": "API",
        "email": "assessment.api@example.local",
        "officeId": office_id,
        "roles": [role_id],
        "sendPasswordToEmail": False,
        "password": API_PASSWORD,
        "repeatPassword": API_PASSWORD,
    }
    resp = client.post_json("/users", body)
    uid = int(resp.get("resourceId") or resp.get("userId"))
    return StepOutcome(
        "api_user",
        "created",
        {"user_id": uid, "username": API_USERNAME, "office_id": office_id, "role_id": role_id},
    )


def verify_api_user_login(
    *,
    base_url: str,
    tenant: str,
    verify_ssl: bool,
    transport: Optional[Any] = None,
) -> StepOutcome:
    try:
        with FineractHttpClient(
            base_url,
            username=API_USERNAME,
            password=API_PASSWORD,
            tenant=tenant,
            verify_ssl=verify_ssl,
            transport=transport,
        ) as api:
            offices = api.get_json("/offices")
            return StepOutcome(
                "api_user_login",
                "ok",
                {"username": API_USERNAME, "offices_visible": len(offices or [])},
            )
    except Exception as exc:  # noqa: BLE001
        return StepOutcome("api_user_login", "failed", {"error": str(exc)})


def run_part_b_setup(
    client: FineractHttpClient,
    *,
    verify_login: bool = True,
    login_transport: Optional[Any] = None,
) -> PartBResult:
    result = PartBResult()

    client.wait_until_ready()

    cur = ensure_currencies(client, keep=["USD"])
    result.steps.append(cur)
    result.currencies = list(cur.detail.get("currencies") or [])
    if CURRENCY not in result.currencies:
        raise RuntimeError(f"RWF not enabled after currency step: {result.currencies}")

    office = ensure_office(client)
    result.steps.append(office)
    result.office_id = int(office.detail["office_id"])

    gls = resolve_gl_accounts(client)
    result.steps.append(gls)
    if gls.status == "failed":
        raise RuntimeError(f"GL accounts missing: {gls.detail}")
    result.gl_map = dict(gls.detail["gl_map"])

    product = ensure_loan_product(client, result.gl_map)
    result.steps.append(product)
    result.product_id = int(product.detail["product_id"])

    role = ensure_role(client)
    result.steps.append(role)
    result.role_id = int(role.detail["role_id"])

    user = ensure_api_user(client, role_id=result.role_id, office_id=result.office_id)
    result.steps.append(user)
    result.user_id = int(user.detail["user_id"])

    if verify_login:
        login = verify_api_user_login(
            base_url=client.base_url,
            tenant=client._headers["Fineract-Platform-TenantId"],
            verify_ssl=False,
            transport=login_transport,
        )
        result.steps.append(login)
        if login.status == "failed":
            raise RuntimeError(f"API user login failed: {login.detail}")

    return result
