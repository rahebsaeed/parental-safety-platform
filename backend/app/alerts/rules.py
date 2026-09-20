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
    # Cloudflare (standard + security / family filtered variants + canary)
    "cloudflare-dns.com",
    "security.cloudflare-dns.com",
    "family.cloudflare-dns.com",
    "one.one.one.one",
    "1.1.1.1",
    "1.0.0.1",
    # Google
    "dns.google",
    "dns.google.com",
    "dns64.dns.google",
    # Quad9 (+ hardened endpoint)
    "dns.quad9.net",
    "dns10.quad9.net",
    "dns11.quad9.net",
    # AdGuard (+ new-style domain)
    "dns.adguard.com",
    "dns.adguard-dns.com",
    "family.adguard-dns.com",
    # NextDNS / CleanBrowsing / Mullvad
    "dns.nextdns.io",
    "doh.cleanbrowsing.org",
    "doh.mullvad.net",
    "dot.mullvad.net",
    "dns.mullvad.net",
    # OpenDNS / Cisco
    "doh.opendns.com",
    "doh.familyshield.opendns.com",
    # Independent / EU providers
    "doh.dns.sb",
    "dns.brahma.world",
    "doh.libredns.gr",
    "doh.ffmuc.net",
    "ordns.he.net",
    "odvr.nic.cz",
    "doh.crypto.sx",
    "controld.com",
    "dns.controld.com",
    "freedns.controld.com",
    # Firefox / OS canaries & probes (their mere presence proves DoH is on)
    "use-application-dns.net",
    "doh.test",
    "dnssec-trigger.nl",
    # Android Private DNS hostnames commonly probed before upgrade
    "private.dns.microsoft.com",
}


# ---------------------------------------------------------------------------
# VPN / Anonymizer / Proxy Endpoints (tunnels hide activity from local DNS)
# ---------------------------------------------------------------------------
KNOWN_VPN_SUFFIXES: set[str] = {
    "nordvpn.com",
    "nordcdn.com",
    "expressvpn.com",
    "expressvpn.net",
    "surfshark.com",
    "surfsharkstatus.com",
    "protonvpn.com",
    "protonvpn.net",
    "mullvad.net",
    "windscribe.com",
    "windscribe.net",
    "tunnelbear.com",
    "hotspotshield.com",
    "hsselite.com",
    "hidemyass.com",
    "hola.org",
    "hola.com",
    "privateinternetaccess.com",
    "vyprvpn.com",
    "ipvanish.com",
    "cyberghostvpn.com",
    "purevpn.com",
    "ivacy.com",
    "vpnunlimited.com",
    "atlasvpn.com",
    "turbovpn.com",
    "vpnproxy.net",
    "riseup.net",
    "calyx.net",
}

KNOWN_TOR_SUFFIXES: set[str] = {
    "torproject.org",
    "tor.eff.org",
    "torproject.net",
    "torservers.net",
    "onion.city",
    "onion.cab",
    "onion.to",
    "onion.link",
    "tor2web.org",
}

# Generic tunnel/proxy tokens matched on whole DNS labels only (never raw
# substrings: "tor" alone would false-positive on "vector"/"history").
_TUNNEL_LABEL_TOKENS: tuple[str, ...] = ("vpn", "wireguard", "openvpn", "shadowsocks", "v2ray", "trojan-go")


# ---------------------------------------------------------------------------
# Explicit adult / gambling keywords (category-independent safety net)
# ---------------------------------------------------------------------------
# Fires on the domain STRING itself, so an explicit site the classifier
# (static rules + AI) hasn't learned yet can never show as safe.
#
# Two strictness levels:
# - SUBSTRING tokens: no legitimate English word contains them, so a raw
#   substring match is safe ("freexxxmovies", "teenporn", "freeporn").
# - STRICT tokens: full word boundaries both sides — short tokens with
#   legitimate lookalikes ("sexton" the surname, "escorted" tours,
#   "milford" the town, "essex"/"sussex").
_ADULT_SUBSTRING_RES: tuple[re.Pattern, ...] = tuple(
    re.compile(kw, re.I)
    for kw in (
        "porn", "porno", "xxx", "sexy", "hentai", "camgirl", "camgirls",
        "playboy", "penthouse", "erotic", "fetish", "bdsm", "swinger",
        "stripclub", "brothel", "onlyfans", "fansly", "manyvids",
    )
)
_ADULT_STRICT_RES: tuple[re.Pattern, ...] = tuple(
    re.compile(rf"\b{kw}\b", re.I)
    for kw in ("sex", "nude", "nudes", "escort", "escorts", "milf")
)

