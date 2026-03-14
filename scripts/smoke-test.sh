#!/usr/bin/env bash
set -euo pipefail

# ── Colors ──────────────────────────────────────────────────────────
GREEN='\033[0;32m'
RED='\033[0;31m'
BOLD='\033[1m'
CYAN='\033[0;36m'
RESET='\033[0m'

# ── Temp dir + cleanup ─────────────────────────────────────────────
TMPDIR="$(mktemp -d)"
DB="$TMPDIR/test.db"
trap 'rm -rf "$TMPDIR"' EXIT

CMD="todo --db $DB"

pass_count=0
fail_count=0

section() {
    echo -e "\n${BOLD}${CYAN}── $1 ──${RESET}"
}

run() {
    local desc="$1"; shift
    echo -e "  ${BOLD}$desc${RESET}"
    echo -e "    \$ $*"
    if output=$("$@" 2>&1); then
        echo "$output" | sed 's/^/    /'
        echo -e "    ${GREEN}PASS${RESET}"
        ((pass_count++)) || true
    else
        echo "$output" | sed 's/^/    /'
        echo -e "    ${RED}FAIL${RESET} (exit $?)"
        ((fail_count++)) || true
        exit 1
    fi
}

run_expect_fail() {
    local desc="$1"; shift
    echo -e "  ${BOLD}$desc${RESET}"
    echo -e "    \$ $*"
    if output=$("$@" 2>&1); then
        echo "$output" | sed 's/^/    /'
        echo -e "    ${RED}FAIL${RESET} (expected non-zero exit)"
        ((fail_count++)) || true
        exit 1
    else
        echo "$output" | sed 's/^/    /'
        echo -e "    ${GREEN}PASS (expected failure)${RESET}"
        ((pass_count++)) || true
    fi
}

# ════════════════════════════════════════════════════════════════════
#  BOARD
# ════════════════════════════════════════════════════════════════════
section "Board commands"

run "Create board 'Work'" \
    $CMD board create Work

run "Create board 'Personal'" \
    $CMD board create Personal

run "List boards" \
    $CMD board ls

run "Switch to 'Work'" \
    $CMD board use Work

run "Rename active board to 'Office'" \
    $CMD board rename Office

run "List boards (verify rename)" \
    $CMD board ls

run "Switch back to 'Personal'" \
    $CMD board use Personal

run "Archive 'Personal'" \
    $CMD board archive

run "List boards (archived hidden)" \
    $CMD board ls

run "List boards --all (archived visible)" \
    $CMD board ls --all

run "Switch to 'Office'" \
    $CMD board use Office

# ── Board error paths ──────────────────────────────────────────────
section "Board error paths"

run_expect_fail "Duplicate board name" \
    $CMD board create Office

# ════════════════════════════════════════════════════════════════════
#  COLUMN
# ════════════════════════════════════════════════════════════════════
section "Column commands"

run "Add column 'Backlog'" \
    $CMD col add Backlog

run "Add column 'In Progress'" \
    $CMD col add "In Progress"

run "Add column 'Done'" \
    $CMD col add Done

run "List columns" \
    $CMD col ls

run "Rename 'Backlog' to 'Todo'" \
    $CMD col rename Backlog Todo

run "List columns (verify rename)" \
    $CMD col ls

run "Archive column 'Todo'" \
    $CMD col archive Todo

run "List columns (after archive)" \
    $CMD col ls

# ════════════════════════════════════════════════════════════════════
#  PROJECT
# ════════════════════════════════════════════════════════════════════
section "Project commands"

run "Create project 'Backend'" \
    $CMD project create Backend --desc "Backend services"

run "Create project 'Frontend'" \
    $CMD project create Frontend

run "List projects" \
    $CMD project ls

run "Show project 'Backend'" \
    $CMD project show Backend

run "Archive project 'Frontend'" \
    $CMD project archive Frontend

run "List projects (after archive)" \
    $CMD project ls

