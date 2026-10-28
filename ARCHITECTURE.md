# Architecture — Integration middleware + Mock ERP

Brief coverage: **A-sync** (CoA), **E/F/H/I** (loan money flows), **G** (Mock ERP ledger), **J** (recovery), **K** (reconciliation).

Fineract config (office, RWF product, API user) is a separate brief section — not named “Part B” here.

## Target picture

```text
                 Partners / channels / ERP
                            │  (API key, correlation id)
                            ▼
┌─────────────────────── Integration Service (middleware) ───────────────────────┐
│  API     /sync/coa /loans/.../disburse /repay /reversals /reconcile /admin/...   │
│  Use cases   DisburseLoan, RecordRepayment, ReverseTransaction,                  │
│              SyncChartOfAccounts, Reconcile                                      │
│              ── idempotency + state machine + legs (one DB) ──                   │
│  Ports       CoreBankingPort | LedgerPort | PaymentRailPort | CoAProviderPort  │
│  Adapters    Fineract | MockErp | OfflineRail (+ MockMoMo stretch)               │
└────────────────────────────────────────────────────────────────────────────────┘
        │                    │                    │
   Fineract (CBS)       Mock ERP (GL)       Banks / mobile money (later)
```

**Rule:** use cases only know ports. Adding M-Pesa or a second bank means one new adapter file and one config entry.

## Transaction identity

| ID | Owner | Purpose |
|----|-------|---------|
| `integration_txn_id` (ULID) | Middleware | Internal PK / tracking |
| `external_reference` | Caller | Idempotency + reconciliation join across all legs |
| Fineract txn externalId | Fineract | Timeout lookup |
| ERP journal `external_reference` | ERP | Uniqueness + reconcile |
| `rail_reference` | Bank/MNO | Status + callback dedupe |
| `correlation_id` | Middleware | Logs |

The **same** `external_reference` is sent to Fineract and the ERP (pass-through; not namespaced).

## State machine (v1 OfflineRail)

Disbursement: `RECEIVED → RAIL_PENDING → RAIL_CONFIRMED → FINERACT_PENDING → FINERACT_DONE → ERP_PENDING → COMPLETED`

Repayment: `RECEIVED → RAIL_CONFIRMED → FINERACT_PENDING → FINERACT_DONE → ERP_PENDING → COMPLETED`

Any leg `UNKNOWN` → `NEEDS_RECONCILIATION`. Rail failure before books → `FAILED`.

## Ports

- `CoreBankingPort` — Fineract loans / GL / undo
- `LedgerPort` — ERP journal create / list
- `PaymentRailPort` — payout / collection / status / callback
- `CoAProviderPort` — list ERP accounts for sync

## Build vs document

| Build (v1) | Document only |
|------------|---------------|
| Ports + Fineract + MockErp + OfflineRail | Telebirr / M-Pesa / bank adapters |
| CoA sync + RWF gate | GL master-data reconciliation |
| Disburse, repay, repayment reversal | Undo disbursement, creditBalanceRefund |
| Mock ERP journals + faults | Real MNO signatures |
| Fineract ↔ ERP reconcile (4 outcomes) | Rail ↔ Fineract reconcile |

## Stack

Both services: **FastAPI + SQLAlchemy + Alembic + PostgreSQL**. One Postgres instance, databases `mock_erp` and `integration`.
