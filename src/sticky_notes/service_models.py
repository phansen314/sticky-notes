from __future__ import annotations

from dataclasses import dataclass

from .models import Column, Project, Task, TaskHistory


# ---- Ref types (relationships as IDs) ----


@dataclass(frozen=True)
class TaskRef(Task):
    blocked_by_ids: tuple[int, ...] = ()
    blocks_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class ProjectRef(Project):
    task_ids: tuple[int, ...] = ()


# ---- Hydrated types (relationships as full objects) ----


@dataclass(frozen=True)
class TaskDetail(TaskRef):
    column: Column | None = None
    project: Project | None = None
    blocked_by: tuple[Task, ...] = ()
    blocks: tuple[Task, ...] = ()
    history: tuple[TaskHistory, ...] = ()


@dataclass(frozen=True)
class ProjectDetail(ProjectRef):
    tasks: tuple[Task, ...] = ()
