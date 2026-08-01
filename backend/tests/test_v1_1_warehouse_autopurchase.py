"""
Backend tests for v1.1 warehouse/auto-purchase separation.

BUG:  auto-purchase created from a Migration invoice must NOT increase warehouse stock.
LATENT: force-editing that auto-purchase to destination=warehouse must STILL not sync stock.
REGRESSION: manual purchase (destination=warehouse) should still increase stock.
REGRESSION: manual purchase (destination=direct_customer) should NOT increase stock.

Runs against LIVE Firestore. All created records are DELETED.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://trade-audit-v1.preview.emergentagent.com"
).rstrip("/")
FB_API_KEY = "AIzaSyDWAJT2Ruvz7SEU62whyn6__6Lnjfe0HpY"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

CREATED = {"invoices": [], "purchases": []}


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
    for iid in list(CREATED["invoices"]):
        try:
            client.delete(f"{BASE_URL}/api/invoices/{iid}", timeout=30)
        except Exception:
            pass
    for pid in list(CREATED["purchases"]):
        try:
            client.delete(f"{BASE_URL}/api/purchases/{pid}", timeout=30)
        except Exception:
            pass


# ── helpers ────────────────────────────────────────────────────────────
def _stock_snapshot(client):
    r = client.get(f"{BASE_URL}/api/warehouse/stock", timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    per_prod = {}
    for row in d.get("items", d.get("products", []) or []):
        pid = row.get("product_id") or row.get("id")
        if pid:
            per_prod[pid] = {
                "on_hand": float(row.get("on_hand", 0) or 0),
                "value": float(row.get("total_value", 0) or 0),
            }
    return {
        "grand_total_value": float(d.get("grand_total_value", d.get("total_value", 0)) or 0),
        "total_units": float(d.get("total_units", d.get("grand_total_units", 0)) or 0),
        "per_product": per_prod,
        "raw": d,
    }


@pytest.fixture(scope="session")
def refs(client):
    customers = client.get(f"{BASE_URL}/api/customers", timeout=60).json()
    suppliers = client.get(f"{BASE_URL}/api/suppliers", timeout=60).json()
    products = client.get(f"{BASE_URL}/api/products", timeout=60).json()
    assert customers and suppliers and len(products) >= 2, "Need customer/supplier/2 products"
    return {
        "customer": customers[0],
        "supplier": suppliers[0],
        "P": products[0],
        "P2": products[1],
    }


# ─────────────────────────────────────────────────────────────
# PRIMARY BUG — auto-purchase from historical invoice must NOT
# increase warehouse stock.
# ─────────────────────────────────────────────────────────────
def test_historical_invoice_autopurchase_does_not_increase_warehouse(client, refs):
    cust = refs["customer"]
    sup = refs["supplier"]
    P = refs["P"]

    baseline = _stock_snapshot(client)
    base_p = baseline["per_product"].get(P["id"], {"on_hand": 0.0, "value": 0.0})

    payload = {
        "customer_id": cust["id"],
        "customer_name": cust.get("name", ""),
        "supplier_id": sup["id"],
        "supplier_name": sup.get("name", ""),
        "supplier_invoice_number": f"QA-DIRECT-{int(time.time())}",
        "items": [{
            "product_id": P["id"],
            "product_name": P.get("name", ""),
            "quantity": 5,
            "unit_price": 100,
            "cost_price": 60,
            "source": "supplier",
        }],
    }
    r = client.post(f"{BASE_URL}/api/invoices", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    inv = r.json()
    invoice_id = inv["id"]
    CREATED["invoices"].append(invoice_id)

    linked_pid = inv.get("linked_purchase_id")
    if not linked_pid:
        # fetch invoice to read link
        detail = client.get(f"{BASE_URL}/api/invoices/{invoice_id}", timeout=30).json()
        linked_pid = detail.get("linked_purchase_id")
    assert linked_pid, f"Invoice did not create a linked_purchase_id: {inv}"
    CREATED["purchases"].append(linked_pid)

    # auto-purchase must be direct_customer + auto_generated
    pr = client.get(f"{BASE_URL}/api/purchases/{linked_pid}", timeout=30)
    assert pr.status_code == 200, pr.text
    pdoc = pr.json()
    assert pdoc.get("destination") == "direct_customer", f"destination={pdoc.get('destination')}"
    assert pdoc.get("auto_generated") is True, f"auto_generated={pdoc.get('auto_generated')}"
    assert pdoc.get("linked_invoice_id") == invoice_id

    # warehouse must be unchanged for product P (live DB — check per-product only)
    after = _stock_snapshot(client)
    after_p = after["per_product"].get(P["id"], {"on_hand": 0.0, "value": 0.0})
    assert abs(after_p["on_hand"] - base_p["on_hand"]) < 0.02, (
        f"P on_hand changed after historical invoice: {base_p['on_hand']} → {after_p['on_hand']}"
    )
    assert abs(after_p["value"] - base_p["value"]) < 0.02, (
        f"P value changed after historical invoice: {base_p['value']} → {after_p['value']}"
    )

    # cleanup and re-verify
    d1 = client.delete(f"{BASE_URL}/api/invoices/{invoice_id}", timeout=30)
    assert d1.status_code in (200, 204), d1.text
    CREATED["invoices"].remove(invoice_id)
    d2 = client.delete(f"{BASE_URL}/api/purchases/{linked_pid}", timeout=30)
    assert d2.status_code in (200, 204, 404), d2.text
    if linked_pid in CREATED["purchases"]:
        CREATED["purchases"].remove(linked_pid)

    final = _stock_snapshot(client)
    final_p = final["per_product"].get(P["id"], {"on_hand": 0.0, "value": 0.0})
    assert abs(final_p["on_hand"] - base_p["on_hand"]) < 0.02
    assert abs(final_p["value"] - base_p["value"]) < 0.02


# ─────────────────────────────────────────────────────────────
# LATENT BUG — editing an auto-generated purchase to
# destination=warehouse must STILL NOT sync warehouse stock.
# ─────────────────────────────────────────────────────────────
def test_edit_autopurchase_to_warehouse_does_not_sync(client, refs):
    cust = refs["customer"]
    sup = refs["supplier"]
    P = refs["P"]

    baseline = _stock_snapshot(client)
    base_p = baseline["per_product"].get(P["id"], {"on_hand": 0.0, "value": 0.0})

    payload = {
        "customer_id": cust["id"],
        "customer_name": cust.get("name", ""),
        "supplier_id": sup["id"],
        "supplier_name": sup.get("name", ""),
        "supplier_invoice_number": f"QA-LATENT-{int(time.time())}",
        "items": [{
            "product_id": P["id"],
            "product_name": P.get("name", ""),
            "quantity": 4,
            "unit_price": 100,
            "cost_price": 60,
            "source": "supplier",
        }],
    }
    r = client.post(f"{BASE_URL}/api/invoices", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    inv = r.json()
    invoice_id = inv["id"]
    CREATED["invoices"].append(invoice_id)
    linked_pid = inv.get("linked_purchase_id") or client.get(
        f"{BASE_URL}/api/invoices/{invoice_id}", timeout=30
    ).json().get("linked_purchase_id")
    assert linked_pid
    CREATED["purchases"].append(linked_pid)

    # Force destination=warehouse on the AUTO purchase
    up = client.put(
        f"{BASE_URL}/api/purchases/{linked_pid}",
        json={"destination": "warehouse"},
        timeout=30,
    )
    assert up.status_code == 200, up.text
    assert up.json().get("destination") == "warehouse"

    after = _stock_snapshot(client)
    after_p = after["per_product"].get(P["id"], {"on_hand": 0.0, "value": 0.0})
    assert abs(after_p["on_hand"] - base_p["on_hand"]) < 0.02, (
        f"LATENT BUG: P on_hand changed: {base_p['on_hand']} → {after_p['on_hand']}"
    )
    assert abs(after_p["value"] - base_p["value"]) < 0.02, (
        f"LATENT BUG: P value changed after force-edit to warehouse: "
        f"{base_p['value']} → {after_p['value']}"
    )

    # cleanup
    client.delete(f"{BASE_URL}/api/invoices/{invoice_id}", timeout=30)
    CREATED["invoices"].remove(invoice_id)
    client.delete(f"{BASE_URL}/api/purchases/{linked_pid}", timeout=30)
    if linked_pid in CREATED["purchases"]:
        CREATED["purchases"].remove(linked_pid)


# ─────────────────────────────────────────────────────────────
# REGRESSION — direct manual purchase (destination=warehouse)
# SHOULD increase warehouse.
# ─────────────────────────────────────────────────────────────
def test_manual_purchase_warehouse_increases_stock(client, refs):
    sup = refs["supplier"]
    P2 = refs["P2"]

    baseline = _stock_snapshot(client)
    base_p2 = baseline["per_product"].get(P2["id"], {"on_hand": 0.0, "value": 0.0})

    payload = {
        "supplier_id": sup["id"],
        "supplier_name": sup.get("name", ""),
        "supplier_invoice_number": f"QA-WH-{int(time.time())}",
        "destination": "warehouse",
        "items": [{
            "product_id": P2["id"],
            "product_name": P2.get("name", ""),
            "quantity": 3,
            "cost_price": 50,
        }],
    }
    r = client.post(f"{BASE_URL}/api/purchases", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    CREATED["purchases"].append(pid)

    after = _stock_snapshot(client)
    after_p2 = after["per_product"].get(P2["id"], {"on_hand": 0.0, "value": 0.0})
    delta_units = after_p2["on_hand"] - base_p2["on_hand"]
    delta_p2_value = after_p2["value"] - base_p2["value"]
    assert abs(delta_units - 3) < 0.05, f"P2 on_hand should +3, got Δ={delta_units}"
    assert abs(delta_p2_value - 150) < 0.05, f"P2 value should +150, got Δ={delta_p2_value}"

    # cleanup
    d = client.delete(f"{BASE_URL}/api/purchases/{pid}", timeout=30)
    assert d.status_code in (200, 204), d.text
    CREATED["purchases"].remove(pid)

    final = _stock_snapshot(client)
    final_p2 = final["per_product"].get(P2["id"], {"on_hand": 0.0, "value": 0.0})
    assert abs(final_p2["on_hand"] - base_p2["on_hand"]) < 0.05, (
        f"After delete, P2 on_hand not restored: {base_p2['on_hand']} → {final_p2['on_hand']}"
    )
    assert abs(final_p2["value"] - base_p2["value"]) < 0.05


# ─────────────────────────────────────────────────────────────
# REGRESSION — manual purchase destination=direct_customer must
# NOT increase warehouse.
# ─────────────────────────────────────────────────────────────
def test_manual_purchase_direct_customer_no_stock(client, refs):
    sup = refs["supplier"]
    P2 = refs["P2"]

    baseline = _stock_snapshot(client)
    base_p2 = baseline["per_product"].get(P2["id"], {"on_hand": 0.0, "value": 0.0})

    payload = {
        "supplier_id": sup["id"],
        "supplier_name": sup.get("name", ""),
        "supplier_invoice_number": f"QA-DC-{int(time.time())}",
        "destination": "direct_customer",
        "items": [{
            "product_id": P2["id"],
            "product_name": P2.get("name", ""),
            "quantity": 2,
            "cost_price": 50,
        }],
    }
    r = client.post(f"{BASE_URL}/api/purchases", json=payload, timeout=60)
    assert r.status_code == 200, r.text
    pid = r.json()["id"]
    CREATED["purchases"].append(pid)

    after = _stock_snapshot(client)
    after_p2 = after["per_product"].get(P2["id"], {"on_hand": 0.0, "value": 0.0})
    assert abs(after_p2["on_hand"] - base_p2["on_hand"]) < 0.05, (
        f"direct_customer must not touch warehouse: {base_p2['on_hand']} → {after_p2['on_hand']}"
    )
    assert abs(after["grand_total_value"] - baseline["grand_total_value"]) < 0.05

    d = client.delete(f"{BASE_URL}/api/purchases/{pid}", timeout=30)
    assert d.status_code in (200, 204), d.text
    CREATED["purchases"].remove(pid)


def test_zzz_cleanup_verify():
    assert not any(CREATED.values()), f"Leftover records: {CREATED}"
