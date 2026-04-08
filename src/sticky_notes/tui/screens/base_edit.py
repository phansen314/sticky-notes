from __future__ import annotations

from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Button, Static

from sticky_notes.tui.widgets.markdown_editor import MarkdownEditor


class _ModalScroll(VerticalScroll, can_focus=False):
    pass


class BaseEditModal(ModalScreen[dict | None]):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "next_field", "Next", show=True),
        Binding("ctrl+b", "prev_field", "Prev", show=True),
    ]

    def action_next_field(self) -> None:
        self.focus_next()

    def action_prev_field(self) -> None:
        self.focus_previous()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "modal-save":
            self.action_save()
        elif event.button.id == "modal-cancel":
            self.dismiss(None)

    def _show_error(self, msg: str) -> None:
        self.query_one("#modal-error", Static).update(msg)

    def action_editor_mode(self) -> None:
        try:
            self.query_one(MarkdownEditor).switch_to_editor()
        except NoMatches:
            pass

    def action_preview_mode(self) -> None:
        try:
            self.query_one(MarkdownEditor).switch_to_preview()
        except NoMatches:
            pass
