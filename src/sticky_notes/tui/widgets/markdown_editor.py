from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.widget import Widget
from textual.widgets import ContentSwitcher, Markdown, TextArea


class _PreviewScroll(VerticalScroll, can_focus=False):
    pass


class MarkdownEditor(Widget):
    """TextArea editor + Markdown preview, toggled via ContentSwitcher."""

    def __init__(self, text: str = "", *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._initial_text = text

    def compose(self) -> ComposeResult:
        with ContentSwitcher(initial="md-editor"):
            yield TextArea(self._initial_text, id="md-editor", tab_behavior="indent")
            with _PreviewScroll(id="md-preview"):
                yield Markdown(self._initial_text)

    @property
    def text(self) -> str:
        return self.query_one("#md-editor", TextArea).text

    def switch_to_editor(self) -> None:
        self.query_one(ContentSwitcher).current = "md-editor"
        self.query_one("#md-editor", TextArea).focus()

    def switch_to_preview(self) -> None:
        self.query_one(Markdown).update(self.text)
        self.query_one(ContentSwitcher).current = "md-preview"
