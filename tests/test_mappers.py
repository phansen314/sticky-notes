from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from sticky_notes.connection import get_connection, init_db, transaction
from sticky_notes.mappers import (
    _shallow_fields,
    project_ref_to_detail,
    project_to_ref,
    row_to_board,
    row_to_column,
    row_to_project,
    row_to_task,
    row_to_task_history,
    task_ref_to_detail,
    task_to_ref,
)
from sticky_notes.models import Board, Column, Project, Task, TaskField, TaskHistory
from sticky_notes.service_models import ProjectDetail, ProjectRef, TaskDetail, TaskRef


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = get_connection(tmp_path / "test.db")
    init_db(c)
    return c


@pytest.fixture
def seeded_conn(conn: sqlite3.Connection) -> sqlite3.Connection:
    with transaction(conn):
        conn.execute("INSERT INTO boards (name) VALUES ('board1')")
        conn.execute("INSERT INTO projects (board_id, name, description) VALUES (1, 'proj1', 'desc')")
        conn.execute("INSERT INTO columns (board_id, name, position) VALUES (1, 'todo', 0)")
        conn.execute(
            "INSERT INTO tasks (board_id, title, column_id, project_id, priority) "
            "VALUES (1, 'task1', 1, 1, 5)"
        )
        conn.execute(
            "INSERT INTO tasks (board_id, title, column_id, priority) "
            "VALUES (1, 'task2', 1, 3)"
        )
        conn.execute("INSERT INTO task_dependencies (task_id, depends_on_id) VALUES (1, 2)")
        conn.execute(
            "INSERT INTO task_history (task_id, field, old_value, new_value, source) "
            "VALUES (1, 'title', 'old', 'task1', 'tui')"
        )
    return conn


class TestRowToBoard:
    def test_maps_row(self, seeded_conn: sqlite3.Connection) -> None:
        row = seeded_conn.execute("SELECT * FROM boards WHERE id = 1").fetchone()
        board = row_to_board(row)
        assert isinstance(board, Board)
        assert board.id == 1
        assert board.name == "board1"
        assert board.archived is False

    def test_archived_is_bool(self, seeded_conn: sqlite3.Connection) -> None:
        seeded_conn.execute("UPDATE boards SET archived = 1 WHERE id = 1")
        row = seeded_conn.execute("SELECT * FROM boards WHERE id = 1").fetchone()
        board = row_to_board(row)
        assert board.archived is True


class TestRowToColumn:
    def test_maps_row(self, seeded_conn: sqlite3.Connection) -> None:
        row = seeded_conn.execute("SELECT * FROM columns WHERE id = 1").fetchone()
        col = row_to_column(row)
        assert isinstance(col, Column)
        assert col.id == 1
        assert col.name == "todo"
        assert col.position == 0
        assert col.archived is False


class TestRowToProject:
    def test_maps_row(self, seeded_conn: sqlite3.Connection) -> None:
        row = seeded_conn.execute("SELECT * FROM projects WHERE id = 1").fetchone()
        project = row_to_project(row)
        assert isinstance(project, Project)
        assert project.name == "proj1"
        assert project.description == "desc"


class TestRowToTask:
    def test_maps_row(self, seeded_conn: sqlite3.Connection) -> None:
        row = seeded_conn.execute("SELECT * FROM tasks WHERE id = 1").fetchone()
        task = row_to_task(row)
        assert isinstance(task, Task)
        assert task.title == "task1"
        assert task.priority == 5
        assert task.project_id == 1
        assert task.archived is False


class TestRowToTaskHistory:
    def test_maps_row(self, seeded_conn: sqlite3.Connection) -> None:
        row = seeded_conn.execute("SELECT * FROM task_history WHERE id = 1").fetchone()
        history = row_to_task_history(row)
        assert isinstance(history, TaskHistory)
        assert history.field == TaskField.TITLE
        assert history.old_value == "old"
        assert history.new_value == "task1"
        assert history.source == "tui"


class TestShallowFields:
    def test_extracts_base_class_fields(self) -> None:
        task = Task(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
        )
        fields = _shallow_fields(task, Task)
        assert set(fields.keys()) == {
            "id", "board_id", "title", "project_id", "description",
            "column_id", "priority", "due_date", "position",
            "archived", "created_at", "start_date", "finish_date",
        }

    def test_filters_subclass_fields_when_parent_specified(self) -> None:
        ref = TaskRef(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
            blocked_by_ids=(2,), blocks_ids=(3,),
        )
        fields = _shallow_fields(ref, Task)
        assert "blocked_by_ids" not in fields
        assert "blocks_ids" not in fields

    def test_includes_subclass_fields_when_subclass_specified(self) -> None:
        ref = TaskRef(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
            blocked_by_ids=(2,), blocks_ids=(3,),
        )
        fields = _shallow_fields(ref, TaskRef)
        assert fields["blocked_by_ids"] == (2,)
        assert fields["blocks_ids"] == (3,)


class TestTaskToRef:
    def test_creates_ref(self) -> None:
        task = Task(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
        )
        ref = task_to_ref(task, blocked_by_ids=(2,), blocks_ids=(3,))
        assert isinstance(ref, TaskRef)
        assert ref.title == "t"
        assert ref.blocked_by_ids == (2,)
        assert ref.blocks_ids == (3,)

    def test_safe_with_subclass_input(self) -> None:
        """Passing a TaskRef where Task is expected should not crash."""
        ref = TaskRef(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
            blocked_by_ids=(99,), blocks_ids=(88,),
        )
        new_ref = task_to_ref(ref, blocked_by_ids=(2,), blocks_ids=(3,))
        assert new_ref.blocked_by_ids == (2,)
        assert new_ref.blocks_ids == (3,)


class TestTaskRefToDetail:
    def test_creates_detail(self) -> None:
        col = Column(id=1, board_id=1, name="todo", position=0, archived=False)
        ref = TaskRef(
            id=1, board_id=1, title="t", project_id=None, description=None,
            column_id=1, priority=0, due_date=None, position=0,
            archived=False, created_at=0, start_date=None, finish_date=None,
            blocked_by_ids=(), blocks_ids=(),
        )
        detail = task_ref_to_detail(ref, column=col, project=None, blocked_by=(), blocks=(), history=())
        assert isinstance(detail, TaskDetail)
        assert detail.column == col
        assert detail.title == "t"


class TestProjectToRef:
    def test_creates_ref(self) -> None:
        project = Project(id=1, board_id=1, name="p", description=None, archived=False, created_at=0)
        ref = project_to_ref(project, task_ids=(1, 2))
        assert isinstance(ref, ProjectRef)
        assert ref.task_ids == (1, 2)
        assert ref.name == "p"


class TestProjectRefToDetail:
    def test_creates_detail(self) -> None:
        ref = ProjectRef(id=1, board_id=1, name="p", description=None, archived=False, created_at=0, task_ids=(1,))
        detail = project_ref_to_detail(ref, tasks=())
        assert isinstance(detail, ProjectDetail)
        assert detail.task_ids == (1,)
        assert detail.tasks == ()

    def test_project_detail_inherits_from_project_ref(self) -> None:
        assert issubclass(ProjectDetail, ProjectRef)
