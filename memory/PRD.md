# Commercial Trading — v1.1 (Finance repo) — Working Notes

## Original Problem Statement
Additive v1.1 release on an EXISTING live system: React + FastAPI + **Firestore** + Firebase Auth.
Repo restored from: https://github.com/shikishikibumba/Finance.git

## Environment Setup (this Emergent pod) — DONE
- App runs against the client's **LIVE Firestore** project `commercial-trading1`.
- `backend/firebase-service-account.json` written from user-provided admin key.
- `backend/.env`: FIREBASE_SERVICE_ACCOUNT, FIREBASE_PROJECT_ID, FIREBASE_STORAGE_BUCKET, ADMIN_EMAIL/PASSWORD.
- `frontend/.env`: REACT_APP_FIREBASE_* web config (fetched via Firebase Management API) + REACT_APP_BACKEND_URL.
- Deps installed: backend `firebase-admin, google-cloud-firestore, resend`; frontend `firebase@^12`.
- Admin login verified: admin@example.com / admin123 (role=admin, seeded on startup).
- ⚠️ LIVE DATA: 16 customers, 375 products, 109 invoices, 122 purchases, 42 payments, 21 audit logs. Avoid destructive/test writes.

## Architecture
- Data layer: `firestore_db.py` = Motor-style async shim over Firestore. All routes use this `db` API.
- Auth: `auth.py` verifies Firebase ID tokens; `require_admin()` gate. Frontend logs in via Firebase JS SDK.

## v1.1 Status (verified in code, 2026)
- Phase A (banks, payment refs, cheque inventory, audit trail, dashboard cheque-due widgets): DONE & live.
- #8 Invoice print terms (returns 30d + Ceramic 30 / Others 90): ALREADY present (screen + print HTML).
- Backdated invoice date: present in invoice edit dialog.
- #9/#10/#11 Products frontend: **IMPLEMENTED THIS SESSION** — ProductsPage.js rewritten:
  - Category field + Primary Supplier searchable dropdown (backend already supported).
  - History dialog: Price History tab (old/new/cost/date/user) + Invoice History tab (invoice#, customer→profile link, date, qty, price, amount).

## Done this session (batch 2) — verified live
- #15 Invoice list: Status + Customer + Date-range filters + sort (Newest/Oldest/Highest/Lowest). Client-side over fetched list.
- #19 Invoice list pagination default 20/page ("Showing 1–20 of 109").
- #3 Payment Reference dropdown (presets from /api/payment-references + inline add) on all payments.
- #20 Related Customer (internal) dropdown on SUPPLIER payments. Backend PaymentUpdate extended to persist payment_reference/related_customer on edit.
- #7 CONFIRMED already done: PurchasesPage detail shows Supplier Invoice #.

## Remaining / to verify next
- #4 Ledger consolidated multi-cheque display ("Payment by Cheque (N Cheques)") — needs reports.py ledger entry shaping.
- #12/#13 Purchase Destination toggle (Warehouse vs Direct Customer) — needs stock model review.
- Warehouse module: valuation banner (#16), search by name/code (#18), opening-stock notes (#17).
- #5 missing-invoices-in-ledger bug (needs reproduction against live data).
- Endorsed-cheque picker on supplier payments (backend supports endorsed_cheque_ids; UI picker not built).
- Apply page-size 20 to other list views (products/purchases/payments) if desired.

## Testing note
Automated/testing-agent runs were kept minimal to avoid writing test records into the client's LIVE Firestore. Verified via read-only UI screenshots.
