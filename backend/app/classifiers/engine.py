"""Domain Classification Engine.

Evaluates rules in priority order and returns a Category for any FQDN.
Also provides bulk classification and in-memory caching.
"""
from __future__ import annotations

import re
from functools import lru_cache

from .categories import Category
from .rules import RULES, Rule


# ---------------------------------------------------------------------------
# Core matching logic
# ---------------------------------------------------------------------------

def _normalize(domain: str) -> str:
    """Lowercase and strip trailing dot."""
    return domain.lower().rstrip(".")


def _match_rule(rule: Rule, domain: str) -> bool:
    """Return True if *domain* satisfies *rule*."""
    match rule.rule_type:
        case "exact":
            return domain == rule.pattern
        case "suffix":
            # e.g. "facebook.com" matches "www.facebook.com" and "facebook.com"
            pat = _normalize(rule.pattern)
            return domain == pat or domain.endswith("." + pat)
        case "contains":
            return rule.pattern in domain
        case "regex":
            return bool(re.search(rule.pattern, domain))
        case _:
            return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4096)
def classify(domain: str) -> Category:
    """Classify *domain* and return a :class:`Category`.

    Results are cached in-process (LRU, 4096 slots).
    """
    norm = _normalize(domain)
    for rule in RULES:
        if _match_rule(rule, norm):
            return rule.category
    return Category.UNCATEGORIZED


def classify_many(domains: list[str]) -> dict[str, Category]:
    """Classify a list of domains in one call.

    Returns a mapping ``{domain: Category}``.
    """
    return {d: classify(d) for d in domains}


def explain(domain: str) -> dict:
    """Return classification with the matching rule details (for debugging).

    Example output::

        {
            "domain": "www.facebook.com",
            "category": "SOCIAL_MEDIA",
            "rule_type": "suffix",
            "pattern": "facebook.com",
        }
    """
    norm = _normalize(domain)
    for rule in RULES:
        if _match_rule(rule, norm):
            return {
                "domain": domain,
                "category": rule.category.value,
                "rule_type": rule.rule_type,
                "pattern": rule.pattern,
            }
    return {
        "domain": domain,
        "category": Category.UNCATEGORIZED.value,
        "rule_type": None,
        "pattern": None,
    }
