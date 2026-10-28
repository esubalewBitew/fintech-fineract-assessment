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
