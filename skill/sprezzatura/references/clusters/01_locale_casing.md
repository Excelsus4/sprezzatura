---
id: locale-casing
name: Turkish Casing & Culture-Sensitive Lookup
category: i18n
---

## Hostile World-State
Windows 11 configured to `tr-TR` (Turkish locale). The code runs on a user machine where `I` lowercases to dotless `ı` (`U+0131`) and `i` uppercases to dotted `İ` (`U+0130`), while persisted keys, enums, headers, and commands are ASCII.

## Per-Stack Applicability
- **Applies:** C#/.NET `string.ToLower()` / `ToUpper()` / `Equals(..., CurrentCultureIgnoreCase)` / `RegexOptions.IgnoreCase` without `CultureInvariant`; Java `String.toLowerCase()` / `toUpperCase()` without `Locale.ROOT`; JS/TS `toLocaleLowerCase()` / `toLocaleUpperCase()` / `localeCompare()`; SQL `LOWER()`/`UPPER()` under Turkish collation; C/C++ `tolower`/`strcasecmp` after `setlocale()`.
- **Ignore/Safe:** Python `str.lower()`/`upper()` (locale-independent); JS/TS `toLowerCase()`/`toUpperCase()` (locale-independent); Rust `to_ascii_lowercase()`; Go `strings.ToLower()`; C# `ToLowerInvariant()` / `OrdinalIgnoreCase`.

## Seed Probes
1. Look up ASCII key `"FILE"`, `"ID"`, or `"INFO"` via culture-sensitive lowercasing under `tr-TR` (`"FILE".ToLower()` -> `"fıle"`).
2. Normalize enum/protocol token `"item"` or `"https"` via `.ToUpper()` under `tr-TR` (`"item".ToUpper()` -> `"İTEM"`).
3. Case-insensitive regex `/^id$/i` or file-extension check `.ToLower().EndsWith(".ini")` on mixed-case input under `tr-TR`.
4. Round-trip `"İZMİR".ToLower()` checking unexpected combining dot `U+0307` length inflation.

## Retire / Disproof Rule
Retire immediately if the stack's casing operation is locale-independent (see Ignore/Safe), or if every comparison/lookup along the traced path preserves original case or uses explicit `OrdinalIgnoreCase` / `Locale.ROOT` / `InvariantCulture`.

## Real Incident Anchor
Oracle, Apache, and .NET apps routinely crashed on `tr-TR` hosts when `"TITLE".toLowerCase()` failed to match `"title"` or `"http".toUpperCase()` failed schema checks ("The Turkey Test", Moser 2008).
