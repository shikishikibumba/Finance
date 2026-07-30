"""Admin-only user management endpoints (Firebase Auth-based).

Only users with custom claim role=admin can list/create/delete users or reset
their passwords. Regular users cannot access any of these endpoints.

User identity is owned by Firebase Authentication. We mirror a minimal profile
(name, role, created_at) into Firestore /users/{uid} for listing/queryability.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, EmailStr, field_validator
from firebase_admin import auth as fb_auth
from datetime import datetime, timezone
from auth import get_current_user, require_admin
from database import db
import logging

router = APIRouter(prefix="/api/users", tags=["users"])
logger = logging.getLogger(__name__)


class CreateUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str = "user"

    @field_validator("password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v

    @field_validator("role")
    @classmethod
    def role_valid(cls, v):
        if v not in ("admin", "user"):
            raise ValueError("role must be 'admin' or 'user'")
        return v


class ResetPasswordRequest(BaseModel):
    new_password: str

    @field_validator("new_password")
    @classmethod
    def password_min_length(cls, v):
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters")
        return v


@router.get("")
async def list_users(user: dict = Depends(get_current_user)):
    require_admin(user)
    users = await db.users.find({}, {"_id": 0, "password_hash": 0}).to_list(1000)
    return users


@router.post("")
async def create_user(req: CreateUserRequest, user: dict = Depends(get_current_user)):
    require_admin(user)
    email = req.email.lower().strip()

    try:
        fb_user = fb_auth.create_user(
            email=email,
            password=req.password,
            display_name=req.name,
            email_verified=True,  # admin-created, no need for verification flow
        )
    except fb_auth.EmailAlreadyExistsError:
        raise HTTPException(status_code=400, detail="Email already in use")
    except Exception as e:
        logger.error(f"Failed to create Firebase user: {e}")
        raise HTTPException(status_code=400, detail=f"Could not create user: {str(e)}")

    fb_auth.set_custom_user_claims(fb_user.uid, {"role": req.role})

    profile = {
        "id": fb_user.uid,
        "email": email,
        "name": req.name,
        "role": req.role,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(profile)
    return {k: v for k, v in profile.items() if k != "_id"}


@router.post("/{uid}/reset-password")
async def reset_password(uid: str, req: ResetPasswordRequest, user: dict = Depends(get_current_user)):
    require_admin(user)
    try:
        fb_auth.update_user(uid, password=req.new_password)
    except fb_auth.UserNotFoundError:
        raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        logger.error(f"Failed to reset password: {e}")
        raise HTTPException(status_code=400, detail=f"Could not reset password: {str(e)}")
    return {"message": "Password reset successfully"}


@router.delete("/{uid}")
async def delete_user(uid: str, user: dict = Depends(get_current_user)):
    require_admin(user)
    if uid == user["id"]:
        raise HTTPException(status_code=400, detail="You cannot delete your own account")
    try:
        fb_auth.delete_user(uid)
    except fb_auth.UserNotFoundError:
        pass  # already gone; idempotent
    except Exception as e:
        logger.error(f"Failed to delete Firebase user: {e}")
        raise HTTPException(status_code=400, detail=f"Could not delete user: {str(e)}")
    await db.users.delete_one({"id": uid})
    return {"message": "User deleted"}
