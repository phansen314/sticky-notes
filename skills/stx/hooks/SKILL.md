---
name: hooks
description: Use when the user wants to write, install, or debug a custom stx hook — e.g. "notify me when a task is done", "block task creation without a description", "send a Slack message when X", "fire a webhook on Y", "post to this endpoint when a task moves to review", "why did my hook not fire". Trigger on phrases like "hook", "pre-hook", "post-hook", "fire on …", "block …", "hooks.toml", "stx event", "audit trail", "automation rule".
---

Author, install, and debug stx hooks — shell commands that fire on entity mutations.

Full event catalog, payload shapes, and recipe library live in
`skills/stx/references/hooks.md`. Delegate to it; don't paraphrase.

## Step 1 — Clarify intent

Collect four fields. Infer from wording; ask only when ambiguous.

- **Event** — consult the event catalog in `references/hooks.md`. Common mappings
  (e.g. "task done" → `task.done`, "rename a group" → `group.updated`) are
  obvious; for anything non-obvious read the catalog rather than guessing.
- **Timing** — verbs drive this:
  - "block / reject / require / enforce / prevent / guard" → **pre**.
  - "notify / log / send / post / call / trigger" → **post**.
  - Pre-hooks veto by exiting non-zero (write rolls back); post-hooks are
    fire-and-forget (exit code ignored).
- **Workspace scope** — global (all workspaces) or scoped to one by exact name?
  Default global.
- **Action** — what the command does. Usually stated directly.

## Step 2 — Verify the event name

```sh
stx --text hook events | grep '^<event>$'
```

If miss, offer close matches. The traps that catch users repeatedly:

- `task.done` vs `task.archived` — done is a flag flip; archived is soft-delete.
- `task.moved` vs `task.updated` — moved fires only on `status_id` change;
  updated covers other fields. Both can co-fire.
- `group.archived` / `workspace.archived` only fire on **cascade** archive.
  Per-entity children of a cascade do NOT fire their own `*_ARCHIVED`.
- Statuses have no metadata — no `status.meta_*` events exist.

## Step 3 — Show the payload shape

Every event belongs to one of 5 categories that determines which extra fields
ride alongside the always-present envelope. The mapping + full field list is in
`references/hooks.md` → **Payload structure**; consult it rather than
paraphrasing.

For the exact entity shape:

```sh
stx hook schema | jq '.["$defs"].<entityType>.properties'
```

(`<entityType>` is `taskEntity` / `groupEntity` / `workspaceEntity` /
`statusEntity` / `edgeEntity`.)

Show the user the exact `jq` path they'll need in Step 4 (e.g.
`.entity.priority`, `.changes.status_id.new`, `.meta_key`).

## Step 4 — Scaffold the TOML block

Template:

```toml
[[hooks]]
event = "<event>"
timing = "<pre|post>"
name = "<short-slug>"          # optional but encouraged — shown by `stx hook ls`
workspace = "<name>"           # OMIT for global; exact-match filter on mutation's workspace
command = '''
<shell command reading payload from stdin>
'''
```

The workspace field is an exact-match filter on the workspace the *mutation*
lands on. It is independent of the CLI `-w` flag and the active workspace
setting — the CLI resolves the target entity, then the hook engine checks the
resolved workspace against each hook's `workspace` field.

### Command-body pattern

For both pre and post, capture the payload once, extract fields, act:

```sh
read payload
val=$(echo "$payload" | jq -r '<jq-path>')
<branch or action on $val>
```

**Pre-hook veto**: add `echo "<reason>" >&2; exit 1` in the rejection branch.

**Post-hook shortcut**: if the command doesn't branch on field values (e.g. just
pipes the payload into `notify-send`), skip `read` and go straight to
`jq -r '<expr>' | <action>` — `jq` reads stdin directly.

Before composing from scratch, check `references/hooks.md` → **Recipe library**
for a near-match to adapt.

Show the composed block and confirm before installing.

## Step 5 — Install and validate

Default: stage for review, validate, then append to the live config on
confirmation.

