"""Safety alert rule definitions and evaluators."""
from __future__ import annotations

import re
from typing import Optional

from backend.app.alerts.types import AlertSeverity, AlertType, DetectionResult
from backend.app.classifiers.categories import Category


# ---------------------------------------------------------------------------
# Known Encrypted DNS (DoH / DoT) Endpoints
# ---------------------------------------------------------------------------
KNOWN_DOH_DOMAINS: set[str] = {
    "cloudflare-dns.com",
    "one.one.one.one",
    "dns.google",
    "dns.google.com",
    "dns.quad9.net",
    "doh.opendns.com",
    "dns.adguard.com",
    "dns.nextdns.io",
    "doh.cleanbrowsing.org",
    "doh.mullvad.net",
}

# ---------------------------------------------------------------------------
# Phishing / Deceptive Pattern Substrings
# ---------------------------------------------------------------------------
PHISHING_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"(?:paypal|paypa1|p-aypal).*(?:verify|login|update|security)", re.I),
        "Brand impersonation attempt targeting PayPal with verification lure.",
    ),
    (
        re.compile(r"(?:appleid|icloud).*(?:verify|account|unlock|support)", re.I),
        "Brand impersonation attempt targeting Apple ID / iCloud credentials.",
    ),
    (
        re.compile(r"(?:netflix|netf1ix).*(?:billing|account|update|renew)", re.I),
        "Subscription billing phishing pattern mimicking Netflix.",
    ),
    (
        re.compile(r"(?:google|g00gle).*(?:security|verification|login-prompt)", re.I),
        "Credential harvesting lure mimicking Google accounts.",
    ),
    (
        re.compile(r"(?:metamask|trustwallet|phantom-wallet).*(?:claim|airdrop|seed)", re.I),
        "Cryptocurrency credential or seed phrase theft lure.",
    ),
    (
        re.compile(r"(?:bank|secure-banking).*(?:login|confirm|alert)", re.I),
        "Generic banking credential verification phishing pattern.",
    ),
]


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def check_unsafe_category(domain: str, category: Category | str) -> Optional[DetectionResult]:
    """Check if domain belongs to an unsafe category (ADULT_CONTENT, etc.)."""
    cat_str = category.value if isinstance(category, Category) else str(category)
    if cat_str != Category.ADULT_CONTENT.value:
        return None

    domain_lower = domain.lower()
    gambling_keywords = ("bet", "casino", "poker", "draftkings", "gambling", "lottery")
    is_gambling = any(kw in domain_lower for kw in gambling_keywords)

    if is_gambling:
        return DetectionResult(
            alert_type=AlertType.UNSAFE_CATEGORY,
            severity=AlertSeverity.HIGH,
            title="Online Gambling / Betting Activity",
            description=f"Observed DNS activity to gambling or wagering service: {domain}",
            rule_matched="CATEGORY:ADULT_CONTENT:GAMBLING",
            explanation=(
                f"Domain '{domain}' was categorized as {Category.ADULT_CONTENT.value} "
                f"and matched gambling/wagering indicators."
            ),
        )

    return DetectionResult(
        alert_type=AlertType.UNSAFE_CATEGORY,
        severity=AlertSeverity.CRITICAL,
        title="Adult Content Access Attempt",
        description=f"Observed DNS activity to adult-oriented or sexually explicit domain: {domain}",
        rule_matched="CATEGORY:ADULT_CONTENT",
        explanation=(
            f"Domain '{domain}' was categorized as {Category.ADULT_CONTENT.value}. "
            "Adult content access triggers immediate safety notification."
        ),
    )


def check_bypass_attempt(domain: str, dns_visibility: str = "FULL") -> Optional[DetectionResult]:
    """Check if query is probing DoH/DoT resolvers or has PARTIAL visibility."""
    domain_lower = domain.lower().rstrip(".")

    # Known DoH endpoint
    if domain_lower in KNOWN_DOH_DOMAINS or any(domain_lower.endswith("." + d) for d in KNOWN_DOH_DOMAINS):
        return DetectionResult(
            alert_type=AlertType.BYPASS_ATTEMPT,
            severity=AlertSeverity.MEDIUM,
            title="Encrypted DNS / Bypass Probe",
            description=f"Query to known public DoH/DoT resolver: {domain}",
            rule_matched="RESOLVER:KNOWN_DOH_ENDPOINT",
            explanation=(
                f"Domain '{domain}' is a public DNS-over-HTTPS/TLS provider. "
                "Devices using this resolver will bypass local parental safety observation."
            ),
        )

    # Visibility is partial
    if dns_visibility.upper() == "PARTIAL":
        return DetectionResult(
            alert_type=AlertType.BYPASS_ATTEMPT,
            severity=AlertSeverity.MEDIUM,
            title="Partial DNS Visibility Detected",
            description=f"DNS query was captured with partial visibility: {domain}",
            rule_matched="VISIBILITY:PARTIAL",
            explanation=(
                f"Query to '{domain}' exhibited partial visibility, indicating the client device "
                "may be utilizing Private DNS or encrypted transport."
            ),
        )

    return None


def check_phishing_suspicious(domain: str) -> Optional[DetectionResult]:
    """Check domain against known deceptive / credential theft patterns."""
    domain_lower = domain.lower()

    for pattern, rationale in PHISHING_PATTERNS:
        if pattern.search(domain_lower):
            return DetectionResult(
                alert_type=AlertType.PHISHING_SUSPICIOUS,
                severity=AlertSeverity.HIGH,
                title="Suspicious / Phishing Pattern Detected",
                description=f"Domain matches deceptive or credential harvesting structure: {domain}",
                rule_matched=f"PATTERN:{pattern.pattern}",
                explanation=rationale,
            )

    return None
