# stx Hooks Reference

Hooks run shell commands in response to stx mutations. **Pre-hooks** fire before the write transaction and can veto the operation by exiting non-zero. **Post-hooks** fire after commit and are fire-and-forget — their exit code is ignored. Both receive a JSON payload on stdin describing the event.

Config lives at `~/.config/stx/hooks.toml`. Commands execute with `shell=True`; anyone who can write that file can run arbitrary code as the stx user — the trust model matches git hooks.

For the CLI subcommands (`stx hook ls|events|validate|schema`), see `cli-reference.md`. The authoritative payload schema is shipped with the package: `stx hook schema`.

---

## Event catalog

All 29 events, grouped by entity. The **category** column determines which extra fields the payload carries (see [Payload structure](#payload-structure)).

### Task events

| Event | Fires on | Category |
|---|---|---|
| `task.created` | `create_task` | created |
| `task.updated` | `update_task` (any field change not covered by a specific event) | updated |
| `task.moved` | `update_task` with `status_id` change | updated |
| `task.done` | `update_task` flipping `done=True`, `mark_task_done`, or auto-flip on entry to a terminal status | updated |
| `task.undone` | `mark_task_undone` | updated |
| `task.archived` | `archive_task` | archived |
| `task.transferred` | `move_task_to_workspace` | transferred |
| `task.assigned` | `update_task` with `group_id` set (non-null) | updated |
| `task.unassigned` | `update_task` with `group_id` cleared to null | updated |
| `task.meta_set` | `set_task_meta`, `replace_task_metadata` (per added/changed key) | meta |
| `task.meta_removed` | `remove_task_meta`, `replace_task_metadata` (per removed key) | meta |

### Group events

| Event | Fires on | Category |
|---|---|---|
| `group.created` | `create_group` | created |
| `group.updated` | `update_group` (any change) | updated |
| `group.archived` | `cascade_archive_group` (top-level only — bulk-archived children are silent) | archived |
| `group.meta_set` | `set_group_meta`, `replace_group_metadata` | meta |
| `group.meta_removed` | `remove_group_meta`, `replace_group_metadata` | meta |

### Workspace events

| Event | Fires on | Category |
|---|---|---|
| `workspace.created` | `create_workspace` | created |
| `workspace.updated` | `update_workspace` | updated |
| `workspace.archived` | `cascade_archive_workspace` (top-level only) | archived |
| `workspace.meta_set` | `set_workspace_meta`, `replace_workspace_metadata` | meta |
| `workspace.meta_removed` | `remove_workspace_meta`, `replace_workspace_metadata` | meta |

### Status events

| Event | Fires on | Category |
|---|---|---|
| `status.created` | `create_status` | created |
| `status.updated` | `update_status` | updated |
| `status.archived` | `archive_status` | archived |

Statuses have no metadata column, so no `status.meta_*` events.

### Edge events

| Event | Fires on | Category |
|---|---|---|
| `edge.created` | `add_edge` | created |
| `edge.archived` | `archive_edge` | archived |
| `edge.updated` | `update_edge` (e.g. acyclic flip) | updated |
| `edge.meta_set` | `set_edge_meta`, `replace_edge_metadata` | meta |
| `edge.meta_removed` | `remove_edge_meta`, `replace_edge_metadata` | meta |

List events from the CLI: `stx hook events`.

---

## Payload structure

Every payload carries these top-level fields:

| Field | Type | Notes |
|---|---|---|
| `event` | string | One of the 29 event names above. |
| `timing` | `"pre"` \| `"post"` | |
| `workspace_id` | int \| null | Null on pre-hooks for `workspace.created` (no id yet). |
| `workspace_name` | string \| null | |
| `entity_type` | `"task"` \| `"group"` \| `"workspace"` \| `"status"` \| `"edge"` | |
| `entity_id` | int \| null | Null on pre-hooks for `created` events (id not yet assigned, except for edges which use `from_id`). |
| `entity` | object \| null | Full entity snapshot (see `$defs` in `stx hook schema`). Null on pre-hooks for `created`. |

Then category-specific fields:

**`created`** — adds `proposed: object | null` (the fields that will be inserted), `changes: null`.

**`updated`** — adds `changes: object` (`{field: {old, new}}` dict) and `proposed: null`.

**`archived`** — adds `changes: object` (always `{archived: {old: bool, new: true}}`) and `proposed: null`.

**`meta`** — adds `meta_key: string`, `meta_value: string | null` (null on `*.meta_removed`), `changes: null`, `proposed: null`.

**`transferred`** — adds `changes: object` (workspace_id old/new), `source_workspace: {id, name}`, `target_workspace: {id, name}`.

Descriptions over 4KB are truncated and marked with `description_truncated: true` on the entity.

Entity shapes are defined in the JSON Schema shipped with the package. Read them programmatically: `stx hook schema | jq '.["$defs"]'`.

---

## Writing hooks

Each hook is a TOML table:

```toml
[[hooks]]
event = "task.created"       # required — exact event name
timing = "post"              # required — "pre" or "post"
command = "shell command"    # required — any shell; receives payload on stdin
name = "notify-creator"      # optional — shown by `stx hook ls`; handy for logs
workspace = "work"           # optional — restricts to one workspace; omit for global
enabled = true               # optional — default true; set false to disable without deleting
```

**Matching order:** for a given event/timing, global hooks fire before workspace-scoped hooks (in config-file order within each group).

**Veto:** a pre-hook that exits non-zero aborts the write. The stx process raises `HookRejectionError` and exits 7 (`EXIT_HOOK_REJECTED`). Subsequent pre-hooks for the same event do not fire.

**Post-hook isolation:** post-hooks run via `subprocess.Popen` in a new session (`start_new_session=True`). Stdout/stderr redirect to `DEVNULL`. Exit code is ignored; failures are silent.

---

## Recipe library

Polished, working examples. Copy-paste into `~/.config/stx/hooks.toml` and run `stx hook validate` first.

### 1. Desktop notify on task completion

```toml
[[hooks]]
event = "task.done"
timing = "post"
name = "notify-done"
command = '''jq -r '"✓ " + .entity.title + " done"' | xargs -I{} notify-send "stx" "{}"'''
```

### 2. Require non-empty description on task creation

```toml
[[hooks]]
event = "task.created"
timing = "pre"
name = "require-description"
workspace = "work"
command = '''
read payload
desc=$(echo "$payload" | jq -r '.proposed.description // ""')
if [ -z "$desc" ]; then
  echo "blocked: description required on work workspace" >&2
  exit 1
fi
'''
```

### 3. Block workspace archive with in-progress tasks

```toml
[[hooks]]
event = "workspace.archived"
timing = "pre"
name = "guard-archive"
command = '''
read payload
ws=$(echo "$payload" | jq -r '.workspace_name')
if stx -w "$ws" --json task ls --status in-progress | jq -e '.data | length > 0' >/dev/null; then
  echo "refusing to archive '$ws': in-progress tasks remain" >&2
  exit 1
fi
'''
```

### 4. Slack webhook on high-priority task moved to review

```toml
[[hooks]]
event = "task.moved"
timing = "post"
name = "slack-review"
command = '''
read payload
priority=$(echo "$payload" | jq -r '.entity.priority')
title=$(echo "$payload" | jq -r '.entity.title')
if [ "$priority" -ge 3 ]; then
  curl -sS -X POST -H 'Content-Type: application/json' \
    -d "{\"text\":\"⚠ high-pri task moved: $title\"}" \
    "$SLACK_WEBHOOK_URL"
fi
'''
```

### 5. JSONL activity log (one hook per event, or pick the ones you care about)

```toml
[[hooks]]
event = "task.updated"
timing = "post"
name = "audit-log"
command = "jq -c '{ts: now|strftime(\"%FT%T\"), event, entity: .entity.title, changes}' >> ~/.local/share/stx/activity.jsonl"

[[hooks]]
event = "task.archived"
timing = "post"
name = "audit-log"
command = "jq -c '{ts: now|strftime(\"%FT%T\"), event, entity: .entity.title}' >> ~/.local/share/stx/activity.jsonl"
```

### 6. Git-sync an Obsidian vault file on group rename

```toml
[[hooks]]
event = "group.updated"
timing = "post"
name = "vault-sync"
command = '''
read payload
old=$(echo "$payload" | jq -r '.changes.title.old // empty')
new=$(echo "$payload" | jq -r '.changes.title.new // empty')
[ -n "$old" ] && [ -n "$new" ] || exit 0
cd ~/vault && git mv "groups/$old.md" "groups/$new.md" 2>/dev/null && \
  git commit -m "rename group $old → $new" -- "groups/$new.md"
'''
```

### 7. Block a deprecated edge kind

```toml
[[hooks]]
event = "edge.created"
timing = "pre"
name = "no-legacy-edges"
command = '''
read payload
kind=$(echo "$payload" | jq -r '.proposed.kind')
if [ "$kind" = "legacy-relates" ]; then
  echo "'legacy-relates' is deprecated; use 'informs' instead" >&2
  exit 1
fi
'''
```

### 8. Cross-workspace transfer notification

```toml
[[hooks]]
event = "task.transferred"
timing = "post"
name = "transfer-notify"
command = '''
read payload
title=$(echo "$payload" | jq -r '.entity.title')
src=$(echo "$payload" | jq -r '.source_workspace.name')
tgt=$(echo "$payload" | jq -r '.target_workspace.name')
notify-send "stx" "$title: $src → $tgt"
'''
```

### 9. Conditional tag on `task.meta_set`

```toml
[[hooks]]
event = "task.meta_set"
timing = "post"
name = "pr-link-notify"
command = '''
read payload
key=$(echo "$payload" | jq -r '.meta_key')
val=$(echo "$payload" | jq -r '.meta_value')
if [ "$key" = "pr_url" ]; then
  notify-send "stx" "PR linked: $val"
fi
'''
```

### 10. Disabled hook (kept around for later)

```toml
[[hooks]]
event = "task.done"
timing = "post"
name = "confetti"
command = "echo 🎉"
enabled = false
```

---

## Gotchas

- **Pre-hook timeout: 10 seconds** (`PRE_HOOK_TIMEOUT_SECONDS` in `hooks.py`). Timeout raises `HookRejectionError` and blocks the write.
- **Post-hook isolation:** never raises back to the caller; don't rely on post-hooks for control flow.
- **Description truncation at 4KB** (`DESCRIPTION_MAX_BYTES`). Truncated payloads include `"description_truncated": true` on the entity so hooks can detect it.
- **Recursive invocation:** a hook that runs `stx ...` inside itself will recursively fire more hooks with no depth limit. Avoid self-referential hooks.
- **Concurrency:** pre-hooks for non-meta mutations receive a snapshot of the entity read *before* the write transaction opens — under concurrent writers the snapshot may be stale by the time the write runs. Optimistic-locking (version CAS) still catches conflicts; the write either commits against fresh state or raises `ConflictError`. A pre-hook veto based on a stale snapshot is not "undone" — it vetoes what was true at read time.
- **Edge meta and `update_edge` hooks** fire *inside* the transaction so pre/post are symmetric under races. This means the pre-hook subprocess runs while the SQLite write lock is held — acceptable in the single-writer use case.
- **Cascade archives** on groups and workspaces emit only the top-level `*_ARCHIVED` event. Per-entity hooks for bulk-archived descendants are intentionally skipped; use the cascade event as the signal.
- **Statuses have no metadata**, so `status.meta_*` events don't exist.

---

## Testing

Before deploying a hook, validate the config:

```bash
stx hook validate
stx hook validate --path /tmp/staged-hooks.toml    # dry-run an alternate file
```

Inspect what's wired up:

```bash
stx hook ls                              # all hooks
stx hook ls --event task.created         # by event
stx hook ls --workspace work             # by workspace
stx hook ls --globals-only               # hooks without a workspace scope
stx hook ls --timing pre                 # only pre-hooks
```

Hand-play a hook command without mutating the DB — pipe a synthetic payload into the command:

```bash
echo '{"event":"task.done","timing":"post","entity":{"title":"test"}}' | \
  jq -r '"✓ " + .entity.title + " done"'
```

For round-trip testing against the running DB, the included smoke script exercises every `stx hook` subcommand end-to-end:

```bash
bash scripts/smoke-hooks.sh
```