```sh
cat > /tmp/stx-new-hook.toml <<'EOF'
<the block>
EOF
stx hook validate --path /tmp/stx-new-hook.toml       # green → safe to install
cat /tmp/stx-new-hook.toml >> ~/.config/stx/hooks.toml
stx hook validate                                      # revalidate combined config
```

Skip the staging step only if the user says "just add it".

If validation fails, paste the error verbatim, identify the offending field
(the error lists `hooks[N]: field …`), fix, re-validate. Never claim the hook
works without a green `stx hook validate`.

## Step 6 — Smoke test

```sh
stx --text hook ls --event <event>   # confirm registration
```

Trigger the event once (use `references/cli-reference.md` to find the right
mutation command) and observe the side-effect:

- Post-hooks emit to their own side-channel (notification, log, webhook).
- Pre-hooks block the mutation; stx exits 7 (`EXIT_HOOK_REJECTED`) with the
  hook's stderr.

Archive any test entities created during smoke-testing with
`stx task archive <id> --force`.

## Debug mode — "my hook didn't fire" / "my pre-hook isn't blocking"

### Pre-flight

1. Registered and enabled?
   ```sh
   stx --text hook ls --event <event>
   ```
   Fix: ensure `~/.config/stx/hooks.toml` exists, `stx hook validate` is green,
   `enabled` isn't `false`, and the hook's `workspace` field (if set) matches
   the mutation's workspace exactly.

### Differential diagnosis

2. **Wrong event.** See Step 2 common confusions. Most frequent miss: using
   `task.done` when the user actually moves tasks to a non-terminal "done"
   status — `task.done` fires only on the `done` flag flip or entry to a
   `is_terminal=true` status. Use `task.moved` with in-command status-name
   filtering otherwise.

3. **Post-hook side-effect failed silently.** Post-hooks redirect stdout/stderr
   to DEVNULL — a segfaulting `notify-send` or broken `curl` produces no
   visible error. Re-run the command against a captured payload to see its
   stderr (see "capturing a real payload" below).

4. **Pre-hook timed out.** 10-second hard limit. Raises `HookRejectionError`
   with stderr `"timed out"` and blocks the write. Confirm via the stx exit
   code and stderr.

5. **Recursive invocation.** Does the hook's command invoke `stx`? That
   mutation fires more hooks with no depth limit. Self-referential loops are a
   real trap.

### Capturing a real payload for isolated testing

`stx` doesn't ship a payload-sample generator. To get a realistic payload for
offline testing, install a throwaway post-hook that dumps stdin to a file,
trigger the event once, then use the captured payload to test your real
command:

```toml
# throwaway — remove after capture
[[hooks]]
event = "<event>"
timing = "post"
name = "dump"
command = "cat > /tmp/stx-sample-payload.json"
```

```sh
stx hook validate                  # re-validate after appending
<trigger event once>
cat /tmp/stx-sample-payload.json | <your-real-command>
```

Remove the throwaway hook before committing the real one.

## Edge cases

- **No `~/.config/stx/hooks.toml`** — `stx hook ls` shows "no hooks". Create
  the file: `mkdir -p ~/.config/stx && touch ~/.config/stx/hooks.toml`.
- **"Fire on every mutation"** — no wildcard. 29 events; the user typically
  wants `*.created` + `*.updated` + `*.archived` pointed at a common log
  command. One `[[hooks]]` entry per event.
- **Old entity state in a post-hook** — available via `changes.<field>.old`
  for `updated` and `archived` categories. Not available for `meta` or
  `transferred` (they carry `meta_key`/`meta_value` or
  `source_workspace`/`target_workspace` instead).
- **Hook needs a secret (`$SLACK_WEBHOOK_URL`, etc.)** — `shell=True` inherits
  the user's environment; document the env var requirement in a comment above
  the `[[hooks]]` block.
- **Pre-hook subprocess holds the SQLite write lock** (for `update_edge`,
  `set_edge_meta` — pre-hooks fire inside the tx to avoid race-asymmetry).
  Keep those pre-hooks fast; a slow network call blocks concurrent writers for
  up to the 10-second timeout.
