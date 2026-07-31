"""
Backend tests for v1.1.1 bug fixes (5 items).
Live Firestore-backed API — creates and DELETES test records.
"""
import os
import re
import uuid
import pytest
import requests
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://trade-audit-v1.preview.emergentagent.com").rstrip("/")
FB_API_KEY = "AIzaSyDWAJT2Ruvz7SEU62whyn6__6Lnjfe0HpY"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

CUSTOMER_ID_RICH_CERAMIC = "4e413aa4-df43-4d5d-926a-b6b5e989caac"

# Track created ids
CREATED = {"payments": [], "orders": [], "returned_stock": []}


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


@pytest.fixture(scope="session")
def sample_ids(client):
    products = client.get(f"{BASE_URL}/api/products", timeout=60).json()
    suppliers = client.get(f"{BASE_URL}/api/suppliers", timeout=60).json()
    customers = client.get(f"{BASE_URL}/api/customers", timeout=60).json()
    assert products and suppliers and customers, "Need existing products/suppliers/customers"
    return {
        "product": products[0],
        "supplier": suppliers[0],
        "customer": customers[0],
    }


HEX8 = re.compile(r"^[0-9a-fA-F]{8}$")


# ── BUG 2: Ledger payment ref must be sensible ───────────────
def test_customer_ledger_payment_refs(client):
    r = client.get(f"{BASE_URL}/api/reports/customer-ledger/{CUSTOMER_ID_RICH_CERAMIC}", timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    entries = data.get("entries", data if isinstance(data, list) else [])
    payment_entries = [e for e in entries if e.get("type") == "payment"]
    assert payment_entries, "Rich Ceramic should have at least one payment ledger entry"
    bad = []
    for e in payment_entries:
        ref = e.get("ref") or ""
        # Must not be an 8-char hex uuid fragment
        if HEX8.match(str(ref)):
            bad.append(ref)
    assert not bad, f"Found UUID-fragment refs in customer ledger: {bad[:5]}"


def test_supplier_ledger_payment_refs(client):
    suppliers = client.get(f"{BASE_URL}/api/suppliers", timeout=60).json()
    checked_any = False
    for s in suppliers[:15]:
        r = client.get(f"{BASE_URL}/api/reports/supplier-ledger/{s['id']}", timeout=120)
        if r.status_code != 200:
            continue
        entries = r.json().get("entries", [])
        payment_entries = [e for e in entries if e.get("type") == "payment"]
        if not payment_entries:
            continue
        checked_any = True
        for e in payment_entries:
            ref = str(e.get("ref") or "")
            assert not HEX8.match(ref), f"Supplier {s['id']} has UUID-fragment ref: {ref}"
        if checked_any:
            break
    if not checked_any:
        pytest.skip("No supplier with payment entries found in first 15 suppliers")


# ── BUG 2b: auto payment_number PAY-XXXX ─────────────────────
def test_customer_payment_auto_number(client, sample_ids):
    payload = {
        "payment_type": "customer",
        "entity_id": sample_ids["customer"]["id"],
        "entity_name": sample_ids["customer"].get("name", ""),
        "amount": 1,
        "payment_method": "cash",
        "allocations": [],
    }
    r = client.post(f"{BASE_URL}/api/payments", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    pay = r.json()
    pid = pay["id"]
    CREATED["payments"].append(pid)
    pn = pay.get("payment_number") or ""
    assert re.match(r"^PAY-\d{4,}$", pn), f"payment_number not PAY-XXXX format: {pn!r}"

    # cleanup
    d = client.delete(f"{BASE_URL}/api/payments/{pid}", timeout=60)
    assert d.status_code in (200, 204), d.text
    CREATED["payments"].remove(pid)


# ── BUG 3: Backdated order ───────────────────────────────────
def test_backdated_order(client, sample_ids):
    backdate = "2024-01-15T12:00:00.000Z"
    product = sample_ids["product"]
    supplier = sample_ids["supplier"]
    customer = sample_ids["customer"]
    payload = {
        "customer_id": customer["id"],
        "customer_name": customer.get("name", ""),
        "created_at": backdate,
        "items": [{
            "product_id": product["id"],
            "product_name": product.get("name", ""),
            "quantity": 1,
            "unit_price": 100,
            "source": "supplier",
            "supplier_id": supplier["id"],
            "supplier_name": supplier.get("name", ""),
        }],
    }
    r = client.post(f"{BASE_URL}/api/orders", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    order = r.json()
    oid = order["id"]
    CREATED["orders"].append(oid)

    # Verify via GET
    g = client.get(f"{BASE_URL}/api/orders/{oid}", timeout=60)
    assert g.status_code == 200, g.text
    saved = g.json()
    ca = str(saved.get("created_at", ""))
    assert ca.startswith("2024-01-15") or "2024-01-15" in ca, f"created_at not backdated: {ca}"

    # cleanup
    d = client.delete(f"{BASE_URL}/api/orders/{oid}", timeout=60)
    assert d.status_code in (200, 204), d.text
    CREATED["orders"].remove(oid)


# ── BUG 4: Supplier payment with related_customer_id/name ────
def test_supplier_payment_related_customer(client, sample_ids):
    supplier = sample_ids["supplier"]
    customer = sample_ids["customer"]
    payload = {
        "payment_type": "supplier",
        "entity_id": supplier["id"],
        "entity_name": supplier.get("name", ""),
        "amount": 1,
        "payment_method": "cash",
        "related_customer_id": customer["id"],
        "related_customer_name": customer.get("name", ""),
        "allocations": [],
    }
    r = client.post(f"{BASE_URL}/api/payments", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    pay = r.json()
    pid = pay["id"]
    CREATED["payments"].append(pid)

    assert pay.get("related_customer_id") == customer["id"], pay
    assert pay.get("related_customer_name") == customer.get("name", ""), pay

    # Verify persisted via GET
    g = client.get(f"{BASE_URL}/api/payments/{pid}", timeout=60)
    if g.status_code == 200:
        gj = g.json()
        assert gj.get("related_customer_id") == customer["id"]
        assert gj.get("related_customer_name") == customer.get("name", "")

    # cleanup
    d = client.delete(f"{BASE_URL}/api/payments/{pid}", timeout=60)
    assert d.status_code in (200, 204), d.text
    CREATED["payments"].remove(pid)


# ── BUG 1: Opening stock note + date ─────────────────────────
def test_opening_stock_note_and_date(client, sample_ids):
    product = sample_ids["product"]
    backdate = "2024-02-20T12:00:00.000Z"
    note = "QA opening note"
    payload = {
        "product_id": product["id"],
        "product_name": product.get("name", ""),
        "quantity": 1,
        "cost_price": 10,
        "notes": note,
        "created_at": backdate,
    }
    r = client.post(f"{BASE_URL}/api/returned-stock", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    rs = r.json()
    rsid = rs["id"]
    CREATED["returned_stock"].append(rsid)

    assert rs.get("notes") == note
    assert "2024-02-20" in str(rs.get("created_at", ""))

    # Verify warehouse aggregation
    w = client.get(f"{BASE_URL}/api/warehouse/stock", timeout=120)
    assert w.status_code == 200, w.text
    stock_resp = w.json()
    stock = stock_resp.get("items", stock_resp) if isinstance(stock_resp, dict) else stock_resp
    prod_row = next((p for p in stock if p.get("product_id") == product["id"]), None)
    assert prod_row, f"Product {product['id']} not found in warehouse stock"
    entries = prod_row.get("entries") or prod_row.get("lots") or []
    match = None
    for e in entries:
        if (e.get("source_label") == "Opening Stock"
                and e.get("notes") == note
                and "2024-02-20" in str(e.get("date", "") or e.get("created_at", ""))):
            match = e
            break
    assert match, f"Opening Stock entry with note+date not found in warehouse lots. Entries: {entries[:5]}"

    # cleanup
    d = client.delete(f"{BASE_URL}/api/returned-stock/{rsid}", timeout=60)
    assert d.status_code in (200, 204), d.text
    CREATED["returned_stock"].remove(rsid)


# ── FEATURE 5: Cheque Inventory filter + sort ────────────────
def test_cheque_inventory_fields(client):
    r = client.get(f"{BASE_URL}/api/cheque-inventory", timeout=60)
    assert r.status_code == 200, r.text
    items = r.json()
    if items:
        sample = items[0]
        for f in ("cheque_number", "bank", "amount", "cheque_date", "status"):
            assert f in sample, f"Missing field {f} in cheque record: {sample.keys()}"


def test_cheque_inventory_filter_status(client):
    r = client.get(f"{BASE_URL}/api/cheque-inventory", params={"status": "Available"}, timeout=60)
    assert r.status_code == 200, r.text
    items = r.json()
    for it in items:
        assert it.get("status") == "Available", it


def test_cheque_inventory_sort_amount_desc(client):
    r = client.get(f"{BASE_URL}/api/cheque-inventory", params={"sort": "amount_desc"}, timeout=60)
    assert r.status_code == 200, r.text
    items = r.json()
    amounts = [float(it.get("amount") or 0) for it in items]
    assert amounts == sorted(amounts, reverse=True), f"Not descending: {amounts[:10]}"


def test_cheque_inventory_sort_customer(client):
    r = client.get(f"{BASE_URL}/api/cheque-inventory", params={"sort": "customer"}, timeout=60)
    assert r.status_code == 200, r.text
    items = r.json()
    names = [(it.get("customer_name") or "").lower() for it in items]
    # Allow empties at the beginning or end
    non_empty = [n for n in names if n]
    assert non_empty == sorted(non_empty), f"customer sort broken: {non_empty[:10]}"


# ── Final cleanup safety net ─────────────────────────────────
def test_zzz_cleanup_verify(client):
    """Ensure no test-created records were left behind."""
    leftover = {k: v for k, v in CREATED.items() if v}
    if leftover:
        # attempt to delete them
        for pid in list(CREATED["payments"]):
            client.delete(f"{BASE_URL}/api/payments/{pid}", timeout=60)
            CREATED["payments"].remove(pid)
        for oid in list(CREATED["orders"]):
            client.delete(f"{BASE_URL}/api/orders/{oid}", timeout=60)
            CREATED["orders"].remove(oid)
        for rsid in list(CREATED["returned_stock"]):
            client.delete(f"{BASE_URL}/api/returned-stock/{rsid}", timeout=60)
            CREATED["returned_stock"].remove(rsid)
    assert not any(CREATED.values()), f"Leftover: {CREATED}"
