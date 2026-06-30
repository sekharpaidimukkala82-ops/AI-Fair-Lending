"""Authentication routes: register, login, profile, users."""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Depends, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from backend.auth.security import hash_password, verify_password, create_access_token
from backend.auth.dependencies import get_current_user, require_role
from backend.database.connection import get_db
from backend.database.crud import (
    create_user, get_user_by_email, get_user_by_username,
    update_user_login, list_users, log_action
)
from backend.database.models import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


class RegisterRequest(BaseModel):
    email: str = Field(..., description="User email")
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8)
    full_name: str = Field(default="")
    institution: str = Field(default="")
    role: str = Field(default="analyst")

class LoginRequest(BaseModel):
    email: str
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    username: str
    role: str
    full_name: str
    institution: str

class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: str
    role: str
    institution: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime]


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """Register a new user."""
    if await get_user_by_email(db, request.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    if await get_user_by_username(db, request.username):
        raise HTTPException(status_code=400, detail="Username already taken")
    user = await create_user(
        db, email=request.email, username=request.username,
        hashed_password=hash_password(request.password),
        full_name=request.full_name, role=request.role,
        institution=request.institution,
    )
    await log_action(db, "user.register", user_id=user.id, resource_type="user", resource_id=user.id)
    token = create_access_token({"sub": user.id, "role": user.role})
    return TokenResponse(access_token=token, user_id=user.id, username=user.username,
                         role=user.role, full_name=user.full_name or "", institution=user.institution or "")


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    """Login and receive a JWT token."""
    user = await get_user_by_email(db, request.email)
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is disabled")
    await update_user_login(db, user.id)
    await log_action(db, "user.login", user_id=user.id, resource_type="user", resource_id=user.id)
    token = create_access_token({"sub": user.id, "role": user.role})

    # Auto-load this user's saved API keys into memory
    try:
        from backend.database.crud import get_user_api_keys
        from backend.core.key_encryption import decrypt_key
        from backend.core import ai_provider as _ai
        keys = await get_user_api_keys(db, user.id)
        for k in keys:
            plain = decrypt_key(k.encrypted_key)
            if plain:
                _ai.set_api_key(k.provider, plain)
                if k.active_model:
                    _ai.set_active_provider(k.provider, k.active_model)
    except Exception:
        pass

    return TokenResponse(access_token=token, user_id=user.id, username=user.username,
                         role=user.role, full_name=user.full_name or "", institution=user.institution or "")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """Get current user profile."""
    return UserResponse(
        id=current_user.id, email=current_user.email, username=current_user.username,
        full_name=current_user.full_name or "", role=current_user.role,
        institution=current_user.institution or "", is_active=current_user.is_active,
        created_at=current_user.created_at, last_login=current_user.last_login
    )


@router.get("/users", response_model=List[UserResponse])
async def get_users(
    current_user: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db)
):
    """List all users (admin only)."""
    users = await list_users(db)
    return [UserResponse(id=u.id, email=u.email, username=u.username, full_name=u.full_name or "",
                         role=u.role, institution=u.institution or "", is_active=u.is_active,
                         created_at=u.created_at, last_login=u.last_login) for u in users]


@router.post("/logout")
async def logout(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Logout (client should discard token)."""
    await log_action(db, "user.logout", user_id=current_user.id)
    return {"status": "logged out", "message": "Token invalidated on client side"}
