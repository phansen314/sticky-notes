from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "sticky-notes" / "sticky-notes.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection(db_path: Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text()
    for statement in schema.split(";"):
        statement = statement.strip()
        if statement:
            conn.execute(statement)


@contextmanager
def transaction(
    conn: sqlite3.Connection,
) -> Generator[sqlite3.Connection, None, None]:
    conn.execute("BEGIN")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise
