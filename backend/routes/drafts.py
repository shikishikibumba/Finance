from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Any, Dict
from datetime import datetime, timezone
import uuid
from database import db
from auth import get_current_user

router = APIRouter(prefix="/api/drafts", tags=["drafts"])


class DraftIn(BaseModel):
    kind: str                      # "order" | "historical_invoice"
    label: Optional[str] = ""
    data: Dict[str, Any] = {}


@router.get("")
async def list_drafts(kind: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if kind:
        query["kind"] = kind
    drafts = await db.drafts.find(query, {"_id": 0}).sort("updated_at", -1).to_list(500)
    return drafts


@router.post("")
async def create_draft(data: DraftIn, user=Depends(get_current_user)):
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "kind": data.kind,
        "label": data.label or "Untitled draft",
        "data": data.data or {},
        "user_email": user.get("email", ""),
        "created_at": now,
        "updated_at": now,
    }
    await db.drafts.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{draft_id}")
async def update_draft(draft_id: str, data: DraftIn, user=Depends(get_current_user)):
    existing = await db.drafts.find_one({"id": draft_id}, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Draft not found")
    await db.drafts.update_one(
        {"id": draft_id},
        {"$set": {
            "label": data.label or existing.get("label", "Untitled draft"),
            "data": data.data or {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )
    return await db.drafts.find_one({"id": draft_id}, {"_id": 0})


@router.delete("/{draft_id}")
async def delete_draft(draft_id: str, user=Depends(get_current_user)):
    result = await db.drafts.delete_one({"id": draft_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"message": "Draft deleted"}
