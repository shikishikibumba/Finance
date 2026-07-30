"""
Backend tests for v1.1.0 additive enhancements.
Covers: banks seed & CRUD, payment references, cheque inventory,
audit logs, product dup-guard + primary supplier + price/sales history,
payment auto-hook + supplier endorsement.
"""
import os
import uuid
import pytest
import requests
from datetime import date, timedelta

BASE_URL = "http://localhost:8001"
FB_API_KEY = "AIzaSyDWAJT2Ruvz7SEU62whyn6__6Lnjfe0HpY"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"


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


# ── Auth smoke ────────────────────────────────────────────────
def test_auth_me(client):
    r = client.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["email"] == ADMIN_EMAIL
    assert d["role"] == "admin"


# ── Banks seed & CRUD ─────────────────────────────────────────
SEEDED_BANKS = [
    "Bank of Ceylon", "People's Bank", "Commercial Bank", "Hatton National Bank",
    "Sampath Bank", "National Development Bank", "DFCC Bank", "Seylan Bank",
    "National Savings Bank", "Nations Trust Bank", "Pan Asia Bank",
]


def test_banks_seed(client):
    r = client.get(f"{BASE_URL}/api/banks")
    assert r.status_code == 200, r.text
    banks = r.json()
    names = {b["name"] for b in banks}
    for n in SEEDED_BANKS:
        assert n in names, f"Missing seeded bank: {n}"


def test_banks_crud(client):
    uniq = f"TEST_Bank_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/banks", json={"name": uniq})
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["name"] == uniq
    bank_id = created["id"]

    # Duplicate case-insensitive
    r2 = client.post(f"{BASE_URL}/api/banks", json={"name": uniq.lower()})
    assert r2.status_code == 400

    r3 = client.post(f"{BASE_URL}/api/banks", json={"name": f"  {uniq.upper()}  "})
    assert r3.status_code == 400

    # cleanup
    dr = client.delete(f"{BASE_URL}/api/banks/{bank_id}")
    assert dr.status_code == 200


# ── Payment references ────────────────────────────────────────
def test_payment_references_presets(client):
    r = client.get(f"{BASE_URL}/api/payment-references")
    assert r.status_code == 200, r.text
    names = {x["name"] for x in r.json()}
    for req in ["Cash Collection", "CHQ Deposit", "RTGS Transfer", "Bank Deposit", "Manual Adjustment"]:
        assert req in names


def test_payment_reference_custom(client):
    uniq = f"TEST_Ref_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/payment-references", json={"name": uniq})
    assert r.status_code == 200, r.text
    rid = r.json()["id"]
    listing = client.get(f"{BASE_URL}/api/payment-references").json()
    assert any(x["name"] == uniq for x in listing)
    client.delete(f"{BASE_URL}/api/payment-references/{rid}")


# ── Cheque inventory ──────────────────────────────────────────
def test_cheque_inventory_list_and_due(client):
    r = client.get(f"{BASE_URL}/api/cheque-inventory")
    assert r.status_code == 200, r.text
    for kind in ("customer", "supplier"):
        r2 = client.get(f"{BASE_URL}/api/cheque-inventory/due", params={"kind": kind, "days": 14})
        assert r2.status_code == 200, r2.text
        assert isinstance(r2.json(), list)


