from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, Static, TextArea

from sticky_notes.service_models import ProjectDetail


class ProjectEditModal(ModalScreen[dict | None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "next_field", "Next", show=True),
        Binding("ctrl+m", "prev_field", "Prev", show=True),
    ]

    def __init__(self, detail: ProjectDetail) -> None:
        self.detail = detail
        super().__init__()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="project-edit-container"):
            yield Label(str(self.detail.id), id="project-edit-id")

            yield Static("Name", classes="form-label")
            yield Input(
                value=self.detail.name,
                placeholder="Project name",
                id="project-edit-name",
                classes="form-field",
            )

            yield Static("Description", classes="form-label")
            yield TextArea(
                self.detail.description or "",
                id="project-edit-desc",
                classes="form-field",
                tab_behavior="indent",
            )

            yield Static("", id="project-edit-error")
            with Horizontal(id="project-edit-buttons"):
                yield Button("Save", variant="primary", id="project-edit-save")
                yield Button("Cancel", id="project-edit-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#project-edit-name", Input).focus()

    def action_next_field(self) -> None:
        self.focus_next()

    def action_prev_field(self) -> None:
        self.focus_previous()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "project-edit-save":
            self.action_save()
        elif event.button.id == "project-edit-cancel":
            self.dismiss(None)

    def _show_error(self, msg: str) -> None:
        self.query_one("#project-edit-error", Static).update(msg)

    def action_save(self) -> None:
        name = self.query_one("#project-edit-name", Input).value.strip()
        if not name:
            self._show_error("Name is required")
            return

        desc_text = self.query_one("#project-edit-desc", TextArea).text.strip()
        description = desc_text or None

        form_values: dict[str, Any] = {
            "name": name,
            "description": description,
        }

        changes: dict[str, Any] = {}
        for field, new_val in form_values.items():
            old_val = getattr(self.detail, field)
            if new_val != old_val:
                changes[field] = new_val

        if not changes:
            self.dismiss(None)
            return

        self.dismiss({"project_id": self.detail.id, "changes": changes})
