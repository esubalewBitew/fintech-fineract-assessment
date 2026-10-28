# Remaining work plan (brief B–K + evidence)

This plan covers **gaps after** the current middleware/Mock ERP scaffold.  
Do **one step at a time**. After each step: run tests yourself, read the diff, append a line to `AI_USAGE.md`.

Commit style: small logical commits. **Never** push Apache `fineract-src` history. Prefer **no** `Co-authored-by: Cursor`.

DB rule: app services must **not** connect as `root`. Use dedicated owners (`mock_erp`, `integration`) created in init SQL.

---

## Step 0 — Hygiene (before new features)

### Goal
- Dedicated Postgres roles/DBs (not `root`)
- Split commits for current local work
- `DECISIONS.md` lives in assessment root (not only inside a Fineract patch)

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H0.1 | Fresh `docker compose up` | `mock_erp` / `integration` DBs owned by matching users; apps start and migrate |
| H0.2 | Tables created | Owner role can `CREATE TABLE` on its DB `public` schema |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F0.1 | Connect as non-owner without grants | `permission denied for schema public` | `CREATE USER …; CREATE DATABASE … OWNER …` |
| F0.2 | Old volume without new roles | App crash on startup | Run init SQL manually or recreate volume |
| F0.3 | One mega-commit | Brief flag | Split ~5 commits (docs / mock-erp / integration core / sync / money+reconcile) |

### Evidence
- `evidence/00-db-roles.txt` — `\du` and `\l` showing owners

---

## Step 1 — Part B: Fineract setup script (empty DB → ready tenant)

### Goal
Script from empty/patched Fineract: **Kigali office**, **RWF**, product **“SME Asset Finance”** (18%, 12 monthly, full GL mappings), **least-privilege API user**.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H1.1 | Run setup against fresh Fineract | Office Kigali exists; currency RWF enabled |
| H1.2 | Product create | SME Asset Finance: 18% p.a., 12 months, accounting rule mappings set |
| H1.3 | API user | User can call needed loan/GL APIs only (not superuser if brief requires) |
| H1.4 | Re-run script | Idempotent (skip or update safely) |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F1.1 | Fineract not up | Connection refused | Wait health; retry |
| F1.2 | GL mapping account missing | 403/400 on product | Ensure CoA sync (A) ran first or seed GLs in script |
| F1.3 | Duplicate office/product | Conflict | Lookup by name/externalId before create |
| F1.4 | Wrong currency | Later loan fails | Assert RWF in script; fail fast |

### Deliverables
- `scripts/fineract_setup_part_b.py` (or `.sh` + httpx)
- `evidence/01-part-b-setup.json`
- Tests: dry-run mocks for create-or-get office/product/user

---

## Step 2 — Part C: IDs — service creates client + loan

### Goal
Remove “map only” as the primary path. Service **creates client** (`externalId = client_uid`) and **applies for loan** (`externalId = loan_reference`), then stores ids in `client_map` / `loan_map`.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H2.1 | `POST /clients` `{client_uid,…}` | Fineract client created; map row; same `externalId` |
| H2.2 | `POST /loans/apply` `{loan_reference, client_uid, product,…}` | Loan applied; map row; `externalId` = loan_reference |
| H2.3 | Replay same client_uid | Idempotent → existing client id |
| H2.4 | Disburse uses loan_reference only | Resolves via map; no manual Fineract id required |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F2.1 | Unknown product | 400 | Part B product must exist |
| F2.2 | client_uid conflict different payload | 409 | Do not overwrite; return conflict |
| F2.3 | Loan apply timeout | Unknown state | Lookup `GET /loans/external-id/{loan_reference}` (Part J) |
| F2.4 | Still calling `/loans/map` only | Brief fail | Keep map as admin escape hatch; document primary = create/apply |

### Deliverables
- Use cases + Fineract adapter methods: `create_client`, `apply_loan`
- Routes; unit tests with respx
- `evidence/02-part-c-ids.json`

---

## Step 3 — Part D: Lifecycle to Closed

