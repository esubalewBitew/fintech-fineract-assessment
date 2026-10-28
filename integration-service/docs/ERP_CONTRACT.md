# Mock ERP HTTP contract

Auth: `X-Api-Key: mock-erp-key`

## Accounts

`GET /accounts` → list  
`GET /accounts/{external_reference}`  
`POST /accounts` — unique `external_reference` + `code`

```json
{
  "external_reference": "ERP-FEE-INC",
  "code": "4001",
  "name": "Fee Income",
  "type": "INCOME",
  "usage": "DETAIL",
  "currency": "RWF",
  "description": "Fee Income",
  "manual_entries_allowed": true
}
```

Fineract `externalReference` = **same** `external_reference` (pass-through).

## Journals

`POST /journal-entries` — balanced (≥2 lines, ΣDR=ΣCR)  
- new → 201  
- same ref + same payload hash → 200  
- same ref + different payload → 409  

`GET /journal-entries?external_reference=&since=`
