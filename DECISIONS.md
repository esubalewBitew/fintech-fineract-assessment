# Decisions

## Fineract GL `externalReference` (CBS customization)

`externalReference` is optional. Stock `POST /glaccounts` without it is unchanged.

It is set only in `GLAccount.fromJson`. `GLAccount.update` does not read it, so it is immutable after create.

The comparator checks `glCode`, `name`, `type`, `usage`, `parentId`, and `description`. It does not check `externalReference`, `disabled`, `manualEntriesAllowed`, or `tagId`. Fineract GL has no currency column. Non-RWF is rejected in the Integration Service.

A concurrent create can pass the select and then hit `uk_acc_gl_external_reference`. PostgreSQL aborts that transaction. The insert runs in `insertNewGLAccount` (`REQUIRES_NEW`). The catch calls `GLAccountExternalReferenceConflictResolver` (`REQUIRES_NEW`) to re-read. Identical payload returns the existing id. A different payload throws `GLAccountExternalReferenceConflictException`, mapped to HTTP 409. This is not the command retry list.

## Integration middleware naming

Workstreams are referred to by brief letters (**A-sync, E, F, G, H, I, J, K**), not “Part B”. In the brief, Part B is Fineract configuration (office, RWF, product, API user).

## Part B bootstrap

`scripts/fineract_setup_part_b.py` is the brief Part B deliverable: idempotent create-or-get for Kigali office, RWF currency, SME Asset Finance (cash accounting mapped to CoA-synced glCodes), and least-privilege `assessment-api` role/user. Product creation requires CoA GLs first (`POST /sync/coa`). Demo API password is local-only in `scripts/fineract_setup/setup.py` (Fineract complexity policy).

## `external_reference` pass-through (not namespaced)

Alternative considered: prefix refs as `mock-erp:ERP-1001`. Rejected for v1 because reviewers may require the Fineract `externalReference` to **match** the ERP value exactly.

**Decision:** send the ERP / caller `external_reference` unchanged to Fineract and to ERP journals. Middleware uniqueness for CoA mapping uses `UNIQUE(source_system, external_reference)` on `gl_account_map`. Transaction idempotency uses `UNIQUE(operation_type, external_reference)` on `integration_transaction`.

## Currency gate

Allowed currency is **RWF** only, enforced in the Integration Service before any Fineract GL create or money booking. Mock ERP may store a USD seed account to prove the gate.

## Rails

v1 implements `OfflineRail` (immediately confirmed). Telebirr, M-Pesa, and banks are future `PaymentRailPort` adapters — documented, not coded.

## Reversals

Never edit a booked transaction. Post the opposite. v1 builds **repayment undo** + ERP reversing journal (`REV-<orig>`). Undo-disbursal and credit-balance refund are design-only.
