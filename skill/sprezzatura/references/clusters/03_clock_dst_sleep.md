---
id: clock-dst-sleep
name: DST Gaps, Clock Jumps & Laptop Sleep Spikes
category: time
---

## Hostile World-State
A machine in `America/New_York` during DST spring-forward (`02:00` skipped) and fall-back (`01:30` occurs twice), OR a laptop closed for 3 hours mid-session and reopened while an NTP step shifts the system wall clock backward by 60 seconds.

## Per-Stack Applicability
- **Applies:** Elapsed-time / timeout / rate-limit / game-loop `dt` math using wall-clock APIs (`DateTime.Now`, `Date.now()`, `time.time()`, `System.currentTimeMillis()`); naive `date + 86400s` "next day" arithmetic; local-time schedulers/cron without IANA TZ; un-clamped frame `deltaTime` after sleep/debugger pause.
- **Ignore/Safe:** Monotonic clocks (`time.monotonic()`, `performance.now()`, `Stopwatch`, `System.nanoTime()`, `Instant::now()`) used strictly for durations; pure UTC timestamps stored with explicit offset/Z and converted only at UI display.

## Seed Probes
1. Schedule or parse local wall time `02:30` on DST spring-forward day (nonexistent time) or `01:30` on fall-back day (ambiguous timestamp colliding with unique keys).
2. Subtract two wall-clock reads while NTP steps the clock backward by 30s (negative duration bypasses cooldown, locks retry loop, or fails assertion).
3. Suspend the OS for 3 hours and resume: observe un-clamped `dt = 10800s` tunneling physics, expiring all in-flight timers at once, or firing burst callbacks.
4. Assume every calendar day equals `86,400` seconds or hardcode a static region UTC offset (e.g., `Europe/Istanbul` pre/post-2016).

## Retire / Disproof Rule
Retire if elapsed durations exclusively use monotonic clocks with upper-bound clamping where relevant, and all persisted/scheduled instants use UTC or proper IANA TZDB conversion.

## Real Incident Anchor
Cloudflare's 2017 DNS outage crashed resolvers when Go's wall-clock subtraction returned a negative duration during a leap second; countless games tunnel entities through walls after Alt-Tab/sleep spikes.
