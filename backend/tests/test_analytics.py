"""Tests for Phase 7 — Analytics subsystem."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.analytics.service import enrich_category_metrics, generate_csv_stream
from backend.app.analytics.types import NETWORK_INDICATOR_DISCLAIMER
from backend.app.db import analytics_repo as repo
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.models.base import Base
from backend.app.models.classification import DomainClassification
from backend.app.models.device import Device
from backend.app.models.dns import DnsQuery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def analytics_engine():
    """In-memory SQLite engine with StaticPool and seeded multi-device activity."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session_()

    # Seed 2 devices
    dev1 = Device(
        device_id="dev_phone",
        friendly_name="Mom Phone",
        device_type="iOS",
        status="online",
        confidence="HIGH",
        first_seen="2026-09-10 08:00:00",
        last_seen="2026-09-12 23:00:00",
    )
    dev2 = Device(
        device_id="dev_tablet",
        friendly_name="Kid Tablet",
        device_type="Android",
        status="online",
        confidence="HIGH",
        first_seen="2026-09-10 08:00:00",
        last_seen="2026-09-12 23:00:00",
    )
    session.add_all([dev1, dev2])
    session.flush()

    # Seed domain classifications
    session.add_all([
        DomainClassification(domain="youtube.com", category="STREAMING_VIDEO"),
        DomainClassification(domain="facebook.com", category="SOCIAL_MEDIA"),
        DomainClassification(domain="wikipedia.org", category="EDUCATION"),
        DomainClassification(domain="google.com", category="PRODUCTIVITY"),
    ])
    session.flush()

    # Seed queries with varied hours and dates
    queries = [
        # dev_phone: Social media & productivity
        DnsQuery(
            occurred_at="2026-09-12 09:15:00",
            source_ip="192.168.1.10",
            device_id="dev_phone",
            domain="facebook.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        DnsQuery(
            occurred_at="2026-09-12 09:20:00",
            source_ip="192.168.1.10",
            device_id="dev_phone",
            domain="google.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        DnsQuery(
            occurred_at="2026-09-12 14:00:00",
            source_ip="192.168.1.10",
            device_id="dev_phone",
            domain="facebook.com",
            query_type="AAAA",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        # dev_tablet: Streaming & Education
        DnsQuery(
            occurred_at="2026-09-12 14:30:00",
            source_ip="192.168.1.11",
            device_id="dev_tablet",
            domain="youtube.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        DnsQuery(
            occurred_at="2026-09-12 16:45:00",
            source_ip="192.168.1.11",
            device_id="dev_tablet",
            domain="youtube.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        DnsQuery(
            occurred_at="2026-09-12 16:50:00",
            source_ip="192.168.1.11",
            device_id="dev_tablet",
            domain="wikipedia.org",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
        # Unclassified domain on dev_tablet
        DnsQuery(
            occurred_at="2026-09-11 20:00:00",
            source_ip="192.168.1.11",
            device_id="dev_tablet",
            domain="obscure-domain.xyz",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        ),
    ]
    session.add_all(queries)
    session.commit()
    session.close()
    return engine, Session_


@pytest.fixture(scope="function")
def orm_session(analytics_engine):
    _, Session_ = analytics_engine
    session = Session_()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def api_client(analytics_engine):
    _, Session_ = analytics_engine

    def _override_get_session():
        session = Session_()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_session] = _override_get_session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_session, None)


# ---------------------------------------------------------------------------
# Repository Tests
# ---------------------------------------------------------------------------

