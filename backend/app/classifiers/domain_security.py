
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


# Keyword-based security classification
_DANGEROUS_KEYWORDS = [
    "gambling", "casino", "porn", "adult", "xxx", "nsfw", "bet", "wagering",
    "lottery", "slots", "poker", "casino", "hookah", "weed", "cannabis",
    "heroin", "cocaine", "meth", "fentanyl", "opioid", "drug", "mdma",
    "assault", "violence", "hitman", "kill", "suicide", "self-harm",
    "knife", "gun", "weapon", "explosive", "bomb", "terrorist",
    "racist", "hate", "supremacist", "nazi", "kkk", "white power",
]

_RISKY_KEYWORDS = [
    "chat", "dating", "meet", "hookup", "random", "stranger", "anonymous",
    "tinder", "bumble", "hinge", "dating", "relationship",
    "dark", "shadow", "deep", "web",
    "crypto", "bitcoin", "ethereum", "trading", "forex",
    "steam", "gaming", "roblox", "fortnite", "minecraft",
    "tiktok", "instagram", "snapchat", "whatsapp", "telegram",
    "reddit", "4chan", "9chan", "discord",
    "cricfree", "stream", "watch", "free", "proxy",
    "tor", "vpn", "proxy",
    "instagram", "facebook", "twitter", "x.com",
]

_SAFE_KEYWORDS = [
    "google", "youtube", "wikipedia", "github", "stackoverflow",
    "wikipedia", "khan", "coursera", "edx", "udemy", "duolingo",
    "amazon", "ebay", "shop", "store",
    "news", "bbc", "cnn", "reuters", "nytimes",
    "weather", "map", "google", "apple",
    "microsoft", "office", "gmail", "outlook",
    "health", "medical", "doctor", "hospital",
    "education", "school", "university", "learning",
    "music", "spotify", "netflix", "disney",
    "news", "bbc", "cnn", "reuters",
    "weather", "calendar", "timer",
    "translate", "dictionary", "thesaurus",
    "cloud", "cdn", "infrastructure",
    "api", "analytics", "tracking",
]


def classify_domain(domain: str) -> DomainSecurity:
    """Classify a domain's security level based on keywords.

    Returns a DomainSecurity object with the security level, category,
    risk score, and reason.
    """
    domain_lower = domain.lower().strip()
    
    # Remove leading www. and subdomains for classification
    base_domain = domain_lower.replace("www.", "")
    parts = base_domain.split(".")
    base = parts[0] if parts else domain_lower
    
    # Check for dangerous keywords
    for keyword in _DANGEROUS_KEYWORDS:
        if keyword in base_domain or keyword in base:
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.DANGEROUS,
                category="ADULT_CONTENT",
                risk_score=90,
                reason=f"Matches dangerous keyword: '{keyword}'",
            )
    
    # Check for risky keywords
    for keyword in _RISKY_KEYWORDS:
        if keyword in base_domain or keyword in base:
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.RISKY,
                category="SOCIAL_MEDIA",
                risk_score=50,
                reason=f"Matches risky keyword: '{keyword}'",
            )
    
    # Check for safe keywords
    for keyword in _SAFE_KEYWORDS:
        if keyword in base_domain or keyword in base:
            return DomainSecurity(
                domain=domain,
                security_level=SecurityLevel.SAFE,
                category="PRODUCTIVITY",
                risk_score=5,
                reason=f"Matches safe keyword: '{keyword}'",
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
