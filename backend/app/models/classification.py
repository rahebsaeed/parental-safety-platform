"""ORM model for domain classification overrides and cache."""
from __future__ import annotations

from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.models.base import Base


class DomainClassification(Base):
    """Stores the resolved category for each unique domain seen on the network.

    Rows are upserted by the classification service whenever a new domain
    appears in *dns_queries*.  Manual overrides (``is_override=1``) are never
    overwritten by automatic re-classification.
    """

    __tablename__ = "domain_classifications"

    # The fully-qualified domain name is the natural primary key.
    domain: Mapped[str] = mapped_column(String(255), primary_key=True)

    # Category string matching Category enum value (e.g. "SOCIAL_MEDIA").
    category: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UNCATEGORIZED", index=True
    )

    # Rule that produced this classification (for audit / debugging).
    rule_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    pattern: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 1 = manually set by an operator and must not be overwritten automatically.
    is_override: Mapped[int] = mapped_column(default=0, nullable=False)

    # Human-readable note (for overrides).
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ISO-8601 timestamps managed at the application layer.
    classified_at: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    def __repr__(self) -> str:
        return (
            f"<DomainClassification(domain={self.domain!r}, "
            f"category={self.category!r}, is_override={self.is_override})>"
        )
