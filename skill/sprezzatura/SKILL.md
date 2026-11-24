---
name: sprezzatura
description: >-
  Sprezzatura — Adaptive Fault-Cluster QA Audit. Weaponizes the "Turkey Test"
  principle via a 3-stage pipeline: deterministic stdlib surface fingerprinting + reachability
  profiling, isolated parallel read-only Cluster Hunters driven by <=45-line Hostile World-State
  cards with per-stack applicability matrices, and a fresh-context Blind Skeptical Verifier
  with opt-in scratch reproduction (--prove) and confirm-before-file issue drafting.
  Trigger explicitly via /sprezzatura, /sprez, or when the user asks to stress-test code/diffs for
  hidden environmental, locale, timing, filesystem, concurrency, or boundary defects.
---

# Sprezzatura (`/sprezzatura`, `/sprez`) — Adaptive Fault-Cluster QA Audit

Sprezzatura replaces noisy, generic 40-item code review checklists with **isolated, high-curvature hostile world-state probes** (like the classic *Turkey Test*), defended by a **Blind Skeptical Verifier** so only concrete, reachable defects reach the developer.

> **Core Invariants (Non-Negotiable):**
> 1. **Strictly Read-Only by Default:** Never modify target repository source files during an audit.
> 2. **Never Auto-File Issues:** Present findings and drafts first; file GitHub issues or backlog items ONLY after explicit user confirmation of selected IDs and duplicate-fingerprint checks.
> 3. **0 Findings (`CLEAN`) Is a Valid, High-Scoring Outcome:** Never invent speculative bugs to justify a run.
> 4. **Never Confuse Silence With Completion:** Always disclose completed vs. skipped vs. timed-out charters.

---

## Invocation & Modes

```text
/sprezzatura [path-or-scope] [--mode quick|standard|deep] [--repo] [--prove]
/sprez [path-or-scope] [--mode quick|standard|deep] [--repo] [--prove]
```

| Mode | Active Hunters | Verification Stage | When to Use |
|---|---:|---|---|
| `quick` | `0–1` | 1 Blind Verifier | Small diff or single targeted risk check |
| `standard` *(default)* | Adaptive `0–3` | 1 Blind Verifier | Everyday PR/commit audit (target ≤5 contexts) |
| `deep` | `0–5` | 1 Blind Verifier *(prefer cross-model if available)* + opt-in `--prove` | Milestone / pre-release audit *(show budget notice if >3 hunters or `--repo`)* |

---

## Step-by-Step Procedure

