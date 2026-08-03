"""
Backend tests for v1.1.3 Customer Outstanding bug fix + new date filter.

Scope:
  - PRIMARY BUG: Haseena Ceramic total_outstanding must be POSITIVE (~893175),
    not negative (~-519625). manual_settled must NOT be double-subtracted.
  - No negative per-invoice balances.
  - Independent recomputation for Rich Ceramic.
  - NEW date_from/date_to filter on /reports/customer-outstanding/{id}.
  - REGRESSION: settle → outstanding UNCHANGED → unsettle (net-zero).

Runs against LIVE Firestore. Any mutations are reversed (settle/unsettle).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://trade-audit-v1.preview.emergentagent.com"
).rstrip("/")
FB_API_KEY = "AIzaSyDWAJT2Ruvz7SEU62whyn6__6Lnjfe0HpY"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "admin123"

RICH_CERAMIC_ID = "4e413aa4-df43-4d5d-926a-b6b5e989caac"


@pytest.fixture(scope="session")
def id_token():
    r = requests.post(
        f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key={FB_API_KEY}",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD, "returnSecureToken": True},
        timeout=30,
    )
    assert r.status_code == 200, f"Firebase login failed: {r.status_code} {r.text}"
    tok = r.json().get("idToken")
    assert tok, "No idToken in Firebase response"
    return tok


@pytest.fixture(scope="session")
def H(id_token):
    return {"Authorization": f"Bearer {id_token}", "Content-Type": "application/json"}


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _find_customer(H, needle):
    r = requests.get(f"{BASE_URL}/api/customers", headers=H, timeout=60)
    assert r.status_code == 200, r.text
    needle_l = needle.lower()
    for c in r.json():
        if needle_l in (c.get("name") or "").lower() or needle_l in (c.get("shop_name") or "").lower():
            return c
    return None


def _compute_expected(H, customer_id, date_from=None, date_to=None, use_opening=True):
    """Independent computation using raw endpoints (best-effort against
    what's exposed). Uses /api/invoices, /api/payments, /api/returns."""
    invs = requests.get(f"{BASE_URL}/api/invoices", headers=H, params={"customer_id": customer_id}, timeout=60).json()
    if not isinstance(invs, list):
        invs = invs.get("items", []) if isinstance(invs, dict) else []
    invs = [i for i in invs if i.get("customer_id") == customer_id]

    pays = requests.get(f"{BASE_URL}/api/payments", headers=H, timeout=60).json()
    if not isinstance(pays, list):
        pays = pays.get("items", []) if isinstance(pays, dict) else []
    pays = [p for p in pays if p.get("payment_type") == "customer" and p.get("entity_id") == customer_id]

    rets = requests.get(f"{BASE_URL}/api/returns", headers=H, timeout=60).json()
    if not isinstance(rets, list):
        rets = rets.get("items", []) if isinstance(rets, dict) else []
    inv_ids = {i["id"] for i in invs}
    rets = [
        r for r in rets
        if (r.get("customer_id") == customer_id or r.get("invoice_id") in inv_ids)
        and r.get("destination") != "supplier"
    ]

    def in_range(iso):
        if not iso:
            return True
        d = iso[:10]
        if date_from and d < date_from:
            return False
        if date_to and d > date_to:
            return False
        return True

    if date_from or date_to:
        invs = [i for i in invs if in_range(i.get("created_at", ""))]
        pays = [p for p in pays if in_range(p.get("created_at", ""))]
        rets = [r for r in rets if in_range(r.get("created_at", ""))]

    billed = round(sum(float(i.get("total_amount", 0) or 0) for i in invs), 2)
    paid = round(sum(float(p.get("amount", 0) or 0) for p in pays), 2)
    ret_total = round(sum(float(r.get("total_amount", 0) or 0) for r in rets), 2)

    # Fetch customer to get opening
    cust = requests.get(f"{BASE_URL}/api/customers/{customer_id}", headers=H, timeout=30).json()
    opening = float(cust.get("opening_balance", 0) or 0) if use_opening and not date_from else 0.0

    expected = round(opening + billed - paid - ret_total, 2)
    return {"opening": opening, "billed": billed, "paid": paid, "returns": ret_total, "expected": expected,
            "invs": invs, "pays": pays, "rets": rets}


# ─── Tests ───────────────────────────────────────────────────────────────────
class TestHaseenaPrimaryBug:
    def test_haseena_outstanding_positive_and_matches(self, H):
        cust = _find_customer(H, "Haseena Ceramic")
        assert cust, "Could not find Haseena Ceramic customer"
        cid = cust["id"]
        print(f"\nHaseena Ceramic id={cid}")

        exp = _compute_expected(H, cid)
        print(f"Independent: opening={exp['opening']} billed={exp['billed']} paid={exp['paid']} returns={exp['returns']} expected={exp['expected']}")

        r = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        print(f"API total_outstanding={data.get('total_outstanding')} total_paid={data.get('total_paid')} advance={data.get('advance')}")

        # Primary assertion: not the OLD negative value.
        assert data["total_outstanding"] >= 0, (
            f"Haseena total_outstanding is NEGATIVE ({data['total_outstanding']}), "
            f"bug not fixed."
        )
        assert abs(data["total_outstanding"] - exp["expected"]) < 1.0, (
            f"total_outstanding {data['total_outstanding']} != expected {exp['expected']} "
            f"(billed {exp['billed']} - paid {exp['paid']} - returns {exp['returns']} + opening {exp['opening']})"
        )

        # Response shape includes new fields.
        assert "total_paid" in data
        assert "advance" in data
        assert "date_from" in data and "date_to" in data

        # manual_settled not subtracted: total_paid should equal actual payments,
        # not payments+manual_settled.
        assert abs(data["total_paid"] - exp["paid"]) < 1.0, (
            f"total_paid {data['total_paid']} != actual payments {exp['paid']} — "
            f"manual_settled may still be double counted"
        )

    def test_no_negative_per_invoice_balance(self, H):
        cust = _find_customer(H, "Haseena Ceramic")
        assert cust
        r = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{cust['id']}", headers=H, timeout=60)
        assert r.status_code == 200
        for item in r.json().get("items", []):
            assert item["balance"] >= -0.01, f"Negative balance for {item.get('invoice_number')}: {item['balance']}"


class TestRichCeramic:
    def test_rich_ceramic_matches_expected(self, H):
        exp = _compute_expected(H, RICH_CERAMIC_ID)
        r = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{RICH_CERAMIC_ID}", headers=H, timeout=60)
        assert r.status_code == 200
        data = r.json()
        print(f"\nRich Ceramic: expected={exp['expected']} got={data['total_outstanding']} advance={data.get('advance')}")
        assert abs(data["total_outstanding"] - exp["expected"]) < 1.0, (
            f"Rich Ceramic total_outstanding {data['total_outstanding']} != expected {exp['expected']}"
        )
        # If negative billed/opening/etc, may still be positive; check advance semantics.
        if data["total_outstanding"] < 0:
            assert data.get("advance", 0) > 0, "Negative outstanding without advance"


class TestDateFilter:
    def _pick_window(self, invs):
        dates = sorted([i.get("created_at", "")[:10] for i in invs if i.get("created_at")])
        assert len(dates) >= 2, "Need multiple invoices to test date filter"
        # window excluding the earliest invoice
        return dates[1], dates[-1]

    def test_date_from_and_to_filter(self, H):
        cust = _find_customer(H, "Haseena Ceramic")
        assert cust
        cid = cust["id"]
        # Get full list first
        full = _compute_expected(H, cid)
        assert len(full["invs"]) >= 2, "Not enough invoices for windowed test"
        df, dt = self._pick_window(full["invs"])
        print(f"\nWindow: {df} to {dt}")

        r = requests.get(
            f"{BASE_URL}/api/reports/customer-outstanding/{cid}",
            headers=H, params={"date_from": df, "date_to": dt}, timeout=60,
        )
        assert r.status_code == 200
        data = r.json()

        # (b) echoes date_from/date_to
        assert data.get("date_from") == df
        assert data.get("date_to") == dt

        # (c) opening excluded when date_from set
        assert data.get("opening_balance", 0) == 0

        # (a) every returned item is within window
        for item in data.get("items", []):
            assert df <= item["date"] <= dt, f"Item date {item['date']} outside [{df},{dt}]"

        # (d) totals match independent recomputation for window
        exp = _compute_expected(H, cid, date_from=df, date_to=dt)
        assert abs(data["total_outstanding"] - exp["expected"]) < 1.0, (
            f"Window total {data['total_outstanding']} != expected {exp['expected']} "
            f"(billed={exp['billed']} paid={exp['paid']} returns={exp['returns']})"
        )

    def test_date_from_only(self, H):
        cust = _find_customer(H, "Haseena Ceramic")
        assert cust
        cid = cust["id"]
        full = _compute_expected(H, cid)
        dates = sorted([i.get("created_at", "")[:10] for i in full["invs"] if i.get("created_at")])
        assert len(dates) >= 2
        df = dates[1]
        r = requests.get(
            f"{BASE_URL}/api/reports/customer-outstanding/{cid}",
            headers=H, params={"date_from": df}, timeout=60,
        )
        assert r.status_code == 200
        data = r.json()
        assert data.get("date_from") == df
        assert data.get("opening_balance", 0) == 0
        for item in data.get("items", []):
            assert item["date"] >= df, f"Item date {item['date']} < date_from {df}"


class TestSettleRegression:
    def test_settle_does_not_change_outstanding(self, H):
        """Manual settle marks a bill but must NOT reduce total_outstanding."""
        # Find any customer with an outstanding invoice
        cust = _find_customer(H, "Haseena Ceramic")
        assert cust
        cid = cust["id"]
        r = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", headers=H, timeout=60)
        assert r.status_code == 200
        data_before = r.json()
        items = [it for it in data_before.get("items", []) if it["balance"] > 0.01]
        if not items:
            pytest.skip("No outstanding invoice available for settle regression")

        target = items[0]
        invoice_id = target["invoice_id"]
        before = data_before["total_outstanding"]
        print(f"\nBefore settle: total_outstanding={before}, target invoice={target['invoice_number']} balance={target['balance']}")

        # Settle
        s = requests.post(
            f"{BASE_URL}/api/invoices/{invoice_id}/settle",
            headers=H, json={"amount": None}, timeout=30,
        )
        assert s.status_code in (200, 201), f"Settle failed: {s.status_code} {s.text}"

        try:
            r2 = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", headers=H, timeout=60)
            assert r2.status_code == 200
            after = r2.json()["total_outstanding"]
            print(f"After settle: total_outstanding={after}")
            assert abs(after - before) < 1.0, (
                f"Manual settle changed outstanding: {before} → {after}. "
                f"manual_settled is still being subtracted."
            )
        finally:
            # ALWAYS unsettle to restore original state
            u = requests.post(
                f"{BASE_URL}/api/invoices/{invoice_id}/unsettle",
                headers=H, json={}, timeout=30,
            )
            assert u.status_code in (200, 201), f"Unsettle failed: {u.status_code} {u.text}"

        # Verify restoration
        r3 = requests.get(f"{BASE_URL}/api/reports/customer-outstanding/{cid}", headers=H, timeout=60)
        final = r3.json()["total_outstanding"]
        print(f"After unsettle: total_outstanding={final}")
        assert abs(final - before) < 1.0, f"State not restored after unsettle: {before} → {final}"
