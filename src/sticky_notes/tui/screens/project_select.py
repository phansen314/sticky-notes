from __future__ import annotations

import sqlite3

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from sticky_notes import service

# Sentinel to distinguish "escape" (no change) from selecting "All Projects" (clear filter).
_CANCEL_SENTINEL = -1


class ProjectSelectModal(ModalScreen[int]):
    """Picker modal for filtering tasks by project.

    Dismisses with:
    - project_id (int > 0): filter to that project
    - 0: "All Projects" selected (clear filter)
    - _CANCEL_SENTINEL (-1): escape / cancel (no change)
    """

    DEFAULT_CSS = """
    ProjectSelectModal {
        align: center middle;
    }

    ProjectSelectModal #select-container {
        width: 50;
        max-height: 60%;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }

    ProjectSelectModal #select-title {
        text-style: bold;
        text-align: center;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
    ]

    def __init__(
        self,
        conn: sqlite3.Connection,
        board_id: int,
        current_project_id: int | None,
    ) -> None:
        super().__init__()
        self._projects = service.list_projects(conn, board_id)
        self._current_project_id = current_project_id

    def compose(self) -> ComposeResult:
        with Vertical(id="select-container"):
            yield Static("Filter by Project", id="select-title")
            all_marker = "> " if self._current_project_id is None else "  "
            options: list[Option] = [
                Option(f"{all_marker}All Projects", id="0"),
            ]
            for p in self._projects:
                if not p.archived:
                    marker = "> " if p.id == self._current_project_id else "  "
                    options.append(Option(f"{marker}{p.name}", id=str(p.id)))
            yield OptionList(*options, id="project-option-list")

    def on_mount(self) -> None:
        option_list = self.query_one("#project-option-list", OptionList)
        if self._current_project_id is None:
            option_list.highlighted = 0
        else:
            active_projects = [p for p in self._projects if not p.archived]
            for idx, project in enumerate(active_projects):
                if project.id == self._current_project_id:
                    option_list.highlighted = idx + 1  # +1 for "All Projects"
                    break
        option_list.focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(int(event.option.id))

    def action_cancel(self) -> None:
        self.dismiss(_CANCEL_SENTINEL)
