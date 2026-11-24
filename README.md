# Sprezzatura

> *Sprezzatura* (Castiglione, 1528) — studied nonchalance: effortless ease on the surface, invisible rigor underneath. This tool is the rigor underneath.

**Your tests pass on your machine. Sprezzatura asks what happens on someone else's** — a different locale, a DST jump, a path with spaces, a process killed mid-write, or a request arriving twice.

A read-only QA audit skill for **Claude Code**, **Antigravity**, and **Codex CLI**. It fingerprints your diff deterministically, runs isolated per-cluster reviewers only for failure classes the code can actually reach, and filters every finding through a fresh-context blind verifier before anything reaches your screen.

`/sprezzatura` · `/spz` · zero dependencies (Python 3.9+ stdlib) · never edits target files · never files issues without confirmation

---

## When to Run It

- **Before merging a PR or cutting a release** when changes touch file I/O, parsing, wire serialization, auth boundaries, retries, or date/locale handling.
- **When shipping across OS or locale boundaries** — Windows/Linux paths, Unicode or spaced filenames, non-US locale casing or decimal commas, DST or monotonic clock assumptions.
- **Before deploying state-transition logic** such as schema migrations, cold-start initialization, lock files, or atomic-write / crash-recovery paths.
- **When picking up an unfamiliar module** (`--path src/billing`) and wanting a scoped, read-only risk sweep without speculative code patches.

---

## Quick Start

Requires Python 3.9+ (standard library only) and one of Claude Code, Antigravity (`agy`), or Codex CLI.

### 1. Install

Clone the repository and run the local installer helper (supports `--dry-run`, handles reinstalls cleanly, and generates `plugin.json` for Antigravity):

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
# Claude Code (+ /sprezzatura and /spz slash commands)
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

### 2. Run in a Target Repository

Open your coding agent inside the **repository you want to audit** (`cd /path/to/your-project`), not inside the cloned `sprezzatura` directory:

```text
/sprezzatura                              # Auto-scope (working diff -> merge-base)
/spz src/payments --mode standard         # Audit a specific module
/spz --mode deep --prove                  # Up to 5 clusters + opt-in scratch repro
/spz --repo --mode deep                   # Full repository audit (confirms budget first)
```

| Mode | Active Clusters | Verification | Best For |
|---|---:|---|---|
| `quick` | `0–1` | 1 Blind Verifier | Small diff or single targeted risk check |
| `standard` *(default)* | Adaptive `0–3` | 1 Blind Verifier | Everyday PR / commit audit (target ≤5 contexts) |
| `deep` | `0–5` | 1 Blind Verifier + opt-in `--prove` | Pre-release / milestone hardening |

On a clean default branch with no diff, Sprezzatura stops and asks for a `--path` or explicit `--repo` confirmation instead of silently scanning the entire repository.

---

## What It Checks (12 Fault Clusters)

Each cluster card in [`skill/sprezzatura/references/clusters/`](./skill/sprezzatura/references/clusters/) is lint-enforced by `tools/lint_cards.py` to stay `<=45` lines and `<=250` words with `3–5` concrete seed probes, per-stack applicability rules, and an explicit disproof rule.

| # | Cluster ID | Category | Focus | Card |
|---:|---|---|---|---|
| 01 | `locale-casing` | `i18n` | Culture-sensitive casing (e.g., Turkish `i`/`İ`, `I`/`ı`) & lookup | [01_locale_casing.md](./skill/sprezzatura/references/clusters/01_locale_casing.md) |
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

## Reading the Report

Reports open with a concise summary separating completed checks from skipped or timed-out checks, followed by confirmed findings (if any) and opt-in follow-up actions:

```text
Impact: <count + user-visible consequence>; checks <done>/<selected>; unfinished <count>
Evidence: <STATIC-ONLY | PROVEN>; revision <sha>; <raw> -> <confirmed>
Next: <smallest concrete next check>
Coverage: <skipped or timed-out clusters and 1-line reasons>

F01 | <Blocker | Major | Watch> | <STATIC-ONLY | PROVEN | REPRO-FAILED> | <regression | pre-existing>
Location: <file:line> (<symbol>) | Fingerprint: sprezzatura:<10-char-hash>
Trigger: <concrete input> | Contract: <expected behavior>
Impact: <user-visible failure> | Next check: <verification step>

Actions: Verify F01 | File F01 | Recheck
```

- **Proof tags:** Default findings are `STATIC-ONLY`. Passing `--prove` or replying `Verify F01` runs an isolated scratch check through the real product entry point plus a passing control (`PROVEN` or `REPRO-FAILED`; heavy GUI/engine builds stay `STATIC-ONLY`).
- **Issue filing:** Replying `File F01` previews the exact draft and checks `gh issue list --search "sprezzatura:<fp>"` for duplicates; nothing is created until you explicitly confirm.

---

## How It Keeps Noise Down

- **Deterministic scoping (`scripts/fingerprint.py`):** Respects `.gitignore`, excludes test files from production cluster scoring by default (`--include-tests` opt-in), and activates only reachable clusters (never padding a small diff).
- **Isolated per-cluster checks:** Each active cluster runs in its own read-only subagent with one compact card, a per-stack applicability matrix (preventing cross-stack false positives such as flagging Python `str.lower()` under Turkish casing), and an explicit `0 findings (CLEAN)` rule.
- **Fresh-context blind verification:** An independent reviewer sees only normalized evidence records—with reviewer prose and confidence scores stripped—re-reads cited code and callers to attempt refutation, merges shared root causes, and assigns stable fingerprints.
- **Read-only by default:** Never modifies target repository files and never runs reproduction or issue creation without explicit opt-in.

---

## Scope

Sprezzatura complements unit tests, linters, and SAST; it does not replace them. It reports concrete, reachable failure paths with evidence and never writes patches. Style, naming, and general PR review comments are out of scope.

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

- Companion skill in the same craft lineage: **[Sfumato](https://github.com/Excelsus4/sfumato)** — Dual-track cross-domain ideation for breaking LLM homogenization.
- Licensed under the [MIT License](./LICENSE).
