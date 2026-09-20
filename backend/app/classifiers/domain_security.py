
"""Domain security classification.

Classifies domains as safe, risky, or dangerous based on keywords.
Used to help parents understand what their children are accessing.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class SecurityLevel(str, Enum):
    """Security risk level for a domain."""
    SAFE = "SAFE"
    RISKY = "RISKY"
    DANGEROUS = "DANGEROUS"
    UNKNOWN = "UNKNOWN"


SECURITY_META: dict[SecurityLevel, dict[str, str]] = {
    SecurityLevel.SAFE: {
        "label": "Safe",
        "color": "#4caf50",
        "icon": "check_circle",
    },
    SecurityLevel.RISKY: {
        "label": "Risky",
        "color": "#ff9800",
        "icon": "warning",
    },
    SecurityLevel.DANGEROUS: {
        "label": "Dangerous",
        "color": "#f44336",
        "icon": "error",
    },
    SecurityLevel.UNKNOWN: {
        "label": "Unknown",
        "color": "#9e9e9e",
        "icon": "help_outline",
    },
}


@dataclass(frozen=True)
class DomainSecurity:
    """Security classification for a single domain."""
    domain: str
    security_level: SecurityLevel
    category: str
    risk_score: int  # 0-100
    reason: str


# Keyword-based security classification.
#
# Matching discipline (learned from live false labels):
# - SAFE fires ONLY on exact/suffix match against known-safe roots. Generic
#   infrastructure tokens (cloud, cdn, api, analytics, news, shop, music…)
#   must never mark a domain safe — sketchy sites hide behind them.
# - Short DANGEROUS/RISKY tokens (bet, tor, vpn, gun, kkk, …) match on word
#   boundaries only: raw substrings false-positive on "alphabet", "vector",
#   "history", "storage", "monitor".
import re as _re

_DANGEROUS_KEYWORDS = [
    "gambling", "casino", "porn", "adult", "xxx", "nsfw", "wagering",
    "lottery", "slots", "poker", "hookah", "weed", "cannabis",
    "heroin", "cocaine", "meth", "fentanyl", "opioid", "mdma",
    "assault", "violence", "hitman", "suicide", "self-harm",
    "knife", "weapon", "explosive", "bomb", "terrorist",
    "racist", "supremacist", "nazi", "white power",
    "hentai", "escort", "nude", "camgirl", "onlyfans", "fansly",
    "1xbet", "melbet", "mostbet", "parimatch", "unibet",
    "bet365", "betway", "draftkings", "pokerstars",
]

# Short tokens matched with word boundaries (compiled below).
_DANGEROUS_TOKENS = ("bet", "gun", "kkk", "kill", "hate", "drug", "bombs", "stake")

_RISKY_KEYWORDS = [
    "chat", "dating", "hookup", "stranger", "anonymous",
    "tinder", "bumble", "hinge", "relationship",
    "dark", "shadow",
    "crypto", "bitcoin", "ethereum", "trading", "forex",
    "steam", "gaming", "roblox", "fortnite", "minecraft",
    "tiktok", "instagram", "snapchat", "whatsapp", "telegram",
    "reddit", "4chan", "discord",
    "cricfree", "proxy", "torrent",
    "facebook", "twitter",
]

_RISKY_TOKENS = ("tor", "vpn", "proxy", "meet", "random", "stream", "watch", "free", "web", "deep", "dark")

# Known-safe ROOTS — suffix/exact match only (never substrings).
_SAFE_ROOTS = [
    "google.com", "youtube.com", "youtu.be", "wikipedia.org", "github.com",
    "stackoverflow.com", "stackexchange.com", "khanacademy.org",
    "coursera.org", "edx.org", "udemy.com", "duolingo.com",
    "bbc.com", "bbc.co.uk", "cnn.com", "reuters.com", "nytimes.com",
    "gmail.com", "outlook.com", "office.com", "microsoft.com",
    "apple.com", "icloud.com",
    "spotify.com", "netflix.com", "disney.com", "disneyplus.com",
    "ebay.com", "amazon.com",
    "ubuntu.com", "canonical.com", "debian.org", "python.org",
    "mozilla.org", "firefox.com",
]


def _boundary_res(tokens: tuple[str, ...]) -> tuple["_re.Pattern", ...]:
    return tuple(_re.compile(rf"\b{_re.escape(tok)}\b") for tok in tokens)


_DANGEROUS_TOKEN_RES = _boundary_res(_DANGEROUS_TOKENS)
_RISKY_TOKEN_RES = _boundary_res(_RISKY_TOKENS)


def _is_safe_root(domain_lower: str) -> str | None:
    for root in _SAFE_ROOTS:
        if domain_lower == root or domain_lower.endswith("." + root):
            return root
    return None


def classify_domain(domain: str) -> DomainSecurity:
    """Classify a domain's security level based on keywords.

    Returns a DomainSecurity object with the security level, category,
    risk score, and reason.
    """
    domain_lower = domain.lower().strip().strip(".")
    
    # Check for dangerous keywords (substring for multi-char, boundaries
    # for short tokens)
    for keyword in _DANGEROUS_KEYWORDS:
        if keyword in domain_lower:
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.DANGEROUS,
                category="ADULT_CONTENT",
                risk_score=90,
                reason=f"Matches dangerous keyword: '{keyword}'",
            )
    for pattern in _DANGEROUS_TOKEN_RES:
        if pattern.search(domain_lower):
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.DANGEROUS,
                category="ADULT_CONTENT",
                risk_score=90,
                reason=f"Matches dangerous keyword: '{pattern.pattern}'",
            )
    
    # Check for risky keywords
    for keyword in _RISKY_KEYWORDS:
        if keyword in domain_lower:
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.RISKY,
                category="SOCIAL_MEDIA",
                risk_score=50,
                reason=f"Matches risky keyword: '{keyword}'",
            )
    for pattern in _RISKY_TOKEN_RES:
        if pattern.search(domain_lower):
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.RISKY,
                category="SOCIAL_MEDIA",
                risk_score=50,
                reason=f"Matches risky keyword: '{pattern.pattern}'",
            )
    
    # Safe ONLY on exact/suffix match against known-safe roots — never on
    # generic substrings. Anything else stays honestly UNKNOWN.
    safe_root = _is_safe_root(domain_lower)
    if safe_root:
        return DomainSecurity(
            domain=domain,
            security_level=SecurityLevel.SAFE,
            category="PRODUCTIVITY",
            risk_score=5,
            reason=f"Matches known-safe domain: '{safe_root}'",
        )
    
    # Default: unknown
    return DomainSecurity(
        domain=domain,
        security_level=SecurityLevel.UNKNOWN,
        category="UNCATEGORIZED",
        risk_score=25,
        reason="No classification match found",
    )


# Batch classification
def classify_domains(domains: list[str]) -> list[DomainSecurity]:
    """Classify multiple domains at once."""
    return [classify_domain(d) for d in domains]


# Get subject/interest from domain
def get_subject(domain: str) -> str:
    """Extract a human-readable subject from a domain."""
    domain_lower = domain.lower().strip()
    base = domain_lower.replace("www.", "").split(".")[0]
    
    # Map common domains to subjects
    subject_map = {
        "google": "Search", "youtube": "Video", "wikipedia": "Education",
        "facebook": "Social Media", "instagram": "Social Media",
        "tiktok": "Social Media", "whatsapp": "Messaging",
        "twitter": "Social Media", "reddit": "Social Media",
        "github": "Programming", "stackoverflow": "Programming",
        "netflix": "Streaming", "spotify": "Music",
        "amazon": "Shopping", "ebay": "Shopping",
        "news": "News", "bbc": "News", "cnn": "News",
        "gaming": "Gaming", "steam": "Gaming", "roblox": "Gaming",
        "gambling": "Gambling", "casino": "Gambling",
        "mail": "Email", "gmail": "Email", "outlook": "Email",
        "translate": "Translation", "dictionary": "Education",
    }
    
    for key, subject in subject_map.items():
        if key in base:
            return subject
    
    # Try to extract a meaningful subject from the domain
    if base.endswith("tv"):
        return "Streaming"
    if base.endswith("news"):
        return "News"
    if base.endswith("game"):
        return "Gaming"
    if base.endswith("chat"):
        return "Chat"
    if base.endswith("learn"):
        return "Education"
    if base.endswith("shop"):
        return "Shopping"
    
    return "Other"
