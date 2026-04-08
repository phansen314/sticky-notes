from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, Footer, Input, Static

from sticky_notes.models import Workspace
from sticky_notes.tui.screens.base_edit import BaseEditModal, _ModalScroll


class WorkspaceEditModal(BaseEditModal):
    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        super().__init__()

    def compose(self) -> ComposeResult:
        with _ModalScroll(classes="modal-container"):
            yield Static(str(self.workspace.id), classes="modal-id")

            yield Static("Name", classes="form-label")
            yield Input(
                value=self.workspace.name,
                placeholder="Workspace name",
                id="workspace-edit-name",
                classes="form-field",
            )

            yield Static("", id="modal-error", classes="modal-error")
            with Horizontal(classes="modal-buttons"):
                yield Button("Save", variant="primary", id="modal-save")
                yield Button("Cancel", id="modal-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#workspace-edit-name", Input).focus()

    def action_save(self) -> None:
        name = self.query_one("#workspace-edit-name", Input).value.strip()
        if not name:
            self._show_error("Name is required")
            return

        changes: dict[str, Any] = {}
        if name != self.workspace.name:
            changes["name"] = name

        if not changes:
            self.dismiss(None)
            return

        self.dismiss({"workspace_id": self.workspace.id, "changes": changes})
