---
name: next
description: Use when the user wants to pick up the next actionable task from an stx workspace — surfaces the highest-priority ready task from the blocks DAG, shows its full context (description, group, edges, metadata, history), and optionally marks it in-progress. Trigger on: "what should I work on", "pick up next task", "what's next", "next task", "/next".
---

Pick up the next actionable task from the active stx workspace.

## Step 1 — Get the ready frontier

```sh
stx next --rank --limit 5 --json
```

Parse the response:

- **`ready` is empty** — nothing is currently actionable. Show a summary of the `blocked` list (what's gated and what's blocking it), then stop. Suggest completing the pending blocker tasks first.
- **`ready` has items** — proceed with `ready[0]` (highest-priority by rank). Mention how many other tasks are also on the frontier.

## Step 2 — Hydrate the top task

```sh
stx task show <task-id> --json
```

Extract and present:
- Task number, title, priority, due date, done flag
- Description (if set — render as Markdown)
- Status name
- Group title (if assigned)
- `edge_targets` — tasks/groups this task blocks downstream
- `edge_sources` — tasks/groups that block this task (should be empty if it's on the frontier, but surface any for transparency)
- Metadata key/value pairs (branch, jira, owner, etc.)
- Last 3 history entries

## Step 3 — Group context (if task has a group)

```sh
stx group show <group-title> --json
```

Show:
- Group ancestry path (workspace → parent → … → group)
- Sibling tasks in the same group and their done state
- `group.done` — whether the group as a whole is complete

## Step 4 — What this task gates

From the `stx next` output, find all entries in `blocked` whose `blocked_by` array contains this task's ID. List them as "downstream work gated on this task."

## Step 5 — Offer to start

If the task's current status is not an active/in-progress status, offer to move it:

```sh
stx task mv <task-id> -S "<in-progress-status>"
```

Do not move automatically — let the user confirm.

## Step 6 — Work order summary

Present a concise summary:

```
━━━ Next Task ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  task-NNNN  [priority P]  <title>
  Status:    <status>
  Group:     workspace → group → subgroup
  Due:       <date or —>

  <description if set>

  Metadata:  branch=feat/x  jira=PROJ-42

  Blocking downstream:
    task-MMMM  <title>
    task-PPPP  <title>

  Recent history:
    <field> changed <old> → <new>  (source, timestamp)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Edge cases

- **No active workspace** — `stx workspace ls` to list options, then `stx workspace use <name>`.
- **No tasks exist** — workspace is empty; suggest creating tasks or seeding from a plan.
- **No blocking edges** — all tasks are on the frontier; `stx next --rank` sorts by priority, due date, id — the result is still correct.
- **Different DAG edge kind** — pass `--edge-kind <kind>` to `stx next` if the workspace uses a kind other than `blocks`.
- **`--limit N`** — the user can ask for more candidates: run `stx next --rank --limit N` and let them choose.
