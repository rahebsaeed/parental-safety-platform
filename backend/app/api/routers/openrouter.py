from __future__ import annotations

from typing import Optional
import sqlite3
from fastapi import APIRouter, Body, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.app.classifiers.openrouter_classifier import (
    classify_with_openrouter,
    classify_domains_batch,
    get_cached_classification,
    get_model_status,
    get_openrouter_api_key,
    save_classification,
    save_openrouter_api_key,
    test_openrouter_api_key,
    DEFAULT_CATEGORIES,
    FREE_MODEL,
)
from backend.app.db.session import get_db
from backend.app.db.repository import Repository

router = APIRouter(prefix="/openrouter", tags=["OpenRouter LLM"])


class ApiKeyBody(BaseModel):
    key: Optional[str] = Field(None, description="OpenRouter API key")


class ClassifyBatchBody(BaseModel):
    domains: Optional[list[str]] = Field(None, description="List of domains to classify")


class TestKeyBody(BaseModel):
    key: Optional[str] = Field(None, description="API key to test; omit to test the saved key")


@router.get("/categories")
def get_categories(
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Return the list of available categories."""
    return JSONResponse(content={"categories": DEFAULT_CATEGORIES})


@router.get("/classify/{domain}")
def classify_domain(
    domain: str,
    force: bool = Query(False, description="Force re-classification even if cached"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Classify a domain using OpenRouter's free LLM model."""
    cached = get_cached_classification(domain) if not force else None
    
    if cached:
        return JSONResponse(content={
            "domain": domain,
            "category": cached["category"],
            "confidence": cached["confidence"],
            "model": cached["model"],
            "cached": True,
        })
    
    result = classify_with_openrouter(domain)

    if result["category"] != "UNKNOWN" or get_openrouter_api_key():
        save_classification(domain, result["category"], result["confidence"],
                            result.get("model") or FREE_MODEL)
    
    return JSONResponse(content={
        "domain": domain,
        "category": result["category"],
        "confidence": result["confidence"],
        "reason": result["reason"],
        "cached": False,
    })


@router.post("/classify-batch")
def classify_batch(
    body: ClassifyBatchBody | None = Body(None),
    domains: list[str] | None = Query(None, description="List of domains to classify"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Classify multiple domains using OpenRouter."""
    domain_list = (body.domains if body and body.domains else None) or domains or []
    if not domain_list:
        return JSONResponse(status_code=422, content={"detail": "Provide 'domains' in the JSON body or as query params"})
    results = classify_domains_batch(domain_list)
    return JSONResponse(content={"results": results})


@router.get("/api-key-status")
def get_api_key_status(
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Check if OpenRouter API key is configured, plus free-model health
    (which model serves next, which are cooling down)."""
    key = get_openrouter_api_key()
    return JSONResponse(content={
        "configured": key is not None,
        "has_key": key is not None,
        "models": get_model_status(),
    })


@router.post("/api-key")
def save_api_key(
    body: ApiKeyBody | None = Body(None),
    key: Optional[str] = Query(None, description="OpenRouter API key"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Save the OpenRouter API key (JSON body preferred: {"key": "..."})."""
    resolved = ((body.key or "").strip() if body and body.key else "") or (key.strip() if key else "")
    if not resolved:
        return JSONResponse(status_code=422, content={"detail": "Provide 'key' in the JSON body or as a query param"})
    save_openrouter_api_key(resolved)
    return JSONResponse(content={"message": "API key saved"})


@router.post("/api-key/test")
def test_api_key(
    body: TestKeyBody | None = Body(None),
    key: Optional[str] = Query(None, description="API key to test; omit to test the saved key"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Validate an OpenRouter API key without saving it (or validate the saved key)."""
    candidate = (body.key.strip() if body and body.key else None) or (key.strip() if key else "") or None
    result = test_openrouter_api_key(candidate)
    status = 200 if result.get("ok") else 502
    return JSONResponse(status_code=status, content=result)


@router.get("/top-domains-by-category")
def get_top_domains_by_category(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    limit: int = Query(20, ge=1, le=100),
    start_date: Optional[str] = Query(None, description="Start date filter"),
    end_date: Optional[str] = Query(None, description="End date filter"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    """Get top domains grouped by OpenRouter category."""
    records = Repository.get_top_domains(
        conn, device_id=device_id, limit=limit * 2,
        start_date=start_date, end_date=end_date,
    )
    
    category_domains: dict[str, list[dict]] = {}
    for record in records:
        domain = record.domain if hasattr(record, "domain") else str(record)
        query_count = record.query_count if hasattr(record, "query_count") else 0
        cached = get_cached_classification(domain)
        category = cached["category"] if cached else "UNKNOWN"
        
        if category not in category_domains:
            category_domains[category] = []
        category_domains[category].append({
            "domain": domain,
            "query_count": query_count,
        })
    
    result = []
    for category, domains in sorted(category_domains.items()):
        result.append({
            "category": category,
            "domains": domains[:5],
            "total_queries": sum(d["query_count"] for d in domains),
        })
    
    return JSONResponse(content={"categories": result})
