"""Export a sticky-notes database to a Markdown report."""

from __future__ import annotations

import datetime
import sqlite3


def export_markdown(conn: sqlite3.Connection) -> str:
    """Return full database export as a Markdown string."""
    lines: list[str] = [
        "# Sticky Notes Export",
        "",
        f"Generated: {datetime.date.today().isoformat()}",
        "",
    ]

    boards = conn.execute(
        "SELECT id, name FROM boards WHERE archived = 0"
    ).fetchall()

    for board in boards:
        bid = board["id"]
        lines.append(f"## Board: {board['name']}")
        lines.append("")

        # Columns (active only)
        cols = conn.execute(
            "SELECT id, name, position FROM columns "
            "WHERE board_id = ? AND archived = 0 ORDER BY position",
            (bid,),
        ).fetchall()

        # Tasks (active only)
        tasks = conn.execute(
            "SELECT id, title, column_id, project_id, priority, due_date, position "
            "FROM tasks WHERE board_id = ? AND archived = 0 "
            "ORDER BY column_id, position, id",
            (bid,),
        ).fetchall()
        task_ids = {t["id"] for t in tasks}

        # Projects (active only)
        projects = conn.execute(
            "SELECT id, name, description FROM projects "
            "WHERE board_id = ? AND archived = 0",
            (bid,),
        ).fetchall()
        proj_map = {p["id"]: p["name"] for p in projects}

        # Group tasks by column
        tasks_by_col: dict[int, list[sqlite3.Row]] = {}
        for t in tasks:
            tasks_by_col.setdefault(t["column_id"], []).append(t)

        # -- Column summary table --
        lines.append("### Columns")
        lines.append("")
        lines.append("| # | Column | Tasks |")
        lines.append("|---|--------|-------|")
        for i, c in enumerate(cols, 1):
            count = len(tasks_by_col.get(c["id"], []))
            lines.append(f"| {i} | {c['name']} | {count} |")
        lines.append("")

        # -- Projects table --
        if projects:
            proj_task_count: dict[int, int] = {}
            for t in tasks:
                if t["project_id"]:
                    proj_task_count[t["project_id"]] = (
                        proj_task_count.get(t["project_id"], 0) + 1
                    )
            lines.append("### Projects")
            lines.append("")
            lines.append("| Project | Description | Tasks |")
            lines.append("|---------|-------------|-------|")
            for p in projects:
                desc = p["description"] or ""
                count = proj_task_count.get(p["id"], 0)
                lines.append(f"| {p['name']} | {desc} | {count} |")
            lines.append("")

        # -- Tasks grouped by column --
        lines.append("### Tasks")
        lines.append("")
        for c in cols:
            col_tasks = tasks_by_col.get(c["id"], [])
            if not col_tasks:
                continue
            lines.append(f"#### {c['name']}")
            lines.append("")
            lines.append("| Task | Title | Priority | Project | Due |")
            lines.append("|------|-------|----------|---------|-----|")
            for t in col_tasks:
                task_num = f"task-{t['id']:04d}"
                pri = f"P{t['priority']}" if t["priority"] else ""
                proj = proj_map.get(t["project_id"], "")
                due = (
                    datetime.datetime.fromtimestamp(
                        t["due_date"], tz=datetime.timezone.utc
                    ).strftime("%Y-%m-%d")
                    if t["due_date"]
                    else ""
                )
                lines.append(f"| {task_num} | {t['title']} | {pri} | {proj} | {due} |")
            lines.append("")

        # -- Dependencies (Mermaid) --
        deps = conn.execute(
            "SELECT task_id, depends_on_id FROM task_dependencies"
        ).fetchall()
        board_deps = [
            (d["task_id"], d["depends_on_id"])
            for d in deps
            if d["task_id"] in task_ids and d["depends_on_id"] in task_ids
        ]
        if board_deps:
            lines.append("### Dependencies")
            lines.append("")
            lines.append("```mermaid")
            lines.append("graph LR")
            for tid, did in board_deps:
                lines.append(f"    task-{tid:04d} --> task-{did:04d}")
            lines.append("```")
            lines.append("")
            lines.append('> Arrow reads "depends on"')
            lines.append("")

    return "\n".join(lines) + "\n"
