---
phase: 04-route-detail-and-eta-predictions
plan: 02
subsystem: ui
tags: [route-detail, stop-list, eta, transit-diagram, bottom-sheet]

requires:
  - phase: 04-route-detail-and-eta-predictions
    plan: 01
    provides: "GTFS stops in routesSlice.stops[routeId], useStaticRouteData hook"
provides:
  - "RouteDetailView component with sticky header, transit diagram stop list, and live ETAs"
  - "StopRow component with numbered route-colored indicators and connecting line"
  - "RouteCard onPress -> selectRoute dispatch for content swap"
  - "hexToRgba exported from RouteCard for shared use"
affects: [05-animated-markers, 06-favorites-alerts]

tech-stack:
  added: []
  patterns: [transit-diagram-ui, eta-derivation-from-gtfs-rt, conditional-content-swap]

key-files:
  created:
    - src/components/sheet/RouteDetailView.tsx
    - src/components/sheet/StopRow.tsx
  modified:
    - src/components/sheet/RouteCard.tsx
    - src/components/sheet/RouteList.tsx

key-decisions:
  - "Plain View mapping instead of FlatList for stop list (stop counts are small, typically 4-15 per route)"
  - "ETA derived from vehiclePosition.nextStopId matching — recomputes reactively with 5s polling cycle"
  - "Instant content swap (no animation) — map polyline appearing provides visual transition feedback"
  - "hexToRgba exported from RouteCard rather than duplicated, since it is a small pure function"
  - "Stop tap toggles selection (tap again to deselect) for intuitive interaction"

patterns-established:
  - "Transit diagram pattern: numbered circles with connecting lines via absolute-positioned views"
  - "ETA formatting: < 60s -> '< 1 min', >= 60s -> 'N min', no vehicles -> 'No buses en route'"
  - "Content swap in bottom sheet: conditional render based on Redux selectedRouteId"

requirements-completed: [ROUTE-05, ROUTE-06, ROUTE-07, ROUTE-08, ROUTE-10, ETA-03]

duration: 2min
completed: 2026-03-26
---

# Phase 4 Plan 2: Route Detail View and ETA Display Summary

**Route Detail View with transit-diagram stop list and GTFS-RT-derived ETAs, wired into bottom sheet via RouteCard onPress content swap**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T17:43:57Z
- **Completed:** 2026-03-26T17:46:48Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- RouteDetailView component with sticky header (route name in 32pt headlineLG, 4px color stripe, tinted background, back arrow, favorite star)
- StopRow component with numbered route-colored circular indicators and 2px vertical connecting line creating transit diagram
- ETA derivation logic matching vehicles by nextStopId, formatted as "3 min", "< 1 min", or "No buses en route" with middle dot separators
- RouteCard onPress dispatches selectRoute to swap bottom sheet content from route list to route detail
- Back button clears both route and stop selection, returning to route list

## Task Commits

Each task was committed atomically:

1. **Task 1: Build RouteDetailView and StopRow components** - `9a8efdb` (feat)
2. **Task 2: Wire RouteCard onPress and integrate RouteDetailView into RouteList** - `884d470` (feat)

## Files Created/Modified

- `src/components/sheet/RouteDetailView.tsx` - Route detail with sticky header, stop list, ETA derivation (new)
- `src/components/sheet/StopRow.tsx` - Transit diagram stop row with sequence indicator and ETA text (new)
- `src/components/sheet/RouteCard.tsx` - Exported hexToRgba for shared use (modified)
- `src/components/sheet/RouteList.tsx` - Added RouteCard onPress wiring and conditional RouteDetailView rendering (modified)

## Decisions Made

- Used plain View mapping instead of FlatList for stop list since stop counts are small (4-15 per route)
- ETAs derived from vehiclePosition.nextStopId matching, naturally refreshing with existing 5s polling cycle
- Instant content swap (no animation) for simplicity -- the map polyline and stop markers appearing simultaneously provides visual feedback
- Exported hexToRgba from RouteCard rather than duplicating it
- Stop tap toggles selection (tap same stop again to deselect)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Route Detail View is fully functional and wired into the bottom sheet
- Map overlays (polylines + stop markers) can be added in Plan 04-03 to complete the route selection experience
- ETA predictions from the ML model can replace stub data when Phase 5 integrates the trained model

## Self-Check: PASSED

All 4 files verified present. Both task commits (9a8efdb, 884d470) verified in git log.

---
*Phase: 04-route-detail-and-eta-predictions*
*Completed: 2026-03-26*
