# Phase 7 — Analytics Architecture

## Overview

The Analytics subsystem converts raw DNS request telemetry into actionable category, temporal, and trend summaries for parents.

### Scientific & Ethical Grounding (Sections 11 & 34)

1. **Explicit Prohibition of "Screen Time" Claims**:
   - DNS request volume reflects network requests, background synchronisation, app push notifications, and keep-alive packets.
   - It **does not measure screen time or human engagement duration**.
   - All analytics schemas and endpoints explicitly label activity as `network_activity` or `query_volume` and carry a permanent disclaimer:
     > *"Network-derived indicator of DNS request activity. Does not represent screen time or human engagement duration. Background processes, push notifications, and telemetry generate network requests independently of user activity."*

2. **Objective Measurement**:
   - Indicators describe what network packets occurred, never speculating about human psychological states or emotions.

---

## 1. Analytics Aggregations

### Category Distribution
- Grouped by Phase 5 category (`SOCIAL_MEDIA`, `STREAMING_VIDEO`, `EDUCATION`, `PRODUCTIVITY`, `TECH_INFRASTRUCTURE`, etc.).
- Computes query volume, distinct domain diversity, and percentage of total activity.
- Supports network-wide overview or per-device filtering.

### Active Hours (Time-of-Day)
- 24-hour histogram from `00:00` to `23:59`.
- Identifies time periods of elevated network activity (e.g. late night activity vs daytime learning).

### Daily Timeline
- Trend analysis over recent days (14-day default, configurable up to 90 days).
- Captures query count and active device count per date.

---

## 2. Data Portability & Export (Section 36)

The platform supports full data portability for parents:
- **CSV Stream** (`GET /api/analytics/export/csv`): Memory-efficient chunked streaming suitable for large historical datasets.
- **JSON Export** (`GET /api/analytics/export/json`): Structured hierarchical data format.
- Both endpoints support date range (`start_time`, `end_time`), `device_id`, and `category` filters.

---

## 3. REST API Endpoints

Mounted under `/api/analytics`:

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/api/analytics/overview` | Overall network metrics (total queries, active devices, dominant category). |
| `GET` | `/api/analytics/categories` | Query distribution across categories with labels, colors, and percentages. |
| `GET` | `/api/analytics/active-hours` | 24-hour distribution of query volume (00:00 to 23:59). |
| `GET` | `/api/analytics/timeline` | Daily request volume and active device count timeline. |
| `GET` | `/api/analytics/export/csv` | Downloadable CSV data export stream. |
| `GET` | `/api/analytics/export/json` | Structured JSON data export. |

---

## 4. Verification Results

- **Automated Tests**: 15 dedicated analytics tests in `backend/tests/test_analytics.py` verifying category distributions, hourly bucketing, daily trends, streaming CSV output, JSON export, and ethical disclaimer labeling assertions.
- **Platform Test Suite**: 97 backend tests + 133 collector tests = 230 tests passing.
- **Live Verification**: Evaluated on 950 live queries in `discovery.sqlite3` across 157 unique domains.
