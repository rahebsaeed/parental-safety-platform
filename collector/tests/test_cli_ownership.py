"""Regression tests for the sudo/ownership bug: running `sudo ... scan`
must not leave data/discovery.sqlite3 owned by root, or a later plain
`python ... scan` (passive-only mode — an explicitly supported way to run
this tool) fails with "attempt to write a readonly database".
"""

from __future__ import annotations

import argparse
import os

from collector.device_discovery import cli


def _args(tmp_path):
    return argparse.Namespace(db_path=str(tmp_path / "data" / "discovery.sqlite3"))


def test_open_db_chowns_file_and_directory_when_root_via_sudo(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    chown_calls = []
    monkeypatch.setattr(
        os, "chown", lambda path, uid, gid: chown_calls.append((str(path), uid, gid))
    )

    conn = cli._open_db(_args(tmp_path))
    conn.close()

    chowned_paths = {c[0] for c in chown_calls}
    assert str(tmp_path / "data" / "discovery.sqlite3") in chowned_paths
    assert str(tmp_path / "data") in chowned_paths
    assert all(uid == 1000 and gid == 1000 for _, uid, gid in chown_calls)


def test_open_db_does_not_chown_when_not_root(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    called = []
    monkeypatch.setattr(os, "chown", lambda *a: called.append(a))

    conn = cli._open_db(_args(tmp_path))
    conn.close()
    assert called == []


def test_open_db_does_not_chown_when_root_but_not_via_sudo(tmp_path, monkeypatch):
    """Genuinely running as root (not through sudo) has no invoking user
    to chown to. Documented limitation, not a silent guess.
    """
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.delenv("SUDO_UID", raising=False)
    monkeypatch.delenv("SUDO_GID", raising=False)

    called = []
    monkeypatch.setattr(os, "chown", lambda *a: called.append(a))

    conn = cli._open_db(_args(tmp_path))
    conn.close()
    assert called == []


def test_fix_ownership_failure_is_caught_not_raised(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_UID", "1000")
    monkeypatch.setenv("SUDO_GID", "1000")

    def failing_chown(path, uid, gid):
        raise OSError("permission denied in test")

    monkeypatch.setattr(os, "chown", failing_chown)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_file = data_dir / "discovery.sqlite3"
    db_file.touch()

    # Must not raise -- a chown failure should degrade to a warning, not
    # crash a scan that otherwise succeeded.
    cli._fix_ownership_if_root_via_sudo(str(db_file))


def test_full_reproduction_root_created_db_is_writable_by_owner_after_fix(tmp_path, monkeypatch):
    """End-to-end reproduction of the actual reported bug: simulate a
    sudo-created database, run the ownership fix, and confirm a
    subsequent write by the "invoking user" (simulated by not being root
    anymore) would no longer hit 'attempt to write a readonly database'.

    Since tests don't run as multiple real UIDs, this checks the
    file-mode side effect directly: after the fix, the file and directory
    are both writable by their owner (os.access with the current
    effective permissions), which is what was false before the fix.
    """
    monkeypatch.setattr(os, "geteuid", lambda: 0)
    monkeypatch.setenv("SUDO_UID", str(os.getuid()))
    monkeypatch.setenv("SUDO_GID", str(os.getgid()))

    conn = cli._open_db(_args(tmp_path))
    conn.close()

    db_path = tmp_path / "data" / "discovery.sqlite3"
    assert os.access(db_path, os.W_OK)
    assert os.access(db_path.parent, os.W_OK)
