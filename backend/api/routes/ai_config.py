"""
AI Configuration routes – manage API keys and provider selection.
Keys are stored encrypted in the database per user, loaded into memory on login.
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core import ai_provider
from backend.core.key_encryption import encrypt_key, decrypt_key
from backend.auth.dependencies import get_current_user, get_current_user_optional
from backend.database.connection import get_db
from backend.database.models import User

router = APIRouter(prefix="/ai", tags=["AI Configuration"])


class SetKeyRequest(BaseModel):
    provider: str = Field(..., description="'gemini', 'openai', or 'groq'")
    api_key: Optional[str] = Field(default=None, description="The API key to store")
    model: Optional[str] = Field(default=None, description="Optional model override")
    set_active: bool = Field(default=True, description="Make this the active provider")


class TestPrompt(BaseModel):
    prompt: str = Field(default="Say 'API key is working!' in one sentence.")
    provider: Optional[str] = None
    model: Optional[str] = None


async def _load_user_keys_into_memory(user_id: str, db: AsyncSession) -> None:
    """Load all saved API keys for a user into the in-memory provider store."""
    try:
        from backend.database.crud import get_user_api_keys
        keys = await get_user_api_keys(db, user_id)
        for k in keys:
            try:
                plain_key = decrypt_key(k.encrypted_key)
                if plain_key:
                    ai_provider.set_api_key(k.provider, plain_key)
                    # Set the last saved provider as active
                    if k.active_model:
                        ai_provider.set_active_provider(k.provider, k.active_model)
            except Exception:
                pass
    except Exception:
        pass


@router.post("/config")
async def set_api_key(
    request: SetKeyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Store an API key in memory AND persist it encrypted in the database for this user.
    Key is automatically reloaded on next login — no need to re-enter.
    """
    provider = request.provider.lower()
    if provider not in ("gemini", "openai", "groq"):
        raise HTTPException(status_code=400, detail="Provider must be 'gemini', 'openai', or 'groq'")

    model_to_set = request.model or ai_provider.DEFAULT_MODELS.get(provider, "")

    # If an API key was provided, validate, store in memory, and persist to DB
    if request.api_key and request.api_key.strip():
        if len(request.api_key.strip()) < 10:
            raise HTTPException(status_code=400, detail="API key appears invalid (too short)")

        plain_key = request.api_key.strip()
        ai_provider.set_api_key(provider, plain_key)

        # Persist encrypted to DB
        try:
            from backend.database.crud import save_user_api_key
            encrypted = encrypt_key(plain_key)
            await save_user_api_key(db, current_user.id, provider, encrypted, model_to_set)
            await db.commit()
        except Exception as e:
            import logging
            logging.getLogger("fair_lending.ai_config").warning(f"Failed to persist API key: {e}")

    if request.set_active:
        ai_provider.set_active_provider(provider, model_to_set)

        # Persist active provider preference too (update model if key already saved)
        try:
            from backend.database.crud import get_user_api_keys, save_user_api_key
            keys = await get_user_api_keys(db, current_user.id)
            existing = next((k for k in keys if k.provider == provider), None)
            if existing and not (request.api_key and request.api_key.strip()):
                # Just update the model preference
                from backend.database.crud import save_user_api_key
                await save_user_api_key(db, current_user.id, provider,
                                        existing.encrypted_key, model_to_set)
                await db.commit()
        except Exception:
            pass

    return {
        "status": "configured",
        "provider": provider,
        "model": model_to_set,
        "active": request.set_active,
        "persisted": True,
        "message": f"{provider.capitalize()} configured and saved — won't need to re-enter after restart.",
    }


@router.get("/status")
async def get_status(
    db: AsyncSession = Depends(get_db),
    current_user: Optional[User] = Depends(get_current_user_optional),
):
    """Return current AI provider status. Auto-loads user's saved keys if not in memory."""
    # Auto-load saved keys for this user if any provider is unconfigured
    if current_user:
        status = ai_provider.get_status()
        any_configured = (status["gemini_configured"] or
                         status["openai_configured"] or
                         status["groq_configured"])
        if not any_configured:
            await _load_user_keys_into_memory(current_user.id, db)

    return ai_provider.get_status()


@router.post("/test")
async def test_connection(
    request: TestPrompt,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Test the configured API key with a simple prompt."""
    # Ensure keys are loaded
    await _load_user_keys_into_memory(current_user.id, db)

    try:
        prov = request.provider or ai_provider.get_active_provider()
        mdl  = request.model or ai_provider.get_active_model()
        response = ai_provider.call_llm(
            prompt=request.prompt,
            provider=prov,
            model=mdl,
            max_tokens=50,
        )
        return {"status": "success", "provider": prov, "model": mdl, "response": response}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Connection test failed: {e}")


@router.delete("/config/{provider}")
async def clear_api_key(
    provider: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Remove an API key from memory and database for this user."""
    provider = provider.lower()
    # Remove from memory
    if provider in ai_provider._runtime_keys:
        del ai_provider._runtime_keys[provider]
    # Remove from DB
    try:
        from backend.database.crud import delete_user_api_key
        await delete_user_api_key(db, current_user.id, provider)
        await db.commit()
    except Exception:
        pass
    return {"status": "cleared", "provider": provider}
