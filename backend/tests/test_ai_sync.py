"""Tests for AI-assisted classification (OpenRouter verdicts -> rules).

An unlisted adult domain must end up ADULT_CONTENT in domain_classifications
so the alert scan fires — never silently UNCATEGORIZED. Uses mocked AI
responses; no network calls.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from unittest.mock import patch

from backend.app.classifiers.categories import Category
from backend.app.classifiers.openrouter_classifier import map_ai_category
from backend.app.db import classification_repo as repo
from backend.app.models.base import Base
from backend.app.models import Device, DnsQuery, DomainClassification


@pytest.fixture(scope="function")
def orm_session() -> Session:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autocommit=False, autoflush=False)()
    session.add(
        Device(
            device_id="dev_01", friendly_name="Kid", device_type="Android",
            status="online", confidence="HIGH",
            first_seen="2026-09-12 12:00:00", last_seen="2026-09-12 23:00:00",
        )
    )
    session.commit()
    try:
        yield session
    finally:
        session.close()


def _add_queries(session: Session, domain: str, count: int) -> None:
    for _ in range(count):
        session.add(
            DnsQuery(
                occurred_at="2026-09-12 23:00:00", source_ip="192.168.1.4",
                device_id="dev_01", domain=domain, query_type="A",
                response_status="NOERROR", dns_visibility="FULL",
            )
        )
    session.commit()


# ---------------------------------------------------------------------------
# Mapping
# ---------------------------------------------------------------------------

class TestMapAiCategory:
    def test_unsafe_and_gambling_map_to_adult_content(self):
        assert map_ai_category("UNSAFE") == Category.ADULT_CONTENT
        assert map_ai_category("GAMBLING") == Category.ADULT_CONTENT

    def test_benign_categories_map_sensibly(self):
        assert map_ai_category("MESSAGING") == Category.SOCIAL_MEDIA
        assert map_ai_category("SOCIAL_MEDIA") == Category.SOCIAL_MEDIA
        assert map_ai_category("STREAMING") == Category.STREAMING_VIDEO
        assert map_ai_category("INFRASTRUCTURE_SYSTEM") == Category.TECH_INFRASTRUCTURE

    def test_unknown_and_garbage_map_to_none(self):
        assert map_ai_category("UNKNOWN") is None
        assert map_ai_category("SOMETHING_ELSE") is None
        assert map_ai_category("") is None
        assert map_ai_category("unsafe") == Category.ADULT_CONTENT  # case-insensitive


# ---------------------------------------------------------------------------
# upsert_ai_classification
# ---------------------------------------------------------------------------

class TestUpsertAiClassification:
    def test_creates_openrouter_row(self, orm_session: Session):
        row = repo.upsert_ai_classification(
            orm_session, "evil.test", Category.ADULT_CONTENT,
            model="test-model", reason="AI says adult",
        )
        orm_session.commit()
        assert row is not None
        assert row.category == "ADULT_CONTENT"
        assert row.rule_type == "openrouter"
        assert row.pattern == "test-model"
        assert row.is_override == 0

    def test_never_overwrites_manual_override(self, orm_session: Session):
        repo.set_override(orm_session, "mom-blog.test", "EDUCATION", note="parent")
        orm_session.commit()
        result = repo.upsert_ai_classification(
            orm_session, "mom-blog.test", Category.ADULT_CONTENT,
            model="test-model", reason="AI disagrees",
        )
        assert result is None
        row = repo.get_classification(orm_session, "mom-blog.test")
        assert row.category == "EDUCATION"
        assert row.is_override == 1


# ---------------------------------------------------------------------------
# ai_sync_uncategorized
# ---------------------------------------------------------------------------

def _patch_ai(monkeypatch, verdicts: dict, key: str | None = "k"):
    import time as time_mod

    monkeypatch.setattr(
        "backend.app.classifiers.openrouter_classifier.get_openrouter_api_key",
        lambda: key,
    )
    monkeypatch.setattr(
        "backend.app.classifiers.openrouter_classifier.classify_domains_batch",
        lambda domains: {
            d: {"category": verdicts.get(d, "UNKNOWN"), "confidence": 0.9,
                "reason": "mocked", "model": "mock-model"}
            for d in domains
        },
    )
    # Batch pacing sleeps are real seconds — neutralize globally; the
    # dedicated pacing test below asserts on them explicitly.
    monkeypatch.setattr(time_mod, "sleep", lambda s: None)


class TestAiSyncUncategorized:
    def test_no_key_is_graceful(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "mystery.test", 5)
        _patch_ai(monkeypatch, {}, key=None)
        result = repo.ai_sync_uncategorized(orm_session, limit=10)
        assert result["no_api_key"] is True
        assert result["ai_classified"] == 0
        assert repo.get_classification(orm_session, "mystery.test") is None

    def test_unsafe_verdict_persists_adult_content(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "evil-porn.test", 5)
        _patch_ai(monkeypatch, {"evil-porn.test": "UNSAFE"})
        result = repo.ai_sync_uncategorized(orm_session, limit=10)
        assert result["ai_classified"] == 1
        row = repo.get_classification(orm_session, "evil-porn.test")
        assert row is not None
        assert row.category == "ADULT_CONTENT"
        assert row.rule_type == "openrouter"
        assert row.is_override == 0

    def test_unknown_verdict_is_not_persisted(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "weird.test", 5)
        _patch_ai(monkeypatch, {"weird.test": "UNKNOWN"})
        result = repo.ai_sync_uncategorized(orm_session, limit=10)
        assert result["still_unknown"] == 1
        # The static rule pass still records the domain as UNCATEGORIZED,
        # but the AI verdict itself must not be stored as a rule — the
        # domain stays retryable on the next AI run.
        row = repo.get_classification(orm_session, "weird.test")
        assert row is not None
        assert row.category == "UNCATEGORIZED"
        assert row.rule_type != "openrouter"

    def test_rule_known_domains_never_hit_ai(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "youtube.com", 10)
        _add_queries(orm_session, "mystery.test", 1)
        seen: list[list[str]] = []
        _patch_ai(monkeypatch, {"mystery.test": "STREAMING"})
        import backend.app.classifiers.openrouter_classifier as ai_mod
        orig = ai_mod.classify_domains_batch
        monkeypatch.setattr(
            ai_mod, "classify_domains_batch",
            lambda domains: (seen.append(list(domains)), orig(domains))[1],
        )
        repo.ai_sync_uncategorized(orm_session, limit=10)
        assert seen and "youtube.com" not in seen[0]
        assert "mystery.test" in seen[0]
        assert repo.get_classification(orm_session, "youtube.com").category == "STREAMING_VIDEO"

    def test_volume_ordering_and_limit(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "popular.test", 9)
        _add_queries(orm_session, "rare.test", 1)
        _patch_ai(monkeypatch, {"popular.test": "GAMING", "rare.test": "GAMING"})
        result = repo.ai_sync_uncategorized(orm_session, limit=1)
        assert result["ai_classified"] == 1
        assert repo.get_classification(orm_session, "popular.test") is not None
        assert repo.get_classification(orm_session, "rare.test") is None

    def test_override_rows_are_untouchable(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "mom-blog.test", 9)
        repo.set_override(orm_session, "mom-blog.test", "EDUCATION", note="parent")
        orm_session.commit()
        _patch_ai(monkeypatch, {"mom-blog.test": "UNSAFE"})
        result = repo.ai_sync_uncategorized(orm_session, limit=10)
        assert result["ai_classified"] == 0
        assert repo.get_classification(orm_session, "mom-blog.test").category == "EDUCATION"


class TestVerdictParsing:
    def _fake_response(self, content, status=200):
        class FakeResponse:
            status_code = status

            def raise_for_status(self):
                if status >= 400:
                    raise Exception(f"HTTP {status}")

            def json(self):
                return {"choices": [{"message": {"content": content}}]}

        return FakeResponse()

    def test_inline_category_colon_reason(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            lambda *a, **k: self._fake_response(
                "MESSAGING: it's a WhatsApp-related chat site"),
        )
        result = ai_mod.classify_with_openrouter("web.whatsapp.com")
        assert result["category"] == "MESSAGING"
        assert ai_mod.map_ai_category(result["category"]) is not None
        from backend.app.classifiers.categories import Category
        assert ai_mod.map_ai_category(result["category"]) == Category.SOCIAL_MEDIA

    def test_endash_separator(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            lambda *a, **k: self._fake_response(
                "MESSAGING – the domain is a WhatsApp-related chat site"),
        )
        result = ai_mod.classify_with_openrouter("web.whatsapp.com")
        assert result["category"] == "MESSAGING"

    def test_bare_category_still_works(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            lambda *a, **k: self._fake_response("UNSAFE"),
        )
        assert ai_mod.classify_with_openrouter("evil.test")["category"] == "UNSAFE"

    def test_unparseable_answer_is_unknown(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            lambda *a, **k: self._fake_response("This is a website for chatting."),
        )
        result = ai_mod.classify_with_openrouter("x.test")
        assert result["category"] == "UNKNOWN"


class TestAiClassifyDomain:
    def test_persists_mapped_verdict(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "mystery.test", 3)
        _patch_ai(monkeypatch, {"mystery.test": "MESSAGING"})
        outcome = repo.ai_classify_domain(orm_session, "mystery.test")
        assert outcome["ai_used"] is True
        assert outcome["verdict"] == "MESSAGING"
        assert outcome["row"].category == "SOCIAL_MEDIA"
        assert outcome["row"].rule_type == "openrouter"

    def test_skips_ai_when_rules_know_it(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "youtube.com", 3)
        seen: list[list[str]] = []
        _patch_ai(monkeypatch, {})
        import backend.app.classifiers.openrouter_classifier as ai_mod
        orig = ai_mod.classify_domains_batch
        monkeypatch.setattr(
            ai_mod, "classify_domains_batch",
            lambda domains: (seen.append(list(domains)), orig(domains))[1],
        )
        outcome = repo.ai_classify_domain(orm_session, "youtube.com")
        assert outcome["ai_used"] is False
        assert seen == []
        assert outcome["row"].category == "STREAMING_VIDEO"

    def test_no_key_raises(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "mystery.test", 3)
        _patch_ai(monkeypatch, {}, key=None)
        with pytest.raises(RuntimeError, match="No OpenRouter API key"):
            repo.ai_classify_domain(orm_session, "mystery.test")

    def test_override_is_never_touched(self, orm_session: Session, monkeypatch):
        _add_queries(orm_session, "mom-blog.test", 3)
        repo.set_override(orm_session, "mom-blog.test", "EDUCATION", note="parent")
        orm_session.commit()
        _patch_ai(monkeypatch, {"mom-blog.test": "UNSAFE"})
        outcome = repo.ai_classify_domain(orm_session, "mom-blog.test")
        assert outcome["ai_used"] is False
        assert outcome["row"].category == "EDUCATION"


class TestModelRotation:
    @pytest.fixture(autouse=True)
    def _clean_cooldowns(self):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        ai_mod._MODEL_COOLDOWN_UNTIL.clear()
        yield
        ai_mod._MODEL_COOLDOWN_UNTIL.clear()

    def _fake_post(self, calls, script):
        """script: list of (status, content) consumed in order."""
        import backend.app.classifiers.openrouter_classifier as ai_mod

        class FakeResponse:
            def __init__(self, status, content):
                self.status_code = status
                self._content = content

            def raise_for_status(self):
                if self.status_code >= 400:
                    raise ai_mod.requests.exceptions.HTTPError(f"HTTP {self.status_code}")

            def json(self):
                return {"choices": [{"message": {"content": self._content}}]}

        def fake_post(url, headers=None, json=None, timeout=None):
            calls.append(json["model"])
            status, content = script[min(len(calls) - 1, len(script) - 1)]
            return FakeResponse(status, content)

        return fake_post

    def test_cooling_model_is_skipped(self, monkeypatch):
        import time

        import backend.app.classifiers.openrouter_classifier as ai_mod

        ai_mod._MODEL_COOLDOWN_UNTIL[ai_mod.FREE_MODELS[0]] = time.monotonic() + 600
        calls: list[str] = []
        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            self._fake_post(calls, [(200, "MESSAGING: chat app")]),
        )
        result = ai_mod.classify_with_openrouter("x.test")
        assert result["category"] == "MESSAGING"
        assert calls == [ai_mod.FREE_MODELS[1]]
        assert result["model"] == ai_mod.FREE_MODELS[1]

    def test_429_cools_model_and_fails_over(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        calls: list[str] = []
        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            self._fake_post(calls, [(429, ""), (200, "GAMING: games")]),
        )
        result = ai_mod.classify_with_openrouter("x.test")
        assert result["category"] == "GAMING"
        assert calls == [ai_mod.FREE_MODELS[0], ai_mod.FREE_MODELS[1]]
        status = {m["model"]: m for m in ai_mod.get_model_status()}
        assert status[ai_mod.FREE_MODELS[0]]["cooling"] is True
        assert status[ai_mod.FREE_MODELS[1]]["cooling"] is False

    def test_retired_model_is_parked(self, monkeypatch):
        import backend.app.classifiers.openrouter_classifier as ai_mod

        calls: list[str] = []
        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            self._fake_post(calls, [(404, "not found"), (200, "UNSAFE: adult")]),
        )
        result = ai_mod.classify_with_openrouter("x.test")
        assert result["category"] == "UNSAFE"
        status = {m["model"]: m for m in ai_mod.get_model_status()}
        assert status[ai_mod.FREE_MODELS[0]]["retry_in"] > 3600

    def test_all_cooling_still_tries_after_bounded_wait(self, monkeypatch):
        import time

        import backend.app.classifiers.openrouter_classifier as ai_mod

        for m in ai_mod.FREE_MODELS:
            ai_mod._MODEL_COOLDOWN_UNTIL[m] = time.monotonic() + 3600
        slept: list[float] = []
        monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
        calls: list[str] = []
        monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
        monkeypatch.setattr(
            ai_mod.requests, "post",
            self._fake_post(calls, [(200, "STREAMING: video")]),
        )
        result = ai_mod.classify_with_openrouter("x.test")
        assert result["category"] == "STREAMING"
        assert slept and slept[0] <= 30


class TestBatchPacing:
    def test_paces_between_network_calls_not_cached(self, monkeypatch):
        import time as time_mod

        import backend.app.classifiers.openrouter_classifier as ai_mod

        ai_mod._MODEL_COOLDOWN_UNTIL.clear()
        try:
            monkeypatch.setattr(ai_mod, "get_openrouter_api_key", lambda: "k")
            monkeypatch.setattr(
                ai_mod, "get_cached_classification",
                lambda d: {"category": "GAMING", "confidence": 0.9, "model": "m"}
                if d == "cached.test" else None,
            )
            monkeypatch.setattr(
                ai_mod, "classify_with_openrouter",
                lambda d: {"category": "GAMING", "confidence": 0.9,
                           "reason": "m", "model": "m"},
            )
            monkeypatch.setattr(ai_mod, "save_classification", lambda *a: None)
            slept: list[float] = []
            monkeypatch.setattr(time_mod, "sleep", lambda s: slept.append(s))
            results = ai_mod.classify_domains_batch(
                ["cached.test", "a.test", "b.test", "c.test"])
            assert set(results) == {"cached.test", "a.test", "b.test", "c.test"}
            # 3 network calls -> paced between 2nd and 3rd... i.e. sleeps
            # only between calls, never before the first, never for cache.
            assert slept == [ai_mod.BATCH_PACE_SECONDS] * 2
        finally:
            ai_mod._MODEL_COOLDOWN_UNTIL.clear()


# ---------------------------------------------------------------------------
# Alert chain: AI verdict -> stored ADULT_CONTENT -> alert fires
# ---------------------------------------------------------------------------

class TestAiToAlertChain:
    def test_adult_verdict_triggers_unsafe_alert(self, orm_session: Session, monkeypatch):
        from backend.app.alerts.engine import evaluate
        from backend.app.alerts.types import AlertSeverity

        _add_queries(orm_session, "evil-porn.test", 3)
        _patch_ai(monkeypatch, {"evil-porn.test": "UNSAFE"})
        repo.ai_sync_uncategorized(orm_session, limit=10)
        orm_session.commit()

        row = repo.get_classification(orm_session, "evil-porn.test")
        detection = evaluate("evil-porn.test", category=row.category, dns_visibility="FULL")
        assert detection is not None
        assert detection.severity == AlertSeverity.CRITICAL
