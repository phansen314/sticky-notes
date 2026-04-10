ALTER TABLE workspaces ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata));
ALTER TABLE projects ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata));
ALTER TABLE groups ADD COLUMN metadata TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata));
