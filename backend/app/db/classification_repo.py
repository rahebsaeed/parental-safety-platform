"""Repository layer for domain classification operations."""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.app.models.classification import DomainClassification
from backend.app.classifiers import classify, explain, Category


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------

def upsert_classification(
    session: Session,
    domain: str,
    *,
    force: bool = False,
) -> DomainClassification:
    """Classify *domain* and upsert the result into *domain_classifications*.

    If a row already exists with ``is_override=1`` it is left unchanged
    (unless *force* is True, which is reserved for admin overrides).

    Returns the (possibly unchanged) :class:`DomainClassification` row.
    """
    existing: DomainClassification | None = session.get(DomainClassification, domain)

    if existing and existing.is_override and not force:
        return existing

    info = explain(domain)

    if existing is None:
        row = DomainClassification(
            domain=domain,
            category=info["category"],
            rule_type=info["rule_type"],
            pattern=info["pattern"],
            is_override=0,
            classified_at=_now_iso(),
        )
        session.add(row)
        return row

    # Update existing non-override row
    existing.category = info["category"]
    existing.rule_type = info["rule_type"]
    existing.pattern = info["pattern"]
    existing.classified_at = _now_iso()
    if force:
        existing.is_override = 0
    return existing


def set_override(
    session: Session,
    domain: str,
    category: str | Category,
    note: str | None = None,
) -> DomainClassification:
    """Manually override the category for *domain*.

    Creates a new row if one does not exist.  Sets ``is_override=1``
    so automatic re-classification skips this domain.
    """
    if isinstance(category, Category):
        category = category.value

    existing: DomainClassification | None = session.get(DomainClassification, domain)
    if existing is None:
        row = DomainClassification(
            domain=domain,
            category=category,
            rule_type=None,
            pattern=None,
            is_override=1,
            note=note,
            classified_at=_now_iso(),
        )
        session.add(row)
        return row

    existing.category = category
    existing.is_override = 1
    existing.note = note
    existing.classified_at = _now_iso()
    return existing


# ---------------------------------------------------------------------------
# AI sync — persist OpenRouter verdicts as rules
# ---------------------------------------------------------------------------

def upsert_ai_classification(
    session: Session,
    domain: str,
    rule_category: Category,
    *,
    model: str,
    reason: str | None = None,
    force: bool = False,
) -> DomainClassification | None:
    """Persist an AI verdict as a first-class classification row.

    Manual overrides (``is_override=1``) are never touched unless *force*
    is True. Returns the row, or None if an override blocked the write.
    """
    existing: DomainClassification | None = session.get(DomainClassification, domain)
    if existing and existing.is_override and not force:
        return None

    if existing is None:
        row = DomainClassification(
            domain=domain,
            category=rule_category.value,
            rule_type="openrouter",
            pattern=model,
            is_override=0,
            note=(reason or "")[:500] if reason else None,
            classified_at=_now_iso(),
        )
        session.add(row)
        return row

    existing.category = rule_category.value
    existing.rule_type = "openrouter"
    existing.pattern = model
    if reason:
        existing.note = reason[:500]
    existing.classified_at = _now_iso()
    if force:
        existing.is_override = 0
    return existing


def ai_sync_uncategorized(session: Session, limit: int = 20) -> dict:
    """Classify UNCATEGORIZED (or never-seen) domains with the AI model and
    persist verdicts as rules so they never show UNCATEGORIZED again.

    Candidates are ordered by recent query volume, so repeatedly visited
    unknowns (the dangerous ones) are handled first. Bounded by *limit* to
    cap external API cost per run. UNKNOWN verdicts are deliberately not
    persisted, keeping those domains retryable. Manual overrides are sacred.

    Returns {"considered", "ai_classified", "still_unknown", "no_api_key"}.
    """
    from backend.app.classifiers import openrouter_classifier as ai
    from backend.app.models.dns import DnsQuery  # avoid circular import at top
    from sqlalchemy import func, or_, select

    if not ai.get_openrouter_api_key():
        return {
            "considered": 0, "ai_classified": 0,
            "still_unknown": 0, "no_api_key": True,
        }

    uncat_rows = (
        select(DomainClassification.domain)
        .where(
            DomainClassification.category == Category.UNCATEGORIZED.value,
            or_(
                DomainClassification.is_override == 0,
                DomainClassification.is_override.is_(None),
            ),
        )
    )
    candidate_rows = (
        session.query(DnsQuery.domain, func.count().label("c"))
        .filter(
            or_(
                DnsQuery.domain.notin_(select(DomainClassification.domain)),
                DnsQuery.domain.in_(uncat_rows),
            )
        )
        .group_by(DnsQuery.domain)
        .order_by(func.count().desc())
        .limit(max(1, limit))
        .all()
    )
    candidates = [domain for (domain, _count) in candidate_rows]

    # Rule pass first (cheap, local): anything the static rules know stays
    # a static verdict and never spends an AI call. NOTE: use upsert's
    # return value directly — with autoflush=False sessions, a fresh
    # session.get() cannot see just-added (unflushed) rows and returns
    # None, which would silently skip every candidate.
    needs_ai: list[str] = []
    for domain in candidates:
        row = upsert_classification(session, domain)
        if row is None or row.is_override:
            continue
        if row.category == Category.UNCATEGORIZED.value:
            needs_ai.append(domain)
    # Commit BEFORE any network I/O: the AI batch takes seconds per
    # domain, and an open SQLite write transaction across that window
    # locks out the DNS collector ("database is locked").
    session.commit()

    # One batched AI pass (cache-aware inside classify_domains_batch).
    results = ai.classify_domains_batch(needs_ai) if needs_ai else {}

    ai_classified = 0
    still_unknown = 0
    for domain in needs_ai:
        result = results.get(domain) or {}
        rule_category = ai.map_ai_category(result.get("category", "UNKNOWN"))
        if rule_category is None:
            still_unknown += 1
            continue
        written = upsert_ai_classification(
            session, domain, rule_category,
            model=result.get("model") or ai.FREE_MODEL,
            reason=result.get("reason"),
        )
        if written is not None:
            ai_classified += 1
    if ai_classified:
        session.commit()

    return {
        "considered": len(candidates),
        "ai_classified": ai_classified,
        "still_unknown": still_unknown,
        "no_api_key": False,
    }


