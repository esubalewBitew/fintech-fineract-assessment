# Interview prep — Part A (Fineract GL `externalReference`)

Use this as a verbal crib sheet: what we built, why, how it fails safely, and how we proved it.

Pinned base: **Apache Fineract `1.16.1`**. Changes ship as **patches only** (`0001`–`0004`), not a fork of Apache history.

Repo: `fintech-fineract-assessment` → `fineract-customization/patches/` + Docker.

---

## 1. One-sentence pitch

We made `POST /glaccounts` **idempotent by optional `externalReference`**: same ERP key + same business payload returns the existing account; same key + different payload returns **HTTP 409**; concurrent double-creates are safe under PostgreSQL’s unique constraint.

---

## 2. Problem we were solving

ERP / Integration Service will sync chart-of-accounts into Fineract. Retries and parallel workers must not create duplicate GLs. Fineract already has `glCode`, but the **external system’s stable id** is `externalReference` (immutable after create). Currency is **not** on the GL entity in Fineract — non-RWF is rejected later in the Integration Service (Part B).

---

## 3. What we delivered (map to patches)

| Patch | What | Why it matters in interview |
|-------|------|-----------------------------|
| `0001` | Liquibase `0270`: column `external_reference` + unique index `uk_acc_gl_external_reference` | DB is source of truth for uniqueness under concurrency |
| `0002` | Command/deserializer/entity/repo + upsert write path + comparator + 409 exception/mapper + `DECISIONS.md` | Full product behavior |
| `0003` | 10-thread Mockito write-service race test | Shows we thought about races, not only happy path |
| `0004` | RestAssured/Feign-raw HTTP IT: idempotent replay + 409 | End-to-end API contract |

Also: assessment **Dockerfile** (clone `1.16.1` → `git am` patches → `bootJar`) + **compose** wired like upstream PostgreSQL env files. Manual curl smoke: create / replay / 409 all passed against `https://localhost:8443`.

---

## 4. Data model & API contract

### Field

- JSON: `externalReference` (optional string).
- DB: `acc_gl_account.external_reference` (nullable), unique when present.
- Set only in **`GLAccount.fromJson`** on create.
- **`GLAccount.update` does not touch it** → immutable after create (by design).

### Stock behavior preserved

- `POST /glaccounts` **without** `externalReference` behaves as before (normal create).
- No change to update/delete rules beyond not allowing mutation of the reference.

### Idempotency rule (compare these fields only)

`GLAccountExternalReferencePayloadComparator`:

- Compared: `glCode`, `name`, `type`, `usage`, `parentId`, `description`
- **Not** compared: `externalReference` (lookup key), `disabled`, `manualEntriesAllowed`, `tagId`
- Rationale: keep the “same business account” definition tight and reviewable; tag/disabled are not part of the ERP sync identity we agreed.

---

## 5. Request flow (say this out loud)

```
POST /glaccounts { ..., externalReference }
        │
        ▼
 deserialize → GLAccountCommand.validateForCreate()
        │
        ▼
 if externalReference blank → classic insert path
        │
        ▼
 SELECT by externalReference
   ├─ found + payload identical → return existing resourceId (200)
   ├─ found + payload differs  → GLAccountExternalReferenceConflictException → HTTP 409
   └─ not found
        │
        ▼
 self.insertNewGLAccount()   @Transactional(REQUIRES_NEW)
        │
        ├─ success → return new id
        └─ unique violation on uk_acc_gl_external_reference
              │
              ▼
           ConflictResolver.resolveAfterUniqueViolation()  (REQUIRES_NEW)
              ├─ re-read + identical → return existing id
              ├─ re-read + differs  → 409
              └─ still missing      → RaceException (subclass of conflict) → 409
```

### Why `REQUIRES_NEW` on insert?

PostgreSQL **aborts the current transaction** after a unique-constraint violation. If insert ran in the outer tx, the catch block could not safely re-query. Nested `REQUIRES_NEW` keeps the failed insert in its own aborted tx; the outer/resolver tx can still read and decide.

### Why not only rely on SELECT-then-INSERT?

Two threads can both see “not found” and both insert. The unique index is the hard guarantee; the catch + re-read is the soft recovery that turns a race into either idempotent success or a clean 409.

---

## 6. Happy-path scenarios (be ready to walk through)

| # | Scenario | Expected |
|---|----------|----------|
| H1 | Create with new `externalReference` | `200`, new `resourceId` |
| H2 | Replay **identical** body (same ref + same compared fields) | `200`, **same** `resourceId` |
| H3 | Create **without** `externalReference` | Normal Fineract create (no upsert) |
| H4 | Update GL name/description via `PUT` | Works; `externalReference` unchanged |
| H5 | Two concurrent identical creates | Exactly one row; both callers get same id (one insert, one race recovery) |

**Live smoke we ran:**

1. Create → `HTTP 200` `resourceId: 1`
2. Identical POST → `HTTP 200` `resourceId: 1`
3. Different name/glCode, same ref → `HTTP 409` + `error.msg.glaccount.external.reference.conflict`

---

## 7. Failure / edge scenarios (interview gold)

