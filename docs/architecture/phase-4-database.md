# Phase 4 — Database Architecture

## Summary

Phase 4 formalizes the platform's data layer from initial raw SQL table creation into **SQLAlchemy 2.0 Declarative Models** and an **Alembic Database Migration Engine**.

It establishes a type-safe, maintainable schema layer supporting both local **SQLite** (default zero-configuration deployment with WAL mode and foreign keys) and **PostgreSQL** (production multi-writer deployment), while preserving all historical data collected in Phases 1 and 2.

---

## Schema & Entity Relationships

```
              ┌──────────────────────────────────────────────┐
              │                   devices                    │
              ├──────────────────────────────────────────────┤
              │ device_id (PK)                 VARCHAR(64)   │
              │ friendly_name                  VARCHAR(100)  │
              │ device_type                    VARCHAR(50)   │
              │ primary_mac                    VARCHAR(32)   │
              │ mac_is_randomized              INTEGER       │
              │ vendor                         VARCHAR(255)  │
              │ status                         VARCHAR(32)   │
              │ confidence                     VARCHAR(32)   │
              │ first_seen                     VARCHAR(64)   │
              │ last_seen                      VARCHAR(64)   │
              └───────┬──────────────────────┬───────────────┘
                      │ 1                    │ 1
                      │                      │
                      │ *                    │ *
        ┌─────────────┴──────────┐   ┌───────┴──────────────────────┐
        │    device_addresses    │   │     device_status_events     │
        ├────────────────────────┤   ├──────────────────────────────┤
        │ id (PK)   INTEGER AUTO │   │ id (PK)         INTEGER AUTO │
        │ device_id (FK) VARCHAR │   │ device_id (FK)  VARCHAR      │
        │ ip_address     VARCHAR │   │ status          VARCHAR      │
        │ mac_address    VARCHAR │   │ occurred_at     VARCHAR      │
        │ hostname       VARCHAR │   └──────────────────────────────┘
        │ vendor         VARCHAR │
        │ observed_at    VARCHAR │
        └────────────────────────┘
                      │
                      │ 1
                      │
                      │ 0..*
        ┌─────────────┴────────────────────────────────────────┐
        │                      dns_queries                     │
        ├──────────────────────────────────────────────────────┤
        │ id (PK)                 INTEGER AUTOINCREMENT        │
        │ occurred_at             VARCHAR(64)  [INDEXED]       │
        │ source_ip               VARCHAR(64)                  │
        │ device_id (FK nullable) VARCHAR(64)  [INDEXED]       │
        │ domain                  VARCHAR(255) [INDEXED]       │
        │ query_type              VARCHAR(16)                  │
        │ response_status         VARCHAR(32)                  │
        │ resolved_addresses      TEXT                         │
        │ dns_visibility          VARCHAR(16)                  │
        └──────────────────────────────────────────────────────┘
```

---

## Model Reference (`backend/app/models/`)

### 1. `Device` ([backend/app/models/device.py](file:///home/raheb/Downloads/parental-safety-platform%20(1)/parental-safety-platform/backend/app/models/device.py))
- Represents a logical device identified on the network.
- Handles randomized MAC address rotation via the Phase 1 confidence model.
- Relationships:
  - `addresses`: 1-to-many with `DeviceAddress` (`cascade="all, delete-orphan"`, ordered by `observed_at DESC`).
  - `status_events`: 1-to-many with `DeviceStatusEvent` (`cascade="all, delete-orphan"`).
  - `dns_queries`: 1-to-many with `DnsQuery` (`back_populates="device"`).

### 2. `DeviceAddress` ([backend/app/models/device.py](file:///home/raheb/Downloads/parental-safety-platform%20(1)/parental-safety-platform/backend/app/models/device.py))
- Tracks historical IP/MAC/hostname pairs associated with a device.
- Indexed by `device_id` and `observed_at`.

### 3. `DeviceStatusEvent` ([backend/app/models/device.py](file:///home/raheb/Downloads/parental-safety-platform%20(1)/parental-safety-platform/backend/app/models/device.py))
- Tracks online/offline state transitions over time.

### 4. `DnsQuery` ([backend/app/models/dns.py](file:///home/raheb/Downloads/parental-safety-platform%20(1)/parental-safety-platform/backend/app/models/dns.py))
- Records every DNS request received and answered by the resolver.
- Attributes requester IP to `device_id` when known; flags `dns_visibility = 'PARTIAL'` when bypassed or unassigned.

---

## Alembic Migration Workflow

Alembic migrations live in `backend/alembic/versions/`.

### Migration Commands

```bash
# Activate virtual environment
source collector/.venv/bin/activate

# Apply migrations to head:
parental-api migrate
# Or using alembic directly:
cd backend && alembic upgrade head

# Check current revision:
cd backend && alembic current

# Stamp an existing database (without running DDL):
parental-api stamp
# Or using alembic:
cd backend && alembic stamp head

# Create a new revision after model changes:
cd backend && alembic revision -m "add_domain_categories"
```

---

## Dual Engine Support (SQLite & PostgreSQL)

The database engine is configured in `backend/app/core/config.py`:

- **SQLite (Default)**:
  `sqlite:////path/to/collector/data/discovery.sqlite3`
  - Automated PRAGMA initialization:
    - `PRAGMA journal_mode=WAL;`
    - `PRAGMA busy_timeout=5000;`
    - `PRAGMA foreign_keys=ON;`
- **PostgreSQL (Production)**:
  Set environment variable:
  ```env
  DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/parental_safety
  ```
  Alembic and SQLAlchemy automatically adapt column types and constraints.
