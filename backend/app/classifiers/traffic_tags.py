"""Observable traffic tags for DNS records.

Every tag here must be derivable from DNS metadata alone (queried domain,
query type, stored classification) — never from packet contents this
platform cannot see. Tags describe *what the domain is known to be*, not
the transport that carried the traffic:

- "DoH" ......... query went to a known encrypted-DNS endpoint. The lookup
                  itself is visible, but anything the client resolves *via*
                  that endpoint afterwards is not.
- "VPN" / "Tor" . first contact with tunnel infrastructure; traffic sent
                  through the tunnel bypasses local observation.
- "SafeSearch" .. forced SafeSearch / Restricted-mode hostname
                  (forcesafesearch.google.com, restrict.youtube.com).

HTTP methods, headers, bodies, cookies, ports and full URLs are NOT
observable at the DNS layer and are therefore never faked here. The
Activity inspector shows exactly the stored DNS record — nothing more.
"""
from __future__ import annotations

from backend.app.alerts.rules import (
    KNOWN_DOH_DOMAINS,
    KNOWN_TOR_SUFFIXES,
    KNOWN_VPN_SUFFIXES,
)


def _matches(domain_lower: str, suffixes: set[str]) -> bool:
    return domain_lower in suffixes or any(
        domain_lower.endswith("." + suffix) for suffix in suffixes
    )


def tags_for_domain(domain: str | None) -> list[str]:
    """Return observable traffic tags for a queried domain (domain-only)."""
    if not domain:
        return []
    normalized = domain.lower().strip().strip(".")
    tags: list[str] = []
    if _matches(normalized, KNOWN_DOH_DOMAINS):
        tags.append("DoH")
    if _matches(normalized, KNOWN_VPN_SUFFIXES):
        tags.append("VPN")
    if _matches(normalized, KNOWN_TOR_SUFFIXES):
        tags.append("Tor")
    if normalized in (
        "forcesafesearch.google.com",
        "restrict.youtube.com",
        "restrictmoderate.youtube.com",
    ) or normalized.endswith(".forcesafesearch.google.com"):
        tags.append("SafeSearch")
    return tags


# ---------------------------------------------------------------------------
# Search engines (domain-level visits — keywords are NOT in DNS traffic)
# ---------------------------------------------------------------------------
# A DNS lookup only ever carries the hostname ("www.google.com"), never the
# "/search?q=..." path. So per-device "search activity" can honestly show
# *which* search engines were used and *when* — but never *what was typed*.
# The UI must say so next to every number on this list.

SEARCH_ENGINES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("google", "Google", ("google.com", "google.co.ma", "google.fr", "google.es", "google.de")),
    ("youtube", "YouTube", ("youtube.com", "youtu.be")),
    ("bing", "Bing", ("bing.com",)),
    ("duckduckgo", "DuckDuckGo", ("duckduckgo.com", "duck.ai")),
    ("yahoo", "Yahoo", ("yahoo.com", "search.yahoo.com")),
    ("brave", "Brave Search", ("search.brave.com",)),
    ("ecosia", "Ecosia", ("ecosia.org",)),
    ("startpage", "Startpage", ("startpage.com",)),
    ("qwant", "Qwant", ("qwant.com",)),
    ("yandex", "Yandex", ("yandex.com", "yandex.ru", "yandex.kz", "yandex.by", "yandex.ua", "yandex.tr", "ya.ru")),
    ("mojeek", "Mojeek", ("mojeek.com",)),
    ("naver", "Naver", ("naver.com",)),
    ("daum", "Daum", ("daum.net",)),
    ("ask", "Ask", ("ask.com",)),
    ("baidu", "Baidu", ("baidu.com",)),
    ("sogou", "Sogou", ("sogou.com",)),
    ("seznam", "Seznam", ("seznam.cz", "search.seznam.cz")),
    ("reddit", "Reddit", ("reddit.com",)),
    ("tiktok", "TikTok", ("tiktok.com",)),
    ("wikipedia", "Wikipedia", ("wikipedia.org",)),
)


def match_search_engine(domain: str | None) -> str | None:
    """Return the engine id if the domain belongs to a search engine."""
    if not domain:
        return None
    normalized = domain.lower().strip().strip(".")
    for engine_id, _label, roots in SEARCH_ENGINES:
        if _matches(normalized, set(roots)):
            return engine_id
    # Any other Google country domain (google.co.uk, google.ca, …).
    import re as _re

    if _re.search(r"(?:^|\.)google\.[a-z]{2,3}(?:\.[a-z]{2})?$", normalized):
        return "google"
    return None


def search_engine_label(engine_id: str) -> str:
    for candidate_id, label, _roots in SEARCH_ENGINES:
        if candidate_id == engine_id:
            return label
    return engine_id
