# Commercial Trading — v1.1 (Finance repo) — Working Notes

## Environment
- Runs against client's LIVE Firestore `commercial-trading1` (⚠️ REAL production data).
- Admin: admin@example.com / admin123 (Firebase). firebase-service-account.json + REACT_APP_FIREBASE_* wired.
- Data layer firestore_db.py = Motor-style shim; routes use the `db` API.

## Delivered (all verified by testing agent on live Firestore)
- Products #9/#10/#11; Invoice list #15 filters/sorts + #19 page 20; print items 10→20.
- Payment #3 reference (auto PAY-XXXX) + #20 related customer + endorse cheques.
- Ledger #4 multi-cheque collapse+drilldown. Purchase #12/#13 destination. Warehouse #16/#17/#18 (unified returned_stock pool). Bank dropdown in Migration payment.
- Settle/Unsettle: reversible; buttons REMOVED from invoice list (kept in Customer Outstanding report).
- Bug round: ledger payment ref sensible, backdated order, supplier-payment customer ref (+Migration), opening-stock date/notes, Cheque Inventory confirmed complete.
- Drafts feature: drafts collection + DraftsDialog; Orders + Migration historical invoice. Autosave (Orders, 3s) + custom naming (prompt).

## Latest session (v1.1.2) — verified 7/7
1. Ledger date range is DISPLAY-ONLY: running balance computed over ALL txns; closing_balance = true total regardless of filter; adds opening_forward. (customer + supplier ledger)
2. Payment dates editable: PaymentUpdate.created_at + PaymentsPage date field.
3. Draft autosave (Orders).
4. Draft custom naming (prompt) on Orders + Migration.
5. Customer Outstanding is ACCOUNT-BASED: total = opening + invoices - ALL payments - returns - manual_settled. Per-invoice display honors explicit allocations first, then FIFO the unallocated pool; returns 'advance' + 'total_paid'. Manual "Settle" button per row in Reports→Customer Outstanding (uses /invoices/{id}/settle, reversible via /unsettle).

## Notes
- Products have no dedicated code field (search matches name/id).
- Reviewer minor (non-blocking): add ISO validation for PaymentUpdate.created_at; drafts PUT ignores `kind`.