class TestAnalyticsRepository:
    def test_category_distribution_all(self, orm_session: Session):
        dist = repo.get_category_distribution(orm_session)
        assert len(dist) >= 4
        cat_counts = {d["category"]: d["query_count"] for d in dist}
        assert cat_counts["SOCIAL_MEDIA"] == 2
        assert cat_counts["STREAMING_VIDEO"] == 2
        assert cat_counts["EDUCATION"] == 1
        assert cat_counts["PRODUCTIVITY"] == 1
        assert cat_counts["UNCATEGORIZED"] == 1

        # Check percentage calculation
        total_pct = sum(d["percentage"] for d in dist)
        assert 99.0 <= total_pct <= 100.5

    def test_category_distribution_device_filter(self, orm_session: Session):
        dist = repo.get_category_distribution(orm_session, device_id="dev_tablet")
        cats = {d["category"] for d in dist}
        assert "STREAMING_VIDEO" in cats
        assert "EDUCATION" in cats
        assert "SOCIAL_MEDIA" not in cats

    def test_hourly_activity_24_hours(self, orm_session: Session):
        hourly = repo.get_hourly_activity(orm_session)
        assert len(hourly) == 24
        hours_map = {h["hour"]: h["query_count"] for h in hourly}
        # Hour 9 (09:15, 09:20) should have 2
        assert hours_map[9] == 2
        # Hour 14 (14:00, 14:30) should have 2
        assert hours_map[14] == 2
        # Hour 16 (16:45, 16:50) should have 2
        assert hours_map[16] == 2
        # Hour 3 should be 0
        assert hours_map[3] == 0

    def test_daily_timeline(self, orm_session: Session):
        timeline = repo.get_daily_timeline(orm_session, days=7)
        dates = {t["date"]: t["query_count"] for t in timeline}
        assert "2026-09-12" in dates
        assert dates["2026-09-12"] == 6
        assert "2026-09-11" in dates
        assert dates["2026-09-11"] == 1

    def test_analytics_overview(self, orm_session: Session):
        overview = repo.get_analytics_overview(orm_session)
        assert overview["total_queries"] == 7
        assert overview["distinct_domains"] == 5
        assert overview["active_devices"] == 2
        assert overview["top_category"] in ("SOCIAL_MEDIA", "STREAMING_VIDEO")

    def test_export_dns_records(self, orm_session: Session):
        records = repo.export_dns_records(orm_session)
        assert len(records) == 7
        rec = records[0]
        assert "occurred_at" in rec
        assert "device_name" in rec
        assert "category" in rec
        assert "domain" in rec


# ---------------------------------------------------------------------------
# Service Tests
# ---------------------------------------------------------------------------

class TestAnalyticsService:
    def test_enrich_category_metrics(self):
        raw = [
            {"category": "SOCIAL_MEDIA", "query_count": 10, "distinct_domains": 2, "percentage": 50.0},
            {"category": "STREAMING_VIDEO", "query_count": 10, "distinct_domains": 1, "percentage": 50.0},
        ]
        enriched = enrich_category_metrics(raw)
        assert len(enriched) == 2
        assert enriched[0]["label"] != ""
        assert enriched[0]["color"].startswith("#")
        assert enriched[0]["icon"] != ""

    def test_generate_csv_stream(self):
        records = [
            {
                "id": 1,
                "occurred_at": "2026-09-12 12:00:00",
                "source_ip": "192.168.1.5",
                "device_id": "dev_01",
                "device_name": "Kid Phone",
                "domain": "youtube.com",
                "category": "STREAMING_VIDEO",
                "query_type": "A",
                "response_status": "NOERROR",
                "dns_visibility": "FULL",
            }
        ]
        chunks = list(generate_csv_stream(records))
        full_csv = "".join(chunks)
        assert "occurred_at,source_ip,device_id" in full_csv
        assert "youtube.com" in full_csv
        assert "Kid Phone" in full_csv


# ---------------------------------------------------------------------------
# API Integration & Ethical Labeling Tests
# ---------------------------------------------------------------------------