### Stage 1 — Hybrid Surface Profiler (Orchestrator)
Record `{USER_LANGUAGE}` (matching the user's request language).

1. **Run the deterministic stdlib fingerprinter (single command, zero external deps; use `python3` on macOS/Linux if `python` is unavailable):**
   ```bash
   python "<skill_dir>/scripts/fingerprint.py" --repo "<repo_root>" --scope <auto|diff|merge-base|path|repo> [--path "<subpath>"] [--include-tests]
   ```
   - **Test-file hygiene:** Test files (`tests/`, `test_*.py`, `*_test.*`, `*.spec.*`) are excluded from candidate cluster scoring by default (`tests_excluded: true`, with `test_file_count` reported) so test harnesses do not drown out production signals; pass `--include-tests` (or target a test path directly via `--path`) when auditing tests.
   - **Default Scope Cascade (`--scope auto`):**
     1. Explicit `<path>` if provided by user.
     2. Working tree diff (staged + unstaged + untracked source files).
     3. Clean feature branch → diff against merge-base (`main`/`master`).
     4. Clean default branch with no diff → stop and ask the user to pick a target path or confirm `--repo` (never silently spray 500 legacy files).
2. **Establish Reachability & Adaptively Select Clusters (`0` to mode max):**
   - Inspect the JSON output (`detected_stacks`, `target_files`, `candidate_clusters` with concrete API/import/boundary evidence, and `unmatched_clusters`).
   - Select **only genuinely reachable clusters** (a small diff may earn `0` or `1` hunter — do NOT pad to 3).
   - Cite concrete evidence from `fingerprint.py` for every selected cluster. You may nominate **at most 1 unlisted cluster** only if you cite a specific entry point and a plausible broken product contract.
   - Bind each selected cluster to its exact target file slice and entry points (plus 1-hop callers/callees needed to judge reachability).
3. **Print a Compact Pre-Flight Lock (≤4 lines):**
   - Scope & revision (`git rev-parse --short HEAD` or `working-tree`), detected stack(s), active clusters, and a 1-line `Skipped Clusters` note.
   - If `--repo` or `deep` with `>3` hunters was implicitly triggered, confirm cost/scope before fanning out.

---

### Stage 2 — Isolated Parallel Cluster Hunters (Read-Only)
Spawn **1 fresh, isolated read-only subagent per selected cluster** in parallel using the Stage 2 template in [prompt_templates.md](./references/prompt_templates.md):
- **Antigravity (`agy`):** `invoke_subagent` with `TypeName: "research"` (or `"self"` strictly instructed read-only), `Model: "inherit"`.
- **Claude Code:** `Agent` tool (fresh context, read-only tools only).
- **Codex CLI:** Isolated `codex exec -s read-only` workers; if the client lacks parallel isolation, run sequentially and **explicitly disclose reduced independence** in the final report.

**Hunter Rules:**
- **Zero Cross-Talk:** Hunters never see each other's findings or cards.
- **Load Only One Card:** Pass ONLY the assigned card (`references/clusters/<card>.md`), the detected stack profile, and the assigned file slice.
- **Stack Applicability Gate:** Hunters MUST honor the card's `Per-Stack Applicability` section (e.g., never flag locale-independent Python `str.lower()` or JS `toLowerCase()` under `locale-casing`).
- **Evidence Contract (Pre-Verifier Hard Filter):** Every candidate finding MUST populate ALL required fields (`cluster`, `probe_id`, `file:line`, `symbol`, `origin: regression|pre-existing`, `trigger_input`, `expected_contract`, `actual_failure`, `traced_path`, `user_impact`). Drop any candidate missing a field before Stage 3.
- **Hard Cap:** Maximum `4` findings per hunter, `0` floor. **Problem-only** (no unsolicited code patches or style nits).
- **UX Hygiene:** While hunters run in parallel, do not stream partial analysis; wait until all complete or time out, and record any unfinished/timed-out hunter explicitly.

---

### Stage 3 — Blind Skeptical Verifier (Fresh Clean Context)
If all hunters returned `0` valid candidates, skip Stage 3 and jump straight to Stage 4 (distinguishing clean completion from any timed-out hunter).

Otherwise, spawn **1 fresh clean-context Verifier subagent** using the Stage 3 template in [prompt_templates.md](./references/prompt_templates.md):
- **Blind Input Rule:** Strip all hunter prose, persuasion, confidence scores, and severity labels. Pass ONLY the normalized structured evidence records + target repo read access.
- **Hostile Defense-Attorney Posture:** For every candidate, the Verifier MUST re-read the cited `file:line` and upstream callers/callees/contracts and **actively try to disprove it** (`DISPROVED` if guarded upstream, unreachable, wrong stack semantics, or governed by a different contract such as a wire spec requiring decimal dots).
- **Deduplicate & Rank:** Merge findings sharing one root cause and one fix. Assign `CONFIRMED: Blocker | Major | Watch` (max `10` findings per report).
- **Stable Fingerprints:** Compute a deterministic 10-char fingerprint per confirmed finding via:
  ```bash
  python "<skill_dir>/scripts/fingerprint.py" --hash "<cluster>" "<normalized_rel_path>" "<symbol>" "<probe_id>"
  ```
- **Prune Tally:** Return a single count line (`N raw -> M confirmed, K pruned`). Keep discarded hypotheses off the user's first screen.

---

### Stage 3.5 — Opt-In Executable Proof (`Verify` / `--prove`)
Run ONLY when the user explicitly passes `--prove` (on Verifier-confirmed `Blocker`/`Major` findings, capped at `N=5`) OR invokes `Verify <ID>` on a specific finding after Stage 4:
1. **Heavy-Build Guard:** If the target requires Unity Editor, native GUI, or external hardware, do NOT fake a partial harness — keep `STATIC-ONLY` and state why.
2. **Isolated Scratch Execution:** Run in a disposable temp directory or detached `git worktree` outside the target tree, with no network access and zero edits to lockfiles or target files. Clean up scratch space immediately after.
3. **Real Entry-Point + Control Requirement:** A probe earns `PROVEN` ONLY if it fails through the **actual product entry point** at the audited revision AND a matching **control input passes** on the same entry point. Record OS/runtime/locale environment.
4. **Status Tags:** `PROVEN` | `STATIC-ONLY` | `REPRO-FAILED` *(unproven, not automatically false)*.

---

### Stage 4 — First-Screen Report & Opt-In Action Loop
Deliver the report in `{USER_LANGUAGE}` following strict anti-slop ergonomics:

1. **First Screen (Top 3 Lines — Answer 3 Questions):**
   - **What breaks for the user?** (Count + headline impact, or explicit `0 findings` across `X/Y completed charters` + any timed-out charter warning).
   - **What evidence supports it?** (`STATIC-ONLY` vs `PROVEN`, revision, prune tally `N raw -> M confirmed`).
   - **What to do next?** (Smallest concrete next step).
2. **Confirmed Findings Table & Concise Cards (Problem-Only):**
   - For each confirmed finding (`F01..F10`): ID, Fingerprint (`sprezzatura:<fp>`), Severity, Proof Tag, Origin (`regression` vs `pre-existing`), `file:line`, Trigger, Broken Contract, User Impact, and Smallest Next Check.
   - Keep raw hunter logs and rejected hypotheses out of the main output (only print if user asks).
3. **Optional Local Export & Recheck Diff:**
   - If a prior `.sprezzatura/last_run.json` exists for the same scope (only written when user opts in or invokes export/file), compare fingerprints and tag each item `NEW` | `STILL-PRESENT` | `RESOLVED` | `FLAPPING`.
4. **Action Footer (Never Auto-Execute):**
   Offer three crisp follow-ups:
   - **`Verify F01`** — Run isolated scratch reproduction through the product entry point (`PROVEN` / `REPRO-FAILED`).
   - **`File F01, F02`** — Preview exact issue text + destination (`gh issue create` or `BACKLOG.md`), run `gh issue list --search "sprezzatura:<fp>"` duplicate check, and create **only after explicit confirmation**.
   - **`Recheck`** — Re-run the same cluster & trigger/control after a fix to confirm `RESOLVED`.

---

## Validation Checklist (Before Delivering Report)
- [ ] `fingerprint.py` ran cleanly and scope/skipped clusters were disclosed in ≤4 lines.
- [ ] Every active hunter ran in an isolated read-only context with ONLY its assigned card and target slice (or sequential fallback was explicitly disclosed).
- [ ] Every hunter respected the card's `Per-Stack Applicability` matrix and problem-only rule.
- [ ] Stage 3 Verifier ran blind (without hunter confidence/narrative) and actually re-read cited code + callers.
- [ ] Completed vs. unfinished/timed-out charters are explicitly separated on the first screen.
- [ ] Zero target files were modified and zero external issues were filed without explicit user confirmation.
