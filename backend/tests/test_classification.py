"""Tests for Phase 5 — Domain Classification Engine and API."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.session import get_session
from backend.app.models.base import Base
from backend.app.models import Device, DnsQuery, DomainClassification
from backend.app.classifiers import classify, classify_many, explain, Category
from backend.app.db import classification_repo as repo


from sqlalchemy.pool import StaticPool


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def orm_engine():
    """In-memory SQLite engine with StaticPool and full schema + seed data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session_()

    # Seed a device and some DNS queries
    session.add(
        Device(
            device_id="dev_01",
            friendly_name="Kid Tablet",
            device_type="Android",
            status="online",
            confidence="HIGH",
            first_seen="2026-09-12 12:00:00",
            last_seen="2026-09-12 23:00:00",
        )
    )
    session.flush()
    for domain in ["youtube.com", "facebook.com", "badword.com", "google.com"]:
        session.add(
            DnsQuery(
                occurred_at="2026-09-12 23:00:00",
                source_ip="192.168.1.4",
                device_id="dev_01",
                domain=domain,
                query_type="A",
                response_status="NOERROR",
                dns_visibility="FULL",
            )
        )
    session.commit()
    session.close()
    return engine, Session_


@pytest.fixture(scope="function")
def orm_session(orm_engine):
    _, Session_ = orm_engine
    session = Session_()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def api_client(orm_engine):
    """FastAPI test client with ORM session dependency overridden."""
    _, Session_ = orm_engine

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
# Engine unit tests
# ---------------------------------------------------------------------------

class TestClassificationEngine:
    def setup_method(self):
        classify.cache_clear()

    def test_classify_social_media(self):
        assert classify("www.facebook.com") == Category.SOCIAL_MEDIA

    def test_classify_streaming(self):
        assert classify("youtube.com") == Category.STREAMING_VIDEO
        assert classify("i.ytimg.com") == Category.STREAMING_VIDEO

    def test_classify_gaming(self):
        assert classify("roblox.com") == Category.GAMING
        assert classify("cdn.roblox.com") == Category.GAMING

    def test_classify_education(self):
        assert classify("en.wikipedia.org") == Category.EDUCATION

    def test_classify_productivity(self):
        assert classify("docs.google.com") == Category.PRODUCTIVITY

    def test_classify_adult_content(self):
        assert classify("pornhub.com") == Category.ADULT_CONTENT

    def test_classify_adult_gambling(self):
        assert classify("bet365.com") == Category.ADULT_CONTENT

    def test_classify_ads_tracking(self):
        assert classify("doubleclick.net") == Category.ADS_TRACKING
        assert classify("ads.doubleclick.net") == Category.ADS_TRACKING

    def test_classify_telemetry_contains(self):
        assert classify("telemetry.api.swiftkey.com") == Category.ADS_TRACKING

    def test_classify_tech_infra(self):
        assert classify("connectivitycheck.gstatic.com") == Category.TECH_INFRASTRUCTURE

    def test_classify_news_media(self):
        assert classify("www.bbc.com") == Category.NEWS_MEDIA

    def test_classify_shopping(self):
        assert classify("www.amazon.com") == Category.SHOPPING

    def test_classify_uncategorized(self):
        assert classify("totally-unknown-random-domain-xyz123.net") == Category.UNCATEGORIZED

    def test_classify_many(self):
        results = classify_many(["youtube.com", "facebook.com", "totally-unknown-xyz.net"])
        assert results["youtube.com"] == Category.STREAMING_VIDEO
        assert results["facebook.com"] == Category.SOCIAL_MEDIA
        assert results["totally-unknown-xyz.net"] == Category.UNCATEGORIZED

    def test_explain_returns_rule_info(self):
        info = explain("www.youtube.com")
        assert info["category"] == "STREAMING_VIDEO"
        assert info["rule_type"] == "suffix"
        assert "youtube.com" in info["pattern"]

    def test_explain_uncategorized(self):
        info = explain("unknown999.tld")
        assert info["category"] == "UNCATEGORIZED"
        assert info["rule_type"] is None
        assert info["pattern"] is None

    def test_suffix_match_exact(self):
        """Exact domain name should match its own suffix rule."""
        assert classify("facebook.com") == Category.SOCIAL_MEDIA

    def test_suffix_match_subdomain(self):
        """n-deep subdomain should still match suffix rule."""
        assert classify("a.b.c.facebook.com") == Category.SOCIAL_MEDIA

    def test_no_false_suffix_match(self):
        """myfacebook.com should NOT match facebook.com suffix rule."""
        result = classify("myfacebook.com")
        assert result != Category.SOCIAL_MEDIA


# ---------------------------------------------------------------------------
# Repository unit tests
# ---------------------------------------------------------------------------

