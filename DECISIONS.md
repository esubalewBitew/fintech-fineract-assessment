# externalReference on GL accounts

`externalReference` is optional. Stock `POST /glaccounts` without it is unchanged.

It is set only in `GLAccount.fromJson`. `GLAccount.update` does not read it, so it is immutable after create.

The comparator checks `glCode`, `name`, `type`, `usage`, `parentId`, and `description`. It does not check `externalReference`, `disabled`, `manualEntriesAllowed`, or `tagId`. Fineract GL has no currency column. Non-RWF is rejected in the Integration Service.

A concurrent create can pass the select and then hit `uk_acc_gl_external_reference`. PostgreSQL aborts that transaction. The insert runs in `insertNewGLAccount` (`REQUIRES_NEW`). The catch calls `GLAccountExternalReferenceConflictResolver` (`REQUIRES_NEW`) to re-read. Identical payload returns the existing id. A different payload throws `GLAccountExternalReferenceConflictException`, mapped to HTTP 409. This is not the command retry list.
