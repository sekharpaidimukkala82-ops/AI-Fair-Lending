"""
Chat routes – conversational RAG interface for fair lending intelligence.
"""

from __future__ import annotations

import time
from typing import List

from fastapi import APIRouter, HTTPException

from backend.core.monitoring import get_monitoring_engine
from backend.core.rag_engine import RAGEngine
from backend.models.schemas import ChatMessage, ChatRequest, ChatResponse, StatusResponse

router = APIRouter(prefix="/chat", tags=["Chat"])

def _get_rag_engine():
    if not hasattr(_get_rag_engine, "_instance"):
        try:
            _get_rag_engine._instance = RAGEngine()
        except Exception:
            _get_rag_engine._instance = None
    return _get_rag_engine._instance

_monitor = get_monitoring_engine()


@router.post("", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Main conversational endpoint.
    Accepts a list of messages with a session_id, retrieves relevant context
    from the vector store, and generates a response via Gemini.
    """
    if not request.messages:
        raise HTTPException(status_code=400, detail="At least one message is required.")

    # The most recent user message is the query
    user_messages = [m for m in request.messages if m.role == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found in messages list.")

    question = user_messages[-1].content.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # History = all messages except the final user question
    history = request.messages[:-1] if len(request.messages) > 1 else []

    t0 = time.time()
    response = _get_rag_engine().query(
        question=question,
        session_id=request.session_id,
        history=history,
        top_k=request.top_k,
        provider=request.provider,
        model=request.model,
        dataset_id=request.dataset_id,
    )
    elapsed = time.time() - t0

    # Record for monitoring
    _monitor.record_query(request.session_id, question, elapsed)

    return response


@router.get("/history/{session_id}", response_model=List[ChatMessage])
async def get_chat_history(session_id: str):
    """Return the full conversation history for a given session."""
    history = _get_rag_engine().get_history(session_id)
    if not history:
        return []
    return history


@router.delete("/session/{session_id}", response_model=StatusResponse)
async def clear_session(session_id: str):
    """Clear conversation history for a session."""
    _get_rag_engine().clear_session(session_id)
    return StatusResponse(
        status="success",
        message=f"Session '{session_id}' cleared.",
        details={"session_id": session_id},
    )


@router.get("/sessions")
async def list_sessions():
    """Return all active session IDs."""
    sessions = _get_rag_engine().list_sessions()
    return {"sessions": sessions, "count": len(sessions)}
