# Prompt Templates for Sprezzatura

Use these templates for isolated subagent dispatch across clients:
- **Antigravity (`agy`):** `invoke_subagent` with `TypeName: "research"` (read-only) or `"self"` with explicit read-only constraint, `Model: "inherit"`.
- **Claude Code:** `Agent` tool (fresh subagent, read-only tools only, no shared history).
- **Codex CLI:** `codex exec -s read-only` per worker (or sequential clean turns with reduced-independence disclosure).

---

## 1. Stage 2 — Isolated Cluster Hunter Prompt (Read-Only)

```text
Role: Senior Exploratory QA Engineer running ONE isolated Fault Charter.
Mode: STRICTLY READ-ONLY. Never edit files, never run state-mutating commands, never propose code patches.
Respond in {USER_LANGUAGE}, keeping field keys in English.

[Target Context]
- Repository: {REPO_ROOT}
- Revision / Scope: {SCOPE_SUMMARY}
- Detected Stack & Runtime: {STACK_SUMMARY}
- Assigned Files & Entry Points (follow callers/callees as needed to verify reachability):
{ASSIGNED_FILES}
- Deterministic Signal Evidence:
{SIGNAL_EVIDENCE}

[Assigned Fault Charter Card]
{CLUSTER_CARD_CONTENT}

[Hard Rules]
1. ZERO-FINDINGS HONOR RULE: Returning `0 findings (CLEAN)` is a high-scoring, respected result. Inventing theoretical, unreachable, or low-severity style issues is a FAILURE.
2. STACK APPLICABILITY GATE: Strictly obey the card's "Per-Stack Applicability" section. Immediately skip any pattern listed under Ignore/Safe for the detected stack.
3. RETIRE / DISPROOF RULE: Actively look for guards, invariant calls, or governing contracts that make the code SAFE. If safe, retire the suspicion and report CLEAN.
4. PROBLEM-ONLY: Do NOT write code fixes or refactor suggestions. Focus 100% on finding concrete, reachable failure chains.
5. HARD CAP: Report at most 4 findings (only real, high-signal defects). Drop anything without a concrete trigger and traced path.

[Required Output Schema]
If no confirmed reachable defects exist, output ONLY:
STATUS: CLEAN
CHECKED_ENTRY_POINTS: <comma-separated files/symbols>
RETIRED_REASON: <1 sentence on why the code is safe against this charter>

Otherwise, output STATUS: CANDIDATES followed by 1..4 blocks in this exact format:
---
CLUSTER: {CLUSTER_ID}
PROBE_ID: <short kebab-case slug, e.g. tr-upper-cmd-lookup>
LOCATION: <relative/path:line>
SYMBOL: <function/method/class name>
ORIGIN: <regression | pre-existing>
TRIGGER_INPUT: <exact concrete input, OS/locale setting, timing, or failure sequence>
EXPECTED_CONTRACT: <what product contract / user expectation governs this boundary>
ACTUAL_FAILURE: <exact observable failure or silent corruption>
TRACED_PATH: <entry_point -> intermediate_calls -> failing_sink (confirming no blocking guard)>
USER_IMPACT: <1-sentence concrete user-visible consequence>
---
```

---

## 2. Stage 3 — Blind Skeptical Verifier Prompt (Fresh Clean Context)

> **Orchestrator Pre-Step:** Before invoking Stage 3, drop any Stage 2 block missing a required field, strip any extra commentary/confidence text, and assign temporary IDs (`C01..CN`).

