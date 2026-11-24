---
id: network-hostile
name: Missing Timeouts, Half-Open Sockets & Retry Storms
category: network
---

## Hostile World-State
A remote peer accepts TCP connect and then never sends a byte (blackhole), Wi-Fi drops mid-download and returns 10 seconds later, or an upstream returns HTTP `429`/`503` with an HTML error page instead of JSON.

## Per-Stack Applicability
- **Applies:** Python `requests.get/post` or `urllib.request.urlopen` without explicit `timeout=`; Node `fetch` / `http.request` without `AbortSignal.timeout`; C# `HttpClient` created per-request (socket exhaustion) or infinite timeout; retry loops without exponential backoff + jitter + max attempts; callers parsing `resp.json()` without checking `status_code` / `Content-Type`; unbounded response body reads.
- **Ignore/Safe:** Pure offline/local code with zero network/IPC calls; shared `HttpClient`/session configured with connect+read timeouts, bounded retries with jitter, and status checks before body parsing.

## Seed Probes
1. Peer accepts TCP handshake and hangs forever: does the call block a worker thread/event loop indefinitely due to missing timeout?
2. Upstream returns HTTP `502 Bad Gateway` with `<html>...` body (or truncated JSON mid-stream): does the caller throw an unhandled parse error or swallow failure silently?
3. Connection drops on 100 concurrent clients simultaneously: do immediate fixed-interval retries without jitter trigger a thundering herd?
4. Caller creates a fresh `HttpClient` / TCP pool inside a loop without reuse or disposal.

## Retire / Disproof Rule
Retire if the scope makes no network/IPC calls, or every outbound client enforces explicit connect/read timeouts, status validation, bounded body size, and capped jittered backoff.

## Real Incident Anchor
Python `requests.get(url)` defaults to `timeout=None` (wait forever), routinely hanging production workers and CI agents indefinitely on stalled upstream sockets.
