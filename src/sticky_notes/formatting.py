from __future__ import annotations


def format_task_num(task_id: int) -> str:
    return f"task-{task_id:04d}"


def format_priority(priority: int) -> str:
    return f"[P{priority}]"
