# Commercial Trading — v1.1 (Finance repo) — Working Notes

## Environment
- Runs against client's LIVE Firestore project `commercial-trading1` (⚠️ REAL production data).
- Admin login: admin@example.com / admin123 (Firebase Auth). Firebase web config + service account wired.
- Data layer `firestore_db.py` = Motor-style shim; all routes use the `db` API.

## v1.1 status (latest session)
- Products #9/#10/#11 (category, primary supplier, price + invoice history) — done.
- Invoice list #15 filters/sorts + #19 page-size 20 — done. Print line-items 10→20.
- Payment form #3 payment reference + #20 related customer + endorse-cheque picker — done.
- Ledger #4 multi-cheque collapse + drill-down — done.
- Purchase #12/#13 destination (Warehouse/Direct Customer) — done.
- Warehouse module #16/#17/#18 (valuation banner, search, opening-stock notes) via unified returned_stock pool — done.
- Bank dropdown in Migration → Historical Payment — done.
- Settle/Unsettle buttons on invoice list — REMOVED per user (backend endpoints remain).

## This session — bug fixes (verify with testing agent)
1. Opening stock (#17): added Stock Date field to Returns → Add Opening Stock dialog (backend returned_stock already stores notes + created_at). Notes + date show in Warehouse lot breakdown.
2. Ledger payment reference "random word": reports.py customer+supplier ledger `ref` now = payment_number → payment_reference → "Payment" (was UUID fragment). Also payments now auto-generate payment_number `PAY-XXXX` on create.
3. Backdated Order (#19): OrderCreate/OrderUpdate accept created_at; OrdersPage create form has Order Date input (backdate). create_order uses provided date.
4. Supplier Payment Customer Reference (#20) in Migration: MigrationPage historical payment now has Customer (internal ref) dropdown for supplier payments; saved via related_customer_id/name (backend PaymentCreate already supports).
5. Cheque Inventory (#21): ALREADY fully implemented (ChequeInventoryPage + routes/cheque_inventory.py) — auto-create on customer cheque, auto-link supplier on endorsement, all columns/filters/sorts. No change needed.