class TestAnalyticsAPI:
    def test_get_overview_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/overview")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 7
        assert data["active_devices"] == 2
        # Ethical labeling assertion: disclaimer present, metrics are request/query based
        assert "disclaimer" in data
        assert "network-derived indicator" in data["disclaimer"].lower()
        metric_keys = [k for k in data.keys() if k != "disclaimer"]
        assert not any("screen" in k or "app_time" in k for k in metric_keys)

    def test_get_categories_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/categories")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_queries"] == 7
        assert len(data["categories"]) >= 4
        # Check that UI metadata is present
        for cat in data["categories"]:
            assert "label" in cat
            assert "color" in cat
            assert "icon" in cat
        # Ethical disclaimer assertion
        assert "disclaimer" in data

    def test_get_categories_device_filter(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/categories?device_id=dev_tablet")
        assert resp.status_code == 200
        data = resp.json()
        assert data["device_id"] == "dev_tablet"
        cats = [c["category"] for c in data["categories"]]
        assert "STREAMING_VIDEO" in cats
        assert "SOCIAL_MEDIA" not in cats

    def test_get_active_hours_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/active-hours")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["hourly_distribution"]) == 24
        assert "disclaimer" in data

    def test_get_timeline_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/timeline?days=7")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["timeline"]) >= 2
        assert "disclaimer" in data

    def test_export_csv_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/export/csv")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment; filename=" in resp.headers["content-disposition"]
        text = resp.text
        assert "occurred_at" in text
        assert "youtube.com" in text
        assert "facebook.com" in text

    def test_export_json_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/export/json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["record_count"] == 7
        assert len(data["records"]) == 7
        assert "disclaimer" in data
        assert "network-derived indicator" in data["disclaimer"].lower()

    def test_search_engines_repo(self, orm_session: Session):
        from backend.app.db import analytics_repo as repo

        data = repo.get_search_engine_activity(orm_session, days=90)
        by_engine = {e["engine"]: e for e in data["engines"]}
        # google.com x1 (phone) + youtube.com x2 + wikipedia.org x1 (tablet)
        assert by_engine["google"]["visits"] == 1
        assert by_engine["youtube"]["visits"] == 2
        assert by_engine["wikipedia"]["visits"] == 1
        assert "facebook" not in by_engine  # not a search engine

    def test_search_engines_device_filter(self, orm_session: Session):
        from backend.app.db import analytics_repo as repo

        data = repo.get_search_engine_activity(
            orm_session, device_id="dev_tablet", days=90
        )
        by_engine = {e["engine"]: e for e in data["engines"]}
        assert set(by_engine) == {"youtube", "wikipedia"}

    def test_search_engines_endpoint(self, api_client: TestClient):
        resp = api_client.get("/api/analytics/search-engines?days=90")
        assert resp.status_code == 200
        data = resp.json()
        assert "keywords_note" in data
        assert "never" in data["keywords_note"].lower() or "keywords" in data["keywords_note"].lower()
        assert any(e["engine"] == "youtube" for e in data["engines"])
        assert all("engine" in v and "occurred_at" in v for v in data["visits"])

    def test_opened_next_topics(self, orm_session: Session):
        from datetime import datetime, timezone, timedelta
        from backend.app.db import analytics_repo as repo
        from backend.app.models.dns import DnsQuery

        now = datetime.now(timezone.utc).replace(microsecond=0)
        iso = lambda dt: dt.isoformat()
        orm_session.add_all([
            DnsQuery(occurred_at=iso(now - timedelta(minutes=30)), source_ip="1.1.1.1",
                     device_id="dev_phone", domain="www.google.com", query_type="A",
                     response_status="NOERROR", dns_visibility="FULL"),
            DnsQuery(occurred_at=iso(now - timedelta(minutes=28)), source_ip="1.1.1.1",
                     device_id="dev_phone", domain="example-topic.com", query_type="A",
                     response_status="NOERROR", dns_visibility="FULL"),
            DnsQuery(occurred_at=iso(now - timedelta(minutes=27)), source_ip="1.1.1.1",
                     device_id="dev_phone", domain="mail.google.com", query_type="A",
                     response_status="NOERROR", dns_visibility="FULL"),
            DnsQuery(occurred_at=iso(now - timedelta(hours=5)), source_ip="1.1.1.1",
                     device_id="dev_phone", domain="stale-topic.com", query_type="A",
                     response_status="NOERROR", dns_visibility="FULL"),
        ])
        orm_session.commit()

        data = repo.get_search_engine_activity(orm_session, device_id="dev_phone", days=1)
        google = next(e for e in data["engines"] if e["engine"] == "google")
        opened = {n["domain"] for n in google["opened_next"]}
        assert "example-topic.com" in opened
        # Engine hosts never echo as "opened next", even mid-window…
        assert "mail.google.com" not in opened
        assert "www.google.com" not in opened
        # …and neither do domains outside the 10-minute window.
        assert "stale-topic.com" not in opened
