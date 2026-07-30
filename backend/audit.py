"""Audit trail helper. Immutable append-only.

Usage:
    from audit import log_audit
    await log_audit(user, "invoices", "Create", record_id=doc["id"], previous=None, new=doc)
"""
import uuid
from datetime import datetime, timezone
from database import db


AUDITED_MODULES = [
    "orders", "purchases", "invoices", "customer_payments", "supplier_payments",
    "returns", "products", "customers", "suppliers", "banks", "cheque_inventory",
    "delivery_orders", "users",
]

AUDIT_ACTIONS = ["Create", "Edit", "Delete", "Cancel", "Return", "Restore"]


async def log_audit(
    user: dict | None,
    module: str,
    action: str,
    record_id: str,
    previous: dict | None = None,
    new: dict | None = None,
    note: str = "",
):
    """Append an immutable audit log entry. Never raises — logging must not
    block business flow."""
    try:
        entry = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": (user or {}).get("id"),
            "user_email": (user or {}).get("email"),
            "module": module,
            "action": action,
            "record_id": record_id,
            "previous": _strip(previous),
            "new": _strip(new),
            "note": note,
        }
        await db.audit_logs.insert_one(entry)
    except Exception:
        # Best-effort. Do NOT crash the caller.
        pass


def _strip(doc):
    """Drop non-serialisable fields before storage."""
    if not doc:
        return None
    out = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        out[k] = v
    return out
