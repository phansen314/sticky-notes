from __future__ import annotations

from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from sticky_notes.formatting import format_priority, format_task_num
from sticky_notes.service_models import TaskRef
from sticky_notes.tui.markup import escape_markup


class TaskCard(Static):
    can_focus = True

    DEFAULT_CSS = """
    TaskCard {
        height: auto;
        padding: 0 1;
        margin: 0 0 1 0;
        border: solid $primary;
    }
    """

    BINDINGS = [
        Binding("up", "nav('up')", show=False),
        Binding("down", "nav('down')", show=False),
        Binding("left", "nav('left')", show=False),
        Binding("right", "nav('right')", show=False),
    ]

    class Navigate(Message):
        """Request directional navigation from the parent BoardView."""

        def __init__(self, direction: str) -> None:
            self.direction = direction
            super().__init__()

    def __init__(self, task_ref: TaskRef) -> None:
        self.task_ref = task_ref
        label = (
            f"{format_task_num(task_ref.id)}  "
            f"{escape_markup(format_priority(task_ref.priority))}  "
            f"{escape_markup(task_ref.title)}"
        )
        super().__init__(label)

    def action_nav(self, direction: str) -> None:
        self.post_message(self.Navigate(direction))
