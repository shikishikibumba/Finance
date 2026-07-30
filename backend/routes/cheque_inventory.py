"""Cheque Inventory module — full lifecycle tracking of every cheque.

Auto-populated when a customer pays by cheque (via hook in payments.py).
Endorsed to supplier when supplier is paid using an inventoried cheque.
Own cheques (retained for future deposit) can be entered manually.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timezone
import uuid
from database import db
from auth import get_current_user
from audit import log_audit

router = APIRouter(prefix="/api/cheque-inventory", tags=["cheque-inventory"])


VALID_STATUSES = ["Available", "Issued to Supplier", "Deposited", "Cleared", "Bounced"]


class ChequeCreate(BaseModel):
    cheque_number: str
    bank: str
    amount: float
    cheque_date: str
    received_date: Optional[str] = None
    customer_id: Optional[str] = None
    customer_name: Optional[str] = ""
    notes: Optional[str] = ""
    own_cheque: Optional[bool] = False


class ChequeStatusUpdate(BaseModel):
    status: str
    note: Optional[str] = ""


# ── Internal helper used by payments.py to auto-create records ─────────
async def create_customer_cheque(
    *, cheque_number: str, bank: str, amount: float, cheque_date: str,
    customer_id: str, customer_name: str, payment_id: str,
    received_date: Optional[str] = None,
) -> dict:
    doc = {
        "id": str(uuid.uuid4()),
        "cheque_number": cheque_number,
        "bank": bank or "",
        "amount": float(amount or 0),
        "cheque_date": cheque_date or "",
        "received_date": received_date or datetime.now(timezone.utc).isoformat(),
        "customer_id": customer_id,
        "customer_name": customer_name or "",
        "supplier_id": None,
        "supplier_name": None,
        "issued_date": None,
        "status": "Available",
        "own_cheque": False,
        "customer_payment_id": payment_id,
        "supplier_payment_id": None,
        "notes": "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cheque_inventory.insert_one(doc)
    doc.pop("_id", None)
    return doc


async def endorse_to_supplier(
    cheque_id: str, supplier_id: str, supplier_name: str, payment_id: str,
) -> dict:
    """Mark a cheque as issued to a supplier. Only cheques with status
    'Available' can be endorsed. Returns the updated cheque doc."""
    cheque = await db.cheque_inventory.find_one({"id": cheque_id}, {"_id": 0})
    if not cheque:
        raise HTTPException(status_code=404, detail=f"Cheque {cheque_id} not found")
    if cheque.get("status") != "Available":
        raise HTTPException(
            status_code=400,
            detail=f"Cheque {cheque.get('cheque_number')} is not available (status: {cheque.get('status')})"
        )
    update = {
        "status": "Issued to Supplier",
        "supplier_id": supplier_id,
        "supplier_name": supplier_name or "",
        "issued_date": datetime.now(timezone.utc).isoformat(),
        "supplier_payment_id": payment_id,
    }
    await db.cheque_inventory.update_one({"id": cheque_id}, {"$set": update})
    return {**cheque, **update}


# ── HTTP endpoints ────────────────────────────────────────────────────
@router.get("")
async def list_cheques(
    user=Depends(get_current_user),
    customer_id: Optional[str] = None,
    supplier_id: Optional[str] = None,
    bank: Optional[str] = None,
    status: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    sort: str = Query("date_desc"),
):
    query = {}
    if customer_id:
        query["customer_id"] = customer_id
    if supplier_id:
        query["supplier_id"] = supplier_id
    if bank:
        query["bank"] = bank
    if status:
        query["status"] = status

    docs = await db.cheque_inventory.find(query, {"_id": 0}).to_list(5000)

    # Filter numeric/date ranges in memory (Firestore adapter has limited operators)
    if min_amount is not None:
        docs = [d for d in docs if float(d.get("amount", 0) or 0) >= min_amount]
    if max_amount is not None:
        docs = [d for d in docs if float(d.get("amount", 0) or 0) <= max_amount]
    if date_from:
        docs = [d for d in docs if (d.get("cheque_date") or "") >= date_from]
    if date_to:
        docs = [d for d in docs if (d.get("cheque_date") or "") <= date_to]

    sort_key = {
        "date_desc": lambda d: (d.get("cheque_date") or ""),
        "date_asc": lambda d: (d.get("cheque_date") or ""),
        "customer": lambda d: (d.get("customer_name") or "").lower(),
        "supplier": lambda d: (d.get("supplier_name") or "").lower(),
        "amount_desc": lambda d: float(d.get("amount", 0) or 0),
        "amount_asc": lambda d: float(d.get("amount", 0) or 0),
        "bank": lambda d: (d.get("bank") or "").lower(),
    }.get(sort, lambda d: d.get("cheque_date", ""))
    reverse = sort in ("date_desc", "amount_desc")
    docs.sort(key=sort_key, reverse=reverse)
    return docs


@router.get("/due")
async def list_cheques_due(
    days: int = 14,
    kind: str = Query("customer"),  # "customer" or "supplier"
    user=Depends(get_current_user),
):
    """Cheques falling due in the next `days` days.

    - kind=customer → cheques received from customers not yet cleared
    - kind=supplier → cheques we've issued to suppliers not yet cleared
    """
    from datetime import date, timedelta
    today = date.today().isoformat()
    horizon = (date.today() + timedelta(days=days)).isoformat()
    if kind == "customer":
        q = {"status": {"$in": ["Available", "Deposited"]}}
        docs = await db.cheque_inventory.find(q, {"_id": 0}).to_list(5000)
        docs = [d for d in docs if d.get("customer_id") and today <= (d.get("cheque_date") or "") <= horizon]
    else:
        q = {"status": "Issued to Supplier"}
        docs = await db.cheque_inventory.find(q, {"_id": 0}).to_list(5000)
        docs = [d for d in docs if d.get("supplier_id") and today <= (d.get("cheque_date") or "") <= horizon]
    docs.sort(key=lambda d: d.get("cheque_date") or "")
    return docs


@router.get("/{cheque_id}")
async def get_cheque(cheque_id: str, user=Depends(get_current_user)):
    doc = await db.cheque_inventory.find_one({"id": cheque_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Cheque not found")
    return doc


@router.post("/own")
async def create_own_cheque(data: ChequeCreate, user=Depends(get_current_user)):
    """Add a cheque retained by us for future deposit into our own accounts."""
    doc = {
        "id": str(uuid.uuid4()),
        "cheque_number": data.cheque_number.strip(),
        "bank": data.bank or "",
        "amount": float(data.amount or 0),
        "cheque_date": data.cheque_date or "",
        "received_date": data.received_date or datetime.now(timezone.utc).isoformat(),
        "customer_id": data.customer_id,
        "customer_name": data.customer_name or "",
        "supplier_id": None,
        "supplier_name": None,
        "issued_date": None,
        "status": "Available",
        "own_cheque": True,
        "customer_payment_id": None,
        "supplier_payment_id": None,
        "notes": data.notes or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.cheque_inventory.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "cheque_inventory", "Create", doc["id"], None, doc)
    return doc


@router.patch("/{cheque_id}/status")
async def update_status(cheque_id: str, data: ChequeStatusUpdate, user=Depends(get_current_user)):
    if data.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(VALID_STATUSES)}")
    prev = await db.cheque_inventory.find_one({"id": cheque_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Cheque not found")
    update = {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}
    if data.note:
        update["notes"] = ((prev.get("notes") or "") + f"\n[{datetime.now(timezone.utc).isoformat()}] {data.note}").strip()
    await db.cheque_inventory.update_one({"id": cheque_id}, {"$set": update})
    updated = await db.cheque_inventory.find_one({"id": cheque_id}, {"_id": 0})
    await log_audit(user, "cheque_inventory", "Edit", cheque_id, prev, updated)
    return updated


@router.delete("/{cheque_id}")
async def delete_cheque(cheque_id: str, user=Depends(get_current_user)):
    prev = await db.cheque_inventory.find_one({"id": cheque_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Cheque not found")
    if prev.get("status") not in ("Available",) and not prev.get("own_cheque"):
        raise HTTPException(
            status_code=400,
            detail=f"Only 'Available' cheques or own cheques can be deleted (current status: {prev.get('status')})"
        )
    await db.cheque_inventory.delete_one({"id": cheque_id})
    await log_audit(user, "cheque_inventory", "Delete", cheque_id, prev, None)
    return {"message": "Cheque deleted"}
