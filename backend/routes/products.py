from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timezone
import uuid
from database import db
from auth import get_current_user
from audit import log_audit

router = APIRouter(prefix="/api/products", tags=["products"])


class ProductCreate(BaseModel):
    name: str
    unit: Optional[str] = "pcs"
    selling_price: float = 0
    cost_price: Optional[float] = 0
    category: Optional[str] = "General"
    primary_supplier_id: Optional[str] = None
    primary_supplier_name: Optional[str] = ""


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    unit: Optional[str] = None
    selling_price: Optional[float] = None
    cost_price: Optional[float] = None
    category: Optional[str] = None
    primary_supplier_id: Optional[str] = None
    primary_supplier_name: Optional[str] = None


async def _check_duplicate_name(name: str, exclude_id: Optional[str] = None):
    """Case-insensitive, trim-safe uniqueness check."""
    normalized = (name or "").strip().lower()
    if not normalized:
        raise HTTPException(status_code=400, detail="Product name is required")
    all_products = await db.products.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(5000)
    for p in all_products:
        if exclude_id and p.get("id") == exclude_id:
            continue
        if (p.get("name") or "").strip().lower() == normalized:
            raise HTTPException(status_code=400, detail=f"Product '{name.strip()}' already exists")


@router.get("")
async def list_products(search: Optional[str] = None, supplier_id: Optional[str] = None, user=Depends(get_current_user)):
    query = {}
    if search:
        query = {"name": {"$regex": search, "$options": "i"}}
    products = await db.products.find(query, {"_id": 0}).sort("name", 1).to_list(5000)
    if supplier_id:
        products = [p for p in products if p.get("primary_supplier_id") == supplier_id]
    return products


@router.get("/{product_id}")
async def get_product(product_id: str, user=Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.get("/{product_id}/price-history")
async def price_history(product_id: str, user=Depends(get_current_user)):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    hist = list(product.get("price_history") or [])
    hist.sort(key=lambda h: h.get("date") or "", reverse=True)
    return hist


@router.get("/{product_id}/sales-history")
async def sales_history(product_id: str, user=Depends(get_current_user)):
    """List every invoice line where this product was sold."""
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    invoices = await db.invoices.find({}, {"_id": 0}).to_list(5000)
    rows = []
    for inv in invoices:
        for it in inv.get("items", []):
            if it.get("product_id") == product_id:
                rows.append({
                    "invoice_id": inv.get("id"),
                    "invoice_number": inv.get("invoice_number"),
                    "customer_id": inv.get("customer_id"),
                    "customer_name": inv.get("customer_name"),
                    "date": inv.get("created_at"),
                    "quantity": it.get("quantity"),
                    "unit_price": it.get("unit_price"),
                    "amount": it.get("amount"),
                })
    rows.sort(key=lambda r: r.get("date") or "", reverse=True)
    return rows


@router.post("")
async def create_product(data: ProductCreate, user=Depends(get_current_user)):
    # v1.1.0 #6 — duplicate prevention
    await _check_duplicate_name(data.name)
    # v1.1.0 #11 — primary supplier optional but auto-resolve name if id provided
    supplier_name = data.primary_supplier_name or ""
    if data.primary_supplier_id and not supplier_name:
        sup = await db.suppliers.find_one({"id": data.primary_supplier_id}, {"_id": 0})
        supplier_name = (sup or {}).get("name", "")
    doc = {
        "id": str(uuid.uuid4()),
        "name": data.name.strip(),
        "unit": data.unit or "pcs",
        "selling_price": data.selling_price,
        "cost_price": data.cost_price or 0,
        "category": (data.category or "General").strip() or "General",
        "primary_supplier_id": data.primary_supplier_id or "",
        "primary_supplier_name": supplier_name,
        "price_history": [{
            "selling_price": data.selling_price,
            "cost_price": data.cost_price or 0,
            "date": datetime.now(timezone.utc).isoformat(),
            "user_email": (user or {}).get("email", ""),
        }],
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.products.insert_one(doc)
    doc.pop("_id", None)
    await log_audit(user, "products", "Create", doc["id"], None, doc)
    return doc


@router.put("/{product_id}")
async def update_product(product_id: str, data: ProductUpdate, user=Depends(get_current_user)):
    prev = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Product not found")

    update = {k: v for k, v in data.model_dump().items() if v is not None}
    if not update:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Duplicate name check when renaming
    if "name" in update and update["name"].strip().lower() != (prev.get("name") or "").strip().lower():
        await _check_duplicate_name(update["name"], exclude_id=product_id)

    # Resolve primary_supplier_name when only id was changed
    if update.get("primary_supplier_id") and "primary_supplier_name" not in update:
        sup = await db.suppliers.find_one({"id": update["primary_supplier_id"]}, {"_id": 0})
        update["primary_supplier_name"] = (sup or {}).get("name", "")

    # Track price changes (only when selling_price actually changed)
    prev_selling = float(prev.get("selling_price", 0) or 0)
    new_selling = float(update.get("selling_price", prev_selling))
    if "selling_price" in update and new_selling != prev_selling:
        history_entry = {
            "previous_price": prev_selling,
            "new_price": new_selling,
            "selling_price": new_selling,
            "cost_price": update.get("cost_price", prev.get("cost_price", 0)),
            "date": datetime.now(timezone.utc).isoformat(),
            "user_email": (user or {}).get("email", ""),
        }
        await db.products.update_one(
            {"id": product_id},
            {"$push": {"price_history": history_entry}}
        )

    await db.products.update_one({"id": product_id}, {"$set": update})
    updated = await db.products.find_one({"id": product_id}, {"_id": 0})
    await log_audit(user, "products", "Edit", product_id, prev, updated)
    return updated


@router.delete("/{product_id}")
async def delete_product(product_id: str, user=Depends(get_current_user)):
    prev = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not prev:
        raise HTTPException(status_code=404, detail="Product not found")
    await db.products.delete_one({"id": product_id})
    await log_audit(user, "products", "Delete", product_id, prev, None)
    return {"message": "Product deleted"}
