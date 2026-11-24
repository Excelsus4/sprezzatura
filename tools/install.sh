#!/usr/bin/env bash
# Sprezzatura installer (macOS / Linux / Git Bash).
#
# Usage (from a local checkout):
#   bash tools/install.sh [--target claude|agy|codex|all|auto] [--agy-mode plugin|skill] [--dry-run]
#
# Targets:
#   claude -> ~/.claude/skills/sprezzatura  (+ ~/.claude/commands/*.md)
#   codex  -> ~/.codex/skills/sprezzatura
#   agy    -> plugin mode (default): ~/.gemini/config/plugins/sprezzatura/skills/sprezzatura
#                                    + generated ~/.gemini/config/plugins/sprezzatura/plugin.json
#             skill mode:            ~/.gemini/config/skills/sprezzatura
#   all    -> all of the above
#   auto   -> every agent whose config dir exists (default; falls back to claude)
#
# Options:
#   --dry-run          print actions without writing anything
#   --home DIR         install under DIR instead of $HOME (testing)
#   --source DIR       use DIR as the repo root instead of auto-detecting
#   --agy-mode MODE    plugin (default) or skill
set -euo pipefail

# --- product metadata ---
SKILL_NAME="sprezzatura"
DISPLAY_NAME="Sprezzatura"
PLUGIN_VERSION="0.1.0"
PLUGIN_DESCRIPTION="Read-only diff audit for locale, clock, path, crash, and concurrency bugs that pass local tests. Isolated checks, blind verifier."
PROMPT_1="Audit my current changes for edge-case bugs with Sprezzatura"
PROMPT_2="Run a Sprezzatura deep audit on this branch before release"
PROMPT_3="Check this folder for locale, clock, and filesystem edge-case bugs with Sprezzatura"

TARGET="auto"
AGY_MODE="plugin"
DRY_RUN=0
HOME_DIR="${HOME:-}"
SOURCE=""

usage() { sed -n '2,21p' "$0" 2>/dev/null | sed 's/^# \{0,1\}//'; }
# Fail loudly (not via a silent `set -e` abort on `shift 2`) when a flag lacks its value.
need_value() { [ "$2" -ge 2 ] || { echo "error: $1 requires a value" >&2; exit 2; }; }

while [ $# -gt 0 ]; do
  case "$1" in
    --target) need_value "$1" $#; TARGET="$2"; shift 2 ;;
    --target=*) TARGET="${1#*=}"; shift ;;
    --agy-mode) need_value "$1" $#; AGY_MODE="$2"; shift 2 ;;
    --agy-mode=*) AGY_MODE="${1#*=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --home) need_value "$1" $#; HOME_DIR="$2"; shift 2 ;;
    --home=*) HOME_DIR="${1#*=}"; shift ;;
    --source) need_value "$1" $#; SOURCE="$2"; shift 2 ;;
    --source=*) SOURCE="${1#*=}"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; exit 2 ;;
  esac
done

case "$TARGET" in
  claude|agy|codex|all|auto) ;;
  *) echo "error: --target must be claude|agy|codex|all|auto (got '$TARGET')" >&2; exit 2 ;;
esac
case "$AGY_MODE" in
  plugin|skill) ;;
  *) echo "error: --agy-mode must be plugin|skill (got '$AGY_MODE')" >&2; exit 2 ;;
esac
[ -n "$HOME_DIR" ] || { echo "error: HOME is not set; use --home DIR" >&2; exit 2; }

log() { printf '%s\n' "$*"; }
run() {
  if [ "$DRY_RUN" -eq 1 ]; then log "[dry-run] $*"; else "$@"; fi
}

# --- locate source (local checkout only) -------------------------------------
if [ -z "$SOURCE" ]; then
  SCRIPT_PATH="${BASH_SOURCE[0]:-}"
  if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
    SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
    for cand in "$SCRIPT_DIR" "$SCRIPT_DIR/.."; do
      if [ -f "$cand/skill/$SKILL_NAME/SKILL.md" ]; then SOURCE="$(cd "$cand" && pwd)"; break; fi
    done
  fi
  if [ -z "$SOURCE" ]; then
    echo "error: local $DISPLAY_NAME checkout not found (expected skill/$SKILL_NAME/SKILL.md next to or above this script)." >&2
    echo "       Clone https://github.com/Excelsus4/sprezzatura and run tools/install.sh from the checkout, or pass --source <repo root>." >&2
    exit 1
  fi
