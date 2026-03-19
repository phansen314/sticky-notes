from __future__ import annotations

import sqlite3

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sticky_notes import service


class BoardSelectModal(ModalScreen[int | None]):
    DEFAULT_CSS = """
    BoardSelectModal {
        align: center middle;
    }

    BoardSelectModal #select-container {
        width: 50;
        max-height: 60%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    BoardSelectModal #select-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(self, conn: sqlite3.Connection, current_board_id: int | None) -> None:
        super().__init__()
        self._boards = service.list_boards(conn)
        self._current_board_id = current_board_id

    def compose(self) -> ComposeResult:
        with Vertical(id="select-container"):
            yield Static("Switch Board", id="select-title")
            options = [
                Option(
                    f"{'> ' if b.id == self._current_board_id else '  '}{b.name}",
                    id=str(b.id),
                )
                for b in self._boards
                if not b.archived
            ]
            yield OptionList(*options, id="board-option-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#board-option-list", OptionList)
        # Highlight the current board
        for idx, board in enumerate(b for b in self._boards if not b.archived):
            if board.id == self._current_board_id:
                option_list.highlighted = idx
                break
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        board_id = int(event.option.id)
        self.dismiss(board_id)

    def action_cancel(self) -> None:
        self.dismiss(None)
