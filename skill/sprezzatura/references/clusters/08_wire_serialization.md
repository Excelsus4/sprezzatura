---
id: wire-serialization
name: Serialization Drift, Array Unwrapping & Unknown Enums
category: serialization
---

## Hostile World-State
A producer adds one new enum value or optional field, a PowerShell 5.1 script serializes a 1-element array, or a CSV/JSON payload carries nested quotes, trailing commas, `null` vs omitted keys, or default-depth truncation.

## Per-Stack Applicability
- **Applies:** PowerShell 5.1 `ConvertFrom-Json` + `@(...)` double-nesting or `ConvertTo-Json` default `-Depth 2` silently stringifying nested objects and unwrapping 1-element arrays; strict deserializers crashing on unknown enum values/extra JSON fields; hand-rolled CSV/INI/regex parsers instead of RFC parsers; JS/Python `eval`/unsafe `yaml.load`/`pickle.loads` on untrusted payloads; lossy round-trips dropping unknown fields.
- **Ignore/Safe:** Strict schema validators (`pydantic`, `zod`, `System.Text.Json`) configured explicitly for version tolerance; PowerShell `ConvertTo-Json -InputObject @($arr) -Depth N` with verified shape; `yaml.safe_load`.

## Seed Probes
1. Round-trip a **0-element** and **1-element** collection through serializer -> deserializer (especially PowerShell 5.1 JSON pipelines or XML-to-JSON bridges).
2. Send a payload containing an unknown enum string, an extra unexpected field, or a nested object at depth 4+.
3. Inject a comma, newline, or double-quote inside a CSV/delimiter-separated field (`"Smith, Jr."`).
4. Distinguish explicit `null`, omitted key, and empty string `""` across patch/update serializers.

## Retire / Disproof Rule
Retire if serialization uses standard RFC libraries with explicit depth/array-shape handling, unknown fields/enums follow a documented compatibility policy, and untrusted input never enters unsafe loaders.

## Real Incident Anchor
PowerShell 5.1 `ConvertTo-Json` default `-Depth 2` and 1-element array unwrapping silently corrupt build manifests into `{"value": [...], "Count": N}` or `"System.Object[]"`.
