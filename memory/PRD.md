# Commercial Trading — v1.1 (Finance repo) — Working Notes

## Environment
- LIVE Firestore `commercial-trading1` (⚠️ REAL production data). Admin: admin@example.com / admin123 (Firebase).
- firestore_db.py = Motor-style shim; routes use `db`.

## Key modules delivered (all testing-agent verified)
- Products #9/#10/#11; Invoice list filters/sort/page-20; Payments (ref auto PAY-XXXX, related customer, endorse cheques, editable date); Ledger multi-cheque collapse; Purchase destination; Warehouse valuation (unified returned_stock pool); Bank dropdown in Migration; Drafts (autosave + naming); Settle/Unsettle (reversible).
- Auto-purchases from invoices are destination=direct_customer, never touch warehouse; invoice delete cascades linked auto-purchase + reverses stock.

## Latest fix (v1.1.4) — Invoice print formatting
- lib/print.js: removed the portrait/landscape heuristic (caused inconsistency); ALL invoices now print @page size A5 landscape. ITEMS_PER_PAGE=10 (was 20). Each 10-item chunk is a full .page with repeated header (brand + INVOICE# + Bill To + column thead); Total Due + Returns/Credit Terms + Thank-you only on the last page. Verified 100% by testing agent (invoices with 2/10/12/18 items incl. long names).

## Latest fix (v1.1.3) — Customer Outstanding
BUG: Haseena Ceramic showed NEGATIVE outstanding because bills were BOTH manually settled AND paid → formula subtracted manual_settled AND payments (double count).
FIX (routes/reports.py customer_outstanding):
- total_outstanding = opening + billed - payments - returns  (manual_settled REMOVED from the math; it's only a per-invoice display status now). Payments are the source of truth.
- Per-invoice FIFO uses payments only (explicit allocations first, then oldest-first pool). Balances never negative; overpayment surfaces as `advance`.
- Added date_from/date_to query params: filters invoices + payments + returns to the window; opening excluded when date_from set. Returns date_from/date_to.
- Frontend ReportsPage: From/To date inputs + Apply/Clear on the Customer Outstanding tab (data-testid cust-out-from / cust-out-to / cust-out-apply / cust-out-clear).

## Latest fix (v1.1.5) — Firestore read-quota blowout + login breakage (2026-10-01)
ROOT CAUSE (application code, NOT billing): firestore_db.py `_fetch_all()` streamed the ENTIRE collection on every op (find/find_one/update/delete). "Get one invoice" or "update one payment" read the whole collection → tens of thousands of reads/day → ~51K → Firestore `resource-exhausted` (daily free quota) → `/auth/me` Firestore read threw → AuthContext caught it, set user=false → login silently bounced back to /login.
FIX:
- backend/firestore_db.py: added `_split_query()` + query-aware `_fetch_all(query)`. Single-doc lookups `{"id": x}` now do `document(id).get()` (1 read); top-level equality filters push to Firestore server-side via `.where(filter=FieldFilter(...))`. Threaded `query` into find/find_one/count/update_one/update_many/delete_one/delete_many. Python `_doc_matches` re-check retained for complex ops ($in/$or/$regex/ranges still full-scan — acceptable, less common). Verified live: filter-by-customer_id read 5 docs instead of scanning all 230.
- backend/auth.py: `/auth/me` now derives name/role from the Firebase token claims first; Firestore profile read is best-effort in try/except so login NEVER breaks when Firestore is throttled/down. (Admins need the `role` custom claim set — they have it.)
- frontend/contexts/AuthContext.js: fetchProfile logs real error status instead of silent warn.
- frontend/pages/ChequeInventoryPage.js: fixed Vercel build error — `ArrowsClockwise` (Phosphor, not in lucide-react) → `RefreshCw`. Frontend now compiles.
- Verified: admin login → dashboard end-to-end on preview. Backend clean reload.
- REMAINING (not needed for fix): dashboard.py:56 + some reports.py endpoints legitimately scan whole collections (empty-query aggregates) — add date-scoping/cache only if those pages are hit often.
- Firebase side: confirm Blaze plan is linked to the same GCP billing account as project commercial-trading1; message should clear after quota window resets. Code fix prevents recurrence.

## Notes
- Manual "Settle" button remains in Customer Outstanding but no longer double-deducts (payments drive the total).
- Products have no code field (search matches name/id).
