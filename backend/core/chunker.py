"""
Text Chunker – splits long texts into overlapping chunks suitable for embedding.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List

from backend.models.schemas import DocumentChunk


class TextChunker:
    """
    Token-aware (character-proxy) text chunking with configurable size and overlap.
    """

    def __init__(
        self,
        default_chunk_size: int = 750,
        default_overlap: int = 100,
    ) -> None:
        self.default_chunk_size = default_chunk_size
        self.default_overlap = default_overlap

    # ------------------------------------------------------------------
    # Core splitting logic
    # ------------------------------------------------------------------

    def chunk_text(
        self,
        text: str,
        chunk_size: int = 750,
        overlap: int = 100,
    ) -> List[str]:
        """
        Split *text* into chunks of approximately *chunk_size* characters
        with *overlap* characters of context carried forward.

        Splitting is word-boundary-aware: chunks never break mid-word.

        Parameters
        ----------
        text       : Input string to chunk.
        chunk_size : Target maximum characters per chunk.
        overlap    : Number of characters from the previous chunk to include
                     at the start of the next chunk.

        Returns
        -------
        List of non-empty string chunks.
        """
        if not text or not text.strip():
            return []

        text = text.strip()

        if len(text) <= chunk_size:
            return [text]

        chunks: List[str] = []
        words = text.split()
        current_words: List[str] = []
        current_len: int = 0

        for word in words:
            word_len = len(word) + 1  # +1 for the space
            if current_len + word_len > chunk_size and current_words:
                # Finalise current chunk
                chunk_text = " ".join(current_words)
                chunks.append(chunk_text)

                # Build overlap: keep trailing words totalling ~overlap chars
                overlap_words: List[str] = []
                overlap_len = 0
                for w in reversed(current_words):
                    if overlap_len + len(w) + 1 > overlap:
                        break
                    overlap_words.insert(0, w)
                    overlap_len += len(w) + 1

                current_words = overlap_words
                current_len = overlap_len

            current_words.append(word)
            current_len += word_len

        if current_words:
            chunks.append(" ".join(current_words))

        return [c for c in chunks if c.strip()]

    # ------------------------------------------------------------------
    # Document → DocumentChunk list
    # ------------------------------------------------------------------

    def chunk_document(
        self,
        doc_text: str,
        metadata: Dict[str, Any],
        chunk_size: int = 750,
        overlap: int = 100,
    ) -> List[DocumentChunk]:
        """
        Chunk a single document text and wrap each chunk in a DocumentChunk.

        Parameters
        ----------
        doc_text   : Full text of the document.
        metadata   : Metadata dict attached to every chunk (source, title, etc.).
        chunk_size : Target characters per chunk.
        overlap    : Overlap characters between consecutive chunks.

        Returns
        -------
        List[DocumentChunk]
        """
        source = metadata.get("source", metadata.get("filename", "unknown"))
        raw_chunks = self.chunk_text(doc_text, chunk_size=chunk_size, overlap=overlap)
        total = len(raw_chunks)

        doc_chunks: List[DocumentChunk] = []
        for idx, text in enumerate(raw_chunks):
            chunk_id = str(uuid.uuid4())
            chunk_meta = {
                **metadata,
                "chunk_index": idx,
                "total_chunks": total,
                "chunk_size_chars": len(text),
            }
            doc_chunks.append(
                DocumentChunk(
                    chunk_id=chunk_id,
                    text=text,
                    metadata=chunk_meta,
                    source=source,
                    chunk_index=idx,
                    total_chunks=total,
                )
            )

        return doc_chunks

    # ------------------------------------------------------------------
    # Batch chunking
    # ------------------------------------------------------------------

    def chunk_batch(
        self,
        documents: List[Dict[str, Any]],
        chunk_size: int = 750,
        overlap: int = 100,
    ) -> List[DocumentChunk]:
        """
        Chunk a list of document dicts.

        Each dict must have:
          - "text"     : str – the document body
          - "metadata" : dict – metadata (source, title, etc.)

        Parameters
        ----------
        documents  : List of {"text": ..., "metadata": ...} dicts.
        chunk_size : Target characters per chunk.
        overlap    : Overlap characters.

        Returns
        -------
        Flat list of DocumentChunk objects across all documents.
        """
        all_chunks: List[DocumentChunk] = []
        for doc in documents:
            text = doc.get("text", "")
            metadata = doc.get("metadata", {})
            chunks = self.chunk_document(
                text,
                metadata,
                chunk_size=chunk_size,
                overlap=overlap,
            )
            all_chunks.extend(chunks)
        return all_chunks
