"""Shared SQLite connection hardening for lgwks durable stores."""

from __future__ import annotations

import sqlite3
from pathlib import Path


def connect(path: str | Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=check_same_thread)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA temp_store=MEMORY")
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
    except sqlite3.DatabaseError:
        # Some in-memory or constrained SQLite handles reject WAL; keep the safer
        # defaults we can always apply and degrade cleanly.
        pass
    return conn
