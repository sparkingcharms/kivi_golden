"""SQLite persistence and the migration runner.

Design notes:
  * Memories are append-friendly: an edit supersedes rather than overwrites, so
    provenance survives. `superseded_by` gives the chain.
  * Every memory row carries the id of the utterance it came from. Nothing is
    stored without a source you can read back.
  * `trace` and `trace_step` record why a request behaved the way it did.
    This is the engineer-facing surface required by the brief.

The schema lives in `migrations/*.sql`, not in this file. Each migration runs
once, in filename order, inside a transaction, and is recorded in
`schema_migrations`. `connect()` applies anything pending, so the app is never
running against a half-migrated database, and `python manage.py migrate` does
the same thing explicitly.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .config import DB_PATH

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

# Applied to every connection. These are connection settings, not schema, so
# they are not migrations.
PRAGMAS = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
"""

_VERSION_TABLE = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    TEXT PRIMARY KEY,
    applied_ts REAL NOT NULL
);
"""


def migrations() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def applied(conn: sqlite3.Connection) -> set[str]:
    conn.executescript(_VERSION_TABLE)
    return {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}


def migrate(conn: sqlite3.Connection, verbose: bool = False) -> list[str]:
    """Apply every pending migration in order. Returns the versions applied."""
    done = applied(conn)
    run: list[str] = []
    for path in migrations():
        version = path.stem
        if version in done:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            conn.executescript("BEGIN;\n" + sql + "\nCOMMIT;")
        except sqlite3.Error:
            conn.rollback()
            raise
        conn.execute(
            "INSERT INTO schema_migrations (version, applied_ts) VALUES (?,?)",
            (version, time.time()),
        )
        conn.commit()
        run.append(version)
        if verbose:
            print(f"  applied {version}")
    return run


def pending(conn: sqlite3.Connection) -> list[str]:
    done = applied(conn)
    return [p.stem for p in migrations() if p.stem not in done]


def connect(path: Path | str = DB_PATH, auto_migrate: bool = True) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(PRAGMAS)
    if auto_migrate:
        migrate(conn)
    return conn

def now() -> float:
    return time.time()


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def jload(text: str | None) -> Any:
    if not text:
        return {}
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {}


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def db_size_bytes(path: Path | str = DB_PATH) -> int:
    total = 0
    p = Path(path)
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(p) + suffix)
        if f.exists():
            total += f.stat().st_size
    return total


def reset(path: Path | str = DB_PATH) -> None:
    p = Path(path)
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(p) + suffix)
        if f.exists():
            f.unlink()
