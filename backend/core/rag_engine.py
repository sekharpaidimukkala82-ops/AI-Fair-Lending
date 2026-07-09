"""
RAG Engine – combines ChromaDB retrieval with AI generation (Gemini or OpenAI).
Uses the unified ai_provider module so the model can be switched at runtime.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any, Dict, List, Optional

from backend.config import Config
from backend.core import ai_provider
from backend.core.vector_store import VectorStore
from backend.models.schemas import ChatMessage, ChatResponse, SearchResult


SYSTEM_PROMPT = """You are a Fair Lending Intelligence Assistant – an expert AI built into the
FairLend AI Enterprise Platform, specialising in HMDA data analysis, fair lending compliance,
and mortgage underwriting.

## Your Role
Answer questions in two modes:

**Mode 1 — Platform questions** (e.g. "how does ML work here?", "what features does this platform have?"):
Answer from your knowledge of the FairLend AI platform. The platform includes:
- ML Engine: RandomForest approval-prediction model, Isolation Forest anomaly detection, K-Means applicant segmentation
- Fairness Engine: Disparate Impact (80% rule), Statistical Parity Difference, Equalized Odds analysis across race, sex, and ethnicity
- RAG Chat: Semantic search over uploaded lending datasets using ChromaDB vector store + AI generation
- Reports: Auto-generated PDF/HTML compliance reports with narrative summaries
- SHAP explainability: Feature importance and individual prediction explanations
- Multi-provider AI: Google Gemini, OpenAI GPT, Groq (free LLaMA/Mixtral)
- Supports: HMDA LAR files, German Credit, generic CSV lending datasets

**Mode 2 — Data questions** (e.g. "what is the approval rate?", "show disparities by race"):
Answer strictly from the Retrieved Context below. Quote statistics exactly. If context is
insufficient, say so — do not fabricate data.

## Guidelines
1. Never confuse platform capabilities with the user's uploaded dataset contents.
2. When discussing protected classes (race, sex, age, national origin), be precise and objective.
3. Flag any potential fair lending concerns you observe in the data.
4. Use plain language suitable for both compliance officers and business analysts.
5. If a question mixes both modes, answer the platform part from knowledge and the data part from context.

## Retrieved Context (from uploaded dataset)
{context}