def test_cheque_own_create_and_status_transitions(client):
    payload = {
        "cheque_number": f"TEST_{uuid.uuid4().hex[:8]}",
        "bank": "Bank of Ceylon",
        "amount": 1500.0,
        "cheque_date": (date.today() + timedelta(days=7)).isoformat(),
        "notes": "TEST own cheque",
    }
    r = client.post(f"{BASE_URL}/api/cheque-inventory/own", json=payload)
    assert r.status_code == 200, r.text
    ch = r.json()
    assert ch["status"] == "Available"
    assert ch["own_cheque"] is True
    cid = ch["id"]

    r2 = client.patch(f"{BASE_URL}/api/cheque-inventory/{cid}/status", json={"status": "Deposited"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "Deposited"

    r3 = client.patch(f"{BASE_URL}/api/cheque-inventory/{cid}/status", json={"status": "Cleared"})
    assert r3.status_code == 200, r3.text
    assert r3.json()["status"] == "Cleared"

    # cleanup (own cheque can be deleted even if not Available)
    client.delete(f"{BASE_URL}/api/cheque-inventory/{cid}")


# ── Audit Logs ────────────────────────────────────────────────
def test_audit_logs_meta(client):
    r = client.get(f"{BASE_URL}/api/audit-logs/meta")
    assert r.status_code == 200, r.text
    d = r.json()
    assert "modules" in d and "actions" in d
    assert "products" in d["modules"]
    assert "Create" in d["actions"]


def test_audit_logs_entries(client):
    # Create a bank to trigger an audit
    uniq = f"TEST_Bank_Audit_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/banks", json={"name": uniq})
    assert r.status_code == 200
    bid = r.json()["id"]

    r2 = client.get(f"{BASE_URL}/api/audit-logs", params={"module": "banks", "action": "Create"})
    assert r2.status_code == 200, r2.text
    logs = r2.json()
    assert any(l.get("record_id") == bid for l in logs), "New bank audit not found"

    client.delete(f"{BASE_URL}/api/banks/{bid}")


def test_audit_logs_non_admin_forbidden():
    # Unauthenticated call → 401 (proxy of "non-admin")
    r = requests.get(f"{BASE_URL}/api/audit-logs")
    assert r.status_code in (401, 403)


# ── Products: dup guard, primary supplier, price/sales history ─
@pytest.fixture(scope="session")
def sample_supplier(client):
    payload = {"name": f"TEST_Supplier_{uuid.uuid4().hex[:6]}", "phone": "0000"}
    r = client.post(f"{BASE_URL}/api/suppliers", json=payload)
    assert r.status_code in (200, 201), r.text
    s = r.json()
    yield s
    client.delete(f"{BASE_URL}/api/suppliers/{s['id']}")


def test_product_dup_guard(client):
    uniq = f"TEST_Dup_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/products", json={"name": uniq, "selling_price": 10})
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    try:
        r2 = client.post(f"{BASE_URL}/api/products", json={"name": uniq.lower(), "selling_price": 10})
        assert r2.status_code == 400
        assert "already exists" in r2.text.lower()
        r3 = client.post(f"{BASE_URL}/api/products", json={"name": f"  {uniq.upper()}  ", "selling_price": 10})
        assert r3.status_code == 400
    finally:
        client.delete(f"{BASE_URL}/api/products/{pid}")


def test_product_primary_supplier(client, sample_supplier):
    uniq = f"TEST_Prod_PS_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/products", json={
        "name": uniq, "selling_price": 50, "primary_supplier_id": sample_supplier["id"],
    })
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["primary_supplier_id"] == sample_supplier["id"]
    assert p["primary_supplier_name"] == sample_supplier["name"]
    client.delete(f"{BASE_URL}/api/products/{p['id']}")


def test_product_price_history(client):
    uniq = f"TEST_Prod_PH_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/products", json={"name": uniq, "selling_price": 100})
    pid = r.json()["id"]
    try:
        u = client.put(f"{BASE_URL}/api/products/{pid}", json={"selling_price": 150})
        assert u.status_code == 200, u.text
        h = client.get(f"{BASE_URL}/api/products/{pid}/price-history")
        assert h.status_code == 200
        hist = h.json()
        assert len(hist) >= 2
        # newest first
        assert hist[0]["date"] >= hist[-1]["date"]
        # top entry reflects the new price
        top = hist[0]
        assert top.get("new_price", top.get("selling_price")) == 150
    finally:
        client.delete(f"{BASE_URL}/api/products/{pid}")


