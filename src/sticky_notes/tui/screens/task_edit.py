from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, TextArea

from sticky_notes.formatting import format_timestamp
from sticky_notes.models import Project, Status
from sticky_notes.service_models import TaskDetail


class TaskEditModal(ModalScreen):
    BINDINGS = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+n", "next_field", "Next", show=True),
        Binding("ctrl+m", "prev_field", "Prev", show=True),
    ]

    def __init__(
        self,
        detail: TaskDetail,
        statuses: tuple[Status, ...],
        projects: tuple[Project, ...],
    ) -> None:
        self.detail = detail
        self._statuses = statuses
        self._projects = projects
        super().__init__()

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="task-edit-container"):
            yield Label(str(self.detail.id), id="task-edit-id")

            yield Static("Title", classes="form-label")
            yield Input(
                value=self.detail.title,
                placeholder="Task title",
                id="task-edit-title",
                classes="form-field",
            )

            yield Static("Description", classes="form-label")
            yield TextArea(
                self.detail.description or "",
                id="task-edit-desc",
                classes="form-field",
                tab_behavior="indent",
            )

            status_options = [(s.name, s.id) for s in self._statuses]
            priority_options = [(str(i), i) for i in range(1, 6)]
            project_options = [(p.name, p.id) for p in self._projects]

            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group"):
                    yield Static("Status", classes="form-label")
                    yield Select(
                        status_options,
                        value=self.detail.status_id,
                        id="task-edit-status",
                        allow_blank=False,
                        classes="form-field",
                    )
                with Vertical(classes="form-group"):
                    yield Static("Priority", classes="form-label")
                    yield Select(
                        priority_options,
                        value=self.detail.priority,
                        id="task-edit-priority",
                        allow_blank=False,
                        classes="form-field",
                    )
                with Vertical(classes="form-group"):
                    yield Static("Project", classes="form-label")
                    yield Select(
                        project_options,
                        value=self.detail.project_id if self.detail.project_id else Select.BLANK,
                        id="task-edit-project",
                        allow_blank=True,
                        classes="form-field",
                    )

            due_str = format_timestamp(self.detail.due_date) if self.detail.due_date else ""
            start_str = format_timestamp(self.detail.start_date) if self.detail.start_date else ""
            finish_str = format_timestamp(self.detail.finish_date) if self.detail.finish_date else ""

            with Horizontal(classes="form-row"):
                with Vertical(classes="form-group"):
                    yield Static("Due Date", classes="form-label")
                    yield Input(
                        value=due_str,
                        placeholder="YYYY-MM-DD",
                        id="task-edit-due",
                        classes="form-field",
                    )
                with Vertical(classes="form-group"):
                    yield Static("Start Date", classes="form-label")
                    yield Input(
                        value=start_str,
                        placeholder="YYYY-MM-DD",
                        id="task-edit-start",
                        classes="form-field",
                    )
                with Vertical(classes="form-group"):
                    yield Static("Finish Date", classes="form-label")
                    yield Input(
                        value=finish_str,
                        placeholder="YYYY-MM-DD",
                        id="task-edit-finish",
                        classes="form-field",
                    )

            yield Static("", id="task-edit-error")
            with Horizontal(id="task-edit-buttons"):
                yield Button("Save", variant="primary", id="task-edit-save")
                yield Button("Cancel", id="task-edit-cancel")

    def on_mount(self) -> None:
        self.query_one("#task-edit-title", Input).focus()

    def action_next_field(self) -> None:
        self.focus_next()

    def action_prev_field(self) -> None:
        self.focus_previous()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "task-edit-save":
            self.action_save()
        elif event.button.id == "task-edit-cancel":
            self.dismiss(None)

    def action_save(self) -> None:
        pass  # Controller phase
