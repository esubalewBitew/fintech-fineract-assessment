# Middleware design

Use cases talk only to **ports**. Adapters implement Fineract, Mock ERP, and OfflineRail today.

Future: `adapters/rails/telebirr.py`, `mpesa.py`, `bank_*.py` registered in `RAILS` — no changes to disburse/repay/reconcile logic.

Payment Hub analogy (Inkomoko CBS): CBS should not embed every MNO; a hub/middleware owns rail adapters. Same boundary here for CoA + money + ledger.