# ---------------------------------------------------------------------------
# Single-domain AI classify + persist (explicit user action)
# ---------------------------------------------------------------------------

def ai_classify_domain(session: Session, domain: str) -> dict:
    """Classify one domain with AI and persist the verdict as a rule.

    Rule pass first (no AI spend when static rules know the answer).
    Returns {"row", "ai_used", "verdict"} where verdict is the raw AI
    category or None. Raises RuntimeError when no API key is configured
    (explicit action — caller surfaces a clear error, unlike the silent
    bulk-sync skip). Manual overrides are never touched.
    """
    from backend.app.classifiers import openrouter_classifier as ai

    if not ai.get_openrouter_api_key():
        raise RuntimeError("No OpenRouter API key configured (Settings → OpenRouter)")

    row = upsert_classification(session, domain)
    # Flush so the follow-up session.get() below can see a just-created
    # row (with autoflush=False it otherwise returns None and the AI
    # upsert below would INSERT a duplicate -> UNIQUE violation).
    session.flush()
    if row is None or row.is_override or row.category != Category.UNCATEGORIZED.value:
        return {"row": row, "ai_used": False, "verdict": None}

    results = ai.classify_domains_batch([domain])
    result = results.get(domain) or {}
    verdict = result.get("category", "UNKNOWN")
    rule_category = ai.map_ai_category(verdict)
    if rule_category is None:
        session.flush()
        return {"row": row, "ai_used": True, "verdict": verdict}

    written = upsert_ai_classification(
        session, domain, rule_category,
        model=result.get("model") or ai.FREE_MODEL,
        reason=result.get("reason"),
    )
    session.flush()
    return {"row": written if written is not None else row,
            "ai_used": True, "verdict": verdict}


# ---------------------------------------------------------------------------
# Bulk sync
# ---------------------------------------------------------------------------

def sync_unclassified(session: Session) -> int:
    """Classify all domains in *dns_queries* that have no classification row.

    Returns the number of new rows written.
    """
    from backend.app.models.dns import DnsQuery  # avoid circular import at top

    from sqlalchemy import select

    # Fetch distinct domains from dns_queries not yet in domain_classifications
    classified_select = select(DomainClassification.domain)
    unclassified = (
        session.query(DnsQuery.domain)
        .filter(DnsQuery.domain.notin_(classified_select))
        .distinct()
        .all()
    )

    count = 0
    for (domain,) in unclassified:
        upsert_classification(session, domain)
        count += 1

    if count:
        session.flush()

    return count


# ---------------------------------------------------------------------------
# Read
# ---------------------------------------------------------------------------

def get_classification(session: Session, domain: str) -> DomainClassification | None:
    """Return the stored classification for *domain*, or None."""
    return session.get(DomainClassification, domain)


def list_by_category(session: Session, category: str | Category) -> list[DomainClassification]:
    """Return all classified domains that belong to *category*."""
    if isinstance(category, Category):
        category = category.value
    return (
        session.query(DomainClassification)
        .filter(DomainClassification.category == category)
        .order_by(DomainClassification.domain)
        .all()
    )


def category_summary(session: Session) -> list[dict]:
    """Return a list of {category, count} dicts ordered by count descending."""
    from sqlalchemy import func

    rows = (
        session.query(DomainClassification.category, func.count().label("count"))
        .group_by(DomainClassification.category)
        .order_by(func.count().desc())
        .all()
    )
    return [{"category": r.category, "count": r.count} for r in rows]
