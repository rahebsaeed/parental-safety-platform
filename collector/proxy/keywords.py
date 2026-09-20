"""Search-keyword extraction from request URLs (proxy-visible only).

A normal DNS lookup never carries "/search?q=..." — only a proxy (or the
endpoint itself) sees URL paths. Each rule maps a search host to the query
parameter(s) holding the typed keywords.
"""
from __future__ import annotations

from urllib.parse import parse_qsl, urlsplit, unquote_plus

# host suffix -> ordered query-parameter names holding the keywords.
_ENGINE_PARAMS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("google.com", ("q",)),
    ("google.co.ma", ("q",)),
    ("google.fr", ("q",)),
    ("bing.com", ("q",)),
    ("duckduckgo.com", ("q",)),
    ("duck.ai", ("q",)),
    ("yahoo.com", ("p",)),
    ("search.yahoo.com", ("p",)),
    ("youtube.com", ("search_query",)),
    ("youtu.be", ("search_query",)),
    ("search.brave.com", ("q",)),
    ("ecosia.org", ("q",)),
    ("startpage.com", ("query",)),
    ("qwant.com", ("q",)),
    ("yandex.com", ("text",)),
    ("yandex.ru", ("text",)),
    ("yandex.kz", ("text",)),
    ("yandex.by", ("text",)),
    ("yandex.ua", ("text",)),
    ("yandex.tr", ("text",)),
    ("ya.ru", ("text",)),
    ("mojeek.com", ("q",)),
    ("naver.com", ("query",)),
    ("daum.net", ("q",)),
    ("ask.com", ("q",)),
    ("baidu.com", ("wd",)),
    ("sogou.com", ("query",)),
    ("seznam.cz", ("q",)),
    ("search.seznam.cz", ("q",)),
    ("reddit.com", ("q",)),
    ("tiktok.com", ("q", "keyword")),
    ("wikipedia.org", ("search",)),
)

# Fallback for every other Google country domain (google.co.uk, google.ca,
# google.ae, …): anchored so lookalikes ("notgoogle.com", "google.com.evil.com")
# never match.
_GOOGLE_ANY_RE = None  # compiled lazily (see _host_match)


def _google_any(host: str) -> bool:
    global _GOOGLE_ANY_RE
    if _GOOGLE_ANY_RE is None:
        import re as _re

        _GOOGLE_ANY_RE = _re.compile(r"(?:^|\.)google\.[a-z]{2,3}(?:\.[a-z]{2})?$")
    return bool(_GOOGLE_ANY_RE.search(host))

_ENGINE_LABELS = {
    "google.com": "Google",
    "bing.com": "Bing",
    "duckduckgo.com": "DuckDuckGo",
    "duck.ai": "DuckDuckGo",
    "yahoo.com": "Yahoo",
    "youtube.com": "YouTube",
    "search.brave.com": "Brave Search",
    "ecosia.org": "Ecosia",
    "startpage.com": "Startpage",
    "qwant.com": "Qwant",
    "yandex.com": "Yandex",
    "mojeek.com": "Mojeek",
    "naver.com": "Naver",
    "daum.net": "Daum",
    "ask.com": "Ask",
    "baidu.com": "Baidu",
    "sogou.com": "Sogou",
    "seznam.cz": "Seznam",
    "search.seznam.cz": "Seznam",
    "reddit.com": "Reddit",
    "tiktok.com": "TikTok",
    "wikipedia.org": "Wikipedia",
}

MAX_KEYWORDS_LEN = 200
# A spaceless blob longer than this is an opaque token (session IDs, integrity
# hashes like Google's `sei`), never something a human typed. Single real
# words ("minecraft", "youtube") are far shorter — skip the blobs so the
# parent's keyword list stays readable.
MAX_TOKEN_LEN = 40


def _host_match(host: str) -> tuple[str, tuple[str, ...]] | None:
    host = host.lower().strip().rstrip(".")
    for suffix, params in _ENGINE_PARAMS:
        if host == suffix or host.endswith("." + suffix):
            return suffix, params
    if _google_any(host):
        return "google.com", ("q",)
    return None


def extract_search(host: str | None, path: str | None) -> tuple[str, str] | None:
    """Return (engine_label, keywords) if the URL is a search submission.

    Only fires on /search-like paths carrying a keyword parameter, so plain
    visits to google.com don't count as searches.
    """
    if not host or not path:
        return None
    matched = _host_match(host)
    if not matched:
        return None
    suffix, params = matched
    try:
        split = urlsplit(path if path.startswith("/") else "/" + path)
    except ValueError:
        return None
    # Engine host + engine keyword parameter is sufficient: plain homepages
    # don't carry these parameters (covers /search, /results, /w/index.php,
    # /wiki/Special:Search, …).
    query = dict(parse_qsl(split.query, keep_blank_values=True))
    for param in params:
        raw = query.get(param)
        if raw:
            keywords = unquote_plus(raw).strip()
            if not keywords:
                continue
            if " " not in keywords and len(keywords) > MAX_TOKEN_LEN:
                continue  # opaque token, not typed words
            return _ENGINE_LABELS.get(suffix, suffix), keywords[:MAX_KEYWORDS_LEN]
    return None
