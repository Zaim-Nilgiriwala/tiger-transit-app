---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: in-progress
stopped_at: Completed 04-01 GTFS static data foundation
last_updated: "2026-03-26T17:40:41Z"
last_activity: "2026-03-26 -- Completed Plan 04-01 (GTFS stops, shapes, route-stop-sequences as TS constants + useStaticRouteData hook + batch ETA endpoint stub)"
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 10
  completed_plans: 7
  percent: 70
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** When a student pulls up the app, they see exactly where their bus is and when it arrives at their stop -- accurate to ~85 seconds -- with zero navigation complexity.
**Current focus:** Phase 4: Route Detail and ETA Predictions -- Plan 01 complete, Plan 02 next

## Current Position

Phase: 4 of 6 (Route Detail and ETA Predictions)
Plan: 1 of 2 in current phase
Status: Plan 04-01 complete, ready for Plan 04-02
Last activity: 2026-03-26 -- Completed Plan 04-01 (GTFS static data foundation)

Progress: [███████░░░] 70%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 4 min
- Total execution time: 0.45 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation and Map Shell | 2/2 | 12 min | 6 min |
| 2. Real-Time Data Pipeline | 1/2 | 4 min | 4 min |
| 3. Bottom Sheet and Route List | 3/3 | 8 min | 3 min |
| 4. Route Detail and ETA Predictions | 1/2 | 3 min | 3 min |

**Recent Trend:**
- Last 5 plans: 4m, 4m, 2m, 2m, 3m
- Trend: Stable (fast)

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 6-phase structure derived from 62 requirements; risk-first ordering (maps, then protobuf, then UI layers)
- [Roadmap]: Animated markers isolated to Phase 5 to contain Android bitmap rendering risk
- [Roadmap]: Design system tokens built in Phase 1 so all subsequent phases inherit the Academic Navigator look
- [01-01]: Used @expo-google-fonts packages instead of manual TTF downloads for reliable font loading
- [01-01]: Excluded pre-existing Code/, ETA-Model/, scripts/ directories from tsconfig to isolate RN project
- [01-01]: Font family keys use expo-google-fonts naming convention (Manrope_700Bold) for direct compatibility
- [01-01]: Shadow shadowColor uses rgba(12, 35, 64, 1) with separate shadowOpacity for cross-platform behavior
- [Phase 01-02]: MapView uses default provider (Apple Maps iOS, Google Maps Android) -- no explicit provider prop
- [Phase 01-02]: GlassBottomBar built as self-contained component for Phase 3 drag/snap wrapping
- [Phase 01-02]: BlurView with rgba background fallback for glassmorphism on both platforms
- [Phase 01-02]: Location button is no-op when permission denied, matching silent-denial UX pattern
- [02-01]: Used protobufjs with Root.fromJSON() embedded descriptor instead of gtfs-realtime-bindings (Hermes-safe, no eval/require)
- [02-01]: Embedded minimal GTFS-RT proto definition as JSON INamespace rather than loading .proto file at runtime
- [02-01]: Store access via store.getState() in AppState resume handler to avoid stale closure over positions
- [03-01]: GestureHandlerRootView added to App.tsx root for global gesture support
- [03-01]: ScrollView enabled/disabled via React state synced from spring settle callback
- [03-01]: Spring config: damping 20, stiffness 150 for responsive but controlled snap feel
- [03-01]: Velocity projection factor 0.15 for natural fling-to-snap behavior
- [03-02]: hexToRgba helper converts route color to 6% opacity tint for card background
- [03-02]: React.memo on RouteCard to prevent re-renders during 5s polling updates
- [03-02]: gap property on cardList container for spacing instead of marginBottom on each card
- [04-01]: Generator script approach for GTFS CSV-to-TS conversion (Node.js parses CSVs, produces hardcoded constants)
- [04-01]: STOPS_BY_ID as Record<string, Stop> for O(1) stop lookup by ID
- [04-01]: First-encountered trip used as canonical stop sequence per route
- [04-01]: Batch ETA endpoint returns source="stub" for clear model/stub distinction

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Validate react-native-maps + Expo SDK 55 New Architecture compatibility immediately at project init
- [Phase 2]: Validate protobuf decoding in Hermes on both platforms before building data-dependent UI
- [Phase 4]: Confirm FastAPI /api/eta/predict request/response schema before building RTK Query integration

## Session Continuity

Last session: 2026-03-26T17:40:41Z
Stopped at: Completed 04-01-PLAN.md
Resume file: .planning/phases/04-route-detail-and-eta-predictions/04-01-SUMMARY.md
