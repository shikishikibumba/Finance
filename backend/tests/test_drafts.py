"""
Backend tests for v1.1 Drafts feature.
Live Firestore-backed API — creates and DELETES test records.
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

CREATED_DRAFT_IDS: list[str] = []


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
def cleanup(client):
    yield
    # Best-effort cleanup of any drafts left behind
    for did in list(CREATED_DRAFT_IDS):
        try:
            client.delete(f"{BASE_URL}/api/drafts/{did}", timeout=30)
        except Exception:
            pass


# ── Order-kind draft: create + round-trip data ───────────────
def test_create_order_draft_roundtrip(client):
    payload = {
        "kind": "order",
        "label": "QA draft",
        "data": {
            "customer_id": "x",
            "customer_name": "QA",
            "items": [
                {"product_id": "p", "product_name": "P", "quantity": 2, "unit_price": 100}
            ],
            "notes": "wip",
        },
    }
    r = client.post(f"{BASE_URL}/api/drafts", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    body = r.json()
    assert body.get("id"), f"missing id: {body}"
    CREATED_DRAFT_IDS.append(body["id"])

    assert body["kind"] == "order"
    assert body["label"] == "QA draft"
    assert body["data"] == payload["data"], f"data did not round-trip: {body['data']}"
    assert body.get("created_at")
    assert body.get("updated_at")
    assert "_id" not in body


# ── List filter by kind ─────────────────────────────────────
def test_list_filter_by_kind(client):
    # There must be at least one order draft created above
    assert CREATED_DRAFT_IDS, "prerequisite create test must run first"
    order_id = CREATED_DRAFT_IDS[0]

    r_order = client.get(f"{BASE_URL}/api/drafts?kind=order", timeout=30)
    assert r_order.status_code == 200, r_order.text
    orders = r_order.json()
    assert isinstance(orders, list)
    ids_o = [d.get("id") for d in orders]
    assert order_id in ids_o, f"created order draft missing from kind=order list"
    assert all(d.get("kind") == "order" for d in orders), "kind=order filter returned wrong kinds"

    r_hist = client.get(f"{BASE_URL}/api/drafts?kind=historical_invoice", timeout=30)
    assert r_hist.status_code == 200, r_hist.text
    hist = r_hist.json()
    ids_h = [d.get("id") for d in hist]
    assert order_id not in ids_h, "order draft leaked into historical_invoice filter"


# ── Update draft ────────────────────────────────────────────
def test_update_draft(client):
    assert CREATED_DRAFT_IDS
    did = CREATED_DRAFT_IDS[0]

    # fetch current updated_at
    lst = client.get(f"{BASE_URL}/api/drafts?kind=order", timeout=30).json()
    original = next(d for d in lst if d["id"] == did)
    original_updated_at = original["updated_at"]

    time.sleep(1.1)  # ensure timestamp changes

    new_data = {
        "customer_id": "x",
        "customer_name": "QA",
        "items": [
            {"product_id": "p", "product_name": "P", "quantity": 2, "unit_price": 100},
            {"product_id": "p2", "product_name": "P2", "quantity": 5, "unit_price": 50},
        ],
        "notes": "updated wip",
    }
    r = client.put(
        f"{BASE_URL}/api/drafts/{did}",
        json={"kind": "order", "label": "QA draft v2", "data": new_data},
        timeout=30,
    )
    assert r.status_code == 200, f"update failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["label"] == "QA draft v2"
    assert body["data"] == new_data, f"updated data mismatch: {body['data']}"
    assert body["updated_at"] != original_updated_at, "updated_at not changed"

    # Re-fetch via list to confirm persistence
    lst2 = client.get(f"{BASE_URL}/api/drafts?kind=order", timeout=30).json()
    fetched = next(d for d in lst2 if d["id"] == did)
    assert fetched["label"] == "QA draft v2"
    assert fetched["data"] == new_data
    assert len(fetched["data"]["items"]) == 2


# ── Historical invoice draft kind ───────────────────────────
def test_historical_invoice_draft(client):
    payload = {
        "kind": "historical_invoice",
        "label": "Old invoice",
        "data": {"invoice_no": "H-001", "amount": 1234.5, "lines": [{"sku": "A", "qty": 3}]},
    }
    r = client.post(f"{BASE_URL}/api/drafts", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create failed: {r.status_code} {r.text}"
    body = r.json()
    hid = body["id"]
    CREATED_DRAFT_IDS.append(hid)

    assert body["kind"] == "historical_invoice"
    assert body["data"] == payload["data"]

    # Should appear under historical_invoice filter
    r_h = client.get(f"{BASE_URL}/api/drafts?kind=historical_invoice", timeout=30)
    assert r_h.status_code == 200
    assert any(d["id"] == hid for d in r_h.json())

    # Should NOT appear under order filter
    r_o = client.get(f"{BASE_URL}/api/drafts?kind=order", timeout=30)
    assert r_o.status_code == 200
    assert not any(d["id"] == hid for d in r_o.json())

    # Delete
    r_del = client.delete(f"{BASE_URL}/api/drafts/{hid}", timeout=30)
    assert r_del.status_code == 200, r_del.text
    CREATED_DRAFT_IDS.remove(hid)

    r_h2 = client.get(f"{BASE_URL}/api/drafts?kind=historical_invoice", timeout=30)
    assert not any(d["id"] == hid for d in r_h2.json()), "deleted draft still listed"


# ── Delete draft + 404 on non-existent ──────────────────────
def test_delete_draft_and_404(client):
    assert CREATED_DRAFT_IDS
    did = CREATED_DRAFT_IDS[0]

    r_del = client.delete(f"{BASE_URL}/api/drafts/{did}", timeout=30)
    assert r_del.status_code == 200, f"delete failed: {r_del.status_code} {r_del.text}"
    CREATED_DRAFT_IDS.remove(did)

    # Confirm removed from list
    lst = client.get(f"{BASE_URL}/api/drafts", timeout=30).json()
    assert not any(d.get("id") == did for d in lst), "deleted draft still listed"

    # Delete non-existent
    r_404 = client.delete(f"{BASE_URL}/api/drafts/does-not-exist-{did}", timeout=30)
    assert r_404.status_code == 404, f"expected 404 on missing draft, got {r_404.status_code} {r_404.text}"
