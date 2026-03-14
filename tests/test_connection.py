from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path

import pytest

from sticky_notes.connection import get_connection, init_db, transaction


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.db"


@pytest.fixture
def conn(db_path: Path) -> sqlite3.Connection:
    c = get_connection(db_path)
    init_db(c)
    return c


class TestGetConnection:
    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        nested = tmp_path / "a" / "b" / "test.db"
        conn = get_connection(nested)
        assert nested.parent.exists()
        conn.close()

    def test_row_factory_is_sqlite_row(self, conn: sqlite3.Connection) -> None:
        assert conn.row_factory is sqlite3.Row

    def test_foreign_keys_enabled(self, conn: sqlite3.Connection) -> None:
        result = conn.execute("PRAGMA foreign_keys").fetchone()
        assert result[0] == 1

    def test_wal_mode(self, conn: sqlite3.Connection) -> None:
        result = conn.execute("PRAGMA journal_mode").fetchone()
        assert result[0] == "wal"


class TestInitDb:
    def test_tables_created(self, conn: sqlite3.Connection) -> None:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        assert tables == {"boards", "projects", "columns", "tasks", "task_dependencies", "task_history"}

    def test_idempotent(self, conn: sqlite3.Connection) -> None:
        init_db(conn)  # second call should not raise


class TestTransaction:
    def test_commit_on_success(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('test')")
        row = conn.execute("SELECT name FROM boards WHERE name = 'test'").fetchone()
        assert row is not None
        assert row["name"] == "test"

    def test_rollback_on_exception(self, conn: sqlite3.Connection) -> None:
        with pytest.raises(ValueError):
            with transaction(conn):
                conn.execute("INSERT INTO boards (name) VALUES ('rollback_test')")
                raise ValueError("boom")
        row = conn.execute("SELECT name FROM boards WHERE name = 'rollback_test'").fetchone()
        assert row is None

    def test_nested_transaction_not_allowed(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('outer')")
            with pytest.raises(sqlite3.OperationalError):
                with transaction(conn):
                    pass


class TestSelfDependencyConstraint:
    def test_task_cannot_depend_on_itself(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('b')")
            conn.execute("INSERT INTO columns (board_id, name) VALUES (1, 'col')")
            conn.execute("INSERT INTO tasks (board_id, title, column_id) VALUES (1, 't', 1)")
        with pytest.raises(sqlite3.IntegrityError):
            with transaction(conn):
                conn.execute("INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (1, 1)")

    def test_valid_dependency_allowed(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('b')")
            conn.execute("INSERT INTO columns (board_id, name) VALUES (1, 'col')")
            conn.execute("INSERT INTO tasks (board_id, title, column_id) VALUES (1, 't1', 1)")
            conn.execute("INSERT INTO tasks (board_id, title, column_id) VALUES (1, 't2', 1)")
        with transaction(conn):
            conn.execute("INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (1, 2)")
        row = conn.execute("SELECT * FROM task_dependencies").fetchone()
        assert row["task_id"] == 1
        assert row["depends_on_id"] == 2


class TestColumnArchived:
    def test_column_has_archived_default_zero(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('b')")
            conn.execute("INSERT INTO columns (board_id, name) VALUES (1, 'col')")
        row = conn.execute("SELECT archived FROM columns WHERE id = 1").fetchone()
        assert row["archived"] == 0

    def test_column_archived_can_be_set(self, conn: sqlite3.Connection) -> None:
        with transaction(conn):
            conn.execute("INSERT INTO boards (name) VALUES ('b')")
            conn.execute("INSERT INTO columns (board_id, name, archived) VALUES (1, 'col', 1)")
        row = conn.execute("SELECT archived FROM columns WHERE id = 1").fetchone()
        assert row["archived"] == 1
