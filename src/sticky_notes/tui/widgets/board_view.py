from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from textual.containers import Horizontal
from textual.widgets import Static

from sticky_notes import service
from sticky_notes.active_board import get_active_board_id
from sticky_notes.models import TaskFilter
from sticky_notes.tui.widgets.column_widget import ColumnWidget
from sticky_notes.tui.widgets.task_card import TaskCard

if TYPE_CHECKING:
    from sticky_notes.tui.app import StickyNotesApp


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class BoardView(Horizontal):
    DEFAULT_CSS = """
    BoardView {
        height: 1fr;
        width: 100%;
    }
    """

    _col_idx: int = 0
    _task_idx: int = 0
    _has_cards: bool = False

    @property
    def typed_app(self) -> StickyNotesApp:
        return self.app  # type: ignore[return-value]

    @property
    def focused_position(self) -> tuple[int, int] | None:
        if not self._has_cards:
            return None
        return (self._col_idx, self._task_idx)

    def on_mount(self) -> None:
        self._load_board()

    def _load_board(self) -> None:
        conn = self.typed_app.conn
        db_path = self.typed_app.db_path
        config = self.typed_app.config

        board_id = get_active_board_id(db_path)
        if board_id is None:
            self.mount(Static("No active board", id="no-board-message"))
            return

        columns = service.list_columns(conn, board_id)
        if not columns:
            self.mount(Static("No columns on this board", id="no-columns-message"))
            return

        task_filter = TaskFilter(include_archived=config.show_archived)
        tasks = service.list_task_refs_filtered(
            conn, board_id, task_filter=task_filter
        )

        tasks_by_column: dict[int, list] = {col.id: [] for col in columns}
        for task_ref in tasks:
            if task_ref.column_id in tasks_by_column:
                tasks_by_column[task_ref.column_id].append(task_ref)

        self.mount(
            *[ColumnWidget(col, tuple(tasks_by_column[col.id])) for col in columns]
        )

        self._col_idx = 0
        self._task_idx = 0
        self._has_cards = any(tasks_by_column[col.id] for col in columns)
        if self._has_cards:
            self.call_after_refresh(self._focus_current)

    def on_task_card_navigate(self, message: TaskCard.Navigate) -> None:
        message.stop()
        match Direction(message.direction):
            case Direction.UP:
                self._cursor_up()
            case Direction.DOWN:
                self._cursor_down()
            case Direction.LEFT:
                self._cursor_left()
            case Direction.RIGHT:
                self._cursor_right()

    def _get_columns(self) -> list[ColumnWidget]:
        return list(self.query(ColumnWidget))

    def _get_cards(self, col: ColumnWidget) -> list[TaskCard]:
        return list(col.query(TaskCard))

    def _focus_current(self) -> None:
        columns = self._get_columns()
        if not columns:
            self._has_cards = False
            return
        self._col_idx = min(self._col_idx, len(columns) - 1)
        cards = self._get_cards(columns[self._col_idx])
        if not cards:
            self._has_cards = False
            return
        self._task_idx = min(self._task_idx, len(cards) - 1)
        cards[self._task_idx].focus()

    def _cursor_up(self) -> None:
        if self._task_idx > 0:
            self._task_idx -= 1
            self._focus_current()

    def _cursor_down(self) -> None:
        columns = self._get_columns()
        if not columns:
            return
        cards = self._get_cards(columns[self._col_idx])
        if self._task_idx < len(cards) - 1:
            self._task_idx += 1
            self._focus_current()

    def _cursor_left(self) -> None:
        columns = self._get_columns()
        for candidate in range(self._col_idx - 1, -1, -1):
            cards = self._get_cards(columns[candidate])
            if cards:
                self._col_idx = candidate
                self._task_idx = min(self._task_idx, len(cards) - 1)
                self._focus_current()
                return

    def _cursor_right(self) -> None:
        columns = self._get_columns()
        for candidate in range(self._col_idx + 1, len(columns)):
            cards = self._get_cards(columns[candidate])
            if cards:
                self._col_idx = candidate
                self._task_idx = min(self._task_idx, len(cards) - 1)
                self._focus_current()
                return