elif [ ! -f "$SOURCE/skill/$SKILL_NAME/SKILL.md" ]; then
  echo "error: $SOURCE/skill/$SKILL_NAME/SKILL.md not found; pass --source <repo root> of a $DISPLAY_NAME checkout" >&2
  exit 1
else
  SOURCE="$(cd "$SOURCE" && pwd)"
fi
log "Source: $SOURCE"

# --- resolve targets ---------------------------------------------------------
TARGETS=""
case "$TARGET" in
  all) TARGETS="claude agy codex" ;;
  auto)
    if [ -d "$HOME_DIR/.claude" ]; then TARGETS="$TARGETS claude"; fi
    if [ -d "$HOME_DIR/.gemini" ]; then TARGETS="$TARGETS agy"; fi
    if [ -d "$HOME_DIR/.codex" ]; then TARGETS="$TARGETS codex"; fi
    if [ -z "$TARGETS" ]; then log "No agent config dirs detected; defaulting to claude"; TARGETS="claude"; fi ;;
  *) TARGETS="$TARGET" ;;
esac

remove_dest() {
  if [ -L "$1" ]; then
    run rm -f "$1"
  elif [ -e "$1" ]; then
    # A previous install copied from a read-only source (0555 dirs / 0444 files)
    # cannot be rm -rf'd without write permission on its directories.
    if [ "$DRY_RUN" -eq 0 ]; then chmod -R u+w "$1" 2>/dev/null || true; fi
    run rm -rf "$1"
  fi
}

install_skill_dir() {  # $1 label, $2 dest
  log "[$1] skill -> $2"
  remove_dest "$2"
  run mkdir -p "$2"
  run cp -R "$SOURCE/skill/$SKILL_NAME/." "$2/"
  if [ "$DRY_RUN" -eq 0 ]; then
    # Keep the installed copy owner-writable so the next reinstall can replace it.
    chmod -R u+w "$2"
    find "$2" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
  fi
}

plugin_json() {
  cat <<EOF
{
  "name": "$SKILL_NAME",
  "displayName": "$DISPLAY_NAME",
  "version": "$PLUGIN_VERSION",
  "description": "$PLUGIN_DESCRIPTION",
  "suggestedPrompts": [
    "$PROMPT_1",
    "$PROMPT_2",
    "$PROMPT_3"
  ]
}
EOF
}

for t in $TARGETS; do
  case "$t" in
    claude)
      install_skill_dir claude "$HOME_DIR/.claude/skills/$SKILL_NAME"
      cmd_dir="$HOME_DIR/.claude/commands"
      found_cmd=0
      for cmd_src in "$SOURCE"/commands/*.md; do
        [ -f "$cmd_src" ] || continue
        if [ "$found_cmd" -eq 0 ]; then run mkdir -p "$cmd_dir"; found_cmd=1; fi
        cmd_dest="$cmd_dir/$(basename "$cmd_src")"
        log "[claude] command -> $cmd_dest"
        if [ -L "$cmd_dest" ] || [ -e "$cmd_dest" ]; then run rm -f "$cmd_dest"; fi
        run cp -f "$cmd_src" "$cmd_dest"
        if [ "$DRY_RUN" -eq 0 ]; then chmod u+w "$cmd_dest"; fi
      done
      if [ "$found_cmd" -eq 0 ]; then
        log "[claude] warning: no $SOURCE/commands/*.md found; skipping slash commands"
      fi ;;
    codex)
      install_skill_dir codex "$HOME_DIR/.codex/skills/$SKILL_NAME" ;;
    agy)
      if [ "$AGY_MODE" = "skill" ]; then
        install_skill_dir agy "$HOME_DIR/.gemini/config/skills/$SKILL_NAME"
      else
        plugin_root="$HOME_DIR/.gemini/config/plugins/$SKILL_NAME"
        legacy="$HOME_DIR/.gemini/config/skills/$SKILL_NAME"
        if [ -e "$legacy" ]; then
          log "[agy] warning: skill-mode install also exists at $legacy (remove it to avoid a duplicate skill)"
        fi
        log "[agy] plugin -> $plugin_root"
        remove_dest "$plugin_root"
        install_skill_dir agy "$plugin_root/skills/$SKILL_NAME"
        manifest="$plugin_root/plugin.json"
        log "[agy] manifest -> $manifest"
        if [ "$DRY_RUN" -eq 1 ]; then
          log "[dry-run] would write $manifest :"
          plugin_json
        else
          plugin_json > "$manifest"
        fi
      fi ;;
  esac
done

if [ "$DRY_RUN" -eq 1 ]; then log "Dry run complete. No files were changed."; else log "$DISPLAY_NAME installed for:$TARGETS"; fi
