from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Static

from sticky_notes.service_models import GroupDetail


class GroupEditModal(ModalScreen[dict | None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "next_field", "Next", show=True),
        Binding("ctrl+m", "prev_field", "Prev", show=True),
    ]

    def __init__(self, detail: GroupDetail) -> None:
        self.detail = detail
        super().__init__()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="group-edit-container"):
            yield Label(str(self.detail.id), id="group-edit-id")

            yield Static("Title", classes="form-label")
            yield Input(
                value=self.detail.title,
                placeholder="Group title",
                id="group-edit-title",
                classes="form-field",
            )

            yield Static("", id="group-edit-error")
            with Horizontal(id="group-edit-buttons"):
                yield Button("Save", variant="primary", id="group-edit-save")
                yield Button("Cancel", id="group-edit-cancel")

    def on_mount(self) -> None:
        self.query_one("#group-edit-title", Input).focus()

    def action_next_field(self) -> None:
        self.focus_next()

    def action_prev_field(self) -> None:
        self.focus_previous()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "group-edit-save":
            self.action_save()
        elif event.button.id == "group-edit-cancel":
            self.dismiss(None)

    def _show_error(self, msg: str) -> None:
        self.query_one("#group-edit-error", Static).update(msg)

    def action_save(self) -> None:
        title = self.query_one("#group-edit-title", Input).value.strip()
        if not title:
            self._show_error("Title is required")
            return

        changes: dict[str, Any] = {}
        if title != self.detail.title:
            changes["title"] = title

        if not changes:
            self.dismiss(None)
            return

        self.dismiss({"group_id": self.detail.id, "changes": changes})
