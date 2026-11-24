---
id: locale-format
name: Decimal Comma, Date Order & Currency Precision
category: i18n
---

## Hostile World-State
A German (`de-DE`) or Turkish (`tr-TR`) OS where decimals use commas (`1,50`), thousands use dots (`1.000`), and dates format as `DD.MM.YYYY` — paired with Japanese Yen (0 decimals) and Kuwaiti Dinar (3 decimals).

## Per-Stack Applicability
- **Applies:** C#/.NET `float.Parse` / `double.Parse` / `decimal.Parse` / `ToString()` / `DateTime.Parse` without `CultureInfo.InvariantCulture`; Java `NumberFormat` / `Scanner` / `String.format` without `Locale.ROOT`; C/C++ `strtod`/`scanf`/`printf` after `setlocale()`; Excel/CSV parsers reading localized numbers; currency math hardcoding `× 100` or `.toFixed(2)`.
- **Ignore/Safe:** JSON parsers (`JSON.parse`, `json.loads`, `System.Text.Json`) obeying RFC 8259 decimal-dot wire contracts; Python `float()`/`int()` (locale-independent); explicit `CultureInfo.InvariantCulture` / ISO-8601 `yyyy-MM-dd`.

## Seed Probes
1. Serialize float `1.5` to a config/CSV/shader text file under `de-DE` (`"1,5"`) and parse it back on `en-US` (or vice versa -> `15` or parse crash).
2. Parse `"04.07.2026"` via default locale date parser (swaps April 7 and July 4 across locales).
3. Pass Japanese Yen (`JPY`, 0 minor units) or Kuwaiti Dinar (`KWD`, 3 minor units) through currency formatter or minor-unit `amount / 100` math.
4. Confirm whose contract governs the boundary: do NOT demand decimal commas inside JSON/wire specs that mandate `.`.

## Retire / Disproof Rule
Retire if all numeric/date parsing and serialization at the boundary explicitly bind `InvariantCulture` / `Locale.ROOT` / ISO-8601, or if the wire format deliberately enforces dot-decimal grammar end-to-end.

## Real Incident Anchor
Steam/Unity games and desktop CAD tools corrupted save files on European Windows installs when `float.ToString()` wrote `0,5` into whitespace/comma-delimited text files.
