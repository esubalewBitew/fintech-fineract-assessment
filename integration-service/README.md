# Integration Service (middleware)

FastAPI + SQLAlchemy + Postgres.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sync/coa` | A-sync CoA from Mock ERP → Fineract |
| POST | `/clients` | Part C — create client (`externalId=client_uid`) |
| POST | `/loans/apply` | Part C — apply loan (`externalId=loan_reference`) |
| POST | `/loans/{ref}/approve` | Approve loan |
| GET | `/loans/{ref}` | Status + balances snapshot |
| POST | `/loans/map` | Admin escape hatch only |
| POST | `/loans/disburse` | Rail → Fineract → ERP (timeout → LOOKUP_BY_EXTERNAL_ID) |
| POST | `/loans/repay` | Rail → Fineract → ERP journal |
| POST | `/transactions/reverse-repayment` | Undo repayment + reversing journal |
| GET | `/reconcile/fineract-erp` | K reconciliation report |
| GET | `/admin/recover` | J NEEDS_RECONCILIATION list |
| POST | `/admin/fineract-fault` | Part J inject `timeout_after_write` |

Auth: `X-Api-Key: integration-key`

## Docs (on disk)

| File | Content |
|------|---------|
| `docs/FLOWS.md` | Sync / disburse / repay / reverse / reconcile sequences |
| `docs/MIDDLEWARE.md` | Ports, states, pass-through refs |
| `docs/ERP_CONTRACT.md` | Mock ERP HTTP contract |
| `../FEATURES_AND_FLOWS.md` | Full tomorrow cheat sheet |
| `../QUICK_COMMANDS.txt` | Copy-paste curls |
