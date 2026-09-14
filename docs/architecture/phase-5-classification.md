# Phase 5 — Domain Classification Architecture

## Overview

The Domain Classification Engine categorizes fully-qualified domain names (FQDNs) observed during DNS monitoring into high-level functional and safety categories (e.g., `SOCIAL_MEDIA`, `STREAMING_VIDEO`, `GAMING`, `EDUCATION`, `PRODUCTIVITY`, `ADULT_CONTENT`, `ADS_TRACKING`, `TECH_INFRASTRUCTURE`, `NEWS_MEDIA`, `SHOPPING`, `UNCATEGORIZED`).

Classification is deterministic, highly performant (in-memory LRU cache + rule table), explainable (tracks matching rule pattern and type), supports manual overrides with persistent state, and provides bulk synchronization with existing DNS observation tables.

---

## 1. Categories

| Category | Description | Safety Alert Trigger (Phase 6) |
| :--- | :--- | :--- |
| `SOCIAL_MEDIA` | Social networks, messaging, photo/video sharing platforms | No |
| `STREAMING_VIDEO` | Video on demand, streaming music, podcasts | No |
| `GAMING` | Online gaming services, game stores, game servers | No |
| `EDUCATION` | Learning platforms, reference, encyclopedias, schools | No |
| `PRODUCTIVITY` | Productivity suites, email, cloud drives, collaboration | No |
| `ADULT_CONTENT` | Adult material, pornography, gambling, betting | **Yes** |
| `ADS_TRACKING` | Ad networks, trackers, telemetry, crash reporting | No |
| `TECH_INFRASTRUCTURE` | CDNs, OS connectivity checks, root DNS, cloud backend | No |
| `NEWS_MEDIA` | News outlets, periodicals, journalism | No |
| `SHOPPING` | E-commerce stores, marketplaces, travel booking | No |
| `UNCATEGORIZED` | Unmatched domains awaiting categorization | No |

---

## 2. Rule Evaluation Architecture

Rules are evaluated in strict top-to-bottom priority order; the first matching rule dictates the category.

1. **Safety First**: `ADULT_CONTENT` rules are evaluated first to guarantee they are never shadowed by broader rules.
2. **Telemetry / Ad Attribution**: `ADS_TRACKING` rules (e.g. `telemetry.*`, `doubleclick.net`) precede platform rules so telemetry beacons are separated from user browsing.
3. **Infrastructure Isolation**: Specific connectivity checks (e.g. `connectivitycheck.gstatic.com`) precede broad product domains (`gstatic.com`).
4. **LRU Cache**: `functools.lru_cache(maxsize=4096)` caches resolved domain strings in memory for sub-millisecond lookups during query ingestion.

### Matching Strategies:
- `suffix`: Matches `domain == pattern` or `domain.endswith("." + pattern)`.
- `contains`: Substring match within the domain name.
- `exact`: Direct exact equality match.
- `regex`: Regular expression pattern.

---

## 3. Database Schema & Migration

### `domain_classifications` Table

Created via Alembic revision `0002_domain_classification.py`:

```sql
CREATE TABLE domain_classifications (
    domain          VARCHAR(255) PRIMARY KEY,
    category        VARCHAR(64)  NOT NULL DEFAULT 'UNCATEGORIZED',
    rule_type       VARCHAR(32),
    pattern         VARCHAR(255),
    is_override     INTEGER      NOT NULL DEFAULT 0,
    note            TEXT,
    classified_at   VARCHAR(64)
);

CREATE INDEX idx_dc_category ON domain_classifications (category);
CREATE INDEX idx_dc_classified_at ON domain_classifications (classified_at);
```

- **Primary Key**: `domain` (FQDN string).
- **Manual Overrides**: `is_override = 1` prevents automatic re-classification jobs from modifying human decisions.

---

## 4. REST API Endpoints

All endpoints are mounted under the `/api` prefix:

### Real-Time & Bulk Engine
- `POST /api/classifications/classify`
  - Body: `{"domains": ["youtube.com", "unknown.example"]}`
  - Evaluates domains on-the-fly without database modification.
- `POST /api/classifications/sync`
  - Scans `dns_queries` for unclassified unique domains and batches them into `domain_classifications`.

### Read & Query
- `GET /api/classifications/domains`
  - Query parameters: `category`, `limit`, `offset`.
  - Lists classified domains with pagination.
- `GET /api/classifications/domains/{domain}`
  - Returns classification for a domain; falls back to real-time engine evaluation if not yet written to DB.
- `GET /api/classifications/summary`
  - Returns aggregate breakdown across all categories with colors, display labels, and icons.

### Operator Management
- `PUT /api/classifications/domains/{domain}/override`
  - Body: `{"category": "EDUCATION", "note": "Khan Academy resource"}`
  - Sets `is_override = 1`.

---

## 5. Verification & Live Metrics

1. **Automated Test Coverage**:
   - 35 dedicated classification tests (`backend/tests/test_classification.py`) covering engine rules, suffix specificity, repository operations, sync idempotence, and REST API.
   - Total backend suite: 57 tests passing.
   - Total collector suite: 133 tests passing.
2. **Live Database Sync**:
   - 132 unique live domains from network traffic successfully classified and populated into `discovery.sqlite3`.
