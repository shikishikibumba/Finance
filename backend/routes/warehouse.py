"""Warehouse valuation & stock visibility (v1.1 #16/#17/#18).

The warehouse on-hand pool is the `returned_stock` collection, which holds
every sellable lot from three sources:
  - manual_opening     → opening stock entered for old dealings (#17)
  - customer_return    → goods returned by customers
  - warehouse_purchase → stock bought to recharge the warehouse (#12/#13)

On-hand per lot = quantity_available - quantity_used (consumption is tracked by
the existing sell-from-stock flow), so valuation is always accurate.
Read-only — no writes here.
"""
from fastapi import APIRouter, Depends
from typing import Optional
from datetime import datetime, timezone
from database import db
from auth import get_current_user

router = APIRouter(prefix="/api/warehouse", tags=["warehouse"])

SOURCE_LABELS = {
    "manual_opening": "Opening Stock",
    "customer_return": "Customer Return",
    "warehouse_purchase": "Warehouse Purchase",
}


@router.get("/stock")
async def warehouse_stock(search: Optional[str] = None, include_empty: bool = False,
                          user=Depends(get_current_user)):
    lots = await db.returned_stock.find({}, {"_id": 0}).sort("created_at", 1).to_list(20000)
    grouped = {}
    for s in lots:
        remaining = round(float(s.get("quantity_available", 0) or 0) - float(s.get("quantity_used", 0) or 0), 4)
        cost = float(s.get("cost_price", 0) or 0)
        pid = s.get("product_id")
        g = grouped.setdefault(pid, {
            "product_id": pid,
            "product_name": s.get("product_name", ""),
            "on_hand": 0.0,
            "total_value": 0.0,
            "entries": [],
        })
        if remaining > 0:
            g["on_hand"] = round(g["on_hand"] + remaining, 4)
            g["total_value"] = round(g["total_value"] + remaining * cost, 2)
        g["entries"].append({
            "date": (s.get("created_at") or "")[:10],
            "source": s.get("source", ""),
            "source_label": SOURCE_LABELS.get(s.get("source", ""), s.get("source", "") or "—"),
            "opening_qty": round(float(s.get("quantity_available", 0) or 0), 4),
            "used": round(float(s.get("quantity_used", 0) or 0), 4),
            "remaining": remaining,
            "cost_price": round(cost, 2),
            "reference": s.get("purchase_number") or s.get("invoice_id") or "",
            "notes": s.get("notes", ""),
        })
    rows = list(grouped.values())
    for r in rows:
        r["unit_cost"] = round(r["total_value"] / r["on_hand"], 2) if r["on_hand"] else 0.0
    if not include_empty:
        rows = [r for r in rows if r["on_hand"] > 0]
    if search:
        q = search.strip().lower()
        rows = [r for r in rows
                if q in (r["product_name"] or "").lower() or q in (r["product_id"] or "").lower()]
    rows.sort(key=lambda r: (r["product_name"] or "").lower())
    return {
        "items": rows,
        "grand_total_value": round(sum(r["total_value"] for r in rows), 2),
        "total_units": round(sum(r["on_hand"] for r in rows), 4),
        "product_count": len(rows),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
