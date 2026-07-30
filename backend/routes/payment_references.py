"""Payment references — dropdown values used in payment forms.

Presets (Cash Collection, CHQ Deposit, RTGS Transfer, Bank Deposit,
Manual Adjustment) are always returned. Users can add custom entries.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from datetime import datetime, timezone
import uuid
from database import db
from auth import get_current_user

router = APIRouter(prefix="/api/payment-references", tags=["payment-references"])


DEFAULT_REFERENCES = [
    "Cash Collection",
    "CHQ Deposit",
    "RTGS Transfer",
    "Bank Deposit",
    "Manual Adjustment",
]


class ReferenceCreate(BaseModel):
    name: str


@router.get("")
async def list_references(user=Depends(get_current_user)):
    custom = await db.payment_references.find({}, {"_id": 0}).to_list(500)
    custom_names = {c.get("name", "").lower() for c in custom}
    presets = [{"id": f"preset-{i}", "name": n, "preset": True}
               for i, n in enumerate(DEFAULT_REFERENCES) if n.lower() not in custom_names]
    return presets + [{**c, "preset": False} for c in custom]


@router.post("")
async def create_reference(data: ReferenceCreate, user=Depends(get_current_user)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    all_existing = await db.payment_references.find({}, {"_id": 0, "name": 1}).to_list(500)
    for r in all_existing:
        if (r.get("name") or "").strip().lower() == name.lower():
            raise HTTPException(status_code=400, detail=f"Reference '{name}' already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "preset": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.payment_references.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.delete("/{ref_id}")
async def delete_reference(ref_id: str, user=Depends(get_current_user)):
    prev = await db.payment_references.find_one({"id": ref_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Reference not found")
    await db.payment_references.delete_one({"id": ref_id})
    return {"message": "Reference deleted"}
