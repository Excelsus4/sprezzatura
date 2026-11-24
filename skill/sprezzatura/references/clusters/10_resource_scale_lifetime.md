---
id: resource-scale-lifetime
name: Empty/100x Scale Cliffs & 72-Hour Resource Leaks
category: lifecycle
---

## Hostile World-State
Input contains `0` items, `1` item, or `100×` typical volume (all duplicates or 50MB single payload), and the long-running process/UI stays open continuously for 72 hours without restart.

## Per-Stack Applicability
- **Applies:** Nested loops / repeated string concatenation / linear `in list` inside loops (`O(n²)` Shlemiel patterns); unbounded in-memory caches/maps/logs growing forever; unclosed file handles, DB connections, subprocesses, or streams on early exception paths; UI/game event listeners, timers, or GPU/texture buffers subscribed without matching unsubscribe/dispose; missing pagination/streaming on unbounded lists.
- **Ignore/Safe:** Bounded `with`/`using`/`try-finally` resource scopes; `O(n)` hash-set lookups; LRU/TTL-bounded caches; one-shot short-lived CLI scripts with bounded small inputs.

## Seed Probes
1. Feed `0` items, `1` item, and `100,000` identical items: check empty-collection crashes (`items[0]`, `max([])`) and `O(n²)` stalls.
2. Throw an exception halfway through a resource-acquiring function: are files, locks, sockets, or child processes leaked?
3. Open and close a view/scene/session 1,000 times over 72 hours: do event listeners, intervals, or unbounded dicts accumulate?
4. Pass a 100MB input file/payload to a routine reading the entire stream into memory at once (`read()` / `ReadAllBytes`).

## Retire / Disproof Rule
Retire if collection boundaries are guarded, algorithmic complexity is linear/log-linear on attacker/user-controlled sizes, caches are bounded, and all handles/listeners pair with deterministic cleanup.

## Real Incident Anchor
"Shlemiel the Painter" `O(n²)` string/array rebuilds pass unit tests on 20 items and freeze production at 20,000; leaked UI event subscriptions silently bleed RAM over multi-hour sessions.
