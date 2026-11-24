---
id: fs-paths-unicode
name: Hostile Paths, Windows Encoding & Case Sensitivity
category: filesystem
---

## Hostile World-State
Windows 11 Korean/Turkish user profile at `C:\Users\김 철수 (dev)\AppData\...` containing spaces, parentheses, non-ASCII, and a ZWJ emoji filename `report_👨‍👩‍👧‍👦.txt`, synced between case-insensitive Windows/macOS and case-sensitive Linux (`ext4`).

## Per-Stack Applicability
- **Applies:** Shell/subprocess commands interpolating paths without quoting/list-args (`os.system`, `shell=True`, `cmd /c`, PowerShell unquoted args); Python `open()` without `encoding="utf-8"` on Windows (defaults to CP949/cp1252!); hardcoded `/` or `\` splitting; `MAX_PATH` (260 chars) on Windows without `\\?\`; UTF-16 `.length` slicing splitting surrogate pairs/ZWJ emojis; case-mismatched asset paths (`Player.png` vs `player.png`).
- **Ignore/Safe:** `subprocess.run([exe, path], shell=False)` with list args; `pathlib.Path` / `os.path.join` / `Path.Combine` paired with explicit UTF-8 I/O.

## Seed Probes
1. Place workspace/input at `C:\Users\김 철수 (v2)\my proj\file.json` and trace every CLI spawn, glob, and URL-to-path conversion.
2. Open a UTF-8 file containing Korean/emoji or a UTF-8 BOM (`\ufeff`) on Windows with default locale encoding (`open(p)` / PowerShell `Get-Content`).
3. Pass a 270-character nested path or reserved Windows filename (`CON`, `NUL`, trailing dot/space) to file creation routines.
4. Reference `Assets/Icon.png` in code while disk holds `Assets/icon.png` (passes on Windows, crashes on Linux CI/builds).

## Retire / Disproof Rule
Retire if all subprocesses pass argument arrays without shell interpolation, all text I/O specifies explicit UTF-8 (handling BOM where external files enter), and paths use OS-agnostic joiners.

## Real Incident Anchor
Windows CP949/cp1252 default encoding in Python `open()` and unquoted `C:\Users\First Last` paths remain top causes of "works on my Mac/Linux, crashes on user's Windows PC" failures.
