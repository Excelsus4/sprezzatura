---
id: auth-trust-boundary
name: IDOR, Trust-Boundary Bypass & Secret Leakage
category: security
---

## Hostile World-State
Authenticated User A swaps only the resource `id` to User B's ID, sends `../../etc/passwd` or `..\secret` in a filename, or triggers an error whose log/response dumps tokens or PII.

## Per-Stack Applicability
- **Applies:** API endpoints fetching by request ID without principal scoping (`WHERE id = ? AND owner_id = ?`); file download/extract handlers joining untrusted paths without canonical root containment (`realpath` / `Path.resolve().is_relative_to`); SQL/shell/template interpolation; logs/errors printing headers, env vars, or API keys; archive extraction without Zip-Slip checks.
- **Ignore/Safe:** Single-user offline CLIs for IDOR (still check traversal & secret logs on untrusted archives/URLs); parameterized queries; canonical root containment checks.

## Seed Probes
1. Swap resource/tenant ID in URL, query, or JSON from User A to User B under User A's session (IDOR).
2. Submit `../../outside.txt`, `/etc/passwd`, or `..\file` into archive extraction or file-serving params (Zip-Slip / traversal).
3. Trigger an exception and trace whether `Authorization`, cookies, or API keys reach logs or responses.
4. Trace untrusted input into SQL, shell, HTML/DOM sinks, or outbound URL fetches (SSRF to `169.254.169.254` / `localhost`).

## Retire / Disproof Rule
Retire if no trust boundary applies (e.g., offline single-user script for IDOR), or every untrusted sink enforces principal scoping, canonical path containment, parameterization, and secret redaction.

## Real Incident Anchor
IDOR and Zip-Slip (`../../` archive entries) remain among the highest-impact production vulnerabilities because authentication passes while object-level authorization or path containment is missing.