| # | Failure | What happens | Status / code |
|---|---------|--------------|---------------|
| F1 | Same `externalReference`, **different** payload (name/glCode/type/usage/parent/description) | Domain rule violation | **HTTP 409**, `error.msg.glaccount.external.reference.conflict` |
| F2 | Concurrent inserts, both pass pre-check | Second hits `uk_acc_gl_external_reference` | Caught → resolver re-reads → identical → same id; differs → 409 |
| F3 | Unique violation but row not visible / gone (extreme race) | `GLAccountExternalReferenceRaceException` | Mapped as conflict family → **409** |
| F4 | Other integrity errors (e.g. duplicate `glCode`) | Existing `handleGLAccountDataIntegrityIssues` | Unchanged Fineract behavior (not our 409 path) |
| F5 | Blank / null `externalReference` | Upsert branch skipped | Classic create |
| F6 | Client tries to “change” reference on update | Update path ignores field | Stays immutable |
| F7 | Integration sends non-RWF currency | **Not in Fineract** — rejected in Integration Service (Part B) | Design decision, say it clearly |
| F8 | Generated Feign `PostGLAccountsRequest` lacks field | IT uses `FeignRawHttpHelper` + raw JSON | Temporary until OpenAPI client regenerated |

**Note on response body:** mapper returns real **HTTP 409**. Fineract’s `ApiGlobalErrorResponse.domainRuleViolation(...)` may still embed an older `httpStatusCode` string in JSON (we saw `"403"` in the body while wire status was `409`). In interview: “Wire status is 409 from our `ExceptionMapper`; the embedded status string is a platform helper quirk — clients must use the HTTP status.”

---

## 8. Tests — what to claim and where they live

### Unit

1. **`GLAccountExternalReferencePayloadComparatorTest`**  
   Identical vs differing each compared field; proves what “same payload” means.

2. **`GLAccountExternalReferenceConflictExceptionMapperTest`**  
   Mapper returns **409** and expected error code / body shape.

3. **10-way concurrent create** (`0003`)  
   Mockito around write service / repo: many threads, same ref, assert single logical create / stable id behavior under race handling. Shows concurrency was a first-class requirement, not an afterthought.

### Integration

4. **`GLAccountIntegrationTest`** (patch `0004`)  
   - `createWithExternalReferenceIsIdempotentForIdenticalPayload`  
   - `createWithExternalReferenceConflictsWhenPayloadDiffers`  
   Uses raw HTTP because the generated client model does not yet expose `externalReference`.

### Manual / Docker

5. Compose up + curl create / replay / 409 against patched image `fineract:assessment`.

**How to say it:** “We tested at three layers: pure comparator/mapper unit tests, a concurrent write-service test, and an HTTP IT plus a Docker smoke.”

---

## 9. Key classes (memory anchors)

| Class | Role |
|-------|------|
| `GLAccountWritePlatformServiceJpaRepositoryImpl` | Upsert orchestration; catch unique violation |
| `insertNewGLAccount` | `REQUIRES_NEW` insert |
| `GLAccountExternalReferenceConflictResolver` | Post-violation re-read + compare |
| `GLAccountExternalReferencePayloadComparator` | Business equality |
| `GLAccountExternalReferenceConflictException` | Payload mismatch |
| `GLAccountExternalReferenceRaceException` | Violation but no row (extends conflict) |
| `GLAccountExternalReferenceConflictExceptionMapper` | Jersey `@Provider` → HTTP 409 |
| `GLAccountRepository.findOneByExternalReference` | Lookup |

---

## 10. Design decisions — defend them

1. **Optional field** — backward compatible with stock clients.  
2. **Immutable after create** — ERP id must not drift; remapping is a new account.  
3. **Unique index in DB** — application check alone is not enough under concurrency.  
4. **`REQUIRES_NEW`** — required because PG kills the failed transaction.  
5. **409 not 400** — conflict with an existing resource identity, not malformed input.  
6. **Comparator subset of fields** — deliberate; document in `DECISIONS.md`.  
7. **Currency out of Fineract** — no GL currency column; Integration Service owns RWF gate.  
8. **Patches not full fork** — reviewers apply `git am` on `1.16.1`; assessment repo stays small and attributable.  
9. **Not on command-retry list** — intentional; conflict is business outcome, not transient command bus failure.

---

## 11. Likely interview questions + short answers

**Q: Why not upsert with `ON CONFLICT DO NOTHING`?**  
A: We need payload comparison: same key can be success or 409. SQL upsert alone does not encode that business rule cleanly across JPA.

**Q: Why HTTP 409?**  
A: The request conflicts with the current state of a resource identified by `externalReference`. Client should stop retrying with a different payload or reconcile.

**Q: What if two different ERPs reuse the same reference?**  
A: Unique constraint makes that a data-governance problem; second different payload gets 409. Integration layer should namespace refs if needed (`ERP-A:…`).

**Q: Is SELECT-then-INSERT enough?**  
A: No — TOCTOU race. Unique index + catch is the real safety net; SELECT is the fast path for the common idempotent retry.

**Q: How do you ship without forking Apache?**  
A: Four `git format-patch` files; Dockerfile clones tag and `git am`s them.

**Q: What’s left?**  
A: Part B — Mock ERP + Integration Service (Python): pull ERP accounts, map currency (reject non-RWF), call Fineract upsert API, handle 200 vs 409.

---

## 12. Conclusion (closing statement for interview)

Today we completed **Part A end-to-end**: schema, API wiring, idempotent create with conflict semantics, concurrency-safe recovery under PostgreSQL, automated tests at unit/race/HTTP levels, and a reproducible Docker path proven with create / replay / 409. The design keeps stock Fineract behavior when the new field is absent, puts uniqueness in the database, and keeps currency policy in the integration layer where it belongs. Next step is the Python Integration Service that drives this API from a Mock ERP.

---

## 13. Quick cheat sheet (30-second version)

- Optional immutable `externalReference` + unique DB index  
- Same ref + same payload → same id  
- Same ref + different payload → **409**  
- Race → unique violation → `REQUIRES_NEW` resolver → same id or 409  
- Currency = Integration Service; patches on `1.16.1`; Docker smoke passed  

---

*Generated for interview prep after Part A implementation (Liquibase → upsert → tests → Docker). See also `DECISIONS.md`.*
