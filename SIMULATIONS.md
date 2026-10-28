# Simulations (evidence commands)

Run from `fineract-assessment/` with the compose stack healthy.

| Make target | Brief | Evidence |
|-------------|-------|----------|
| `make setup-part-b` | Part B | `evidence/01-part-b-setup.json` |
| `make simulate-lifecycle` | D | `evidence/03-lifecycle.json` |
| `make simulate-idempotency` | F | `evidence/05-idempotency.json` |
| `make simulate-concurrency` | I | `evidence/07-concurrency.json` |
| `make simulate-timeout` | J (lookup) | `evidence/08-timeout-lookup.json` |
| `make simulate-j-suite` | J (ERP down / recover / Fineract down) | `evidence/08-j-suite.json` |
| `make simulate-reconcile` | K | `evidence/09-reconcile-four-outcomes.json` |
| `make simulate-coa` | A-sync double-run | `evidence/11-coa-sync-1.json`, `11-coa-sync-2.json` |

Unit tests: `make test`
