"""
Embedder – generates vector embeddings.

Priority:
1. fastembed  (ONNX-based, no PyTorch – preferred)
2. sentence-transformers (requires working PyTorch)
3. Hash-based fallback (deterministic, works everywhere, no ML quality)

The fallback is safe and makes the rest of the platform fully functional.
Real semantic search quality requires option 1 or 2.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import threading
from typing import List, Optional

logger = logging.getLogger("fair_lending.embedder")

# ---------------------------------------------------------------------------
# Detect available embedding backend — wrap EVERY import in try/except
# ---------------------------------------------------------------------------

_BACKEND: str = "hash"   # "fastembed" | "sbert" | "hash"
_FastTextEmbedding = None
_SentenceTransformer = None

# Allow disabling fastembed via env var (saves ~500MB RAM on free tier hosting)
_FASTEMBED_DISABLED = os.environ.get("DISABLE_FASTEMBED", "").lower() in ("1", "true", "yes")

if not _FASTEMBED_DISABLED:
    try:
        from fastembed import TextEmbedding as _FastTextEmbedding  # type: ignore
        _BACKEND = "fastembed"
        logger.info("Embedder: using fastembed (ONNX backend)")
    except Exception:
        pass
else:
    logger.info("Embedder: fastembed disabled via DISABLE_FASTEMBED env var — using hash fallback")

if _BACKEND == "hash":
    # NOTE: sentence-transformers requires PyTorch which has DLL issues
    # on Microsoft Store Python. Skip it entirely — use hash fallback.
    # To enable SBERT, install Python from python.org (not MS Store).
    logger.warning(
        "Embedder: running with hash-based fallback embeddings. "
        "Semantic search similarity will not reflect true text meaning. "
        "For real embeddings: use Python from python.org and run: pip install fastembed"
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384          # matches all-MiniLM-L6-v2 / bge-small output dim

_instance_lock = threading.Lock()
_instance: Optional["Embedder"] = None


# ---------------------------------------------------------------------------
# Embedder class
# ---------------------------------------------------------------------------

class Embedder:
    """
    Thread-safe singleton embedding wrapper.
    """

    _model = None
    _model_lock = threading.Lock()
    _model_loaded = False

    def __init__(self) -> None:
        if not Embedder._model_loaded:
            with Embedder._model_lock:
                if not Embedder._model_loaded:
                    self._load_model()
                    Embedder._model_loaded = True

    @staticmethod
    def _load_model() -> None:
        if _BACKEND == "fastembed" and _FastTextEmbedding is not None:
            try:
                Embedder._model = _FastTextEmbedding(
                    model_name="BAAI/bge-small-en-v1.5",
                    max_length=512,
                )
                logger.info("Embedder: fastembed model loaded (BAAI/bge-small-en-v1.5)")
            except Exception as e:
                logger.warning(f"Embedder: fastembed load failed ({e}), falling back to hash")

        elif _BACKEND == "sbert" and _SentenceTransformer is not None:
            try:
                Embedder._model = _SentenceTransformer("all-MiniLM-L6-v2")
                logger.info("Embedder: sentence-transformers model loaded (all-MiniLM-L6-v2)")
            except Exception as e:
                logger.warning(f"Embedder: SBERT load failed ({e}), falling back to hash")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed_text(self, text: str) -> List[float]:
        """Return a 384-dimensional embedding vector for a single text."""
        if Embedder._model is not None:
            try:
                if _BACKEND == "fastembed":
                    return list(Embedder._model.embed([text]))[0].tolist()
                else:  # sbert
                    return Embedder._model.encode([text])[0].tolist()
            except Exception as e:
                logger.debug(f"Embedder.embed_text failed: {e}")
        return self._hash_embed(text)

    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        """Return embeddings for a list of texts."""
        if not texts:
            return []
        if Embedder._model is not None:
            try:
                if _BACKEND == "fastembed":
                    return [r.tolist() for r in Embedder._model.embed(texts)]
                else:  # sbert
                    import numpy as np
                    result = Embedder._model.encode(texts)
                    # encode() returns ndarray; convert to list of lists
                    if hasattr(result, "tolist"):
                        return result.tolist()
                    return [list(r) for r in result]
            except Exception as e:
                logger.debug(f"Embedder.embed_batch failed: {e}")
        return [self._hash_embed(t) for t in texts]

    def embedding_dimension(self) -> int:
        """Return the embedding vector dimension."""
        return EMBEDDING_DIM

    def backend(self) -> str:
        """Return the name of the active backend."""
        return _BACKEND

    # ------------------------------------------------------------------
    # Fallback: deterministic hash-based embedding
    # ------------------------------------------------------------------

    @staticmethod
    def _hash_embed(text: str, dim: int = EMBEDDING_DIM) -> List[float]:
        """
        Deterministic pseudo-embedding based on character trigram hashing.
        NOT suitable for production semantic search — use for development only.
        """
        vec = [0.0] * dim
        text = text.lower().strip()
        if not text:
            return vec

        for i in range(len(text) - 2):
            trigram = text[i : i + 3]
            h = int(hashlib.md5(trigram.encode()).hexdigest(), 16)
            idx = h % dim
            vec[idx] += 1.0

        # L2 normalise
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]


def get_embedder() -> Embedder:
    """Return the singleton Embedder instance."""
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = Embedder()
    return _instance
