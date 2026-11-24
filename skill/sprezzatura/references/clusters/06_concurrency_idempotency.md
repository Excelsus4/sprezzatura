---
id: concurrency-idempotency
name: Double-Click Races, Out-of-Order Responses & Retries
category: concurrency
---

## Hostile World-State
An impatient user double-clicks Submit 100ms apart; Request A takes 2.5s while Request B takes 200ms so responses arrive in reverse order; a webhook or client retry delivers the exact same mutation twice.

## Per-Stack Applicability
- **Applies:** UI async handlers/effects updating shared state without abort/sequence guards (`AbortController`, request ID check); non-atomic read-modify-write on shared files, caches, or DB rows; HTTP POST/webhook/job handlers lacking idempotency keys or unique constraints; background workers mutating shared in-memory collections without locks.
- **Ignore/Safe:** Pure synchronous single-threaded transforms with no shared mutable state; DB mutations guarded by atomic SQL `UPDATE ... WHERE`, unique idempotency keys, or optimistic version checks; UI queries canceling stale in-flight requests.

## Seed Probes
1. Fire the same click/command/API call twice 50ms apart: does it create duplicate records, charge twice, or spawn overlapping workers?
2. Deliver Response 1 (for older filter/query) AFTER Response 2 (for newer query): does stale data overwrite current UI/state?
3. Replay an identical webhook/retry payload after a client-side timeout while the first attempt already committed.
4. Run two parallel workers reading, appending, and rewriting the same JSON/index file without locking.

## Retire / Disproof Rule
Retire if mutations enforce idempotency keys/DB uniqueness, UI async state discards superseded responses via abort/monotonic request IDs, and concurrent writers serialize safely.

## Real Incident Anchor
Classic frontend search/tab race conditions display stale results over the user's latest selection; unguarded payment/order webhooks create duplicate charges on network timeouts.
