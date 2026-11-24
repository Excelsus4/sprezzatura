---
id: crash-partial-write
name: Mid-Flight Kill, Partial Writes & Zombie Locks
category: durability
---

## Hostile World-State
Power loss or `kill -9` strikes at exactly 50% of a save, config update, or multi-step batch job — or the destination disk hits `0 bytes free` right after truncating an existing file.

## Per-Stack Applicability
- **Applies:** Direct in-place overwrites (`open(path, "w")`, `File.WriteAllText`, `fs.writeFileSync`) of critical state/configs/manifests; multi-file or DB+file updates without transactions or write-ahead markers; PID/lock files with no stale-lock recovery; temp-file `rename` across different mount points/drives (`EXDEV`) or Windows `os.rename` failing when destination already exists.
- **Ignore/Safe:** Atomic write pattern (write sibling temp file in same dir -> `fsync` -> `os.replace`/atomic move); SQLite WAL transactions handling all coupled state atomically; read-only or ephemeral cache files rebuilt cleanly on startup.

## Seed Probes
1. Truncate the primary config/save/state JSON to half its bytes (simulating `open(p, "w")` + `kill -9`) and restart the app: does it lose prior good state or crash-loop?
2. Simulate `ENOSPC` (0 bytes free) during save: does truncation destroy the last valid backup before the new payload succeeds?
3. Leave a stale `.lock` file from a killed process (dead PID) and relaunch: does startup deadlock forever?
4. Kill between Step 1 (DB/state write) and Step 2 (file/side-effect emit), then re-run: is recovery idempotent?

## Retire / Disproof Rule
Retire if durable writes go to a same-directory temp file replaced atomically (`os.replace` / transactional DB), stale locks verify liveness or use OS advisory locks, and corrupt state degrades cleanly.

## Real Incident Anchor
Desktop tools and game save managers routinely wipe user progress when direct `WriteAllText` truncates `save.json` milliseconds before a crash or BSOD.
