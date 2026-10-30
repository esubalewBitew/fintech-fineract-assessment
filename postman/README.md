# Postman

| File | Use |
|------|-----|
| `collection.json` | End-to-end: ERP GLs → CoA sync → Part B → client/loan → money |
| `scenarios.json` | Extra scenarios (idempotency, faults, reconcile, auth) |
| `environment.json` | Local URLs and API keys |

## Import

1. Import `collection.json`, `scenarios.json`, and `environment.json`
2. Select environment **local**
3. Disable SSL verification for `https://localhost:8443`

## Run order (`collection.json`)

1. **00 — Bootstrap** → Refresh run_id  
2. **01** Mock ERP accounts (409 if already seeded is fine)  
3. **02** Sync CoA  
4. **03** Fineract currency / office / loan product (skip if `make setup-part-b` already ran)  
5. **04** Client + loan apply/approve  
6. **05** Disburse / repay  
7. **06** Reconcile / recover  

Stack: `docker compose up -d` from repo root.