### Goal
Orchestrated flow: **Apply → Approve → Disburse → 3 partial repayments → Payoff → Closed**, saving status + balances at each step.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H3.1 | Apply | Status Submitted/Approved pending |
| H3.2 | Approve | Waiting for disbursement |
| H3.3 | Disburse | Active; principal outstanding = disbursed |
| H3.4 | Repayment 1–3 | Outstanding decreases; each step logged |
| H3.5 | Payoff | Closed; outstanding 0 |
| H3.6 | Snapshot file | `evidence/03-lifecycle.json` has every step |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F3.1 | Approve before apply | 400 | Enforce state machine |
| F3.2 | Disburse twice | 409 / unique disbursed_txn | One disbursement guard |
| F3.3 | Over-repay without overpayment product config | Fineract error | Cap at outstanding or enable overpayment |
| F3.4 | Crash mid-lifecycle | Partial steps | Resume from last saved step (J recovery) |

### Deliverables
- `POST /simulations/lifecycle` or `make simulate-lifecycle`
- Step recorder (status, balances, external_references)

---

## Step 4 — Part E: API contract polish

### Goal
API-key auth, validation, **one error format**, correlation ID, **OpenAPI** page.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H4.1 | Valid API key | 2xx |
| H4.2 | `X-Correlation-Id` echoed / logged | Traceable in logs |
| H4.3 | `/docs` OpenAPI | Lists all routes |
| H4.4 | Validation error | Single JSON error envelope |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F4.1 | Missing API key | 401 + same error shape | Dependency |
| F4.2 | Invalid body | 422 + same error shape | Exception handler |
| F4.3 | Upstream 502 | Error envelope with `correlation_id` | Handler wraps |

### Deliverables
- `API.md`, global exception handlers, OpenAPI tags
- Tests for 401/422 envelope

---

## Step 5 — Part F: Idempotency matrix (tests + behavior)

### Goal
Prove every case: **200 replay**, **202 in progress**, **409 mismatch**, **one disbursement per loan even with different references**.

### Happy / contract scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H5.1 | Identical retry after COMPLETED | 200 + same `integration_txn_id` |
| H5.2 | Retry while RAIL_PENDING / FINERACT_PENDING | **202** + current state |
| H5.3 | Same external_reference, different payload | **409** |
| H5.4 | Second disbursement different external_reference same loan | **409** (disbursed_txn_id unique) |
| H5.5 | Concurrent identical disburse | One winner; other 200 replay or 202 |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F5.1 | Missing UNIQUE(op, ref) | Duplicates | DB constraint |
| F5.2 | Returning 200 while still pending | Wrong client retry | Map in-progress states → 202 |
| F5.3 | Blind re-POST after timeout | Double book | Lookup by externalId first (J) |

### Deliverables
- Idempotency tests (parametrize)
- HTTP status mapping in API layer
- `evidence/05-idempotency.txt`

---

## Step 6 — Part H: Mapping purity (confirm + extend tests)

### Goal
Pure functions from Fineract portions → journal lines; unit tests for **repayment split** and **reversal**.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H6.1 | Repay principal+interest | Cash DR; portfolio CR; interest income CR |
| H6.2 | `reverse(lines)` | DR/CR swapped; accounts unchanged |
| H6.3 | No I/O in mapping module | Pure; easy to test |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F6.1 | Unbalanced mapping | ERP 422 | Assert ΣDR=ΣCR in mapper tests |
| F6.2 | Missing GL code in ERP | ERP 400 | Map only seeded accounts; Part B GLs aligned |

### Deliverables
- Expand `test_journal_mapping.py`
- Document portion → account table in `API.md` or `MAPPING.md`

---

## Step 7 — Part I: Concurrency (≈20% score)

### Goal
- 4× sequential disbursement (different loans)
- **10× parallel** disbursement
- Parallel repayments
- Final balances checked against Fineract

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H7.1 | 4 sequential disbursements | 4 Active loans; ERP 4 journals |
| H7.2 | 10 parallel disbursements | 10 successes; no duplicate journals per ref |
| H7.3 | Parallel repayments same loan (distinct refs) | Correct outstanding vs Fineract |
| H7.4 | Parallel identical ref | Idempotent single book |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F7.1 | Race without DB unique | Double insert | UNIQUE + claim pattern |
| F7.2 | Balance drift | Fineract ≠ sum(ERP) | Fail test; open J/K |
| F7.3 | Pool exhaustion | Timeouts | Limit workers; backoff |