class TestClassificationRepository:
    def test_upsert_new_domain(self, orm_session: Session):
        row = repo.upsert_classification(orm_session, "youtube.com")
        orm_session.commit()
        assert row.category == "STREAMING_VIDEO"
        assert row.is_override == 0
        assert row.classified_at is not None

    def test_upsert_idempotent(self, orm_session: Session):
        repo.upsert_classification(orm_session, "youtube.com")
        orm_session.commit()
        repo.upsert_classification(orm_session, "youtube.com")
        orm_session.commit()
        # Still only one row
        count = orm_session.query(DomainClassification).filter_by(domain="youtube.com").count()
        assert count == 1

    def test_override_prevents_reclassification(self, orm_session: Session):
        repo.set_override(orm_session, "youtube.com", "EDUCATION", note="custom")
        orm_session.commit()
        # Re-upsert should NOT change the override
        repo.upsert_classification(orm_session, "youtube.com")
        orm_session.commit()
        row = orm_session.get(DomainClassification, "youtube.com")
        assert row.category == "EDUCATION"
        assert row.is_override == 1
        assert row.note == "custom"

    def test_sync_unclassified(self, orm_session: Session):
        count = repo.sync_unclassified(orm_session)
        orm_session.commit()
        assert count == 4  # 4 unique domains seeded in fixture

    def test_sync_is_idempotent(self, orm_session: Session):
        repo.sync_unclassified(orm_session)
        orm_session.commit()
        count2 = repo.sync_unclassified(orm_session)
        orm_session.commit()
        assert count2 == 0  # already classified

    def test_category_summary(self, orm_session: Session):
        repo.sync_unclassified(orm_session)
        orm_session.commit()
        summary = repo.category_summary(orm_session)
        cats = {r["category"] for r in summary}
        # youtube.com → STREAMING_VIDEO, facebook.com → SOCIAL_MEDIA
        # google.com → PRODUCTIVITY, badword.com → UNCATEGORIZED
        assert "STREAMING_VIDEO" in cats
        assert "SOCIAL_MEDIA" in cats


# ---------------------------------------------------------------------------
# API integration tests
# ---------------------------------------------------------------------------

class TestClassificationAPI:
    def test_classify_endpoint(self, api_client: TestClient):
        resp = api_client.post(
            "/api/classifications/classify",
            json={"domains": ["youtube.com", "facebook.com", "roblox.com"]},
        )
        assert resp.status_code == 200
        results = {r["domain"]: r["category"] for r in resp.json()["results"]}
        assert results["youtube.com"] == "STREAMING_VIDEO"
        assert results["facebook.com"] == "SOCIAL_MEDIA"
        assert results["roblox.com"] == "GAMING"

    def test_classify_uncategorized(self, api_client: TestClient):
        resp = api_client.post(
            "/api/classifications/classify",
            json={"domains": ["unknown-xyz123.net"]},
        )
        assert resp.status_code == 200
        assert resp.json()["results"][0]["category"] == "UNCATEGORIZED"

    def test_sync_endpoint(self, api_client: TestClient, orm_session: Session):
        resp = api_client.post("/api/classifications/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["classified"] >= 0

    def test_get_domain_not_in_db_falls_back_to_engine(self, api_client: TestClient):
        resp = api_client.get("/api/classifications/domains/youtube.com")
        assert resp.status_code == 200
        data = resp.json()
        assert data["domain"] == "youtube.com"
        assert data["category"] == "STREAMING_VIDEO"

    def test_get_domain_stored(self, api_client: TestClient, orm_session: Session):
        repo.upsert_classification(orm_session, "facebook.com")
        orm_session.commit()
        resp = api_client.get("/api/classifications/domains/facebook.com")
        assert resp.status_code == 200
        assert resp.json()["category"] == "SOCIAL_MEDIA"

    def test_override_endpoint(self, api_client: TestClient, orm_session: Session):
        resp = api_client.put(
            "/api/classifications/domains/youtube.com/override",
            json={"category": "EDUCATION", "note": "Khan Academy-equivalent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["category"] == "EDUCATION"
        assert data["is_override"] == 1

    def test_override_invalid_category(self, api_client: TestClient):
        resp = api_client.put(
            "/api/classifications/domains/youtube.com/override",
            json={"category": "NOT_A_REAL_CATEGORY"},
        )
        assert resp.status_code == 422

    def test_summary_endpoint(self, api_client: TestClient, orm_session: Session):
        # First sync so there's something to summarise
        repo.sync_unclassified(orm_session)
        orm_session.commit()
        resp = api_client.get("/api/classifications/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert "total_classified" in data
        # Each item must have the required metadata fields
        for item in data["items"]:
            assert "label" in item
            assert "color" in item
            assert "icon" in item

    def test_list_domains_endpoint(self, api_client: TestClient, orm_session: Session):
        repo.sync_unclassified(orm_session)
        orm_session.commit()
        resp = api_client.get("/api/classifications/domains")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_domains_filter_by_category(self, api_client: TestClient, orm_session: Session):
        repo.sync_unclassified(orm_session)
        orm_session.commit()
        resp = api_client.get("/api/classifications/domains?category=STREAMING_VIDEO")
        assert resp.status_code == 200
        rows = resp.json()
        assert all(r["category"] == "STREAMING_VIDEO" for r in rows)
