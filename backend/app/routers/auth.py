"""
/api/auth — Firebase Authentication Integration
──────────────────────────────────────────────────
HOW IT WORKS:
  1. Frontend signs in with Firebase (email/password or Google)
  2. Firebase gives the frontend an ID Token (JWT signed by Google)
  3. Frontend sends that token: POST /api/auth/firebase
  4. Backend verifies it with Firebase Admin SDK
  5. Backend returns its own JWT for subsequent API calls

FALLBACK (no Firebase configured):
  - POST /api/auth/login  still works with username/password
"""

import os
import hashlib
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.database import get_db
from app.models.schemas import LoginRequest, TokenResponse

router = APIRouter()
security = HTTPBearer(auto_error=False)

SECRET_KEY         = os.getenv("SECRET_KEY", "swachhnetra-gvmc-vizag-2026-CHANGE-ME")
ALGORITHM          = "HS256"
TOKEN_EXPIRE_HOURS = 8
FIREBASE_PROJECT   = os.getenv("FIREBASE_PROJECT_ID", "")

firebase_auth      = None
firebase_available = False


def _init_firebase():
    global firebase_auth, firebase_available
    if firebase_available:
        return True
    try:
        import firebase_admin
        from firebase_admin import credentials, auth
        if not firebase_admin._apps:
            cred_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
            if cred_path and os.path.exists(cred_path):
                firebase_admin.initialize_app(credentials.Certificate(cred_path))
                print("Firebase initialised from service account file")
            else:
                # Local fallback check matching firebase_sync
                CRED_FILENAME = "serviceAccountKey.json"
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
                fallback_cred = os.path.join(base_dir, CRED_FILENAME)
                if not os.path.exists(fallback_cred):
                    fallback_cred = os.path.join(os.getcwd(), CRED_FILENAME)
                
                if os.path.exists(fallback_cred):
                    firebase_admin.initialize_app(credentials.Certificate(fallback_cred))
                    print(f"Firebase initialised from local service account file: {fallback_cred}")
                elif FIREBASE_PROJECT:
                    firebase_admin.initialize_app(options={"projectId": FIREBASE_PROJECT})
                    print("Firebase initialised with project:", FIREBASE_PROJECT)
                else:
                    return False
        firebase_auth = auth
        firebase_available = True
        return True
    except ImportError:
        print("firebase-admin not installed — run: pip install firebase-admin")
        return False
    except Exception as e:
        print(f"Firebase init error: {e}")
        return False


def hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def create_token(data: dict) -> str:
    payload = {**data, "exp": datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def verify_backend_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    if not credentials:
        raise HTTPException(401, "Not authenticated")
    token = credentials.credentials

    # Try Firebase token first
    if _init_firebase() and firebase_available:
        try:
            decoded = firebase_auth.verify_id_token(token)
            uid   = decoded.get("uid", "")
            email = decoded.get("email", "")
            name  = decoded.get("name", email.split("@")[0] if email else "User")
            role  = decoded.get("swachhnetra_role", "citizen")
            return {"sub": uid, "email": email, "name": name, "role": role, "source": "firebase"}
        except Exception:
            pass

    # Try backend JWT
    payload = verify_backend_token(token)
    if payload:
        return {**payload, "source": "backend_jwt"}

    raise HTTPException(401, "Invalid or expired token")


# ─── Request/Response models ───
class FirebaseTokenRequest(BaseModel):
    id_token: str
    role_override: Optional[str] = None   # demo only — remove in production


class FirebaseTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    name: str
    email: str
    uid: str
    firebase_verified: bool


# ─── Routes ───

@router.post("/firebase", response_model=FirebaseTokenResponse)
async def login_with_firebase(body: FirebaseTokenRequest):
    """Exchange a Firebase ID token for a backend access token."""
    if not _init_firebase() or not firebase_available:
        raise HTTPException(503, "Firebase not configured. Use /api/auth/login instead.")
    try:
        decoded = firebase_auth.verify_id_token(body.id_token)
    except Exception as e:
        raise HTTPException(401, f"Firebase token invalid: {e}")

    uid   = decoded.get("uid", "")
    email = decoded.get("email", "")
    name  = decoded.get("name", email.split("@")[0] if email else "User")
    role  = decoded.get("swachhnetra_role", "citizen")
    if body.role_override in ("admin", "worker", "citizen"):
        role = body.role_override   # demo override

    db = await get_db()
    now = datetime.utcnow().isoformat()
    await db.execute(
        "INSERT OR REPLACE INTO users (username,password_hash,role,name,created_at) VALUES (?,?,?,?,?)",
        (uid, "firebase:" + uid, role, name, now)
    )
    await db.commit()

    token = create_token({"sub": uid, "email": email, "role": role, "name": name})
    return FirebaseTokenResponse(
        access_token=token, role=role, name=name,
        email=email, uid=uid, firebase_verified=True
    )


@router.post("/firebase/set-role")
async def set_firebase_role(body: dict, user: dict = Depends(get_current_user)):
    """Admin only: assign custom role to a Firebase user."""
    if user.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    if not firebase_available:
        raise HTTPException(503, "Firebase not available")
    uid      = body.get("uid")
    new_role = body.get("role")
    if not uid or new_role not in ("admin", "worker", "citizen"):
        raise HTTPException(400, "uid and role required")
    firebase_auth.set_custom_user_claims(uid, {"swachhnetra_role": new_role})
    return {"message": f"Role '{new_role}' set for {uid}"}


@router.get("/firebase/status")
async def firebase_status():
    """Check Firebase configuration status."""
    return {
        "firebase_available": _init_firebase(),
        "project_id": FIREBASE_PROJECT or "not configured",
        "fallback": "/api/auth/login",
    }


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest):
    """Fallback: username + password login (works offline / without Firebase)."""
    db = await get_db()
    pw_hash = hash_password(body.password)
    cur = await db.execute(
        "SELECT * FROM users WHERE username=? AND password_hash=?",
        (body.username, pw_hash)
    )
    user = await cur.fetchone()
    if not user:
        raise HTTPException(401, "Invalid username or password")
    token = create_token({"sub": user["username"], "role": user["role"], "name": user["name"]})
    return TokenResponse(access_token=token, role=user["role"], name=user["name"])


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user


@router.post("/change-password")
async def change_password(body: dict, user: dict = Depends(get_current_user)):
    db = await get_db()
    new_hash = hash_password(body.get("new_password", ""))
    await db.execute("UPDATE users SET password_hash=? WHERE username=?", (new_hash, user["sub"]))
    await db.commit()
    return {"message": "Password updated"}
