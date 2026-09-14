from __future__ import annotations

import pytest

from collector.device_discovery import storage


@pytest.fixture
def db_conn(tmp_path):
    """A fresh, real SQLite database in a temp file for each test. Using a
    real file (not :memory:) so the schema-creation path in init_db() is
    exercised the same way it will run in production.
    """
    conn = storage.init_db(tmp_path / "discovery.sqlite3")
    yield conn
    conn.close()
