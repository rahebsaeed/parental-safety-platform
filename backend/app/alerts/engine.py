"""Safety Alert Evaluation Engine.

Evaluates queries across all safety rule vectors and generates structured detection results.
"""
from __future__ import annotations

from typing import Optional

from backend.app.alerts.rules import (
    check_bypass_attempt,
    check_explicit_keywords,
    check_phishing_suspicious,
    check_tunnel_endpoint,
    check_unsafe_category,
)
from backend.app.alerts.types import DetectionResult
from backend.app.classifiers.categories import Category
from backend.app.classifiers.engine import classify


def evaluate(
    domain: str,
    category: Optional[Category | str] = None,
    dns_visibility: str = "FULL",
) -> Optional[DetectionResult]:
    """Evaluate a domain across all safety vectors in priority order.

    1. Unsafe categories (Adult Content, Gambling) — highest priority.
    2. Explicit adult/gambling wording (fires even for unclassified domains).
    3. Phishing / credential theft patterns.
    4. Bypass / Encrypted DNS probing.
    5. VPN / Tor / proxy tunnel endpoints.

    Returns the first matching :class:`DetectionResult`, or None if benign.
    """
    if category is None:
        category = classify(domain)

    # 1. Unsafe category check
    result = check_unsafe_category(domain, category)
    if result:
        return result

    # 2. Explicit wording safety net (category-independent)
    result = check_explicit_keywords(domain)
    if result:
        return result

    # 3. Phishing / deceptive pattern check
    result = check_phishing_suspicious(domain)
    if result:
        return result

    # 4. Encrypted DNS / DoH / visibility bypass check
    result = check_bypass_attempt(domain, dns_visibility=dns_visibility)
    if result:
        return result

    # 5. VPN / Tor / proxy tunnel endpoints
    result = check_tunnel_endpoint(domain)
    if result:
        return result

    return None


def generate_dedup_key(device_id: Optional[str], alert_type: str, domain: str) -> str:
    """Construct a canonical deduplication key for an alert.

    Alerts with matching dedup keys within the cooldown window will be
    aggregated into an occurrence count rather than generating duplicate rows.
    """
    dev = device_id or "unknown"
    dom = domain.lower().strip(".")
    return f"{dev}:{alert_type}:{dom}"
