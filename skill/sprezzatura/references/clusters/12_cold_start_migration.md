---
id: cold-start-migration
name: First-Run Empty State, Schema Upgrade & Read-Only Install
category: lifecycle
---

## Hostile World-State
Brand-new machine with zero prior config/DB/cache directories, installed under a read-only directory (`C:\Program Files\App` or `/usr/local`), OR upgrading in-place from a 6-month-old config/save schema version.

## Per-Stack Applicability
- **Applies:** Apps assuming config/state/cache directories already exist before writing; writing runtime logs/caches/DBs next to the executable instead of user data dirs (`AppData`/`XDG_DATA_HOME`); schema/config loaders assuming newly added fields always exist in older user files; missing migration idempotency when an upgrade runs twice; env vars assumed always set.
- **Ignore/Safe:** Stateless pure libraries with no persistent config/state/install dir; loaders using `mkdir(parents=True, exist_ok=True)`, versioned schema migrations with defaults, and OS user-data directories.

## Seed Probes
1. Delete all user config, cache, and DB directories and launch cold: does startup crash before creating parent directories or defaults?
2. Mark the installation/binary directory strictly read-only and run: does the app attempt to write logs, temp files, or configs next to the binary?
3. Feed a previous-version config/save file missing newly introduced keys (or with old key names/types) into the current loader.
4. Re-run the migration/setup step a second time on an already-migrated state: does it fail or duplicate data?

## Retire / Disproof Rule
Retire if there is no persistent state/config/install boundary, or cold-start directory creation, user-writable storage paths, backward-compatible defaults, and idempotent migrations are all verified.

## Real Incident Anchor
Windows apps tested from writable dev folders routinely crash for end users once installed under read-only `C:\Program Files`, and unversioned config files break returning users after updates.
