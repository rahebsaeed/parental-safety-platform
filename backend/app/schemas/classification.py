"""Pydantic schemas for domain classification API responses."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict


class DomainClassificationRead(BaseModel):
    """Serialised form of a single domain classification."""

    model_config = ConfigDict(from_attributes=True)

    domain: str
    category: str
    rule_type: Optional[str] = None
    pattern: Optional[str] = None
    is_override: int = 0
    note: Optional[str] = None
    classified_at: Optional[str] = None


class CategorySummaryItem(BaseModel):
    """One row in the category breakdown summary."""

    category: str
    count: int
    label: str
    color: str
    icon: str


class CategorySummaryResponse(BaseModel):
    """Full category breakdown across all classified domains."""

    items: list[CategorySummaryItem]
    total_classified: int
    total_unclassified: int


class ClassifyRequest(BaseModel):
    """Request body for classifying one or more domains on-the-fly."""

    domains: list[str]


class ClassifyResult(BaseModel):
    """Classification result for a single domain."""

    domain: str
    category: str
    rule_type: Optional[str] = None
    pattern: Optional[str] = None


class ClassifyResponse(BaseModel):
    results: list[ClassifyResult]


class OverrideRequest(BaseModel):
    """Request body to manually override a domain's category."""

    category: str
    note: Optional[str] = None
