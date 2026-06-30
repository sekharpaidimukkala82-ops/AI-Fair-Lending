"""
Vector Store – simple file-based vector store using numpy dot-product search.

Replaces ChromaDB which crashes on this system due to ONNX runtime issues.
Stores embeddings as a .npz file — fast enough for datasets up to ~100k rows.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from backend.config import Config
from backend.core.embedder import Embedder
from backend.models.schemas import DocumentChunk, SearchResult

logger = logging.getLogger("fair_lending.vector_store")


class VectorStore:
    """
    File-backed vector store using cosine similarity search.
    Persists to {CHROMA_PERSIST_DIR}/vectors.npz and vectors_meta.json.
    """

    def __init__(self, collection_name: Optional[str] = None) -> None:
        self._collection_name = collection_name or Config.COLLECTION_NAME
        self._persist_dir = Path(Config.CHROMA_PERSIST_DIR)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._npz_path = self._persist_dir / f"{self._collection_name}.npz"
        self._meta_path = self._persist_dir / f"{self._collection_name}_meta.json"
        self._embedder = Embedder()

        # In-memory store
        self._ids: List[str] = []
        self._embeddings: Optional[np.ndarray] = None  # shape (N, D)
        self._documents: List[str] = []
        self._metadatas: List[Dict[str, Any]] = []

        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load persisted data from disk."""
        try:
            if self._npz_path.exists() and self._meta_path.exists():
                data = np.load(str(self._npz_path), allow_pickle=False)
                self._embeddings = data["embeddings"]
                with open(self._meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                self._ids = meta["ids"]
                self._documents = meta["documents"]
                self._metadatas = meta["metadatas"]
                logger.info(f"VectorStore loaded {len(self._ids)} vectors from disk")
        except Exception as e:
            logger.warning(f"VectorStore load failed (starting fresh): {e}")
            self._ids = []
            self._embeddings = None
            self._documents = []
            self._metadatas = []

    def _save(self) -> None:
        """Persist current data to disk."""
        try:
            if self._embeddings is not None and len(self._ids) > 0:
                np.savez_compressed(str(self._npz_path), embeddings=self._embeddings)
                with open(self._meta_path, "w", encoding="utf-8") as f:
                    json.dump({
                        "ids": self._ids,
                        "documents": self._documents,
                        "metadatas": self._metadatas,
                    }, f)
        except Exception as e:
            logger.warning(f"VectorStore save failed: {e}")

    # ------------------------------------------------------------------
    # Collection management (compatibility shim)
    # ------------------------------------------------------------------

    def get_or_create_collection(self, name: str):
        """Compatibility shim — no-op for file-based store."""
        return self

    def delete_collection(self) -> None:
        """Clear all data."""
        self._ids = []
        self._embeddings = None
        self._documents = []
        self._metadatas = []
        try:
            self._npz_path.unlink(missing_ok=True)
            self._meta_path.unlink(missing_ok=True)
        except Exception:
            pass

    def count(self) -> int:
        return len(self._ids)

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_documents(
        self,
        chunks: List[DocumentChunk],
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        if not chunks:
            return

        if embeddings is None:
            texts = [c.text for c in chunks]
            embeddings = self._embedder.embed_batch(texts)

        new_embs = np.array(embeddings, dtype=np.float32)

        # Remove duplicates by id
        existing_ids = set(self._ids)
        filtered_chunks, filtered_embs = [], []
        for chunk, emb in zip(chunks, new_embs):
            if chunk.chunk_id not in existing_ids:
                filtered_chunks.append(chunk)
                filtered_embs.append(emb)
            else:
                # Update existing
                idx = self._ids.index(chunk.chunk_id)
                self._embeddings[idx] = emb
                self._documents[idx] = chunk.text
                self._metadatas[idx] = {
                    **{k: str(v) for k, v in chunk.metadata.items()},
                    "source": chunk.source,
                    "chunk_index": str(chunk.chunk_index),
                    "total_chunks": str(chunk.total_chunks),
                }

        if filtered_chunks:
            new_arr = np.array(filtered_embs, dtype=np.float32)
            self._ids.extend([c.chunk_id for c in filtered_chunks])
            self._documents.extend([c.text for c in filtered_chunks])
            self._metadatas.extend([
                {
                    **{k: str(v) for k, v in c.metadata.items()},
                    "source": c.source,
                    "chunk_index": str(c.chunk_index),
                    "total_chunks": str(c.total_chunks),
                }
                for c in filtered_chunks
            ])
            self._embeddings = (
                np.vstack([self._embeddings, new_arr])
                if self._embeddings is not None
                else new_arr
            )

        self._save()
        logger.info(f"VectorStore: {len(self._ids)} total vectors")

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def search(
        self,
        query_embedding: List[float],
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        if self._embeddings is None or len(self._ids) == 0:
            return []

        q = np.array(query_embedding, dtype=np.float32)
        # Cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-9, norms)
        normed = self._embeddings / norms
        q_norm = q / (np.linalg.norm(q) + 1e-9)
        scores = normed @ q_norm  # shape (N,)

        # Apply metadata filters
        if filters:
            mask = np.ones(len(self._ids), dtype=bool)
            for k, v in filters.items():
                for i, meta in enumerate(self._metadatas):
                    if str(meta.get(k, "")) != str(v):
                        mask[i] = False
            scores = scores * mask

        top_indices = np.argsort(scores)[::-1][:top_k]
        results = []
        for idx in top_indices:
            sim = float(scores[idx])
            if sim <= 0:
                continue
            results.append(SearchResult(
                id=self._ids[idx],
                text=self._documents[idx],
                score=round(sim, 4),
                metadata=self._metadatas[idx],
                source=self._metadatas[idx].get("source"),
            ))
        return results

    def search_by_text(
        self,
        query_text: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        embedding = self._embedder.embed_text(query_text)
        return self.search(embedding, top_k=top_k, filters=filters)

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        return {
            "collection_name": self._collection_name,
            "document_count": len(self._ids),
            "embedding_dimension": self._embedder.embedding_dimension(),
            "persist_dir": str(self._persist_dir),
            "backend": "file-based (numpy)",
        }