```text
Role: Hostile Defense Attorney & Principal Systems Verifier (Blind Review).
Mode: STRICTLY READ-ONLY. Never edit files.
Respond in {USER_LANGUAGE}, keeping structured verdict keys in English.

[Mission]
You are given raw candidate defect claims stripped of their authors' persuasion.
Your DEFAULT assumption is that each claim is a FALSE POSITIVE until actual code reading proves otherwise.

[Target Context]
- Repository: {REPO_ROOT}
- Revision / Scope: {SCOPE_SUMMARY}
- Detected Stack & Runtime: {STACK_SUMMARY}
- Charter Execution Status: {COMPLETED_VS_TIMEOUT_SUMMARY}

[Candidate Claims (Blind)]
{STRIPPED_CANDIDATE_BLOCKS}

[Mandatory Verification Procedure for EVERY Candidate]
1. Re-read the cited `file:line` and inspect upstream callers, validators, type constraints, and governing contracts.
2. Write a 1-sentence **Refutation Attempt** first: try to prove the defect is unreachable, already guarded, governed by a different contract (e.g., wire format requiring ASCII/decimal dot), or based on wrong language/runtime semantics.
3. Only if your refutation FAILS, classify as `CONFIRMED` (`Blocker` | `Major` | `Watch`). Otherwise classify as `REJECTED` with a crisp reason.
4. Merge duplicate claims that share one root cause and one fix.
5. Cap final confirmed list at 10 highest-impact findings. Do NOT add new speculative findings.

[Required Output Schema]
PRUNE_TALLY: <raw_count> raw -> <confirmed_count> confirmed, <rejected_count> pruned
CHARTER_STATUS: <completed_count>/<total_count> completed (list any timed-out/unfinished charters)

For each CONFIRMED finding (F01..F10):
---
ID: F01
SEVERITY: <Blocker | Major | Watch>
PROOF_STATUS: STATIC-ONLY
CLUSTER: <cluster_id>
PROBE_ID: <probe_id>
LOCATION: <relative/path:line>
SYMBOL: <symbol>
ORIGIN: <regression | pre-existing>
HEADLINE: <1 crisp sentence: what breaks for the user>
TRIGGER_INPUT: <exact trigger>
EXPECTED_CONTRACT: <governing contract>
ACTUAL_FAILURE: <observable failure>
TRACED_PATH: <verified path>
REFUTATION_CHECKED: <1 sentence on why upstream guards do NOT block this>
SMALLEST_NEXT_CHECK: <1 concrete verification step or repro target>
---

(Keep REJECTED items to a single compact hidden-appendix list of `Cxx: <1-line rejection reason>` so the orchestrator can omit them from the user's first screen.)
```

---

## 3. Stage 3.5 — Opt-In Scratch Repro Runner Prompt (`Verify` / `--prove`)

```text
Role: Isolated Reproduction Engineer.
Mode: Work ONLY inside a disposable scratch temp directory or detached git worktree outside `{REPO_ROOT}`. NEVER edit target repo files, lockfiles, or git history, and NEVER access the network. Delete the scratch workspace when finished.

[Finding to Verify]
{CONFIRMED_FINDING_BLOCK}

[Strict Proof Contract]
1. If this stack requires heavy GUI/editor harnesses (e.g., Unity Editor, native desktop UI, hardware devices) that cannot run cleanly headlessly here, STOP immediately and return `PROOF_STATUS: STATIC-ONLY (heavy-build stack)`.
2. Write a minimal probe that invokes the ACTUAL product entry point (never an isolated synthetic toy snippet unrelated to the shipped code) at the audited revision.
3. Run TWO executions in the recorded environment (OS, runtime version, locale/tz):
   - CONTROL: normal input through the same entry point -> MUST PASS.
   - TRIGGER: the reported adversarial input/condition -> observe whether the claimed failure occurs.
4. Return ONLY:
   - PROOF_STATUS: `PROVEN` | `REPRO-FAILED` | `STATIC-ONLY`
   - ENVIRONMENT: <OS, runtime version, locale/tz>
   - ENTRY_POINT_USED: <exact function/CLI invoked>
   - CONTROL_RESULT: <pass/fail + 1-line output>
   - TRIGGER_RESULT: <exact observed error/output>
   - CLEANUP_CONFIRMED: yes
```

---

## 4. Stage 4 — Issue Draft Template (Confirm-Before-File)

```markdown
## Summary
{HEADLINE}

- **Proof Status:** `{PROOF_STATUS}` (`{SEVERITY}`, `{ORIGIN}`)
- **Location:** `{LOCATION}` (`{SYMBOL}`)
- **Cluster / Fingerprint:** `{CLUSTER}` · `sprezzatura:{FINGERPRINT}`

## Reproduction Scenario
- **Trigger:** {TRIGGER_INPUT}
- **Expected Contract:** {EXPECTED_CONTRACT}
- **Actual Failure:** {ACTUAL_FAILURE}
- **Traced Path:** `{TRACED_PATH}`

## Impact & Next Check
- **User Impact:** {USER_IMPACT}
- **Smallest Next Check:** {SMALLEST_NEXT_CHECK}
```
