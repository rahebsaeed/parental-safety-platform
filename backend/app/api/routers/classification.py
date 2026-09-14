"""Classification API router — Phase 5 endpoints.

GET  /api/v1/classifications/domains              — paginated list of classified domains
GET  /api/v1/classifications/domains/{domain}     — single domain classification
POST /api/v1/classifications/classify             — classify one or many domains on-the-fly
POST /api/v1/classifications/sync                 — classify all unseen dns_query domains
GET  /api/v1/classifications/summary              — category breakdown counts
PUT  /api/v1/classifications/domains/{domain}/override — manual override
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from backend.app.core.auth import get_client_ip
from backend.app.db.session import get_session
from backend.app.db import classification_repo as repo
from backend.app.models.audit import AuditLog
from backend.app.classifiers import explain, CATEGORY_META, Category
from backend.app.schemas.classification import (
    CategorySummaryItem,
    CategorySummaryResponse,
    ClassifyRequest,
    ClassifyResponse,
    ClassifyResult,
    DomainClassificationRead,
    OverrideRequest,
)

router = APIRouter(prefix="/classifications", tags=["Classifications"])


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------

@router.get("/domains", response_model=list[DomainClassificationRead])
def list_classified_domains(
    category: str | None = Query(None, description="Filter by category string"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
) -> list[DomainClassificationRead]:
    """Return all classified domains, optionally filtered by *category*."""
    from backend.app.models.classification import DomainClassification

    q = session.query(DomainClassification)
    if category:
        q = q.filter(DomainClassification.category == category.upper())
    rows = q.order_by(DomainClassification.domain).offset(offset).limit(limit).all()
    return [DomainClassificationRead.model_validate(r) for r in rows]


# ---------------------------------------------------------------------------
# Single domain
# ---------------------------------------------------------------------------

@router.get("/domains/{domain:path}", response_model=DomainClassificationRead)
def get_domain_classification(
    domain: str,
    session: Session = Depends(get_session),
) -> DomainClassificationRead:
    """Return the stored classification for *domain*.

    Falls back to real-time rule evaluation if no row exists yet.
    """
    row = repo.get_classification(session, domain)
    if row:
        return DomainClassificationRead.model_validate(row)

    # Not yet stored — classify on the fly (no DB write)
    info = explain(domain)
    return DomainClassificationRead(
        domain=info["domain"],
        category=info["category"],
        rule_type=info["rule_type"],
        pattern=info["pattern"],
    )


# ---------------------------------------------------------------------------
# Classify on-the-fly (no DB write)
# ---------------------------------------------------------------------------

@router.post("/classify", response_model=ClassifyResponse)
def classify_domains(
    body: ClassifyRequest,
) -> ClassifyResponse:
    """Classify one or many domains in real time without writing to the DB."""
    results = [ClassifyResult(**explain(d)) for d in body.domains]
    return ClassifyResponse(results=results)


# ---------------------------------------------------------------------------
# Sync — classify all unclassified dns_queries
# ---------------------------------------------------------------------------

@router.post("/sync")
def sync_classifications(
    session: Session = Depends(get_session),
) -> dict:
    """Classify all domains in *dns_queries* that have no classification row.

    Returns the number of newly classified domains.
    """
    count = repo.sync_unclassified(session)
    session.commit()
    return {"classified": count, "message": f"Sync complete. {count} domain(s) classified."}


# ---------------------------------------------------------------------------
# Category summary
# ---------------------------------------------------------------------------

@router.get("/summary", response_model=CategorySummaryResponse)
def category_summary(
    session: Session = Depends(get_session),
) -> CategorySummaryResponse:
    """Return category breakdown counts with metadata (label, color, icon)."""
    from backend.app.models.classification import DomainClassification

    raw = repo.category_summary(session)
    total_classified = sum(r["count"] for r in raw if r["category"] != Category.UNCATEGORIZED.value)
    total_unclassified = sum(r["count"] for r in raw if r["category"] == Category.UNCATEGORIZED.value)

    items = []
    for row in raw:
        try:
            cat = Category(row["category"])
        except ValueError:
            cat = Category.UNCATEGORIZED
        meta = CATEGORY_META.get(cat, CATEGORY_META[Category.UNCATEGORIZED])
        items.append(
            CategorySummaryItem(
                category=cat.value,
                count=row["count"],
                label=meta["label"],
                color=meta["color"],
                icon=meta["icon"],
            )
        )

    return CategorySummaryResponse(
        items=items,
        total_classified=total_classified,
        total_unclassified=total_unclassified,
    )


# ---------------------------------------------------------------------------
# Manual override
# ---------------------------------------------------------------------------

@router.put("/domains/{domain:path}/override", response_model=DomainClassificationRead)
def override_classification(
    domain: str,
    body: OverrideRequest,
    request: Request,
    session: Session = Depends(get_session),
) -> DomainClassificationRead:
    """Manually set the category for *domain* (prevents automatic re-classification)."""
    try:
        Category(body.category.upper())
    except ValueError:
        valid = [c.value for c in Category]
        raise HTTPException(
            status_code=422,
            detail=f"Invalid category '{body.category}'. Valid values: {valid}",
        )

    row = repo.set_override(session, domain, body.category.upper(), note=body.note)

    # Record audit log entry
    audit = AuditLog(
        timestamp=datetime.now(timezone.utc).isoformat(),
        actor_ip=get_client_ip(request),
        action="CATEGORY_OVERRIDE",
        target=domain,
        details=json.dumps({"category": body.category.upper(), "note": body.note}),
    )
    session.add(audit)

    session.commit()
    session.refresh(row)
    return DomainClassificationRead.model_validate(row)
