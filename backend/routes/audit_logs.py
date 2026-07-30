"""Audit Trail read-only endpoints. Admin-only. Log is immutable."""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional
from database import db
from auth import get_current_user
from audit import AUDITED_MODULES, AUDIT_ACTIONS

router = APIRouter(prefix="/api/audit-logs", tags=["audit-logs"])


def _require_admin(user: dict):
    if (user or {}).get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")


@router.get("/meta")
async def meta(user: dict = Depends(get_current_user)):
    _require_admin(user)
    return {"modules": AUDITED_MODULES, "actions": AUDIT_ACTIONS}


@router.get("")
async def list_logs(
    user: dict = Depends(get_current_user),
    user_email: Optional[str] = None,
    module: Optional[str] = None,
    action: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    limit: int = 500,
):
    _require_admin(user)
    query = {}
    if user_email:
        query["user_email"] = user_email
    if module:
        query["module"] = module
    if action:
        query["action"] = action

    docs = await db.audit_logs.find(query, {"_id": 0}).to_list(5000)

    if date_from:
        docs = [d for d in docs if (d.get("timestamp") or "") >= date_from]
    if date_to:
        docs = [d for d in docs if (d.get("timestamp") or "") <= (date_to + "T23:59:59")]

    docs.sort(key=lambda d: d.get("timestamp") or "", reverse=True)
    return docs[:limit]


@router.get("/{log_id}")
async def get_log(log_id: str, user: dict = Depends(get_current_user)):
    _require_admin(user)
    doc = await db.audit_logs.find_one({"id": log_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Audit log not found")
    return doc
