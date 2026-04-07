from __future__ import annotations

from textual.containers import Horizontal, Vertical, ScrollableContainer
from textual.message import Message
from textual.widgets import Label

from sticky_notes.models import Task
from sticky_notes.tui.markup import escape_markup
from sticky_notes.tui.model import GroupNode, WorkspaceModel
from sticky_notes.tui.widgets.task_card import TaskCard


class KanbanBoard(Horizontal):
    class TaskActivated(Message):
        """A task card was activated on the kanban board."""

        def __init__(self, task: Task) -> None:
            self.task = task
            super().__init__()

    def load(self, model: WorkspaceModel) -> None:
        self.remove_children()
        all_tasks = self._collect_all_tasks(model)
        tasks_by_status: dict[int, list[Task]] = {}
        for task in all_tasks:
            tasks_by_status.setdefault(task.status_id, []).append(task)
        for status in model.statuses:
            bucket = tasks_by_status.get(status.id, [])
            title = f"{escape_markup(status.name)} ({len(bucket)})"
            cards = [TaskCard(t, classes="task-card") for t in bucket]
            col = Vertical(
                Label(title, classes="status-col-title"),
                ScrollableContainer(*cards),
                id=f"status-col-{status.id}",
                classes="status-col",
            )
            self.mount(col)

    def on_task_card_activated(self, event: TaskCard.Activated) -> None:
        event.stop()
        self.post_message(self.TaskActivated(event.task))

    def _collect_all_tasks(self, model: WorkspaceModel) -> list[Task]:
        tasks: list[Task] = []
        for pnode in model.projects:
            for gnode in pnode.groups:
                self._collect_group_tasks(gnode, tasks)
            tasks.extend(pnode.ungrouped_tasks)
        tasks.extend(model.unassigned_tasks)
        return tasks

    def _collect_group_tasks(self, gnode: GroupNode, tasks: list[Task]) -> None:
        tasks.extend(gnode.tasks)
        for child in gnode.children:
            self._collect_group_tasks(child, tasks)
