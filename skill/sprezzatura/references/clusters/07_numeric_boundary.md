---
id: numeric-boundary
name: Zero, NaN, Falsy Coercion & Float Drift
category: numeric
---

## Hostile World-State
Inputs contain valid `0` (price, index, coordinate `(0,0)` Null Island), negative numbers, `NaN`/`Infinity`, IEEE-754 floats (`0.1 + 0.2`), or 64-bit integer IDs exceeding JS `Number.MAX_SAFE_INTEGER` (`2^53 - 1`).

## Per-Stack Applicability
- **Applies:** JS/TS/Python truthiness checks (`if (!val)`, `val || default`, `if not x:`) treating valid `0` or `0.0` as missing/null; JS JSON parsing 64-bit snowflake/DB IDs as `number`; binary float math for money/exact thresholds (`==` on floats); unguarded division/normalization (`vec / len` when `len == 0` -> `NaN` poisons physics/state); C#/C++ signed integer overflow or `int / int` truncation.
- **Ignore/Safe:** Explicit `val === null || val === undefined` / `val is None` / nullish coalescing `??`; `Decimal`/integer minor-unit arithmetic for money; `BigInt`/string IDs for 64-bit identifiers; explicit `Math.isfinite` / epsilon guards.

## Seed Probes
1. Pass valid `0` (index `0`, discount `0`, lat/lon `(0, 0)`) into fallback/validation expressions (`x || fallback`, `if not x`).
2. Feed `0.0` length vector or empty denominator into normalization/averaging, tracing whether `NaN` propagates into saved state or UI.
3. Pass negative quantity (`-1`), `Infinity`, or `9007199254740993` (`2^53 + 1`) through API/JSON/calculation boundaries.
4. Compare accumulated floats (`0.1 + 0.2 == 0.3`) or cast large `float`/`int64` to `int32` without bounds check.

## Retire / Disproof Rule
Retire if boundaries enforce finite/range validation, explicit null checks (`??` / `is None`) distinguish `0` from absent, and exact-precision types protect financial/ID fields.

## Real Incident Anchor
Ariane 5 Flight 501 self-destructed on an unguarded 64-bit float to 16-bit int overflow; Twitter/Discord clients corrupted 64-bit IDs in JS `JSON.parse` until migrating to string IDs.
