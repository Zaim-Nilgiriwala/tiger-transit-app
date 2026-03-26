---
phase: 2
slug: real-time-data-pipeline
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-26
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None currently configured (Wave 0 installs Jest for unit tests) |
| **Config file** | None -- Wave 0 installs |
| **Quick run command** | `npx jest --testPathPattern=supabase` |
| **Full suite command** | `npx jest` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Manual verification (Edge Function curl + app visual check)
- **After every plan wave:** Full manual test pass (background/foreground, marker rendering, data freshness)
- **Before `/gsd:verify-work`:** Full suite must be green + manual visual confirmation
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | DATA-01 | integration | `curl` Edge Function, verify DB rows | No -- Wave 0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DATA-06 | unit | Test ROUTE_ID_MAP transform | No -- Wave 0 | ⬜ pending |
| 02-01-03 | 01 | 1 | MAP-09 | unit | Test stale filter logic in Edge Function | No -- Wave 0 | ⬜ pending |
| 02-01-04 | 01 | 1 | DATA-07 | integration | Verify position_history after Edge Function run | No -- Wave 0 | ⬜ pending |
| 02-02-01 | 02 | 1 | DATA-02 | manual-only | Run app, observe markers update | N/A | ⬜ pending |
| 02-02-02 | 02 | 1 | DATA-03 | manual-only | Background/foreground app, observe | N/A | ⬜ pending |
| 02-02-03 | 02 | 1 | DATA-04 | unit | Verify Edge Function transform output | No -- Wave 0 | ⬜ pending |
| 02-02-04 | 02 | 1 | MAP-02 | manual-only | Visual verification on device | N/A | ⬜ pending |
| 02-02-05 | 02 | 1 | MAP-04 | manual-only | Visual verification | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Install Jest test framework for unit tests of transform/mapping logic
- [ ] Edge Function testing setup: `supabase functions serve` locally
- [ ] Test stubs for route ID mapping transform (DATA-06)
- [ ] Test stubs for stale vehicle filtering (MAP-09)
- [ ] Test stubs for minutesToNextStops transform (DATA-04)

*Most phase requirements are integration/manual-only due to the distributed nature: Edge Function -> Database -> Realtime -> Client*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Client receives vehicle updates via Realtime within 5s | DATA-02 | Requires live Supabase Realtime WebSocket | Run app, select route, verify markers appear and update |
| Subscription pauses/resumes with AppState | DATA-03 | Requires physical device background/foreground | Background app for 10s, foreground, verify markers resume |
| Bus markers render from Supabase-sourced positions | MAP-02 | Visual verification on device | Select route on map, verify bus markers at correct positions |
| Heading from PHP 'h' field renders directional marker | MAP-04 | Visual verification | Observe bus markers show correct directional rotation |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
