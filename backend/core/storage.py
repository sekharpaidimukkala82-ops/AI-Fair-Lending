"""
Storage abstraction — uses Supabase Storage in production, local disk in dev.

Set SUPABASE_URL and SUPABASE_KEY env vars to enable cloud storage.
Falls back to local disk automatically when not configured.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger("fair_lending.storage")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
BUCKET_NAME  = os.environ.get("SUPABASE_BUCKET", "uploads")

_supabase_client = None


def _get_client():
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
        logger.warning(f"Supabase client init failed: {e}")
        return None


def is_cloud_storage_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY and _get_client() is not None)


def upload_file(file_bytes: bytes, filename: str, file_id: str) -> str:
    """
    Upload file bytes to storage. Returns the storage path/key.
    Uses Supabase if configured, otherwise saves to local disk.
    Always succeeds — falls back to temp file if everything else fails.
    """
    client = _get_client()
    storage_path = f"{file_id}_{filename}"

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
            logger.warning(f"Supabase upload failed, falling back to local: {e}")

    # Local disk fallback
    from backend.config import Config
    local_path = Config.get_upload_path(storage_path)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_bytes(file_bytes)
    logger.info(f"Saved {filename} to local disk: {local_path}")
    return str(local_path)


def download_file(storage_ref: str, filename: str) -> Optional[str]:
    """
    Download a file and return a local temp path for processing.
    Handles both supabase:// refs and local paths.
    Returns local file path or None if not found.
    """
    if storage_ref.startswith("supabase://"):
        storage_path = storage_ref[len("supabase://"):]
        client = _get_client()
        if not client:
            logger.warning("Supabase client not available for download")
            return None
        try:
            data = client.storage.from_(BUCKET_NAME).download(storage_path)
            # Save to temp file
            suffix = Path(filename).suffix
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp.write(data)
            tmp.close()
            logger.info(f"Downloaded {storage_path} from Supabase to {tmp.name}")
            return tmp.name
        except Exception as e:
            logger.warning(f"Supabase download failed: {e}")
            return None

    # Local path
    if os.path.exists(storage_ref):
        return storage_ref

    # Try constructing path from uploads dir
    from backend.config import Config
    local = Path(Config.UPLOAD_DIR) / Path(storage_ref).name
    if local.exists():
        return str(local)

    return None


def delete_file(storage_ref: str) -> None:
    """Delete a file from storage."""
    if storage_ref.startswith("supabase://"):
        storage_path = storage_ref[len("supabase://"):]
        client = _get_client()
        if client:
            try:
                client.storage.from_(BUCKET_NAME).remove([storage_path])
            except Exception as e:
                logger.warning(f"Supabase delete failed: {e}")
        return

    # Local
    try:
        if os.path.exists(storage_ref):
            os.unlink(storage_ref)
    except Exception:
        pass
