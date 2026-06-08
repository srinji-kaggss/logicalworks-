"""Enterprise SQLite hardening tests.

Covers: PRAGMA verification, retry logic, WAL fallback detection,
connection pool exhaustion + release, migration order enforcement,
thread safety, and rollback on migration failure.
"""

from __future__ import annotations

import queue
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

import lgwks_sqlite as sqlite_hardening
import lgwks_entity_graph as entity_graph
import pytest


class TestPragmas:
    def test_foreign_keys_on(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite_hardening.connect(Path(td) / "x.db")
            try:
                assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
            finally:
                conn.close()

    def test_busy_timeout_5000(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite_hardening.connect(Path(td) / "x.db")
            try:
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            finally:
                conn.close()

    def test_wal_mode_active(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite_hardening.connect(Path(td) / "x.db")
            try:
                mode = conn.execute("PRAGMA journal_mode").fetchone()
                assert mode is not None
                assert mode[0].upper() == "WAL"
            finally:
                conn.close()

    def test_synchronous_normal(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite_hardening.connect(Path(td) / "x.db")
            try:
                assert conn.execute("PRAGMA synchronous").fetchone()[0] == 1
            finally:
                conn.close()

    def test_custom_busy_timeout(self):
        with tempfile.TemporaryDirectory() as td:
            conn = sqlite_hardening.connect(Path(td) / "x.db", busy_timeout_ms=10000)
            try:
                assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10000
            finally:
                conn.close()


class TestRetryLogic:
    def test_retry_on_busy_eventually_succeeds(self):
        """Reader tries to switch a plain DB to WAL while writer holds lock.
        PRAGMA journal_mode=WAL needs EXCLUSIVE and will BUSY; retry recovers."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "busy.db"
            # Create a plain-journal DB (not WAL) and hold a write lock
            writer = sqlite3.connect(str(db_path))
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")

            result = []
            err: Exception | None = None

            def bg():
                nonlocal result, err
                try:
                    # wal=True (default) tries to switch plain DB to WAL → BUSY
                    reader = sqlite_hardening.connect(
                        db_path,
                        max_retries=2,
                        backoff_seconds=0.05,
                        busy_timeout_ms=100,
                    )
                    result = reader.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    # Verify WAL is now active
                    mode = reader.execute("PRAGMA journal_mode").fetchone()
                    result.append(("journal_mode", mode[0]))
                    reader.close()
                except Exception as e:
                    err = e

            t = threading.Thread(target=bg)
            t.start()
            time.sleep(0.05)
            writer.commit()
            writer.close()
            t.join(timeout=2)
            assert t.is_alive() is False
            assert err is None
            assert any(r[0] == "t" for r in result)
            assert any(r == ("journal_mode", "wal") for r in result)

    def test_retry_exhaustion_raises(self):
        """If the lock never releases, 0 retries should raise OperationalError immediately."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "busy.db"
            writer = sqlite3.connect(str(db_path))
            writer.execute("BEGIN IMMEDIATE")
            writer.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")

            result = []
            err: Exception | None = None

            def bg():
                nonlocal result, err
                try:
                    reader = sqlite_hardening.connect(
                        db_path,
                        max_retries=0,
                        backoff_seconds=0.01,
                        busy_timeout_ms=50,
                    )
                    result.append("connected")
                    reader.close()
                except Exception as e:
                    err = e

            t = threading.Thread(target=bg)
            t.start()
            t.join(timeout=2)
            assert t.is_alive() is False
            assert isinstance(err, sqlite3.OperationalError)
            writer.rollback()
            writer.close()


class TestConnectionPool:
    def test_pool_acquire_release(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "pool.db"
            with sqlite_hardening.ConnectionPool(db_path, max_connections=2) as pool:
                c1 = pool.acquire()
                c2 = pool.acquire()
                # Verify distinct connections
                assert c1 is not c2
                # Release and re-acquire
                pool.release(c1)
                c3 = pool.acquire()
                assert c3 is c1  # recycled
                pool.release(c2)
                pool.release(c3)

    def test_pool_exhaustion_blocks_then_times_out(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "pool.db"
            with sqlite_hardening.ConnectionPool(
                db_path, max_connections=1, timeout=0.1
            ) as pool:
                c1 = pool.acquire()
                with pytest.raises(queue.Empty):
                    pool.acquire()
                pool.release(c1)

    def test_pool_context_manager_closes_all(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "pool.db"
            pool = sqlite_hardening.ConnectionPool(db_path, max_connections=2)
            with pool:
                c1 = pool.acquire()
                c2 = pool.acquire()
                pool.release(c1)
                pool.release(c2)
            # After context exit, acquire should raise
            with pytest.raises(RuntimeError, match="closed"):
                pool.acquire()

    def test_pool_thread_safety(self):
        """Multiple threads acquire/release without crashes."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "pool.db"
            with sqlite_hardening.ConnectionPool(db_path, max_connections=3) as pool:
                errors: list[Exception] = []

                def worker():
                    try:
                        for _ in range(10):
                            conn = pool.acquire()
                            conn.execute(
                                "CREATE TABLE IF NOT EXISTS counters (n INTEGER)"
                            )
                            conn.execute(
                                "INSERT INTO counters (n) VALUES (?)", (threading.current_thread().ident,)
                            )
                            conn.commit()
                            pool.release(conn)
                    except Exception as e:
                        errors.append(e)

                threads = [threading.Thread(target=worker) for _ in range(5)]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join(timeout=5)
                assert not errors
                # Final connection check
                c = pool.acquire()
                count = c.execute("SELECT COUNT(*) FROM counters").fetchone()[0]
                assert count == 50  # 5 threads × 10 inserts
                pool.release(c)


class TestMigrations:
    def test_migration_tracks_version(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "migrate.db"
            conn = sqlite_hardening.connect(db_path)
            try:
                mgr = sqlite_hardening.MigrationManager(conn)
                mgr.init()
                assert mgr.current_version() == 0

                migrations = [
                    (1, "create_users", "CREATE TABLE users (id INTEGER PRIMARY KEY);"),
                    (2, "create_posts", "CREATE TABLE posts (id INTEGER PRIMARY KEY, user_id INTEGER);"),
                ]
                mgr.apply(migrations)
                assert mgr.current_version() == 2
                assert mgr.is_applied(1)
                assert mgr.is_applied(2)
            finally:
                conn.close()

    def test_migration_idempotent(self):
        """Re-running the same migrations is a no-op."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "migrate.db"
            conn = sqlite_hardening.connect(db_path)
            try:
                mgr = sqlite_hardening.MigrationManager(conn)
                migrations = [
                    (1, "create_users", "CREATE TABLE users (id INTEGER PRIMARY KEY);"),
                ]
                mgr.apply(migrations)
                # Second run should not fail
                mgr.apply(migrations)
                assert mgr.current_version() == 1
            finally:
                conn.close()

    def test_migration_order_enforced(self):
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "migrate.db"
            conn = sqlite_hardening.connect(db_path)
            try:
                mgr = sqlite_hardening.MigrationManager(conn)
                bad = [
                    (2, "create_posts", "CREATE TABLE posts (id INTEGER PRIMARY KEY);"),
                    (1, "create_users", "CREATE TABLE users (id INTEGER PRIMARY KEY);"),
                ]
                with pytest.raises(RuntimeError, match="out of order"):
                    mgr.apply(bad)
            finally:
                conn.close()

    def test_migration_rollback_on_failure(self):
        """On migration failure the version must not be recorded so the
        migration can be re-applied after the bug is fixed.  SQLite
        auto-commits DDL, so a partially-created table may remain; the
        important guarantee is that _migrations.version is not updated."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "migrate.db"
            conn = sqlite_hardening.connect(db_path)
            try:
                mgr = sqlite_hardening.MigrationManager(conn)
                bad = [
                    (
                        1,
                        "broken",
                        "CREATE TABLE ok (id INTEGER PRIMARY KEY); INSERT INTO ok VALUES (1); SYNTAX ERROR;",
                    ),
                ]
                with pytest.raises(RuntimeError, match="failed"):
                    mgr.apply(bad)
                # The broken migration must not be recorded
                assert mgr.is_applied(1) is False
                assert mgr.current_version() == 0
                # Connection must remain usable
                cur = conn.execute("SELECT 42")
                assert cur.fetchone()[0] == 42
            finally:
                conn.close()


class TestGraphDBIntegration:
    def test_graphdb_uses_hardened_connection(self):
        with tempfile.TemporaryDirectory() as td:
            db = entity_graph.GraphDB(Path(td) / "graph.db")
            try:
                assert db._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
                assert db._conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000
            finally:
                db.close()