### Deliverables
- `scripts/concurrency_part_i.py` + `make simulate-concurrency`
- `evidence/07-concurrency-*.json`
- pytest with ThreadPoolExecutor against testcontainers or compose

---

## Step 8 — Part J: Failures (5 scenarios + restart)

### Goal
1. ERP fault (already partly there)  
2. **Fineract down**  
3. **Fineract timeout → lookup by externalId** (no blind retry)  
4. Crash between Fineract success and ERP post  
5. **Restart recovery** clears/continues `NEEDS_RECONCILIATION`

### Happy / recovery scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H8.1 | After Fineract timeout, lookup finds txn | Complete ERP leg; COMPLETED |
| H8.2 | Crash after Fineract, before ERP | NEEDS_RECONCILIATION; recover posts journal |
| H8.3 | Restart `/admin/recover` or sweep | Listed then resolved |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F8.1 | Fineract down at disburse | FAILED or NEEDS_RECON; no ERP journal | Don’t invent success |
| F8.2 | Blind retry after timeout | Duplicate disburse | Mandatory externalId GET |
| F8.3 | ERP down after Fineract | NEEDS_RECON | Recover when ERP up |
| F8.4 | Lookup 404 after timeout | NEEDS_RECON / manual | Evidence + alert |

### Deliverables
- Fault toggles / toxiproxy or mock transport
- `evidence/08-j1` … `08-j5`
- Tests for timeout→lookup path

---

## Step 9 — Part K: Reconciliation — all 4 outcomes in one report

### Goal
Seed data so one report shows: **MATCHED**, **MISSING_IN_ERP**, **MISSING_IN_FINERACT**, **AMOUNT_MISMATCH**.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H9.1 | Seed script | Four refs with engineered divergence |
| H9.2 | `GET /reconcile/fineract-erp` | All 4 outcomes present |
| H9.3 | Reversal netting | Documented rule; MATCHED only with reverse journal |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F9.1 | Only MATCHED shown | Incomplete seed | Explicit seed for each outcome |
| F9.2 | Wrong join key | False MISSING_* | Join on `external_reference` only |

### Deliverables
- `scripts/seed_reconcile_k.py`
- `evidence/09-reconcile-four-outcomes.json`

---

## Step 10 — Docs, Make, evidence, AI disclosure

### Goal
`README`, `API.md`, `SIMULATIONS.md`, `AI_USAGE.md`, `Makefile` (`simulate-*`), `evidence/`.

### Happy scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H10.1 | `make simulate-coa` | Writes evidence; exit 0 |
| H10.2 | `make simulate-lifecycle` | Part D evidence |
| H10.3 | AI_USAGE.md | One line per Cursor-assisted step |

### Failure scenarios
| ID | Failure | Symptom | Fix |
|----|---------|---------|-----|
| F10.1 | Evidence missing in PR | Reviewer reject | CI or checklist |
| F10.2 | README still says “Part B” for middleware | Confusion | Use brief letters |

---

## Step 11 — A sync evidence + Java notes

### Goal
- Run CoA sync **twice**; save both outputs under `evidence/`
- Confirm Java IT + Dockerfile; keep assessment `DECISIONS.md` out of future patches if regenerating

### Scenarios
| ID | Scenario | Expected |
|----|----------|----------|
| H11.1 | First sync | `created` / `skipped_currency` |
| H11.2 | Second sync | `already_mapped` / idempotent |
| F11.1 | DECISIONS inside Fineract patch only | Reviewer noise | Prefer assessment-root DECISIONS |

---

## Recommended execution order (today → next)

1. Step 0 hygiene + split commits (**no push** until you review)  
2. Step 1 Part **B**  
3. Step 2 Part **C**  
4. Step 3 Part **D**  
5. Steps 5–6 (**F**, **H** tests)  
6. Step 7 **I**  
7. Step 8 **J**  
8. Step 9 **K**  
9. Step 10 docs/evidence  
10. Step 11 CoA double-run evidence  

After each step: tests + diff review + `AI_USAGE.md` line.