_GAMBLING_KEYWORD_RES: tuple[re.Pattern, ...] = tuple(
    re.compile(rf"\b{kw}\b", re.I)
    for kw in (
        "1xbet", "melbet", "mostbet", "parimatch", "1win", "22bet", "betwinner",
        "unibet", "bwin", "ladbrokes", "williamhill", "paddypower", "skybet",
        "stake", "sportsbook", "bookmaker",
    )
)
# Bare "bet" only as a full label (1x.bet, super.bet) — never inside words.
_BET_LABEL_RE = re.compile(r"(?:^|\.)bet(?:\.|$)", re.I)

# ---------------------------------------------------------------------------
# Phishing / Deceptive Pattern Substrings
# ---------------------------------------------------------------------------
def _endswith_any(domain_lower: str, suffixes: set[str]) -> str | None:
    """Return the matched suffix, or None. Matches the registrable domain
    itself or any subdomain of it."""
    for suffix in suffixes:
        if domain_lower == suffix or domain_lower.endswith("." + suffix):
            return suffix
    return None


def _labels(domain_lower: str) -> list[str]:
    return [label for label in domain_lower.strip(".").split(".") if label]


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
    (
        re.compile(r"(?:microsoft|office365|outlook|onedrive|sharepoint).*(?:verify|login|password|expired|quota|shared-?file)", re.I),
        "Brand impersonation targeting Microsoft / Office365 credentials, a top phishing lure.",
    ),
    (
        re.compile(r"(?:amazon|amzn).*(?:verify|order|payment|suspend|refund|prize)", re.I),
        "Brand impersonation mimicking Amazon order/payment notifications.",
    ),
    (
        re.compile(r"(?:facebook|meta|instagram|messenger).*(?:verify|login|copyright|appeal|security)", re.I),
        "Brand impersonation targeting Meta / Facebook / Instagram accounts.",
    ),
    (
        re.compile(r"(?:whatsapp|wa-me).*(?:verify|code|prize|gift|voicemail)", re.I),
        "Smishing-style lure mimicking WhatsApp verification or prize messages.",
    ),
    (
        re.compile(r"(?:dhl|aramex|fedex|ups|chronopost|amana|ows).*(?:pay|payment|fee|customs|deliver|track|parcel)", re.I),
        "Fake parcel-delivery lure asking for a fee or payment (classic smishing).",
    ),
    (
        re.compile(r"(?:binance|coinbase|kraken|blockchain).*(?:verify|wallet|suspend|airdrop|bonus)", re.I),
        "Cryptocurrency exchange impersonation targeting wallet credentials.",
    ),
    (
        re.compile(r"(?:apple-pay|icloud|apple).*(?:bill|invoice|purchase|subscription|receipt)", re.I),
        "Fake Apple billing/invoice lure harvesting payment credentials.",
    ),
    (
        re.compile(r"(?:account|profile).*(?:suspend|locked|restrict|terminat).*", re.I),
        "Generic account-suspension scare lure pressuring urgent action.",
    ),
    (
        re.compile(r"xn--[a-z0-9-]+.*(?:login|verify|bank|paypal|secure|account|update)", re.I),
        "Punycode (internationalized) domain combined with a credential lure — a classic lookalike-domain attack.",
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


def check_explicit_keywords(domain: str) -> Optional[DetectionResult]:
    """Category-independent safety net: explicit adult/gambling wording in
    the domain string itself fires even when the classifier (static rules
    + AI) hasn't learned the domain yet. Word boundaries keep family names
    and places (Essex, Sussex, Sexton, alphabet) from false-positive."""
    normalized = domain.lower().strip(".")
    for pattern in _ADULT_SUBSTRING_RES + _ADULT_STRICT_RES:
        if pattern.search(normalized):
            return DetectionResult(
                alert_type=AlertType.UNSAFE_CATEGORY,
                severity=AlertSeverity.CRITICAL,
                title="Adult Content Access Attempt",
                description=f"Observed DNS activity to explicitly adult-themed domain: {domain}",
                rule_matched=f"KEYWORD:ADULT_EXPLICIT:{pattern.pattern}",
                explanation=(
                    f"Domain '{domain}' contains an explicit adult-content keyword "
                    f"({pattern.pattern}). Fired on wording alone so unlisted sites "
                    "cannot show as safe."
                ),
            )
    for pattern in _GAMBLING_KEYWORD_RES:
        if pattern.search(normalized):
            return DetectionResult(
                alert_type=AlertType.UNSAFE_CATEGORY,
                severity=AlertSeverity.HIGH,
                title="Online Gambling / Betting Activity",
                description=f"Observed DNS activity to gambling or wagering service: {domain}",
                rule_matched=f"KEYWORD:GAMBLING:{pattern.pattern}",
                explanation=(
                    f"Domain '{domain}' contains a gambling/wagering keyword "
                    f"({pattern.pattern}). Fired on wording alone so unlisted sites "
                    "cannot show as safe."
                ),
            )
    if _BET_LABEL_RE.search(normalized):
        return DetectionResult(
            alert_type=AlertType.UNSAFE_CATEGORY,
            severity=AlertSeverity.HIGH,
            title="Online Gambling / Betting Activity",
            description=f"Observed DNS activity to betting service: {domain}",
            rule_matched="KEYWORD:GAMBLING:bet-label",
            explanation=(
                f"Domain '{domain}' uses 'bet' as a full DNS label, a strong "
                "indicator of a betting service."
            ),
        )
    return None


def check_tunnel_endpoint(domain: str) -> Optional[DetectionResult]:
    """VPN / Tor / proxy endpoint check — tunnels hide activity from local
    DNS observation, so their first sighting deserves an advisory alert."""
    domain_lower = domain.lower().strip(".")
    tor_hit = _endswith_any(domain_lower, KNOWN_TOR_SUFFIXES)
    if tor_hit:
        return DetectionResult(
            alert_type=AlertType.BYPASS_ATTEMPT,
            severity=AlertSeverity.HIGH,
            title="Anonymity Network (Tor) Activity",
            description=f"Observed DNS activity to Tor anonymity infrastructure: {domain}",
            rule_matched=f"TUNNEL:TOR:{tor_hit}",
            explanation=(
                f"Domain '{domain}' belongs to Tor anonymity-network infrastructure. "
                "Tor traffic is intentionally untraceable and bypasses all local "
                "parental safety observation."
            ),
        )
    vpn_hit = _endswith_any(domain_lower, KNOWN_VPN_SUFFIXES)
    if vpn_hit:
        return DetectionResult(
            alert_type=AlertType.BYPASS_ATTEMPT,
            severity=AlertSeverity.MEDIUM,
            title="VPN / Tunnel Endpoint",
            description=f"Observed DNS activity to commercial VPN infrastructure: {domain}",
            rule_matched=f"TUNNEL:VPN:{vpn_hit}",
            explanation=(
                f"Domain '{domain}' belongs to a commercial VPN provider. "
                "Traffic sent through the tunnel bypasses local parental safety "
                "observation while the tunnel is up."
            ),
        )
    labels = set(_labels(domain_lower))
    tunnel_token = next((t for t in _TUNNEL_LABEL_TOKENS if t in labels), None)
    if tunnel_token:
        return DetectionResult(
            alert_type=AlertType.BYPASS_ATTEMPT,
            severity=AlertSeverity.MEDIUM,
            title="Possible Tunnel / Proxy Host",
            description=f"Observed DNS activity to a host advertising tunneling software: {domain}",
            rule_matched=f"TUNNEL:TOKEN:{tunnel_token}",
            explanation=(
                f"DNS label '{tunnel_token}' in '{domain}' indicates tunneling/proxy "
                "software (VPN, WireGuard, Shadowsocks…). Such hosts can carry "
                "traffic around local observation."
            ),
        )
    return None


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
