# Phase 6 — Safety Alert Architecture

## Overview

The Safety Alert subsystem observes network activity and alerts parents to potential security, privacy, or content concerns.

### Architectural Principles:
1. **Advisory Only (Never Auto-Block)**: The platform never drops DNS packets, alters resolver responses, or terminates network traffic (Sections 9, 33). Safety alerts empower parents to have informed conversations and take device-level action.
2. **Hard Explainability Requirement**: Every alert records the specific rule that triggered it, the category or pattern matched, and a plain-language explanation (Section 35).
3. **Intelligent Deduplication**: Repetitive queries within a configurable cooldown window (default 1 hour) are aggregated into an `occurrence_count` counter with an updated `last_seen_at` timestamp, completely eliminating notification flooding (Section 10).

---

## 1. Alert Severities & Types

### Severities
- `CRITICAL`: Immediate safety concern (e.g. sexually explicit or adult content access).
- `HIGH`: Significant safety risk (e.g. online gambling/wagering, brand impersonation/phishing lures).
- `MEDIUM`: Privacy or observation limitation (e.g. encrypted DNS bypass, DoH probes, partial visibility).
- `LOW`: Informational security notice.

### Types
- `UNSAFE_CATEGORY`: Triggered by Phase 5 domain classifications (e.g. `ADULT_CONTENT`, gambling).
- `PHISHING_SUSPICIOUS`: Triggered by deceptive domain patterns, typosquatting, or credential harvesting lures.
- `BYPASS_ATTEMPT`: Triggered by public DoH/DoT endpoints or `PARTIAL` DNS query visibility.
- `ANOMALOUS_BURST`: Triggered by sudden high-frequency queries to unclassified destinations.

---

## 2. Detection & Explainability Engine

Rules are evaluated in strict priority order:

1. **Unsafe Category Evaluator**:
   - Matches if domain category is `ADULT_CONTENT`.
   - Gambling indicators (`bet`, `casino`, `poker`, `draftkings`, etc.) produce `HIGH` severity.
   - Sexually explicit domains produce `CRITICAL` severity.
   - Evidence records the category and matching domain.
2. **Phishing & Deceptive Pattern Evaluator**:
   - Regular expression pattern table detecting lures mimicking sensitive brands (PayPal, Apple ID, Netflix, Google, Crypto wallets, Banking).
   - Records regex pattern and specific threat rationale.
3. **Encrypted DNS / Bypass Evaluator**:
   - Detects queries directed at known public DoH/DoT endpoints (`cloudflare-dns.com`, `dns.google`, `one.one.one.one`, `doh.cleanbrowsing.org`, etc.).
   - Detects queries flagged with `PARTIAL` DNS visibility, identifying devices utilizing iCloud Private Relay or operating system-level Private DNS.

---

## 3. Deduplication Architecture

Alert deduplication relies on a canonical key:
```
dedup_key = f"{device_id or 'unknown'}:{alert_type}:{domain.lower().strip('.')}"
```

When an alert trigger fires:
1. The repository queries for an existing `ACTIVE` alert with the matching `dedup_key`.
2. If an active alert exists and the time difference between `last_seen_at` and the event timestamp is within `cooldown_seconds` (default 3600s):
   - `occurrence_count` is incremented by 1.
   - `last_seen_at` is updated to the query timestamp.
   - No new database row or redundant alert is created.
3. If no active alert exists or the cooldown window has elapsed:
   - A new `SafetyAlert` row is created with `occurrence_count = 1`.

---

## 4. Database Schema & Migration

### `safety_alerts` Table

Created via Alembic revision `0003_safety_alerts.py`:

```sql
CREATE TABLE safety_alerts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id        VARCHAR(64) REFERENCES devices(device_id) ON DELETE SET NULL,
    domain           VARCHAR(255) NOT NULL,
    alert_type       VARCHAR(64) NOT NULL,
    severity         VARCHAR(32) NOT NULL DEFAULT 'MEDIUM',
    title            VARCHAR(255) NOT NULL,
    description      TEXT NOT NULL,
    rule_matched     VARCHAR(128) NOT NULL,
    explanation      TEXT NOT NULL,
    status           VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    dedup_key        VARCHAR(255) NOT NULL,
    created_at       VARCHAR(64) NOT NULL,
    last_seen_at     VARCHAR(64) NOT NULL
);

CREATE INDEX idx_alerts_device_id ON safety_alerts (device_id);
CREATE INDEX idx_alerts_status ON safety_alerts (status);
CREATE INDEX idx_alerts_severity ON safety_alerts (severity);
CREATE INDEX idx_alerts_dedup_key ON safety_alerts (dedup_key);
CREATE INDEX idx_alerts_created_at ON safety_alerts (created_at);
```

---

## 5. REST API Endpoints

Mounted under `/api/alerts`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/alerts` | Paginated list of alerts (filters: `status`, `severity`, `device_id`). |
| `GET` | `/api/alerts/summary` | Aggregate alert counters (total, active, by severity, by type). |
| `POST` | `/api/alerts/scan` | Trigger safety scan on recent DNS queries. |
| `GET` | `/api/alerts/{id}` | Full alert detail including explainability rationale. |
| `PATCH` | `/api/alerts/{id}` | Update status (`ACKNOWLEDGED`, `DISMISSED`, `RESOLVED`). |

---

## 6. Verification Results

- **Unit & Integration Tests**: 25 dedicated tests in `backend/tests/test_alerts.py` verifying all detection vectors, explainability, deduplication cooldown windows, and API endpoints.
- **Platform Test Suite**: 82 backend tests + 133 collector tests = 215 tests passing.
- **Live Traffic Scan**: 852 real network queries scanned on `discovery.sqlite3` resulting in 23 unique alerts created and 8 occurrences aggregated.