# ════════════════════════════════════════════════════════════════════
#  TASK SHORTCUTS: add, ls, show, edit, mv, done, rm, log
# ════════════════════════════════════════════════════════════════════
section "Task: add"

run "Add task 'Set up CI'" \
    $CMD add "Set up CI" --desc "GitHub Actions pipeline" --project Backend --priority 2

run "Add task 'Write docs'" \
    $CMD add "Write docs"

run "Add task 'Fix login bug' with due date" \
    $CMD add "Fix login bug" --due 2026-04-01 --priority 3

# ────────────────────────────────────────────────────────────────────
section "Task: ls"

run "List tasks" \
    $CMD ls

run "List tasks --all (includes archived)" \
    $CMD ls --all

# ────────────────────────────────────────────────────────────────────
section "Task: show"

run "Show task 1" \
    $CMD show 1

run "Show task with task- prefix" \
    $CMD show task-0002

# ────────────────────────────────────────────────────────────────────
section "Task: edit"

run "Edit task title" \
    $CMD edit 2 --title "Write documentation"

run "Edit task description and priority" \
    $CMD edit 1 --desc "CI with GitHub Actions + linting" --priority 1

run "Edit task due date" \
    $CMD edit 2 --due 2026-05-01

run "Show task 2 (verify edits)" \
    $CMD show 2

# ────────────────────────────────────────────────────────────────────
section "Task: mv"

run "Move task 1 to 'In Progress'" \
    $CMD mv 1 "In Progress"

run "List tasks (verify move)" \
    $CMD ls

# ────────────────────────────────────────────────────────────────────
section "Task: done"

run "Mark task 1 done" \
    $CMD done 1

run "List tasks (verify done)" \
    $CMD ls

# ────────────────────────────────────────────────────────────────────
section "Task: rm"

run "Archive task 2" \
    $CMD rm 2

run "List tasks (task 2 hidden)" \
    $CMD ls

run "List tasks --all (task 2 visible)" \
    $CMD ls --all

# ────────────────────────────────────────────────────────────────────
section "Task: log"

run "Show change log for task 1" \
    $CMD log 1

# ════════════════════════════════════════════════════════════════════
#  DEPENDENCIES
# ════════════════════════════════════════════════════════════════════
section "Dependency commands"

run "Add dep: task 3 depends on task 1" \
    $CMD dep add 3 1

run "Show task 3 (verify dep)" \
    $CMD show 3

# ════════════════════════════════════════════════════════════════════
#  MARKDOWN EXPORT (run while dep exists so Mermaid diagram has content)
# ════════════════════════════════════════════════════════════════════
section "Markdown Export"

EXPORT_PATH="/tmp/sticky-notes-export.md"

run "Export database to markdown" \
    $CMD export -o "$EXPORT_PATH"

echo -e "  Export written to: ${BOLD}${EXPORT_PATH}${RESET}"

run "Remove dep: task 3 no longer depends on task 1" \
    $CMD dep rm 3 1

run "Show task 3 (dep removed)" \
    $CMD show 3

# ════════════════════════════════════════════════════════════════════
#  ERROR PATHS
# ════════════════════════════════════════════════════════════════════
section "Error paths"

run_expect_fail "Show missing task" \
    $CMD show 9999

run_expect_fail "Move missing task" \
    $CMD mv 9999 "In Progress"

# Test no active board error: use a separate DB with no board set
NO_BOARD_DB="$TMPDIR/no-board.db"
run_expect_fail "No active board" \
    todo --db "$NO_BOARD_DB" ls

# ════════════════════════════════════════════════════════════════════
#  SUMMARY
# ════════════════════════════════════════════════════════════════════
echo ""
echo -e "${BOLD}════════════════════════════════════════${RESET}"
echo -e "${GREEN}  All $pass_count checks passed.${RESET}"
echo -e "${BOLD}════════════════════════════════════════${RESET}"
