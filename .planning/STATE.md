---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: completed
stopped_at: Phase 2 context gathered (rework)
last_updated: "2026-03-26T22:35:29.805Z"
last_activity: "2026-03-26 -- Completed Plan 04-03 (Map overlays: polyline, stop markers, auto-fit, bus dimming)"
progress:
  total_phases: 6
  completed_phases: 3
  total_plans: 10
  completed_plans: 9
  percent: 90
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-03-25)

**Core value:** When a student pulls up the app, they see exactly where their bus is and when it arrives at their stop -- accurate to ~85 seconds -- with zero navigation complexity.
**Current focus:** Phase 4 complete. Ready for Phase 5: Animated Markers and Callout Bubbles

## Current Position

Phase: 4 of 6 (Route Detail and ETA Predictions) -- COMPLETE
Plan: 3 of 3 in current phase (all complete)
Status: Phase 4 complete, ready for Phase 5
Last activity: 2026-03-26 -- Completed Plan 04-03 (Map overlays: polyline, stop markers, auto-fit, bus dimming)

Progress: [█████████░] 90%

## Performance Metrics

**Velocity:**
- Total plans completed: 9
- Average duration: 3 min
- Total execution time: 0.52 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1. Foundation and Map Shell | 2/2 | 12 min | 6 min |
| 2. Real-Time Data Pipeline | 1/2 | 4 min | 4 min |
| 3. Bottom Sheet and Route List | 3/3 | 8 min | 3 min |
| 4. Route Detail and ETA Predictions | 3/3 | 7 min | 2 min |

**Recent Trend:**
- Last 5 plans: 2m, 2m, 3m, 2m, 2m
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
- [04-02]: Plain View mapping for stop list (4-15 stops per route, no FlatList overhead needed)
- [04-02]: ETA derived from vehiclePosition.nextStopId matching, reactive with 5s polling
- [04-02]: Instant content swap in bottom sheet (no animation) -- map polyline provides visual feedback
- [04-02]: hexToRgba exported from RouteCard for shared use in StopRow and RouteDetailView
- [04-03]: Marker with child View for stop dots (Circle uses meters, not pixels -- cannot produce fixed-pixel-size)
- [04-03]: Shadow polyline (9px navy-tinted) underneath main polyline (5px route color) for depth effect
- [04-03]: Auto-fit skips on deselect (selectedRouteId null) -- camera stays in place per user decision
- [04-03]: Stop centering uses animateToRegion with 0.008 delta for close zoom, 500ms animation

### Pending Todos

None yet.

### Blockers/Concerns

- [Phase 1]: Validate react-native-maps + Expo SDK 55 New Architecture compatibility immediately at project init
- [Phase 2]: Validate protobuf decoding in Hermes on both platforms before building data-dependent UI
- [Phase 4]: Confirm FastAPI /api/eta/predict request/response schema before building RTK Query integration

## Session Continuity

Last session: 2026-03-26T22:35:29.798Z
Stopped at: Phase 2 context gathered (rework)
Resume file: .planning/phases/02-real-time-data-pipeline/02-CONTEXT.md
