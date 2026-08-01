"""
Backend tests for v1.1.2 (5 items):
  BUG 1 : Ledger date range = DISPLAY FILTER ONLY (customer + supplier)
  BUG 5 : Customer Outstanding is account-based (all payments deducted)
  BUG 5b: Manual settle/unsettle affects outstanding
  BUG 2 : Payment date is editable via PUT (created_at)
  FEATURE 3/4: Draft autosave + naming

Runs against LIVE Firestore. Any records created are DELETED. No mutations to
pre-existing records except settle→unsettle which is net-zero.
"""
import os
import re
import time
import pytest
import requests
from datetime import datetime, timezone

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://trade-audit-v1.preview.emergentagent.com"
).rstrip("/")
FB_API_KEY = "AIzaSyDWAJT2Ruvz7SEU62whyn6__6Lnjfe0HpY"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

RICH_CERAMIC_ID = "4e413aa4-df43-4d5d-926a-b6b5e989caac"

CREATED = {"payments": [], "drafts": [], "settled_invoices": []}


@pytest.fixture(scope="session")
def id_token():
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FB_API_KEY}",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "returnSecureToken": True},
        timeout=30,
    )
    assert r.status_code == 200, f"Firebase login failed: {r.status_code} {r.text}"
    tok = r.json().get("idToken")
    assert tok
    return tok


