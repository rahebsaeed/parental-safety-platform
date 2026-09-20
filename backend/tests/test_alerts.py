"""Tests for Phase 6 — Safety Alert Subsystem."""
from __future__ import annotations

import pytest
from datetime import datetime, timezone, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.alerts.engine import evaluate, generate_dedup_key
from backend.app.alerts.rules import (
    check_bypass_attempt,
    check_phishing_suspicious,
    check_unsafe_category,
)
from backend.app.alerts.types import AlertSeverity, AlertStatus, AlertType
from backend.app.classifiers.categories import Category
from backend.app.db import alert_repo as repo
from backend.app.db.session import get_session
from backend.app.main import app
from backend.app.models.alert import SafetyAlert
from backend.app.models.base import Base
from backend.app.models.classification import DomainClassification
from backend.app.models.device import Device
from backend.app.models.dns import DnsQuery


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def alert_engine():
    """In-memory SQLite engine with StaticPool and seeded test data."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session_ = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    session = Session_()

    # Seed device
    dev = Device(
        device_id="dev_kid",
        friendly_name="Kid Phone",
        device_type="Android",
        status="online",
        confidence="HIGH",
        first_seen="2026-09-12 10:00:00",
        last_seen="2026-09-12 23:00:00",
    )
    session.add(dev)
    session.flush()

    # Seed some DNS queries
    session.add(
        DnsQuery(
            occurred_at="2026-09-12 23:00:00",
            source_ip="192.168.1.5",
            device_id="dev_kid",
            domain="pornhub.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        )
    )
    session.add(
        DnsQuery(
            occurred_at="2026-09-12 23:05:00",
            source_ip="192.168.1.5",
            device_id="dev_kid",
            domain="paypal-security-verify.net",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        )
    )
    session.add(
        DnsQuery(
            occurred_at="2026-09-12 23:10:00",
            source_ip="192.168.1.5",
            device_id="dev_kid",
            domain="cloudflare-dns.com",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        )
    )
    session.add(
        DnsQuery(
            occurred_at="2026-09-12 23:15:00",
            source_ip="192.168.1.5",
            device_id="dev_kid",
            domain="wikipedia.org",
            query_type="A",
            response_status="NOERROR",
            dns_visibility="FULL",
        )
    )
    # Seed a classified row for pornhub
    session.add(
        DomainClassification(
            domain="pornhub.com",
            category="ADULT_CONTENT",
            rule_type="suffix",
            pattern="pornhub.com",
            is_override=0,
            classified_at="2026-09-12 23:00:00",
        )
    )
    session.commit()
    session.close()
    return engine, Session_


@pytest.fixture(scope="function")
def orm_session(alert_engine):
    _, Session_ = alert_engine
    session = Session_()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def api_client(alert_engine):
    _, Session_ = alert_engine

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
# Rule Evaluator Tests
# ---------------------------------------------------------------------------

class TestAlertRules:
    def test_adult_content_triggers_critical_alert(self):
        res = check_unsafe_category("pornhub.com", Category.ADULT_CONTENT)
        assert res is not None
        assert res.alert_type == AlertType.UNSAFE_CATEGORY
        assert res.severity == AlertSeverity.CRITICAL
        assert "Adult Content" in res.title
        assert "ADULT_CONTENT" in res.rule_matched
        assert res.explanation != ""

    def test_gambling_triggers_high_alert(self):
        res = check_unsafe_category("bet365.com", Category.ADULT_CONTENT)
        assert res is not None
        assert res.alert_type == AlertType.UNSAFE_CATEGORY
        assert res.severity == AlertSeverity.HIGH
        assert "Gambling" in res.title

    def test_benign_category_does_not_trigger_unsafe_alert(self):
        res = check_unsafe_category("wikipedia.org", Category.EDUCATION)
        assert res is None

    def test_known_doh_endpoint_triggers_bypass_alert(self):
        res = check_bypass_attempt("cloudflare-dns.com")
        assert res is not None
        assert res.alert_type == AlertType.BYPASS_ATTEMPT
        assert res.severity == AlertSeverity.MEDIUM
        assert "Bypass" in res.title

    def test_partial_visibility_triggers_bypass_alert(self):
        res = check_bypass_attempt("unknown-domain.com", dns_visibility="PARTIAL")
        assert res is not None
        assert res.alert_type == AlertType.BYPASS_ATTEMPT
        assert "PARTIAL" in res.rule_matched

    def test_full_visibility_benign_does_not_trigger_bypass(self):
        res = check_bypass_attempt("google.com", dns_visibility="FULL")
        assert res is None

    def test_phishing_pattern_paypal_lure(self):
        res = check_phishing_suspicious("paypal-security-update-verify.com")
        assert res is not None
        assert res.alert_type == AlertType.PHISHING_SUSPICIOUS
        assert res.severity == AlertSeverity.HIGH
        assert "PayPal" in res.explanation

    def test_phishing_pattern_apple_lure(self):
        res = check_phishing_suspicious("appleid-account-unlock-support.net")
        assert res is not None
        assert res.alert_type == AlertType.PHISHING_SUSPICIOUS
        assert res.severity == AlertSeverity.HIGH

    def test_normal_paypal_does_not_trigger_phishing(self):
        res = check_phishing_suspicious("www.paypal.com")
        assert res is None


# ---------------------------------------------------------------------------
# Engine Tests
# ---------------------------------------------------------------------------

class TestAlertEngine:
    def test_evaluate_adult_domain(self):
        res = evaluate("xvideos.com")
        assert res is not None
        assert res.alert_type == AlertType.UNSAFE_CATEGORY

    def test_evaluate_phishing_domain(self):
        res = evaluate("netflix-account-renew-billing.com")
        assert res is not None
        assert res.alert_type == AlertType.PHISHING_SUSPICIOUS

    def test_evaluate_benign_domain(self):
        res = evaluate("khanacademy.org")
        assert res is None

    def test_generate_dedup_key(self):
        key = generate_dedup_key("dev_01", "UNSAFE_CATEGORY", "Pornhub.com.")
        assert key == "dev_01:UNSAFE_CATEGORY:pornhub.com"


# ---------------------------------------------------------------------------
# Repository & Deduplication Tests
# ---------------------------------------------------------------------------

class TestAlertRepository:
    def test_create_alert_and_deduplicate(self, orm_session: Session):
        detection = evaluate("pornhub.com")
        assert detection is not None

        # 1st occurrence -> new alert created
        alert1, is_new1 = repo.create_or_dedup_alert(
            orm_session,
            device_id="dev_kid",
            domain="pornhub.com",
            detection=detection,
            cooldown_seconds=3600,
            occurred_at="2026-09-12T23:00:00",
        )
        orm_session.commit()
        assert is_new1 is True
        assert alert1.occurrence_count == 1
        alert_id = alert1.id

        # 2nd occurrence 5 minutes later -> aggregated into existing alert
        alert2, is_new2 = repo.create_or_dedup_alert(
            orm_session,
            device_id="dev_kid",
            domain="pornhub.com",
            detection=detection,
            cooldown_seconds=3600,
            occurred_at="2026-09-12T23:05:00",
        )
        orm_session.commit()
        assert is_new2 is False
        assert alert2.id == alert_id
        assert alert2.occurrence_count == 2
        assert alert2.last_seen_at == "2026-09-12T23:05:00"

    def test_dedup_creates_new_alert_after_cooldown(self, orm_session: Session):
        detection = evaluate("pornhub.com")
        assert detection is not None

        # 1st alert
        alert1, is_new1 = repo.create_or_dedup_alert(
            orm_session,
            device_id="dev_kid",
            domain="pornhub.com",
            detection=detection,
            cooldown_seconds=300,  # 5 min cooldown
            occurred_at="2026-09-12T20:00:00",
        )
        orm_session.commit()
        assert is_new1 is True

        # 2nd alert 2 hours later -> should be a new alert
        alert2, is_new2 = repo.create_or_dedup_alert(
            orm_session,
            device_id="dev_kid",
            domain="pornhub.com",
            detection=detection,
            cooldown_seconds=300,
            occurred_at="2026-09-12T22:00:00",
        )
        orm_session.commit()
        assert is_new2 is True
        assert alert2.id != alert1.id

    def test_update_alert_status(self, orm_session: Session):
        detection = evaluate("pornhub.com")
        alert, _ = repo.create_or_dedup_alert(
            orm_session, "dev_kid", "pornhub.com", detection
        )
        orm_session.commit()

        updated = repo.update_alert_status(orm_session, alert.id, AlertStatus.ACKNOWLEDGED)
        orm_session.commit()
        assert updated is not None
        assert updated.status == "ACKNOWLEDGED"

    def test_scan_queries_for_alerts(self, orm_session: Session):
        result = repo.scan_queries_for_alerts(orm_session)
        orm_session.commit()
        assert result["scanned_queries"] == 4
        # pornhub.com (unsafe), paypal-security-verify.net (phishing), cloudflare-dns.com (bypass)
        assert result["alerts_created"] >= 3

        # Second scan immediately after should aggregate rather than duplicate
        result2 = repo.scan_queries_for_alerts(orm_session)
        orm_session.commit()
        assert result2["alerts_created"] == 0
        assert result2["alerts_aggregated"] >= 3


# ---------------------------------------------------------------------------
# API Integration Tests
# ---------------------------------------------------------------------------

class TestAlertsAPI:
    def test_scan_endpoint(self, api_client: TestClient):
        resp = api_client.post("/api/alerts/scan")
        assert resp.status_code == 200
        data = resp.json()
        assert "scanned_queries" in data
        assert data["alerts_created"] >= 3

    def test_list_alerts_endpoint(self, api_client: TestClient):
        # Scan first
        api_client.post("/api/alerts/scan")
        resp = api_client.get("/api/alerts")
        assert resp.status_code == 200
        alerts = resp.json()
        assert isinstance(alerts, list)
        assert len(alerts) >= 3
        # Check explainability fields
        for a in alerts:
            assert "rule_matched" in a
            assert "explanation" in a
            assert "severity" in a
            assert "title" in a

    def test_list_alerts_filter_severity(self, api_client: TestClient):
        api_client.post("/api/alerts/scan")
        resp = api_client.get("/api/alerts?severity=CRITICAL")
        assert resp.status_code == 200
        alerts = resp.json()
        assert all(a["severity"] == "CRITICAL" for a in alerts)

    def test_get_alert_detail(self, api_client: TestClient):
        api_client.post("/api/alerts/scan")
        list_resp = api_client.get("/api/alerts")
        alert_id = list_resp.json()[0]["id"]

        resp = api_client.get(f"/api/alerts/{alert_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == alert_id
        assert data["rule_matched"] != ""
        assert data["explanation"] != ""

    def test_get_alert_not_found(self, api_client: TestClient):
        resp = api_client.get("/api/alerts/999999")
        assert resp.status_code == 404

    def test_update_alert_status_endpoint(self, api_client: TestClient):
        api_client.post("/api/alerts/scan")
        list_resp = api_client.get("/api/alerts")
        alert_id = list_resp.json()[0]["id"]

        resp = api_client.patch(
            f"/api/alerts/{alert_id}",
            json={"status": "DISMISSED"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "DISMISSED"

    def test_update_alert_invalid_status(self, api_client: TestClient):
        api_client.post("/api/alerts/scan")
        list_resp = api_client.get("/api/alerts")
        alert_id = list_resp.json()[0]["id"]

        resp = api_client.patch(
            f"/api/alerts/{alert_id}",
            json={"status": "NOT_A_REAL_STATUS"},
        )
        assert resp.status_code == 422

    def test_alert_summary_endpoint(self, api_client: TestClient):
        api_client.post("/api/alerts/scan")
        resp = api_client.get("/api/alerts/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert "total_alerts" in data
        assert "active_alerts" in data
        assert "by_severity" in data
        assert "by_type" in data
        assert data["total_alerts"] >= 3


# ---------------------------------------------------------------------------
# Extended detection vectors (DoH, tunnels, explicit keywords, phishing)
# ---------------------------------------------------------------------------

class TestExtendedVectors:
    def test_explicit_adult_keyword_fires_without_category(self):
        res = evaluate("freexxxmovies.test", category="UNCATEGORIZED")
        assert res is not None
        assert res.severity == AlertSeverity.CRITICAL
        assert res.rule_matched.startswith("KEYWORD:ADULT_EXPLICIT")

    def test_explicit_gambling_keyword_fires_without_category(self):
        res = evaluate("melbet-online.test", category="UNCATEGORIZED")
        assert res is not None
        assert res.severity == AlertSeverity.HIGH
        assert res.rule_matched.startswith("KEYWORD:GAMBLING")

    def test_bet_full_label_fires(self):
        res = evaluate("super.bet", category="UNCATEGORIZED")
        assert res is not None
        assert res.severity == AlertSeverity.HIGH

    def test_word_boundaries_avoid_false_positives(self):
        # Family names, places and ordinary words must never fire.
        for benign in (
            "alphabet.test",
            "sussex-records.test",
            "essex.test",
            "sexton.test",
            "milford.test",
            "escorted-tours.test",
            "vector.test",
            "history.test",
            "monitor.test",
            "mistakes.test",
            "stackoverflow.test",
        ):
            assert evaluate(benign, category="UNCATEGORIZED") is None, benign

    def test_glued_explicit_compounds_fire(self):
        # "freexxxmovies" hides "xxx" mid-word — still explicit, must fire.
        for domain in ("freexxxmovies.test", "freeporn.test", "teenporn.test"):
            res = evaluate(domain, category="UNCATEGORIZED")
            assert res is not None, domain
            assert res.severity == AlertSeverity.CRITICAL

    def test_extended_doh_endpoints(self):
        for domain in (
            "dns10.quad9.net",
            "security.cloudflare-dns.com",
            "use-application-dns.net",
            "doh.dns.sb",
        ):
            res = evaluate(domain, category="TECH_INFRASTRUCTURE")
            assert res is not None, domain
            assert res.alert_type == AlertType.BYPASS_ATTEMPT
            assert res.rule_matched == "RESOLVER:KNOWN_DOH_ENDPOINT"

    def test_vpn_endpoint(self):
        res = evaluate("us1.nordvpn.com", category="TECH_INFRASTRUCTURE")
        assert res is not None
        assert res.alert_type == AlertType.BYPASS_ATTEMPT
        assert res.severity == AlertSeverity.MEDIUM
        assert res.rule_matched.startswith("TUNNEL:VPN")

    def test_vpn_suffix_discipline(self):
        # "us-nordvpn.com" is NOT a subdomain of nordvpn.com — no alert.
        assert evaluate("us-nordvpn.com", category="TECH_INFRASTRUCTURE") is None

    def test_tor_endpoint_is_high(self):
        res = evaluate("x.torproject.org", category="TECH_INFRASTRUCTURE")
        assert res is not None
        assert res.severity == AlertSeverity.HIGH
        assert res.rule_matched.startswith("TUNNEL:TOR")

    def test_extended_phishing_lures(self):
        for domain in (
            "microsoft-verify-login.test",
            "amazon-order-suspended.test",
            "facebook-copyright-appeal.test",
            "aramex-pay-customs-fee.test",
            "binance-wallet-verify.test",
            "apple-bill-invoice.test",
            "xn--paypa1-login.test",
        ):
            res = evaluate(domain, category="UNCATEGORIZED")
            assert res is not None, domain
            assert res.alert_type == AlertType.PHISHING_SUSPICIOUS
            assert res.severity == AlertSeverity.HIGH


class TestDomainSecurityDiscipline:
    def test_generic_infra_words_are_not_safe(self):
        from backend.app.classifiers.domain_security import (
            SecurityLevel,
            classify_domain,
        )

        for domain in (
            "evil-api-cloud-shop.test",
            "malicious-news-tracker.test",
            "phish-music-store.test",
            "opencode.ai",
            "main.vscode-cdn.net",
        ):
            assert classify_domain(domain).security_level != SecurityLevel.SAFE, domain

    def test_known_safe_roots_still_safe(self):
        from backend.app.classifiers.domain_security import (
            SecurityLevel,
            classify_domain,
        )

        for domain in ("mail.google.com", "www.youtube.com", "github.com"):
            assert classify_domain(domain).security_level == SecurityLevel.SAFE, domain

    def test_short_tokens_need_boundaries(self):
        from backend.app.classifiers.domain_security import (
            SecurityLevel,
            classify_domain,
        )

        for domain in ("alphabet.test", "vector.test", "history.test", "monitor.test"):
            level = classify_domain(domain).security_level
            assert level not in (SecurityLevel.DANGEROUS, SecurityLevel.RISKY), domain


def test_alerts_carry_device_name(client: TestClient, test_db) -> None:
    """Alerts show the friendly device name, never a bare dev_xx ID."""
    # The shared API fixture schema has no safety_alerts table — create it
    # here (mirrors backend.app.models.alert.SafetyAlert) so this test is
    # self-contained and touches no shared fixture.
    test_db.execute(
        "CREATE TABLE IF NOT EXISTS safety_alerts ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " device_id TEXT, domain TEXT NOT NULL, alert_type TEXT NOT NULL,"
        " severity TEXT NOT NULL DEFAULT 'MEDIUM', title TEXT NOT NULL,"
        " description TEXT NOT NULL, rule_matched TEXT NOT NULL,"
        " explanation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',"
        " occurrence_count INTEGER NOT NULL DEFAULT 1, dedup_key TEXT NOT NULL,"
        " created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
    )
    test_db.execute(
        "INSERT INTO safety_alerts (device_id, domain, alert_type, severity,"
        " title, description, rule_matched, explanation, status,"
        " occurrence_count, dedup_key, created_at, last_seen_at)"
        " VALUES ('dev_01', 'freexxxmovies.test', 'UNSAFE_CATEGORY', 'CRITICAL',"
        " 't', 'd', 'KEYWORD:ADULT_EXPLICIT', 'e', 'ACTIVE', 1,"
        " 'dev_01:UNSAFE_CATEGORY:freexxxmovies.test',"
        " '2026-09-19 06:00:00', '2026-09-19 06:00:00')"
    )
    test_db.commit()
    resp = client.get("/api/alerts")
    assert resp.status_code == 200
    row = next(a for a in resp.json() if a["domain"] == "freexxxmovies.test")
    assert row["device_id"] == "dev_01"
    assert row["device_name"] == "Router Gateway"


_ALERT_DDL = (
    "CREATE TABLE IF NOT EXISTS safety_alerts ("
    " id INTEGER PRIMARY KEY AUTOINCREMENT,"
    " device_id TEXT, domain TEXT NOT NULL, alert_type TEXT NOT NULL,"
    " severity TEXT NOT NULL DEFAULT 'MEDIUM', title TEXT NOT NULL,"
    " description TEXT NOT NULL, rule_matched TEXT NOT NULL,"
    " explanation TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'ACTIVE',"
    " occurrence_count INTEGER NOT NULL DEFAULT 1, dedup_key TEXT NOT NULL,"
    " created_at TEXT NOT NULL, last_seen_at TEXT NOT NULL)"
)


def test_alerts_filter_by_domain(client: TestClient, test_db) -> None:
    """The activity inspector links to alerts for one exact domain."""
    test_db.execute(_ALERT_DDL)
    test_db.execute(
        "INSERT INTO safety_alerts (device_id, domain, alert_type, severity,"
        " title, description, rule_matched, explanation, status,"
        " occurrence_count, dedup_key, created_at, last_seen_at)"
        " VALUES ('dev_02', 'cloudflare-dns.com', 'BYPASS_ATTEMPT', 'MEDIUM',"
        " 't', 'd', 'RESOLVER:KNOWN_DOH_ENDPOINT', 'e', 'ACTIVE', 1,"
        " 'k1', '2026-09-19 06:00:00', '2026-09-19 06:00:00'),"
        " ('dev_02', 'example.com', 'UNSAFE_CATEGORY', 'CRITICAL',"
        " 't', 'd', 'CATEGORY:ADULT_CONTENT', 'e', 'ACTIVE', 1,"
        " 'k2', '2026-09-19 06:00:00', '2026-09-19 06:00:00')"
    )
    test_db.commit()
    resp = client.get("/api/alerts?domain=cloudflare-dns.com")
    assert resp.status_code == 200
    rows = resp.json()
    assert len(rows) == 1
    assert rows[0]["rule_matched"] == "RESOLVER:KNOWN_DOH_ENDPOINT"
