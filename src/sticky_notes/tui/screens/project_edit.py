from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Input, Static

from sticky_notes.service_models import ProjectDetail
from sticky_notes.tui.screens.base_edit import BaseEditModal, _ModalScroll
from sticky_notes.tui.widgets.markdown_editor import MarkdownEditor


class ProjectEditModal(BaseEditModal):
    BINDINGS = BaseEditModal.BINDINGS + [
        Binding("alt+e", "editor_mode", "Edit MD", show=True),
        Binding("alt+p", "preview_mode", "Preview MD", show=True),
    ]

    def __init__(self, detail: ProjectDetail) -> None:
        self.detail = detail
        super().__init__()

    def compose(self) -> ComposeResult:
        with _ModalScroll(classes="modal-container"):
            yield Static(str(self.detail.id), classes="modal-id")

            yield Static("Name", classes="form-label")
            yield Input(
                value=self.detail.name,
                placeholder="Project name",
                id="project-edit-name",
                classes="form-field",
            )

            yield Static("Description (alt+e edit | alt+p preview)", classes="form-label")
            yield MarkdownEditor(
                self.detail.description or "",
                id="project-edit-desc",
                classes="form-field",
            )

            yield Static("", id="modal-error", classes="modal-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", variant="primary", id="modal-save")
                yield Button("Cancel", id="modal-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#project-edit-name", Input).focus()

    def action_save(self) -> None:
        name = self.query_one("#project-edit-name", Input).value.strip()
        if not name:
            self._show_error("Name is required")
            return

        desc_text = self.query_one("#project-edit-desc", MarkdownEditor).text.strip()
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
