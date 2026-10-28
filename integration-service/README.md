# Integration Service (middleware)

FastAPI + SQLAlchemy + Postgres.

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/sync/coa` | A-sync CoA from Mock ERP → Fineract |
| POST | `/loans/map` | Register loan_reference → fineract_loan_id |
| POST | `/loans/disburse` | Rail → Fineract → ERP journal |
| POST | `/loans/repay` | Rail → Fineract → ERP journal |
| POST | `/transactions/reverse-repayment` | Undo repayment + reversing journal |
| GET | `/reconcile/fineract-erp` | K reconciliation report |
| GET | `/admin/recover` | J NEEDS_RECONCILIATION list |

Auth: `X-Api-Key: integration-key`

## Docs (on disk)

| File | Content |
|------|---------|
| `docs/FLOWS.md` | Sync / disburse / repay / reverse / reconcile sequences |
| `docs/MIDDLEWARE.md` | Ports, states, pass-through refs |
| `docs/ERP_CONTRACT.md` | Mock ERP HTTP contract |
| `../FEATURES_AND_FLOWS.md` | Full tomorrow cheat sheet |
| `../QUICK_COMMANDS.txt` | Copy-paste curls |
