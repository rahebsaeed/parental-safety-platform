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