## Conversation History
{history}
"""


class RAGEngine:
    def __init__(self) -> None:
        self._vector_store = VectorStore()
        self._session_memory: Dict[str, List[ChatMessage]] = defaultdict(list)

    def build_context(self, chunks: List[SearchResult]) -> str:
        if not chunks:
            return "No relevant documents were retrieved."
        parts = []
        for i, chunk in enumerate(chunks, 1):
            source = chunk.metadata.get("source", "unknown")
            parts.append(f"[{i}] (source: {source}, relevance: {round(chunk.score, 3)})\n{chunk.text}")
        return "\n\n".join(parts)

    def _format_history(self, history: List[ChatMessage]) -> str:
        if not history:
            return "No prior conversation."
        return "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-10:])

    def query(
        self,
        question: str,
        session_id: str = "default",
        history: Optional[List[ChatMessage]] = None,
        top_k: int = 10,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        dataset_id: Optional[str] = None,
    ) -> ChatResponse:
        t0 = time.time()

        # Filter search to the active dataset if provided
        filters = {"dataset_id": dataset_id} if dataset_id else None
        chunks = self._vector_store.search_by_text(question, top_k=top_k, filters=filters)

        # If dataset-filtered search returns nothing, try without filter (fallback)
        if not chunks and filters:
            chunks = self._vector_store.search_by_text(question, top_k=top_k)

        context = self.build_context(chunks)

        # If still no context and dataset_id is given, generate a data summary directly from the file
        dataset_summary = ""
        if dataset_id and (not chunks or len(chunks) < 3):
            dataset_summary = self._build_dataset_summary(dataset_id)

        if history is None:
            history = self._session_memory[session_id][-(Config.SESSION_HISTORY_LIMIT):]
        else:
            stored = self._session_memory[session_id][-(Config.SESSION_HISTORY_LIMIT // 2):]
            history = stored + list(history)

        # Build prompt with dataset summary if available
        context_section = context
        if dataset_summary:
            context_section = f"DATASET SUMMARY (direct from uploaded file):\n{dataset_summary}\n\nADDITIONAL CONTEXT FROM INDEX:\n{context}"

        full_prompt = (
            SYSTEM_PROMPT.format(context=context_section, history=self._format_history(history))
            + f"\n\nUSER QUESTION: {question}\n\nASSISTANT:"
        )

        try:
            answer = ai_provider.call_llm(
                full_prompt,
                provider=provider,
                model=model,
                max_tokens=Config.GEMINI_MAX_TOKENS
            )
        except ValueError as e:
            answer = (
                f"⚠ {e}\n\n"
                f"**Retrieved context ({len(chunks)} chunks):**\n{context}"
            )

        self._session_memory[session_id].append(ChatMessage(role="user", content=question))
        self._session_memory[session_id].append(ChatMessage(role="assistant", content=answer))

        if len(self._session_memory[session_id]) > Config.SESSION_HISTORY_LIMIT:
            self._session_memory[session_id] = self._session_memory[session_id][-Config.SESSION_HISTORY_LIMIT:]

        return ChatResponse(
            answer=answer,
            sources=chunks,
            session_id=session_id,
            metadata={
                "chunks_retrieved": len(chunks),
                "provider": ai_provider.get_active_provider(),
                "model": ai_provider.get_active_model(),
            },
            response_time_seconds=round(time.time() - t0, 3),
        )

    def _build_dataset_summary(self, dataset_id: str) -> str:
        """
        Build a concise data summary directly from the uploaded file.
        Used when vector index has no chunks for this dataset.
        Returns a plain-text summary the LLM can reason about.
        """
        try:
            from backend.api.routes.fairness import _load_dataset
            from backend.core.fairness_engine import FairnessEngine
            import pandas as pd

            df = _load_dataset(dataset_id)
            engine = FairnessEngine()

            lines = [
                f"Dataset: {len(df)} rows, {len(df.columns)} columns",
                f"Columns: {', '.join(df.columns[:20])}",
            ]

            # Outcome column stats
            outcome_col = engine._detect_outcome_col(df)
            if outcome_col:
                val_counts = df[outcome_col].value_counts()
                lines.append(f"Outcome column '{outcome_col}': {val_counts.to_dict()}")
                total = len(df)
                approved = df[outcome_col].apply(engine._is_approval).sum()
                lines.append(f"Overall approval rate: {approved}/{total} = {approved/total:.1%}")

            # Protected class stats
            protected = engine._detect_all_protected_cols(df)
            for field, col in protected.items():
                if outcome_col:
                    rates = engine.compute_approval_rates_by_group(df, col, outcome_col, field_name=field)
                    if rates:
                        rates_str = ', '.join(f"{g}: {r:.1%}" for g, r in sorted(rates.items()))
                        lines.append(f"Approval rates by {field} ({col}): {rates_str}")

            # Numeric column stats
            numeric_cols = df.select_dtypes(include=['number']).columns[:6]
            for col in numeric_cols:
                if col not in [outcome_col]:
                    lines.append(f"{col}: min={df[col].min():.0f}, max={df[col].max():.0f}, mean={df[col].mean():.0f}")

            return '\n'.join(lines)
        except Exception as e:
            import logging
            logging.getLogger("fair_lending.rag").warning(f"Dataset summary failed: {e}")
            return ""

    def get_history(self, session_id: str) -> List[ChatMessage]:
        return list(self._session_memory.get(session_id, []))

    def clear_session(self, session_id: str) -> None:
        if session_id in self._session_memory:
            del self._session_memory[session_id]

    def list_sessions(self) -> List[str]:
        return list(self._session_memory.keys())