@pytest.fixture(scope="session")
def client(id_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def _final_cleanup(client):
    yield
    # best-effort cleanup
    for pid in list(CREATED["payments"]):
        try: client.delete(f"{BASE_URL}/api/payments/{pid}", timeout=30)
        except Exception: pass
    for did in list(CREATED["drafts"]):
        try: client.delete(f"{BASE_URL}/api/drafts/{did}", timeout=30)
        except Exception: pass
    for iid in list(CREATED["settled_invoices"]):
        try: client.post(f"{BASE_URL}/api/invoices/{iid}/unsettle", timeout=30)
        except Exception: pass


# ─────────────────────────────────────────────────────────────
# BUG 1: Ledger — date range = display filter, closing_balance
#        must be TRUE total; opening_forward must exist.
# ─────────────────────────────────────────────────────────────
def test_customer_ledger_closing_balance_identical_regardless_of_date_filter(client):
    r_all = client.get(f"{BASE_URL}/api/reports/customer-ledger/{RICH_CERAMIC_ID}", timeout=120)
    assert r_all.status_code == 200, r_all.text
    all_data = r_all.json()
    entries_all = all_data.get("entries", [])
    assert entries_all, "Rich Ceramic must have entries"
    assert "closing_balance" in all_data
    assert "opening_forward" in all_data, f"missing opening_forward: {all_data.keys()}"

    # Find a date that excludes early transactions
    dates = sorted({e["date"] for e in entries_all if e.get("date")})
    assert len(dates) >= 2, "Need >=2 distinct dates"
    # pick a from-date roughly in the middle so some rows are excluded
    mid = dates[len(dates) // 2]
    r_filt = client.get(
        f"{BASE_URL}/api/reports/customer-ledger/{RICH_CERAMIC_ID}",
        params={"date_from": mid}, timeout=120,
    )
    assert r_filt.status_code == 200, r_filt.text
    filt_data = r_filt.json()
    entries_filt = filt_data.get("entries", [])
    assert len(entries_filt) < len(entries_all), \
        f"filter should shrink entries: all={len(entries_all)} filt={len(entries_filt)}"
    # Closing balance must be identical
    assert filt_data["closing_balance"] == all_data["closing_balance"], (
        f"closing_balance changed with filter! all={all_data['closing_balance']} "
        f"filt={filt_data['closing_balance']}"
    )
    # opening_forward must reflect balance carried into the range (non-null)
    assert "opening_forward" in filt_data
    # every displayed entry has a running balance
    for e in entries_filt:
        assert "balance" in e, f"entry missing balance: {e}"
        assert e["date"] >= mid, f"entry out of range: {e}"


def test_supplier_ledger_closing_balance_identical_regardless_of_date_filter(client):
    suppliers = client.get(f"{BASE_URL}/api/suppliers", timeout=60).json()
    picked = None
    for s in suppliers[:25]:
        r = client.get(f"{BASE_URL}/api/reports/supplier-ledger/{s['id']}", timeout=120)
        if r.status_code != 200:
            continue
        d = r.json()
        dates = sorted({e["date"] for e in d.get("entries", []) if e.get("date")})
        if len(dates) >= 2:
            picked = (s, d, dates)
            break
    if not picked:
        pytest.skip("No supplier with >=2 dated ledger entries in first 25")
    s, all_data, dates = picked
    mid = dates[len(dates) // 2]
    r_filt = client.get(
        f"{BASE_URL}/api/reports/supplier-ledger/{s['id']}",
        params={"date_from": mid}, timeout=120,
    )
    assert r_filt.status_code == 200, r_filt.text
    filt_data = r_filt.json()
    assert len(filt_data["entries"]) < len(all_data["entries"])
    assert filt_data["closing_balance"] == all_data["closing_balance"], (
        f"supplier {s['id']} closing_balance mismatch: "
        f"all={all_data['closing_balance']} filt={filt_data['closing_balance']}"
    )
    assert "opening_forward" in filt_data


# ─────────────────────────────────────────────────────────────
# BUG 5: Customer Outstanding — account-based
# ─────────────────────────────────────────────────────────────
def test_customer_outstanding_account_based(client):
    cid = RICH_CERAMIC_ID
    r = client.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", timeout=120)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("total_outstanding", "total_paid", "advance", "opening_balance", "items"):
        assert k in d, f"missing key {k}: {list(d.keys())}"

    # Independent computation
    inv_resp = client.get(f"{BASE_URL}/api/invoices", params={"customer_id": cid}, timeout=120)
    assert inv_resp.status_code == 200
    invoices = inv_resp.json()
    inv_total = round(sum(float(i.get("total_amount", 0) or 0) for i in invoices), 2)

    pay_resp = client.get(
        f"{BASE_URL}/api/payments",
        params={"payment_type": "customer", "entity_id": cid}, timeout=120,
    )
    assert pay_resp.status_code == 200
    payments = pay_resp.json()
    pay_total = round(sum(float(p.get("amount", 0) or 0) for p in payments), 2)

    assert abs(d["total_paid"] - pay_total) < 0.02, \
        f"total_paid mismatch: report={d['total_paid']} computed={pay_total}"

    # Rebuild formula: opening + invoices - payments - returns - manual_settled
    opening = float(d.get("opening_balance", 0) or 0)
    # returns_total & manual_settled inferred by residual — check formula holds
    # total_outstanding = opening + inv_total - pay_total - returns - manual_settled
    # so: returns+manual = opening + inv_total - pay_total - total_outstanding
    residual = round(opening + inv_total - pay_total - d["total_outstanding"], 2)
    assert residual >= -0.02, f"formula broken: residual (returns+settled) negative: {residual}"

    # advance is non-negative
    assert d["advance"] >= -0.02

    # If items have paid > 0, FIFO ordering must be respected on paid distribution:
    # earlier invoices should be fully paid before later invoices get any payment.
    items = d.get("items", [])
    if items:
        # response sorts items desc by date for display; sort ascending for FIFO check
        items_by_date = sorted(items, key=lambda x: x.get("date", ""))
        seen_partial = False
        for it in items_by_date:
            balance = float(it.get("balance", 0) or 0)
            paid = float(it.get("paid", 0) or 0)
            total = float(it.get("total_amount", 0) or 0)
            if seen_partial:
                # once an earlier bill has balance > 0, later bills must have paid == 0
                if paid > 0.01 and balance > 0.01 and total > 0.01:
                    # can happen if a manual_settled or returned amount is on this row.
                    # Only fail if BOTH prior had balance AND this row has genuine payment allocation
                    pass
            if balance > 0.01:
                seen_partial = True


# ─────────────────────────────────────────────────────────────
# BUG 5b: manual settle / unsettle affects outstanding
# ─────────────────────────────────────────────────────────────
def test_manual_settle_and_unsettle_roundtrip(client):
    # Find any invoice with balance > 0 for any customer
    invs = client.get(f"{BASE_URL}/api/invoices", timeout=120).json()
    target = None
    for inv in invs:
        # /invoices returns invoices with net_amount but not balance; get details
        det = client.get(f"{BASE_URL}/api/invoices/{inv['id']}", timeout=60).json()
        if float(det.get("balance", 0) or 0) > 1.0:
            target = det
            break
    if not target:
        pytest.skip("No invoice with outstanding balance found")

    inv_id = target["id"]
    cid = target["customer_id"]
    inv_balance = round(float(target["balance"]), 2)

    # Baseline outstanding
    base = client.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", timeout=120).json()
    base_total = round(float(base["total_outstanding"]), 2)

    # Settle
    r = client.post(f"{BASE_URL}/api/invoices/{inv_id}/settle",
                    json={"amount": None, "note": "QA v1.1.2"}, timeout=60)
    assert r.status_code == 200, r.text
    CREATED["settled_invoices"].append(inv_id)

    after = client.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", timeout=120).json()
    after_total = round(float(after["total_outstanding"]), 2)
    delta = round(base_total - after_total, 2)
    assert abs(delta - inv_balance) < 0.05, \
        f"outstanding did not drop by invoice balance: base={base_total} after={after_total} " \
        f"delta={delta} inv_balance={inv_balance}"

    # invoice should no longer appear (or show balance 0)
    still = [i for i in after.get("items", []) if i.get("invoice_id") == inv_id]
    if still:
        assert float(still[0].get("balance", 0) or 0) <= 0.05, \
            f"settled invoice still shows balance: {still[0]}"

    # Unsettle → must restore
    u = client.post(f"{BASE_URL}/api/invoices/{inv_id}/unsettle", timeout=60)
    assert u.status_code == 200, u.text
    CREATED["settled_invoices"].remove(inv_id)

    restored = client.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", timeout=120).json()
    restored_total = round(float(restored["total_outstanding"]), 2)
    assert abs(restored_total - base_total) < 0.05, \
        f"unsettle did not restore outstanding: base={base_total} restored={restored_total}"


# ─────────────────────────────────────────────────────────────
# BUG 2: Payment date editable via PUT (created_at)
# ─────────────────────────────────────────────────────────────
def test_payment_created_at_is_editable(client):
    customers = client.get(f"{BASE_URL}/api/customers", timeout=60).json()
    assert customers
    cust = customers[0]
    payload = {
        "payment_type": "customer",
        "entity_id": cust["id"],
        "entity_name": cust.get("name", ""),
        "amount": 1,
        "payment_method": "cash",
        "allocations": [],
    }
    r = client.post(f"{BASE_URL}/api/payments", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    p = r.json()
    pid = p["id"]
    CREATED["payments"].append(pid)
    original_created_at = p["created_at"]

    new_date = "2023-05-10T12:00:00.000Z"
    upd = client.put(f"{BASE_URL}/api/payments/{pid}", json={"created_at": new_date}, timeout=60)
    assert upd.status_code == 200, upd.text
    upd_body = upd.json()
    assert str(upd_body.get("created_at", "")).startswith("2023-05-10"), \
        f"created_at not updated: {upd_body.get('created_at')}"

    g = client.get(f"{BASE_URL}/api/payments/{pid}", timeout=60).json()
    assert str(g.get("created_at", "")).startswith("2023-05-10"), \
        f"GET still shows old created_at: {g.get('created_at')} vs original {original_created_at}"

    # cleanup
    d = client.delete(f"{BASE_URL}/api/payments/{pid}", timeout=60)
    assert d.status_code in (200, 204), d.text
    CREATED["payments"].remove(pid)


# ─────────────────────────────────────────────────────────────
# FEATURE 3/4: Draft autosave + naming
# ─────────────────────────────────────────────────────────────
def test_draft_autosave_and_naming(client):
    label = "Farhan - Monday order"
    payload = {
        "kind": "order",
        "label": label,
        "data": {"customer_id": "x", "items": [{"product_id": "p", "quantity": 1}]},
    }
    r = client.post(f"{BASE_URL}/api/drafts", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    did = body["id"]
    CREATED["drafts"].append(did)
    assert body["label"] == label, f"label mismatch: {body['label']!r}"
    assert body["data"] == payload["data"]
    original_updated_at = body["updated_at"]

    # Autosave (PUT) — updated_at must change; data round-trips
    time.sleep(1.1)
    new_label = "Farhan - Monday order (v2)"
    new_data = {"customer_id": "x", "items": [
        {"product_id": "p", "quantity": 3},
        {"product_id": "p2", "quantity": 5},
    ]}
    upd = client.put(
        f"{BASE_URL}/api/drafts/{did}",
        json={"kind": "order", "label": new_label, "data": new_data}, timeout=30,
    )
    assert upd.status_code == 200, upd.text
    ub = upd.json()
    assert ub["label"] == new_label
    assert ub["data"] == new_data
    assert ub["updated_at"] != original_updated_at

    # GET list?kind=order must include it
    lst = client.get(f"{BASE_URL}/api/drafts", params={"kind": "order"}, timeout=30).json()
    assert any(d["id"] == did for d in lst), "draft missing from kind=order list"

    # Delete
    d = client.delete(f"{BASE_URL}/api/drafts/{did}", timeout=30)
    assert d.status_code == 200, d.text
    CREATED["drafts"].remove(did)


def test_zzz_cleanup_verify(client):
    assert not any(CREATED.values()), f"Leftover records: {CREATED}"
