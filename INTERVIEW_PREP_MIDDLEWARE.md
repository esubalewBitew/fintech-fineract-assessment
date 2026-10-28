# Interview prep — Integration middleware + Mock ERP (A-sync / E–K)

## One sentence

Middleware with **ports** (CBS, Ledger, Rail, CoA): use cases never import Telebirr/M-Pesa; Mock ERP is a real ledger; one `external_reference` joins Fineract, ERP, and our legs for reconciliation.

## Brief letters (do not say “Part B”)

| Letter | What we built |
|--------|----------------|
| A-sync | CoA sync + RWF gate + pass-through `externalReference` |
| E/F/H/I | Disburse / repay / repayment reverse; journal mapping + `reverse(lines)` |
| G | Mock ERP DB: accounts, balanced journals, uniqueness, faults |
| J | `/admin/recover` lists `NEEDS_RECONCILIATION` |
| K | Fineract↔ERP reconcile: MATCHED / MISSING_IN_ERP / MISSING_IN_FINERACT / AMOUNT_MISMATCH |

Fineract office/product/API user setup remains the brief’s **config** section.

## Why OfflineRail

Assessment money is already settled. Same state machine works later: swap in `MockMoMoRail` / Telebirr adapter without changing use cases.

## Document only

Undo disbursement, creditBalanceRefund, live MNO adapters, rail↔Fineract reconcile, GL master-data reconcile.

## Demo curls

```bash
# CoA sync (skips USD seed)
curl -s -X POST http://localhost:8082/sync/coa -H "X-Api-Key: integration-key"

# Map a Fineract loan id then disburse/repay (requires loan exists in Fineract)
curl -s -X POST http://localhost:8082/loans/map -H "X-Api-Key: integration-key" \
  -H "Content-Type: application/json" \
  -d '{"loan_reference":"L-1","fineract_loan_id":1}'

curl -s -X POST http://localhost:8082/reconcile/fineract-erp -H "X-Api-Key: integration-key"
```
