# Cross-cutting / integration tests (not yet needed)

Component-level tests live next to their code (`collector/tests/`,
`backend/tests/`, `frontend/tests/`). This directory is reserved for tests
that span multiple components once there's more than one component to span —
e.g. collector-writes-to-SQLite → backend-reads-from-it, once Phase 3 exists.
