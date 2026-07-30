"""Banks module — Sri Lankan bank list. Seeded on startup with 11 banks."""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
from database import db
from auth import get_current_user
from audit import log_audit

router = APIRouter(prefix="/api/banks", tags=["banks"])


SL_BANKS = [
    "Bank of Ceylon",
    "People's Bank",
    "Commercial Bank",
    "Hatton National Bank",
    "Sampath Bank",
    "National Development Bank",
    "DFCC Bank",
    "Seylan Bank",
    "National Savings Bank",
    "Nations Trust Bank",
    "Pan Asia Bank",
]


class BankCreate(BaseModel):
    name: str


async def seed_banks():
    """Idempotent — seeds only banks not already present."""
    try:
        for name in SL_BANKS:
            existing = await db.banks.find_one({"name": name}, {"_id": 0})
            if not existing:
                await db.banks.insert_one({
                    "id": str(uuid.uuid4()),
                    "name": name,
                    "seeded": True,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                })
    except Exception:
        pass


@router.get("")
async def list_banks(user=Depends(get_current_user)):
    banks = await db.banks.find({}, {"_id": 0}).to_list(500)
    banks.sort(key=lambda b: b.get("name", "").lower())
    return banks


@router.post("")
async def create_bank(data: BankCreate, user=Depends(get_current_user)):
    name = (data.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Bank name is required")
    # Case-insensitive uniqueness
    existing = await db.banks.find({}, {"_id": 0, "name": 1}).to_list(500)
    for b in existing:
        if (b.get("name") or "").strip().lower() == name.lower():
            raise HTTPException(status_code=400, detail=f"Bank '{name}' already exists")
    doc = {
        "id": str(uuid.uuid4()),
        "name": name,
        "seeded": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.banks.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "banks", "Create", doc["id"], None, doc)
    return doc


@router.delete("/{bank_id}")
async def delete_bank(bank_id: str, user=Depends(get_current_user)):
    prev = await db.banks.find_one({"id": bank_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Bank not found")
    if prev.get("seeded"):
        raise HTTPException(status_code=400, detail="Seeded banks cannot be deleted")
    await db.banks.delete_one({"id": bank_id})
    await log_audit(user, "banks", "Delete", bank_id, prev, None)
    return {"message": "Bank deleted"}
