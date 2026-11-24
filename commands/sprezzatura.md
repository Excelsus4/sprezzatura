---
description: Read-only audit of the current diff, path, or repo for locale, clock, path, crash, and concurrency bugs
argument-hint: [scope or path] [--mode quick|standard|deep] [--repo] [--prove]
---

Read and execute the `sprezzatura` skill (`~/.claude/skills/sprezzatura/SKILL.md`) on the target below.
Default to read-only diff-first scope (`git diff` / merge-base) unless the user specifies a path or `--repo`. Never edit target repository source files and never auto-file GitHub issues without explicit user confirmation of selected IDs.

$ARGUMENTS
