"""Tests for observable traffic tags (DNS-metadata only, never faked)."""
from __future__ import annotations

from backend.app.classifiers.traffic_tags import (
    match_search_engine,
    search_engine_label,
    tags_for_domain,
)


class TestTagsForDomain:
    def test_doh_endpoint_tagged(self):
        assert "DoH" in tags_for_domain("cloudflare-dns.com")
        assert "DoH" in tags_for_domain("dns10.quad9.net")
        assert "DoH" in tags_for_domain("sub.dns.google")

    def test_vpn_and_tor_tagged(self):
        assert "VPN" in tags_for_domain("us1.nordvpn.com")
        assert "Tor" in tags_for_domain("x.torproject.org")

    def test_safesearch_signals_tagged(self):
        assert "SafeSearch" in tags_for_domain("forcesafesearch.google.com")
        assert "SafeSearch" in tags_for_domain("restrict.youtube.com")

    def test_ordinary_domains_untagged(self):
        assert tags_for_domain("www.youtube.com") == []
        assert tags_for_domain("us-nordvpn.com") == []
        assert tags_for_domain(None) == []
        assert tags_for_domain("") == []


class TestSearchEngineMatching:
    def test_major_engines(self):
        assert match_search_engine("www.google.com") == "google"
        assert match_search_engine("google.co.ma") == "google"
        assert match_search_engine("www.youtube.com") == "youtube"
        assert match_search_engine("bing.com") == "bing"
        assert match_search_engine("duckduckgo.com") == "duckduckgo"
        assert match_search_engine("search.yahoo.com") == "yahoo"
        assert match_search_engine("www.reddit.com") == "reddit"
        assert match_search_engine("tiktok.com") == "tiktok"
        assert match_search_engine("en.wikipedia.org") == "wikipedia"

    def test_brave_and_more_engines(self):
        assert match_search_engine("search.brave.com") == "brave"
        assert match_search_engine("www.ecosia.org") == "ecosia"
        assert match_search_engine("www.startpage.com") == "startpage"
        assert match_search_engine("yandex.ru") == "yandex"
        # Browser update hosts are NOT searches
        assert match_search_engine("updates.brave.com") is None
        assert match_search_engine("laptop-updates.brave.com") is None

    def test_google_any_tld(self):
        assert match_search_engine("www.google.co.uk") == "google"
        assert match_search_engine("www.google.ca") == "google"
        assert match_search_engine("notgoogle.com") is None
        assert match_search_engine("google.com.evil.com") is None

    def test_non_engines(self):
        assert match_search_engine("www.youtube.com.evil.com") is None
        assert match_search_engine("notgoogle.com") is None
        assert match_search_engine(None) is None

    def test_labels(self):
        assert search_engine_label("google") == "Google"
        assert search_engine_label("duckduckgo") == "DuckDuckGo"
