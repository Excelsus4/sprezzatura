<div align="center">

# Sprezzatura

### *Weaponize the Turkey Test. Adaptive, Isolated Fault-Cluster QA Audits for Coding Agents.*

<p>
  <img src="https://img.shields.io/badge/Dependencies-Zero_(Pure_Stdlib)-5C4E3F?style=for-the-badge" alt="Zero Dependencies" />
  <img src="https://img.shields.io/badge/Fault_Clusters-12_Hostile_World--States-8E2F21?style=for-the-badge" alt="12 Hostile World-State Clusters" />
  <img src="https://img.shields.io/badge/Default_Mode-Strictly_Read--Only-2F5D62?style=for-the-badge" alt="Read-Only Default" />
  <img src="https://img.shields.io/badge/Agents-Claude_Code_%7C_Antigravity_%7C_Codex-3D4F5F?style=for-the-badge" alt="Cross-Agent Skill" />
</p>

> *"Sprezzatura"* (Italian, Baldassare Castiglione, 1528) — *studied nonchalance*: effortless grace on the surface, backed by relentless, invisible rigor underneath.
>
> **Sprezzatura** (`/sprezzatura`, `/sprez`) is a zero-dependency, cross-agent **Fault-Cluster QA Audit** skill and Antigravity plugin.

</div>

---

## The Problem: Why Generic Code-Review Checklists Fail

Ask an LLM a generic prompt like *"review this diff for edge cases"* and you get shallow box-ticking, style nitpicks, and speculative false positives. Ask it one vivid, adversarial scenario — the classic **Turkey Test** (*"Does this work on a Turkish Windows machine where `'i'.ToUpper() == 'İ'` and decimals use commas?"*) — and it suddenly traces real, production-breaking failure paths.

Meanwhile, stuffing 30+ edge-case checklists into a single prompt causes **anchor bleed** and **attention dilution**, while naive multi-agent fan-out causes **false-positive fatigue** (e.g., flagging locale-independent Python `str.lower()` under a Turkish-locale rule).

**Sprezzatura** turns that asymmetry into a disciplined, repeatable 3-stage pipeline.

---

## How Sprezzatura Works

1. **Stage 1 — Hybrid Surface Profiler (`scripts/fingerprint.py`):**
   - A deterministic, pure-stdlib Python scanner fingerprints the target diff or path for stack, OS/runtime, and API boundary signals (excluding test harnesses from production scoring by default unless `--include-tests` or a test `--path` is passed).
   - The orchestrator verifies reachability, adaptively activates **0–5 genuinely relevant clusters** (never padding small diffs), binds each to exact target files, and discloses skipped clusters in ≤4 lines.
2. **Stage 2 — Isolated Parallel Cluster Hunters (Read-Only):**
   - Spawns **one clean-context, read-only subagent per active cluster** with zero cross-talk.
   - Each hunter receives *only* its assigned **≤45-line Hostile World-State Card** — containing a **Per-Stack Applicability Matrix** (killing cross-stack false positives), `3–5` concrete torture probes, an **Explicit Retire/Disproof Rule**, and a **0-Findings (`CLEAN`) Honor Rule**.
   - Problem-only contract: every candidate must cite `file:line`, `symbol`, trigger input, broken contract, traced path, and user impact (max 4 findings per hunter, zero unsolicited code patches).
3. **Stage 3 — Blind Skeptical Verifier (Fresh Context):**
   - Receives *only* normalized evidence records (hunter prose, persuasion, and confidence scores are stripped).
   - Acts as a hostile defense attorney: re-reads cited code, callers, and guards to **disprove** unreachable or contract-compliant claims, merges shared root causes, and assigns deterministic fingerprints (`sprezzatura:<10-char-hash>`).
4. **Stage 3.5 — Opt-In Execution Proof & Confirm-Before-File:**
   - Findings default to `STATIC-ONLY` in a concise first-screen report (strictly separating completed vs. skipped/timed-out charters).
   - Pass `--prove` or reply `Verify F01` to run an isolated scratch reproduction through the **real product entry point + passing control** (`PROVEN` / `STATIC-ONLY` / `REPRO-FAILED`; heavy GUI/engine stacks safely remain `STATIC-ONLY`).
   - Reply `File F01, F02` to preview exact issue drafts, check for duplicates (`gh issue list --search "sprezzatura:<fp>"`), and file **only after explicit confirmation**.

---

## The 12 Hostile World-State Clusters

Every card in [`skill/sprezzatura/references/clusters/`](./skill/sprezzatura/references/clusters/) is lint-enforced by `tools/lint_cards.py` to stay `<=45` lines and `<=250` words so it never degenerates into a bloated checklist.

