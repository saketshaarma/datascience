import os
import jwt
import bcrypt
import secrets
from datetime import datetime, timezone, timedelta
from bson import ObjectId
from fastapi import APIRouter, Request, Response, HTTPException, Depends
from pydantic import BaseModel, EmailStr

JWT_ALGORITHM = "HS256"
_db = None

# how long lockout / limits
MAX_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def init(db):
    global _db
    _db = db


# ----------------------------- helpers -----------------------------
def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def get_jwt_secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id, "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=60),
        "type": "access",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: str) -> str:
    payload = {
        "sub": user_id,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "refresh",
    }
    return jwt.encode(payload, get_jwt_secret(), algorithm=JWT_ALGORITHM)


def _set_cookies(response: Response, access: str, refresh: str):
    response.set_cookie("access_token", access, httponly=True, secure=True,
                        samesite="none", max_age=3600, path="/")
    response.set_cookie("refresh_token", refresh, httponly=True, secure=True,
                        samesite="none", max_age=604800, path="/")


def _user_public(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "email": user["email"],
        "name": user.get("name", ""),
        "role": user.get("role", "member"),
    }


async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, get_jwt_secret(), algorithms=[JWT_ALGORITHM])
        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await _db.users.find_one({"_id": ObjectId(payload["sub"])})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return user
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def require_admin(request: Request) -> dict:
    user = await get_current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


# ----------------------------- schemas -----------------------------
class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    name: str = ""


class LoginBody(BaseModel):
    email: EmailStr
    password: str


# ----------------------------- brute force -----------------------------
async def _check_lock(identifier: str):
    rec = await _db.login_attempts.find_one({"identifier": identifier})
    if rec and rec.get("count", 0) >= MAX_ATTEMPTS:
        locked_until = rec.get("locked_until")
        if locked_until and datetime.fromisoformat(locked_until) > datetime.now(timezone.utc):
            raise HTTPException(status_code=429, detail="Too many attempts. Try again later.")


async def _record_fail(identifier: str):
    rec = await _db.login_attempts.find_one({"identifier": identifier})
    count = (rec.get("count", 0) if rec else 0) + 1
    update = {"count": count}
    if count >= MAX_ATTEMPTS:
        update["locked_until"] = (datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_MINUTES)).isoformat()
    await _db.login_attempts.update_one({"identifier": identifier}, {"$set": update}, upsert=True)


async def _clear_attempts(identifier: str):
    await _db.login_attempts.delete_one({"identifier": identifier})


# ----------------------------- router -----------------------------
auth_router = APIRouter(prefix="/api/auth")


@auth_router.post("/register")
async def register(body: RegisterBody, response: Response, current=Depends(get_current_user)):
    # only admins can create team accounts
    if current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create accounts")
    email = body.email.lower()
    if await _db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")
    doc = {
        "email": email,
        "password_hash": hash_password(body.password),
        "name": body.name or email.split("@")[0],
        "role": "member",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    res = await _db.users.insert_one(doc)
    doc["_id"] = res.inserted_id
    return _user_public(doc)


@auth_router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    email = body.email.lower()
    identifier = f"login:{email}"
    await _check_lock(identifier)
    user = await _db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await _record_fail(identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await _clear_attempts(identifier)
    access = create_access_token(str(user["_id"]), email)
    refresh = create_refresh_token(str(user["_id"]))
    _set_cookies(response, access, refresh)
    return {"user": _user_public(user), "access_token": access}


@auth_router.post("/logout")
async def logout(response: Response, current=Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/")
    return {"ok": True}


@auth_router.get("/me")
async def me(current=Depends(get_current_user)):
    return _user_public(current)


@auth_router.get("/users")
async def list_users(current=Depends(get_current_user)):
    users = await _db.users.find({}).to_list(500)
    return [_user_public(u) for u in users]


@auth_router.delete("/users/{user_id}")
async def delete_user(user_id: str, current=Depends(get_current_user)):
    if current.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can delete accounts")
    if str(current["_id"]) == user_id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    await _db.users.delete_one({"_id": ObjectId(user_id)})
    return {"ok": True}


# ----------------------------- startup -----------------------------
async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@example.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await _db.users.find_one({"email": admin_email})
    if existing is None:
        await _db.users.insert_one({
            "email": admin_email,
            "password_hash": hash_password(admin_password),
            "name": "Admin",
            "role": "admin",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    elif not verify_password(admin_password, existing["password_hash"]):
        await _db.users.update_one({"email": admin_email},
                                   {"$set": {"password_hash": hash_password(admin_password)}})


async def ensure_indexes():
    await _db.users.create_index("email", unique=True)
    await _db.login_attempts.create_index("identifier")
