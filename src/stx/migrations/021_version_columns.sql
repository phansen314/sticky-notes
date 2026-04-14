-- Migration 021: optimistic-locking version columns on all mutable entity tables.
--
-- Each row's `version` is incremented on every write. Callers that need
-- compare-and-swap semantics (e.g. agent swarms) read the current version,
-- then pass it back as `expected_version`; a rowcount-0 result means a
-- concurrent writer already bumped the version and the caller should retry.
--
-- Scope: workspaces, statuses, groups, tasks, edges.
-- Excluded: journal (append-only, never updated).
--
-- All five are simple ALTERs — no table recreate needed.

ALTER TABLE workspaces ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE statuses   ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE groups     ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tasks      ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
ALTER TABLE edges      ADD COLUMN version INTEGER NOT NULL DEFAULT 0;