| # | Cluster ID | Category | Focus | Card |
|---:|---|---|---|---|
| 01 | `locale-casing` | `i18n` | Turkish `i`/`İ`, `I`/`ı`, culture-sensitive lookup | [01_locale_casing.md](./skill/sprezzatura/references/clusters/01_locale_casing.md) |
| 02 | `locale-format` | `i18n` | Decimal comma, date order, currency precision | [02_locale_format.md](./skill/sprezzatura/references/clusters/02_locale_format.md) |
| 03 | `clock-dst-sleep` | `time` | DST gaps/ambiguity, wall-clock jumps, laptop sleep spikes | [03_clock_dst_sleep.md](./skill/sprezzatura/references/clusters/03_clock_dst_sleep.md) |
| 04 | `fs-paths-unicode` | `filesystem` | Spaces/non-ASCII/emoji paths, Windows CP949/cp1252, case sensitivity | [04_fs_paths_unicode.md](./skill/sprezzatura/references/clusters/04_fs_paths_unicode.md) |
| 05 | `crash-partial-write` | `durability` | Mid-flight `SIGKILL`/`ENOSPC`, truncated files, zombie locks | [05_crash_partial_write.md](./skill/sprezzatura/references/clusters/05_crash_partial_write.md) |
| 06 | `concurrency-idempotency` | `concurrency` | Double-click races, out-of-order responses, non-idempotent retries | [06_concurrency_idempotency.md](./skill/sprezzatura/references/clusters/06_concurrency_idempotency.md) |
| 07 | `numeric-boundary` | `numeric` | Zero, `NaN`/`Inf`, falsy coercion, `fp16`/float drift | [07_numeric_boundary.md](./skill/sprezzatura/references/clusters/07_numeric_boundary.md) |
| 08 | `wire-serialization` | `serialization` | Schema drift, single-item array unwrapping, unknown enums | [08_wire_serialization.md](./skill/sprezzatura/references/clusters/08_wire_serialization.md) |
| 09 | `network-hostile` | `network` | Missing timeouts, half-open sockets, retry storms | [09_network_hostile.md](./skill/sprezzatura/references/clusters/09_network_hostile.md) |
| 10 | `resource-scale-lifetime` | `lifecycle` | Empty/100× scale cliffs, 72-hour handle/timer leaks | [10_resource_scale_lifetime.md](./skill/sprezzatura/references/clusters/10_resource_scale_lifetime.md) |
| 11 | `auth-trust-boundary` | `security` | IDOR, path traversal, SQL/shell boundary bypass, secret logs | [11_auth_trust_boundary.md](./skill/sprezzatura/references/clusters/11_auth_trust_boundary.md) |
| 12 | `cold-start-migration` | `lifecycle` | Empty first-run state, schema upgrades, read-only install dirs | [12_cold_start_migration.md](./skill/sprezzatura/references/clusters/12_cold_start_migration.md) |

---

## Installation

Everything Sprezzatura needs lives in [`skill/sprezzatura/`](./skill/sprezzatura/) — pure Markdown + one zero-dependency Python 3.9+ stdlib script (`scripts/fingerprint.py`).

Clone, inspect the files, and run the local installer helper (supports `--dry-run`, handles reinstalls cleanly, and generates `plugin.json` for Antigravity):

```bash
git clone https://github.com/Excelsus4/sprezzatura.git && cd sprezzatura

# macOS / Linux / Git Bash
bash tools/install.sh --dry-run
bash tools/install.sh --target claude                # claude | agy | codex | all | auto
bash tools/install.sh --target agy --agy-mode plugin # default for agy
```

```powershell
# Windows PowerShell 5.1+ / PowerShell 7
powershell -ExecutionPolicy Bypass -File tools\install.ps1 -DryRun
powershell -ExecutionPolicy Bypass -File tools\install.ps1 -Target all
```

<details>
<summary>Manual copy alternative (no installer script)</summary>

Remove any previous `sprezzatura` folder before copying so `cp -r` does not nest `sprezzatura/sprezzatura`:

```bash
# Claude Code (+ optional /sprezzatura and /sprez slash commands)
mkdir -p ~/.claude/skills ~/.claude/commands
rm -rf ~/.claude/skills/sprezzatura
cp -r skill/sprezzatura ~/.claude/skills/sprezzatura
cp commands/*.md ~/.claude/commands/

# Antigravity (agy) — skill mode (use tools/install.* for native plugin mode)
mkdir -p ~/.gemini/config/skills
rm -rf ~/.gemini/config/skills/sprezzatura
cp -r skill/sprezzatura ~/.gemini/config/skills/sprezzatura

# Codex CLI
mkdir -p ~/.codex/skills
rm -rf ~/.codex/skills/sprezzatura
cp -r skill/sprezzatura ~/.codex/skills/sprezzatura
```

</details>

---

## Usage & Modes

```text
/sprezzatura                              # Auto-scope (working diff -> merge-base)
/sprez src/payments --mode standard       # Targeted module audit
/sprez --mode deep --prove                # Up to 5 clusters + opt-in scratch repro
/sprez --repo --mode deep                 # Full repository audit (confirms budget first)
```

| Mode | Active Hunters | Verification | Best For |
|---|---:|---|---|
| `quick` | `0–1` | 1 Blind Verifier | Small diff or single targeted risk check |
| `standard` *(default)* | Adaptive `0–3` | 1 Blind Verifier | Everyday PR / commit audit (target ≤5 contexts) |
| `deep` | `0–5` | 1 Blind Verifier + opt-in `--prove` | Pre-release / milestone hardening |

### Core Safety Invariants
- **Strictly read-only by default:** Never modifies target repository files during an audit.
- **Never auto-files issues:** Always previews drafts and checks `sprezzatura:<fp>` duplicates first; files only on explicit user confirmation of selected IDs.
- **Honest silence:** `0 findings (CLEAN)` is a first-class outcome, and timed-out/skipped charters are always separated from clean completions.

---

## Local Verification (Development)

```bash
python3 tools/lint_cards.py
python3 -m unittest tools/test_tools.py -v
python3 skill/sprezzatura/scripts/fingerprint.py --repo . --scope repo
bash tools/install.sh --target all --dry-run
```

On Windows PowerShell:

```powershell
python tools/lint_cards.py
python -m unittest tools/test_tools.py -v
python skill/sprezzatura/scripts/fingerprint.py --repo . --scope repo
powershell -ExecutionPolicy Bypass -File tools/install.ps1 -Target all -DryRun
```

---

## Companion Tool & License

- Companion skill in the same Renaissance craft lineage: **[Sfumato](https://github.com/Excelsus4/sfumato)** — Dual-track cross-domain ideation for breaking LLM homogenization.
- Licensed under the [MIT License](./LICENSE).
