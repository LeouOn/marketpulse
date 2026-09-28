#!/usr/bin/env bash
# Create an isolated git worktree for one agent task.
#   docs/agent-tasks/new-worktree.sh T3a [base-ref]
# base-ref defaults to HEAD. Use `main` (after merging prerequisites) for dependent tasks.
set -euo pipefail

id="${1:?usage: new-worktree.sh <task-id, e.g. T3a> [base-ref]}"
base="${2:-HEAD}"
root="$(git rev-parse --show-toplevel)"
dir="$root/../marketpulse-wt/$id"

task_file="$(ls "$root"/docs/agent-tasks/"$id"-*.md 2>/dev/null | head -1 || true)"
[ -n "$task_file" ] || { echo "no task file docs/agent-tasks/$id-*.md" >&2; exit 1; }
[ ! -e "$dir" ] || { echo "$dir already exists (git worktree remove --force '$dir' to redo)" >&2; exit 1; }

mkdir -p "$root/../marketpulse-wt"
git -C "$root" worktree add -b "task/$id" "$dir" "$base"

# Gitignored secrets/config: symlink the owner's real files (agents must treat them read-only).
ln -s "$root/.env" "$dir/.env"
[ -f "$root/config/credentials.yaml" ] && ln -s "$root/config/credentials.yaml" "$dir/config/credentials.yaml"

# Task instructions live outside the tracked tree and are excluded from git status.
mkdir -p "$dir/.agent-task"
cp "$root/docs/agent-tasks/README.md" "$task_file" "$dir/.agent-task/"
exclude="$(git -C "$dir" rev-parse --path-format=absolute --git-path info/exclude)"
mkdir -p "$(dirname "$exclude")"
grep -qxF '.agent-task/' "$exclude" 2>/dev/null || echo '.agent-task/' >> "$exclude"

echo
echo "worktree : $dir"
echo "branch   : task/$id (from $base)"
echo "prompt   : cd '$dir' and tell the agent:"
echo "  Read .agent-task/README.md (shared rules), then .agent-task/$(basename "$task_file"), and do the task."
