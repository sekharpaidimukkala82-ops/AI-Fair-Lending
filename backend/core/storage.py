"""
Storage abstraction — local disk only (SQLite + local uploads folder).

This is the production-ready storage for Railway/Render free tier:
- Files are saved to the uploads/ directory on disk
- No external storage service required
- Works with both local dev and cloud deployments that have persistent volumes

If you later want Supabase: set SUPABASE_URL + SUPABASE_KEY env vars.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fair_lending.storage")

# Supabase is optional — only used if both env vars are set
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BUCKET_NAME  = os.environ.get("SUPABASE_BUCKET", "uploads")

_supabase_client = None


def _get_client():
    """Return Supabase client only if fully configured. Otherwise None."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase storage client initialized")
        return _supabase_client
    except Exception as e:
        logger.warning(f"Supabase client init failed (using local storage): {e}")
        return None


def is_cloud_storage_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and _get_client() is not None)


def upload_file(file_bytes: bytes, filename: str, file_id: str) -> str:
    """
    Save file bytes to local disk. Returns absolute local path.
    Tries Supabase first if configured, falls back to local disk.
    """
    storage_path = f"{file_id}_{filename}"

    # Try Supabase only if configured
    client = _get_client()
    if client:
        try:
            client.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": "application/octet-stream", "upsert": "true"},
            )
            logger.info(f"Uploaded {filename} to Supabase: {storage_path}")
            return f"supabase://{storage_path}"
        except Exception as e:
            logger.warning(f"Supabase upload failed, falling back to local disk: {e}")

    # Always use local disk
    from backend.config import Config
    local_path = Config.get_upload_path(storage_path)
    Path(local_path).parent.mkdir(parents=True, exist_ok=True)
    Path(local_path).write_bytes(file_bytes)
    logger.info(f"Saved {filename} to local disk: {local_path}")
    return str(local_path)


def download_file(storage_ref: str, filename: str = "") -> Optional[str]:
    """
    Return a local file path for the given storage reference.
    Handles supabase:// refs and local paths.
    Returns the local path if found, None if not found.
    """
    if not storage_ref:
        return None

    if storage_ref.startswith("supabase://"):
        storage_path = storage_ref[len("supabase://"):]
        client = _get_client()
        if not client:
            logger.warning("Supabase not configured — cannot download from supabase:// ref")
            return None
        try:
            data = client.storage.from_(BUCKET_NAME).download(storage_path)
            suffix = Path(filename or storage_path).suffix or ".csv"
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            logger.info(f"Downloaded from Supabase: {storage_path} → {tmp.name}")
            return tmp.name
        except Exception as e:
            logger.warning(f"Supabase download failed: {e}")
            return None

    # Local path — check as-is first
    if os.path.exists(storage_ref):
        return storage_ref

    # Try finding by basename in uploads dir
    from backend.config import Config
    local = Path(Config.UPLOAD_DIR) / Path(storage_ref).name
    if local.exists():
        return str(local)

    return None


def delete_file(storage_ref: str) -> None:
    """Delete a file from storage."""
    if not storage_ref:
        return

    if storage_ref.startswith("supabase://"):
        storage_path = storage_ref[len("supabase://"):]
        client = _get_client()
        if client:
            try:
                client.storage.from_(BUCKET_NAME).remove([storage_path])
            except Exception as e:
                logger.warning(f"Supabase delete failed: {e}")
        return

    try:
        if os.path.exists(storage_ref):
            os.unlink(storage_ref)
    except Exception:
        pass
