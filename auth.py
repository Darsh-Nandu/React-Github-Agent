"""
auth.py

JWT authentication for the ReAct GitHub Agent.
Provides user registration, login, and token verification.

Set AUTH_SECRET_KEY in your .env to a strong random string.
Set AUTH_ENABLED=false to disable auth entirely (dev mode).
"""

import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

SECRET_KEY = os.getenv(
    "AUTH_SECRET_KEY", "change-me-in-production-use-a-long-random-string"
)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("AUTH_TOKEN_EXPIRE_MINUTES", "60"))
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() != "false"

pwd_context = CryptContext(schemes=["sha256_crypt"], deprecated="auto")
bearer_scheme = HTTPBearer(auto_error=False)

# In-memory user store (swap for a real DB in production)
_users: dict[str, dict] = {}


# Models


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str


class TokenData(BaseModel):
    user_id: str
    username: str


# Helpers


def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def _create_token(user_id: str, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": user_id, "username": username, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def _decode_token(token: str) -> TokenData:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        username: str = payload.get("username")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")
        return TokenData(user_id=user_id, username=username)
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


# Public API


def register_user(username: str, password: str) -> TokenResponse:
    if username in _users:
        raise HTTPException(status_code=400, detail="Username already taken")
    user_id = str(uuid.uuid4())
    _users[username] = {"user_id": user_id, "hashed_password": _hash_password(password)}
    token = _create_token(user_id=user_id, username=username)
    return TokenResponse(access_token=token, user_id=user_id, username=username)


def login_user(username: str, password: str) -> TokenResponse:
    user = _users.get(username)
    if not user or not _verify_password(password, user["hashed_password"]):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token = _create_token(user_id=user["user_id"], username=username)
    return TokenResponse(access_token=token, user_id=user["user_id"], username=username)


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> TokenData:
    """FastAPI dependency. Returns token data or falls back to guest when auth is disabled."""
    if not AUTH_ENABLED:
        return TokenData(user_id="default-user", username="guest")
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token(credentials.credentials)
