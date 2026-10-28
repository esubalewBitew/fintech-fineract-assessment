# Mock ERP (brief G)

Standalone ledger: chart of accounts + journal entries. Never calls Fineract.

- Postgres persistence (SQLAlchemy)
- Balanced journals required; `external_reference` unique (200 identical / 409 conflict)
- Seed: 9 RWF accounts + 1 USD
- Admin faults: `POST /admin/faults` `{ "mode": "down|timeout_after_write|slow|none" }`

Auth: header `X-Api-Key: mock-erp-key`

Flows: `docs/FLOWS.md`  
Contract: `../integration-service/docs/ERP_CONTRACT.md`  
Master reference: `../FEATURES_AND_FLOWS.md`
