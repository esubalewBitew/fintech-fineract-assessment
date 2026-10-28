# Integration Service API

Base URL (local compose): `http://localhost:8082`  
Auth: header `X-Api-Key: integration-key`  
Correlation: send `X-Correlation-Id`; echoed on every response.

Interactive OpenAPI: [http://localhost:8082/docs](http://localhost:8082/docs)

## Error envelope

All 4xx/5xx use one shape:

```json
{
  "error": {
    "code": "unauthorized|validation_error|conflict|upstream_error|http_error",
    "message": "human readable",
    "correlation_id": "…",
    "details": {}
  }
}
```

## Money / sync routes

| Method | Path | Notes |
|--------|------|-------|
| POST | `/sync/coa` | ERP CoA → Fineract; RWF gate |
| POST | `/clients` | Create/get client by `client_uid` |
| POST | `/loans/apply` | Apply loan by `loan_reference` |
| POST | `/loans/{loan_reference}/approve` | Approve |
| POST | `/loans/map` | Manual loan map (escape hatch) |
| POST | `/loans/disburse` | Idempotent; in-progress replay → **202** |
| POST | `/loans/repay` | Idempotent repay |
| POST | `/transactions/reverse-repayment` | Reverse a completed repay |
| GET | `/reconcile/fineract-erp` | Part K report |
| GET | `/admin/recover` | List `NEEDS_RECONCILIATION` |
| POST | `/admin/recover` | Retry ERP journal for CBS-confirmed rows |
| POST | `/admin/fineract-fault` | `none` \| `timeout_after_write` \| `down` |

## Idempotency (Part F)

- Key: `(operation_type, external_reference)` unique in DB  
- Same payload after COMPLETED → **200** + `idempotent_replay: true`  
- Same key, different payload → **409**  
- Same key while non-terminal state → **202** + current `state`  
- Concurrent identical disburse → one book (Part I evidence)

## Journal mapping (Part H)

| Event | ERP lines |
|-------|-----------|
| Disburse | DR `ERP-LOAN-PORT` / CR `ERP-CASH` |
| Repay | DR `ERP-CASH` / CR `ERP-LOAN-PORT` (+ interest income if split) |
| Reverse | `reverse(lines)` swaps DR/CR |

## Mock ERP

`http://localhost:8081` — `X-Api-Key: mock-erp-key`  
`POST /journal-entries`, `GET /journal-entries`, `POST /admin/faults` (`none|down|slow|timeout_after_write`).
