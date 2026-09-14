from __future__ import annotations

from typing import Optional
import sqlite3
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from backend.app.classifiers.domain_security import (
    DomainSecurity,
    SecurityLevel,
    classify_domain,
    get_subject,
    SECURITY_META,
)
from backend.app.db.session import get_db
from backend.app.db.repository import Repository

router = APIRouter(prefix="/domains", tags=["Domain Security"])


def _stored_rule_map(conn, domains):
    """Map normalized domain -> stored rule category for the given domains.

    Stored rules (static, AI-persisted, manual overrides) are reviewed
    verdicts and take precedence over keyword heuristics in these endpoints.
    """
    wanted = {d.lower().rstrip(".") for d in domains if d}
    if not wanted:
        return {}
    placeholders = ",".join("?" for _ in wanted)
    try:
        rows = conn.execute(
            "SELECT domain, category FROM domain_classifications "
            f"WHERE domain IN ({placeholders})",
            list(wanted),
        ).fetchall()
    except Exception:
        return {}
    return {
        str(r["domain"]).lower().rstrip("."): r["category"] for r in rows
    }


def _apply_stored_rule(domain, classification, stored_rules):
    """Override a keyword classification with its stored rule, if any."""
    stored = stored_rules.get(domain.lower().rstrip("."))
    if not stored or stored == "UNCATEGORIZED":
        return classification
    if stored == "ADULT_CONTENT":
        return DomainSecurity(
            domain=domain,
            security_level=SecurityLevel.DANGEROUS,
            category=stored,
            risk_score=90,
            reason=f"Matched stored rule: {stored}",
        )
    return DomainSecurity(
        domain=domain,
        security_level=SecurityLevel.SAFE,
        category=stored,
        risk_score=5,
        reason=f"Matched stored rule: {stored}",
    )


@router.get("/security")
def get_domain_security(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    limit: int = Query(20, ge=1, le=100, description="Max number of domains"),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO-8601)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO-8601)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    records = Repository.get_top_domains(conn, device_id=device_id, limit=limit, start_date=start_date, end_date=end_date)
    stored_rules = _stored_rule_map(
        conn,
        [r.domain if hasattr(r, "domain") else str(r) for r in records],
    )

    results = []
    for record in records:
        domain = record.domain if hasattr(record, "domain") else str(record)
        query_count = record.query_count if hasattr(record, "query_count") else 0
        unique_devices = record.unique_devices if hasattr(record, "unique_devices") else 0
        classification = _apply_stored_rule(
            domain, classify_domain(domain), stored_rules
        )
        subject = get_subject(domain)
        meta = SECURITY_META[classification.security_level]
        
        results.append({
            "domain": domain,
            "query_count": query_count,
            "unique_devices": unique_devices,
            "security_level": classification.security_level.value,
            "security_label": meta["label"],
            "security_color": meta["color"],
            "security_icon": meta["icon"],
            "category": classification.category,
            "subject": subject,
            "risk_score": classification.risk_score,
            "reason": classification.reason,
        })
    
    results.sort(key=lambda x: x["query_count"], reverse=True)
    
    return JSONResponse(content={
        "device_id": device_id,
        "total_domains": len(results),
        "domains": results,
        "summary": {
            "safe": sum(1 for r in results if r["security_level"] == "SAFE"),
            "risky": sum(1 for r in results if r["security_level"] == "RISKY"),
            "dangerous": sum(1 for r in results if r["security_level"] == "DANGEROUS"),
            "unknown": sum(1 for r in results if r["security_level"] == "UNKNOWN"),
        },
    })


@router.get("/dangerous")
def get_dangerous_domains(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    limit: int = Query(50, ge=1, le=100, description="Max number of domains"),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO-8601)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO-8601)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    records = Repository.get_top_domains(conn, device_id=device_id, limit=limit, start_date=start_date, end_date=end_date)
    stored_rules = _stored_rule_map(
        conn,
        [r.domain if hasattr(r, "domain") else str(r) for r in records],
    )

    dangerous = []
    for record in records:
        domain = record.domain if hasattr(record, "domain") else str(record)
        query_count = record.query_count if hasattr(record, "query_count") else 0
        classification = _apply_stored_rule(
            domain, classify_domain(domain), stored_rules
        )
        if classification.security_level.value in ("DANGEROUS", "RISKY"):
            dangerous.append({
                "domain": domain,
                "query_count": query_count,
                "security_level": classification.security_level.value,
                "security_label": SECURITY_META[classification.security_level]["label"],
                "security_color": SECURITY_META[classification.security_level]["color"],
                "category": classification.category,
                "subject": get_subject(domain),
                "reason": classification.reason,
            })
    
    dangerous.sort(key=lambda x: x["query_count"], reverse=True)
    
    return JSONResponse(content={
        "device_id": device_id,
        "total_flagged": len(dangerous),
        "domains": dangerous,
    })


@router.get("/subjects")
def get_subjects_by_device(
    device_id: Optional[str] = Query(None, description="Filter by device ID"),
    limit: int = Query(50, ge=1, le=100, description="Max number of domains"),
    start_date: Optional[str] = Query(None, description="Start date filter (ISO-8601)"),
    end_date: Optional[str] = Query(None, description="End date filter (ISO-8601)"),
    conn: sqlite3.Connection = Depends(get_db),
) -> JSONResponse:
    records = Repository.get_top_domains(conn, device_id=device_id, limit=limit, start_date=start_date, end_date=end_date)
    stored_rules = _stored_rule_map(
        conn,
        [r.domain if hasattr(r, "domain") else str(r) for r in records],
    )

    subject_counts: dict[str, int] = {}
    domain_list: list[dict] = []

    for record in records:
        domain = record.domain if hasattr(record, "domain") else str(record)
        query_count = record.query_count if hasattr(record, "query_count") else 0
        subject = get_subject(domain)
        classification = _apply_stored_rule(
            domain, classify_domain(domain), stored_rules
        )
        
        subject_counts[subject] = subject_counts.get(subject, 0) + query_count
        domain_list.append({
            "domain": domain,
            "query_count": query_count,
            "subject": subject,
            "security_level": classification.security_level.value,
            "category": classification.category,
        })
    
    subjects = sorted(subject_counts.items(), key=lambda x: x[1], reverse=True)
    
    return JSONResponse(content={
        "device_id": device_id,
        "total_queries": sum(subject_counts.values()),
        "subjects": [{"subject": s, "query_count": c} for s, c in subjects],
        "domain_details": domain_list[:20],
    })
