"""Authentication using Firebase Auth (ID token verification).

Replaces the previous PyJWT + bcrypt custom auth. Clients sign in via the
Firebase JS SDK and send the Firebase ID token in the Authorization header.

  Authorization: Bearer <firebase-id-token>

The token is verified with firebase_admin.auth.verify_id_token(). The user's
profile (name, role) is mirrored to Firestore at /users/{uid} for queryability
and listings.
"""
from fastapi import HTTPException, Request
from firebase_admin import auth as fb_auth
from database import db
import logging

logger = logging.getLogger(__name__)


async def get_current_user(request: Request) -> dict:
    """Verify Firebase ID token from Authorization header and return user dict.

    The returned dict mirrors the previous custom-auth shape so existing route
    code doesn't need to change:
        { "id": <uid>, "email": ..., "name": ..., "role": "admin"|"user" }
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    token = auth_header[7:]

    try:
        decoded = fb_auth.verify_id_token(token, check_revoked=False)
    except fb_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except fb_auth.RevokedIdTokenError:
        raise HTTPException(status_code=401, detail="Token revoked")
    except Exception as e:
        logger.warning(f"ID token verification failed: {e}")
        raise HTTPException(status_code=401, detail="Invalid token")

    uid = decoded["uid"]
    email = decoded.get("email", "")

    # Custom claims (set by admin on user creation)
    role = decoded.get("role") or "user"

    # Pull profile from Firestore /users/{uid} (kept in sync on create)
    profile = await db.users.find_one({"id": uid}, {"_id": 0, "password_hash": 0}) or {}

    return {
        "id": uid,
        "email": email,
        "name": profile.get("name") or decoded.get("name") or email.split("@")[0],
        "role": profile.get("role") or role,
    }


def require_admin(user: dict) -> None:
    """Raise 403 if the user is not an admin."""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
