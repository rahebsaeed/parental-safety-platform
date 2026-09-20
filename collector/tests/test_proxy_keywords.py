"""Tests for collector.proxy.keywords — search-term extraction from URLs.

Pure stdlib: runs anywhere, no mitmproxy needed.
"""
from __future__ import annotations

from collector.proxy.keywords import extract_search


class TestExtractSearch:
    def test_google(self):
        assert extract_search("www.google.com", "/search?q=what+is+safety&oq=x") == (
            "Google", "what is safety",
        )

    def test_youtube_results(self):
        assert extract_search("www.youtube.com", "/results?search_query=cats+101") == (
            "YouTube", "cats 101",
        )

    def test_brave(self):
        assert extract_search(
            "search.brave.com", "/search?q=what+is+safety+parents&conversation=abc"
        ) == ("Brave Search", "what is safety parents")

    def test_bing_duckduckgo_yahoo(self):
        assert extract_search("www.bing.com", "/search?q=hello")[0] == "Bing"
        assert extract_search("duckduckgo.com", "/?q=hello+world")[1] == "hello world"
        assert extract_search("search.yahoo.com", "/search?p=hello")[1] == "hello"

    def test_more_engines(self):
        assert extract_search("www.google.co.uk", "/search?q=hello")[0] == "Google"
        assert extract_search("www.google.ca", "/search?q=hello")[0] == "Google"
        assert extract_search("yandex.kz", "/search/?text=hello")[1] == "hello"
        assert extract_search("www.ask.com", "/web?q=hello")[1] == "hello"
        assert extract_search("www.baidu.com", "/s?wd=hello")[1] == "hello"
        assert extract_search("www.sogou.com", "/web?query=hello")[1] == "hello"
        assert extract_search("search.seznam.cz", "/?q=hello")[1] == "hello"
        assert extract_search("search.daum.net", "/search?q=hello")[1] == "hello"

    def test_google_lookalikes_rejected(self):
        assert extract_search("notgoogle.com", "/search?q=hello") is None
        assert extract_search("google.com.evil.com", "/search?q=hello") is None
        assert extract_search("fakegoogle.com", "/search?q=hello") is None

    def test_wikipedia_index_php(self):
        assert extract_search("en.wikipedia.org", "/w/index.php?search=safety") == (
            "Wikipedia", "safety",
        )

    def test_yandex_text_param(self):
        assert extract_search("yandex.com", "/search/?text=hello")[1] == "hello"

    def test_homepage_is_not_a_search(self):
        assert extract_search("www.google.com", "/") is None
        assert extract_search("www.google.com", "/search") is None

    def test_unknown_host_is_not_a_search(self):
        assert extract_search("example.com", "/search?q=hello") is None

    def test_empty_and_long_keywords(self):
        assert extract_search("www.google.com", "/search?q=") is None
        assert extract_search(None, "/search?q=x") is None
        # Spaceless 500-char blob: opaque token, not typed words.
        assert extract_search("www.google.com", "/search?q=" + "y" * 500) is None
        # Long real phrase with spaces: kept, truncated to 200.
        long_kw = ("word " * 100).strip()
        _engine, keywords = extract_search("www.google.com", f"/search?q={long_kw}")
        assert len(keywords) == 200

    def test_opaque_token_is_not_a_search(self):
        blob = "EgRpSwUEGOHau9UGIjB6S83mxwp8uR4GdyaeR8eDmLKIi3hUV02lYReuF89g1rE82zJvg01qeDBsYqOUjoYyAVJaAUM"
        assert extract_search("www.google.com", f"/search?q={blob}") is None
        # …but a real single word still counts.
        assert extract_search("www.google.com", "/search?q=minecraft") == (
            "Google", "minecraft",
        )
