"""Tests for collector.proxy.addon record logic (fake flows, real SQLite).

Needs mitmproxy importable (present in the production venv); skipped
otherwise so plain CI without the heavy dep still passes.
"""
from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import pytest

mitmproxy = pytest.importorskip("mitmproxy")

from collector.proxy.addon import ParentalProxy  # noqa: E402


def _make_db(path):
    conn = sqlite3.connect(str(path))
    conn.execute(
        "CREATE TABLE devices (device_id TEXT PRIMARY KEY, status TEXT,"
        " first_seen TEXT, last_seen TEXT)"
    )
    conn.execute(
        "CREATE TABLE device_addresses (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " device_id TEXT, ip_address TEXT, mac_address TEXT, hostname TEXT,"
        " vendor TEXT, observed_at TEXT)"
    )
    conn.execute(
        "INSERT INTO devices VALUES ('dev_kid', 'online', '2026-09-19', '2026-09-19')"
    )
    conn.execute(
        "INSERT INTO device_addresses (device_id, ip_address, observed_at)"
        " VALUES ('dev_kid', '192.168.1.8', '2026-09-19')"
    )
    conn.execute(
        "CREATE TABLE proxy_requests (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " occurred_at TEXT, client_ip TEXT, device_id TEXT, method TEXT,"
        " scheme TEXT, host TEXT, port INTEGER, path TEXT, full_url TEXT,"
        " user_agent TEXT, referer TEXT, req_content_type TEXT, req_size INTEGER,"
        " status_code INTEGER, resp_content_type TEXT, resp_size INTEGER,"
        " page_title TEXT, intercepted INTEGER)"
    )
    conn.execute(
        "CREATE TABLE proxy_search_terms (id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " occurred_at TEXT, device_id TEXT, engine TEXT, keywords TEXT, full_url TEXT)"
    )
    conn.commit()
    conn.close()


def _flow(**overrides):
    from mitmproxy.http import Headers

    request = SimpleNamespace(
        method="GET",
        scheme="https",
        host="www.google.com",
        port=443,
        path="/search?q=what+is+safety",
        url="https://www.google.com/search?q=what+is+safety",
        headers=Headers([
            (b"user-agent", b"TestBrowser/1.0"),
            (b"cookie", b"SESSION=super-secret-must-never-store"),
            (b"authorization", b"Bearer also-secret"),
        ]),
        content=b"",
    )
    response = SimpleNamespace(
        status_code=200,
        headers=Headers([(b"content-type", b"text/html; charset=utf-8")]),
        content=b"<html><head><title>what is safety - Google Search</title></head></html>",
    )
    flow = SimpleNamespace(
        request=request,
        response=response,
        client_conn=SimpleNamespace(address=("192.168.1.8", 51234)),
        metadata={},
    )
    for key, value in overrides.items():
        setattr(flow, key, value)
    return flow


def test_search_request_recorded_with_title_and_device(tmp_path):
    db = tmp_path / "proxy.sqlite3"
    _make_db(db)
    addon = ParentalProxy(db_path=str(db))

    addon._record(_flow())

    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM proxy_requests").fetchone()
    assert row["method"] == "GET"
    assert row["host"] == "www.google.com"
    assert row["status_code"] == 200
    assert row["device_id"] == "dev_kid"
    assert row["page_title"] == "what is safety - Google Search"
    assert "SESSION" not in (row["user_agent"] or "")

    search = conn.execute("SELECT * FROM proxy_search_terms").fetchone()
    assert search["engine"] == "Google"
    assert search["keywords"] == "what is safety"
    assert search["device_id"] == "dev_kid"
    conn.close()


def test_plain_visit_records_no_search_term(tmp_path):
    db = tmp_path / "proxy.sqlite3"
    _make_db(db)
    addon = ParentalProxy(db_path=str(db))

    flow = _flow()
    flow.request.path = "/"
    flow.request.url = "https://www.google.com/"
    addon._record(flow)

    conn = sqlite3.connect(str(db))
    assert conn.execute("SELECT COUNT(*) FROM proxy_requests").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM proxy_search_terms").fetchone()[0] == 0
    conn.close()


def test_record_never_breaks_the_proxy(tmp_path):
    db = tmp_path / "proxy.sqlite3"
    _make_db(db)
    addon = ParentalProxy(db_path=str(db))
    # No response attached (connection failed mid-flight)
    flow = _flow()
    flow.response = None
    addon._record(flow, failed=True)
    conn = sqlite3.connect(str(db))
    row = conn.execute("SELECT status_code FROM proxy_requests").fetchone()
    assert row[0] is None
    conn.close()
