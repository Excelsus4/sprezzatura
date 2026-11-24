---
description: Short alias for /sprezzatura — adaptive fault-cluster QA stress-test audit
argument-hint: [scope or path] [--mode quick|standard|deep] [--repo] [--prove]
---

Read and execute the `sprezzatura` skill (`~/.claude/skills/sprezzatura/SKILL.md`) on the target below.
Default to read-only diff-first scope (`git diff` / merge-base) unless the user specifies a path or `--repo`. Never edit target repository source files and never auto-file GitHub issues without explicit user confirmation of selected IDs.

$ARGUMENTS
