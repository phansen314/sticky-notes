-- Migration 020: explicit `done` flag on tasks/groups + `is_terminal` on statuses.
--
-- Motivates the `stx next` command which topo-sorts the active `blocks` edge
-- DAG: it needs a generic notion of "completed" that doesn't rely on a status
-- happening to be named "Done". Users may have multiple terminal statuses
-- (e.g. "done", "won't do", "obsolete"); marking each with `is_terminal=1`
-- causes task moves into them to auto-set `task.done=1`, and moves out to
-- auto-set `task.done=0`. Group `done` is a rolled-up value: a group is done
-- iff every non-archived child task and child group is done. Manual override
-- via `stx task done/undone` and `stx group done/undone` is also supported.
--
-- All three columns are simple ALTERs — no table recreate needed.

ALTER TABLE statuses ADD COLUMN is_terminal INTEGER NOT NULL DEFAULT 0
    CHECK (is_terminal IN (0, 1));

ALTER TABLE tasks ADD COLUMN done INTEGER NOT NULL DEFAULT 0
    CHECK (done IN (0, 1));

ALTER TABLE groups ADD COLUMN done INTEGER NOT NULL DEFAULT 0
    CHECK (done IN (0, 1));

CREATE INDEX idx_tasks_workspace_done ON tasks(workspace_id, done, archived);
CREATE INDEX idx_groups_workspace_done ON groups(workspace_id, done, archived);