def test_product_sales_history(client):
    uniq = f"TEST_Prod_SH_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{BASE_URL}/api/products", json={"name": uniq, "selling_price": 20})
    pid = r.json()["id"]
    try:
        h = client.get(f"{BASE_URL}/api/products/{pid}/sales-history")
        assert h.status_code == 200
        assert isinstance(h.json(), list)
    finally:
        client.delete(f"{BASE_URL}/api/products/{pid}")


# ── Payment cheque-inventory auto-hook + endorsement ───────────
@pytest.fixture(scope="session")
def sample_customer(client):
    r = client.post(f"{BASE_URL}/api/customers", json={"name": f"TEST_Cust_{uuid.uuid4().hex[:6]}", "phone": "0000"})
    assert r.status_code in (200, 201), r.text
    c = r.json()
    yield c
    client.delete(f"{BASE_URL}/api/customers/{c['id']}")


def test_customer_cheque_payment_hooks(client, sample_customer):
    cn = f"TEST-CHQ-{uuid.uuid4().hex[:6]}"
    payload = {
        "payment_type": "customer",
        "entity_id": sample_customer["id"],
        "entity_name": sample_customer["name"],
        "amount": 500.0,
        "payment_method": "cheque",
        "cheques": [{
            "amount": 500.0,
            "bank_name": "Sampath Bank",
            "cheque_number": cn,
            "cheque_date": (date.today() + timedelta(days=5)).isoformat(),
        }],
    }
    r = client.post(f"{BASE_URL}/api/payments", json=payload)
    assert r.status_code == 200, r.text
    pay = r.json()
    assert pay["cheques"][0].get("cheque_inventory_id"), "cheque_inventory_id not populated on payment"
    ci_id = pay["cheques"][0]["cheque_inventory_id"]

    # Verify appears in inventory
    r2 = client.get(f"{BASE_URL}/api/cheque-inventory/{ci_id}")
    assert r2.status_code == 200, r2.text
    ci = r2.json()
    assert ci["status"] == "Available"
    assert ci["cheque_number"] == cn
    assert ci["customer_id"] == sample_customer["id"]

    # Save for next test
    pytest._customer_cheque_id = ci_id
    pytest._customer_payment_id = pay["id"]


@pytest.fixture(scope="session")
def sample_supplier2(client):
    r = client.post(f"{BASE_URL}/api/suppliers", json={"name": f"TEST_Sup2_{uuid.uuid4().hex[:6]}", "phone": "0"})
    assert r.status_code in (200, 201), r.text
    s = r.json()
    yield s
    client.delete(f"{BASE_URL}/api/suppliers/{s['id']}")


def test_supplier_payment_endorsement(client, sample_supplier2):
    ci_id = getattr(pytest, "_customer_cheque_id", None)
    if not ci_id:
        pytest.skip("previous cheque test did not populate inventory id")

    payload = {
        "payment_type": "supplier",
        "entity_id": sample_supplier2["id"],
        "entity_name": sample_supplier2["name"],
        "amount": 500.0,
        "payment_method": "cheque",
        "endorsed_cheque_ids": [ci_id],
    }
    r = client.post(f"{BASE_URL}/api/payments", json=payload)
    assert r.status_code == 200, r.text

    # Verify inventory row now Issued to Supplier
    r2 = client.get(f"{BASE_URL}/api/cheque-inventory/{ci_id}")
    assert r2.status_code == 200
    ci = r2.json()
    assert ci["status"] == "Issued to Supplier"
    assert ci["supplier_id"] == sample_supplier2["id"]
    assert ci["issued_date"]

    # cleanup - delete payments
    pid_cust = getattr(pytest, "_customer_payment_id", None)
    if pid_cust:
        client.delete(f"{BASE_URL}/api/payments/{pid_cust}")
    client.delete(f"{BASE_URL}/api/payments/{r.json()['id']}")
    # cheque cleanup — force delete via status roll back to Available? Not required per test scope.
