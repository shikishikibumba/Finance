from pathlib import Path
from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

from fastapi import FastAPI, APIRouter, Depends
from starlette.middleware.cors import CORSMiddleware
import os
import logging
import uuid
from datetime import datetime, timezone
from firebase_admin import auth as fb_auth
from database import db
from auth import get_current_user

app = FastAPI(redirect_slashes=False)

# CORS — accept the configured list, or fall back to echoing the request origin
# back so Vercel + Render can talk freely. Tokens are sent in Authorization
# header (Firebase ID tokens), so cross-origin cookies are not required.
_cors_env = os.environ.get('CORS_ORIGINS', '*').strip()
if _cors_env == '*' or _cors_env == '':
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in _cors_env.split(',') if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── Auth introspection ──
# Login / register / password reset happen client-side via the Firebase JS SDK.
# The backend only needs an endpoint to introspect the current session.
auth_router = APIRouter(prefix="/api/auth", tags=["auth"])


@auth_router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return user


app.include_router(auth_router)


# ── Module routers ──
from routes.customers import router as customers_router
from routes.suppliers import router as suppliers_router
from routes.products import router as products_router
from routes.orders import router as orders_router
from routes.purchases import router as purchases_router
from routes.invoices import router as invoices_router
from routes.payments import router as payments_router
from routes.dashboard import router as dashboard_router
from routes.reports import router as reports_router
from routes.analytics import router as analytics_router
from routes.settings import router as settings_router
from routes.returns import router as returns_router
from routes.delivery_orders import router as delivery_orders_router
from routes.returned_stock import router as returned_stock_router
from routes.users import router as users_router
from routes.banks import router as banks_router, seed_banks
from routes.payment_references import router as payment_references_router
from routes.cheque_inventory import router as cheque_inventory_router
from routes.audit_logs import router as audit_logs_router
from routes.warehouse import router as warehouse_router
from routes.drafts import router as drafts_router

app.include_router(customers_router)
app.include_router(suppliers_router)
app.include_router(products_router)
app.include_router(orders_router)
app.include_router(purchases_router)
app.include_router(invoices_router)
app.include_router(payments_router)
app.include_router(dashboard_router)
app.include_router(reports_router)
app.include_router(analytics_router)
app.include_router(settings_router)
app.include_router(returns_router)
app.include_router(returned_stock_router)
app.include_router(delivery_orders_router)
app.include_router(users_router)
app.include_router(banks_router)
app.include_router(payment_references_router)
app.include_router(cheque_inventory_router)
app.include_router(audit_logs_router)
app.include_router(warehouse_router)
app.include_router(drafts_router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


async def _seed_admin():
    """Ensure an admin user exists in Firebase Auth.

    Uses ADMIN_EMAIL and ADMIN_PASSWORD env vars.
    - If the user doesn't exist in Firebase Auth → create them.
    - If it exists → update password (so ADMIN_PASSWORD always works) and
      ensure role=admin custom claim.
    Mirror the profile into Firestore /users/{uid}.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower().strip()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")

    try:
        existing = fb_auth.get_user_by_email(admin_email)
        # Reset password + ensure role=admin so the env var is the source of truth
        fb_auth.update_user(existing.uid, password=admin_password, email_verified=True)
        fb_auth.set_custom_user_claims(existing.uid, {"role": "admin"})
        uid = existing.uid
        name = existing.display_name or "Admin"
    except fb_auth.UserNotFoundError:
        created = fb_auth.create_user(
            email=admin_email,
            password=admin_password,
            display_name="Admin",
            email_verified=True,
        )
        fb_auth.set_custom_user_claims(created.uid, {"role": "admin"})
        uid = created.uid
        name = "Admin"

    # Mirror profile into Firestore /users/{uid}
    existing_profile = await db.users.find_one({"id": uid})
    profile = {
        "id": uid,
        "email": admin_email,
        "name": name,
        "role": "admin",
        "created_at": (existing_profile or {}).get("created_at") or datetime.now(timezone.utc).isoformat(),
    }
    if existing_profile:
        await db.users.update_one({"id": uid}, {"$set": profile})
    else:
        await db.users.insert_one(profile)


@app.on_event("startup")
async def startup():
    # Firestore indexes (no-op on Firestore — kept for API compat with previous code)
    await db.customers.create_index("id", unique=True)
    await db.suppliers.create_index("id", unique=True)
    await db.products.create_index("id", unique=True)
    await db.orders.create_index("id", unique=True)
    await db.purchases.create_index("id", unique=True)
    await db.invoices.create_index("id", unique=True)
    await db.payments.create_index("id", unique=True)
    await db.returns.create_index("id", unique=True)
    await db.returned_stock.create_index("id", unique=True)
    await db.invoices.create_index("invoice_number", unique=True)
    await db.purchases.create_index("purchase_number", unique=True)

    # Admin seeding — best effort. If Firebase Auth is unreachable (key rotation,
    # network glitch), still bring the server up so other endpoints work.
    try:
        await _seed_admin()
    except Exception as e:
        logger.warning(f"Admin seeding skipped (will retry on next startup): {e}")

    # v1.1.0 — seed Sri Lankan banks (idempotent)
    try:
        await seed_banks()
    except Exception as e:
        logger.warning(f"Bank seeding skipped: {e}")

    # Phase 7 migration — restore original total_amount on purchases that
    # had been previously reduced by supplier returns. Best-effort.
    try:
        purs = await db.purchases.find(
            {"supplier_return_adjustments": {"$exists": True, "$ne": []}}
        ).to_list(None)
        for pur in purs:
            adjs = pur.get("supplier_return_adjustments") or []
            if not adjs:
                continue
            if pur.get("_phase7_total_restored"):
                continue
            adj_total = round(sum(float(a.get("amount", 0) or 0) for a in adjs), 2)
            if adj_total <= 0:
                continue
            original = float(pur.get("total_amount", 0) or 0)
            await db.purchases.update_one(
                {"id": pur["id"]},
                {"$set": {
                    "total_amount": round(original + adj_total, 2),
                    "_phase7_total_restored": True
                }}
            )
    except Exception as e:
        logger.warning(f"Phase 7 migration skipped: {e}")

    # Write test credentials file — only in dev/Emergent pods where /app exists
    # and is writable. Silently skip on Render / Vercel / other hosts.
    try:
        admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com")
        admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
        os.makedirs("/app/memory", exist_ok=True)
        with open("/app/memory/test_credentials.md", "w") as f:
            f.write(f"# Test Credentials\n\n## Admin (Firebase Auth)\n- Email: {admin_email}\n- Password: {admin_password}\n- Role: admin\n\nUsers are managed in Firebase Authentication. Login happens client-side via Firebase JS SDK. The backend verifies ID tokens.\n")
    except (PermissionError, OSError):
        pass
    logger.info("Admin user (Firebase Auth) seeded and Firestore indexes ready")


@app.on_event("shutdown")
async def shutdown():
    pass


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
