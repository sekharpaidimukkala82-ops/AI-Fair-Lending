"""
Search routes – semantic search across applicants, loans, and policy documents.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.vector_store import VectorStore
from backend.models.schemas import SearchQuery, SearchResult

router = APIRouter(prefix="/search", tags=["Search"])

def _get_vector_store():
    from backend.core.vector_store import VectorStore
    if not hasattr(_get_vector_store, "_instance") or _get_vector_store._instance is None:
        try:
            _get_vector_store._instance = VectorStore()
        except Exception as e:
            import logging
            logging.getLogger("fair_lending.search").error(f"VectorStore init failed: {e}")
            _get_vector_store._instance = None
    if _get_vector_store._instance is None:
        raise HTTPException(status_code=503, detail="Search index unavailable. Please upload data first.")
    return _get_vector_store._instance


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class ApplicantSearchRequest(BaseModel):
    applicant_id: Optional[str] = None
    description: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)


class LoanSearchRequest(BaseModel):
    loan_amount: Optional[float] = None
    loan_type: Optional[str] = None
    loan_purpose: Optional[str] = None
    description: Optional[str] = None
    top_k: int = Field(default=10, ge=1, le=100)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/similar-applicants", response_model=List[SearchResult])
async def search_similar_applicants(request: ApplicantSearchRequest):
    """
    Find applicants semantically similar to a given applicant_id or description.
    """
    if not request.applicant_id and not request.description:
        raise HTTPException(
            status_code=400,
            detail="Provide at least one of: applicant_id or description.",
        )

    query_text = ""
    if request.description:
        query_text = request.description
    elif request.applicant_id:
        query_text = f"Applicant ID: {request.applicant_id}"

    filters: Optional[Dict[str, Any]] = {"type": "narrative"}

    results = _get_vector_store().search_by_text(
        query_text,
        top_k=request.top_k,
        filters=filters,
    )

    # If searching by ID, boost exact match to top
    if request.applicant_id:
        exact = [r for r in results if str(r.metadata.get("applicant_id", "")) == str(request.applicant_id)]
        others = [r for r in results if r not in exact]
        results = exact + others

    return results[: request.top_k]


@router.post("/similar-loans", response_model=List[SearchResult])
async def search_similar_loans(request: LoanSearchRequest):
    """
    Find loans with similar characteristics.
    """
    query_parts: List[str] = []

    if request.loan_amount:
        query_parts.append(f"Requested loan amount is ${request.loan_amount:,.0f}.")
    if request.loan_type:
        query_parts.append(f"Loan type is {request.loan_type}.")
    if request.loan_purpose:
        query_parts.append(f"Loan purpose is {request.loan_purpose}.")
    if request.description:
        query_parts.append(request.description)

    if not query_parts:
        raise HTTPException(status_code=400, detail="Provide at least one search criterion.")

    query_text = " ".join(query_parts)
    results = _get_vector_store().search_by_text(query_text, top_k=request.top_k)
    return results


@router.post("/policy", response_model=List[SearchResult])
async def search_policy_documents(query: SearchQuery):
    """
    Search policy and compliance documents only.
    """
    filters: Dict[str, Any] = {"type": "document"}
    results = _get_vector_store().search_by_text(
        query.query,
        top_k=query.top_k,
        filters=filters,
    )
    return results


@router.post("/semantic", response_model=List[SearchResult])
async def semantic_search(query: SearchQuery):
    """
    General-purpose semantic search across all indexed documents (narratives + policy docs).
    """
    results = _get_vector_store().search_by_text(
        query.query,
        top_k=query.top_k,
        filters=query.filters,
    )
    return results


@router.get("/stats")
async def search_stats():
    """Return vector store statistics."""
    return _get_vector_store().get_stats()
