---
phase: 05-animated-markers-and-callout-bubbles
plan: 01
subsystem: ui
tags: [react-native-maps, animation, requestAnimationFrame, polyline, interpolation]

# Dependency graph
requires:
  - phase: 04-route-detail-and-eta-predictions
    provides: "Route shapes (polylines) in Redux state, BusMarker component, etaspotService"
provides:
  - "useAnimatedPosition hook for smooth polyline-path bus marker animation"
  - "polylineProjection.ts utilities (projectOntoPolyline, interpolateAlongPolyline, tangentAtPoint)"
  - "minutesToNextStops field on VehiclePosition for callout bubble display"
affects: [05-02-callout-bubbles, future-eta-display]

# Tech tracking
tech-stack:
  added: []
  patterns: [requestAnimationFrame animation loop, polyline projection, playback buffer interpolation]

key-files:
  created:
    - src/hooks/useAnimatedPosition.ts
    - src/utils/polylineProjection.ts
  modified:
    - src/types/gtfs.types.ts
    - src/services/etaspotService.ts
    - src/components/map/BusMarker.tsx
    - src/screens/MapScreen.tsx
    - src/hooks/useVehicleSubscription.ts

key-decisions:
  - "requestAnimationFrame over Reanimated for Marker coordinate animation (Marker.coordinate is a plain object, not an Animated.Value)"
  - "Euclidean distance for polyline projection (adequate for campus-scale distances)"
  - "30s gap threshold for fallback 1s animation on missed position updates"
  - "tracksViewChanges toggled true only during active animation frames for GPU savings"

patterns-established:
  - "Playback buffer interpolation: animate from previous to current position along polyline path"
  - "Polyline projection: snap GPS positions to nearest road segment for path-following animation"
  - "rAF loop with clamped time parameter for frame-independent animation"

requirements-completed: [MAP-03, ETA-01]

# Metrics
duration: 3min
completed: 2026-03-28
---

# Phase 5 Plan 1: Animated Markers Summary

**Smooth polyline-path bus animation via rAF playback buffer with road-hugging heading rotation and minutesToNextStops data pipeline**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-28T00:38:17Z
- **Completed:** 2026-03-28T00:41:36Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Bus markers animate smoothly along route polylines between 10s position updates with no visible jumps
- Heading rotates naturally through road curves via polyline tangent computation
- minutesToNextStops array surfaced from PHP API into VehiclePosition for callout bubble display
- tracksViewChanges toggles on/off during animation to minimize GPU overhead

## Task Commits

Each task was committed atomically:

1. **Task 1: Surface minutesToNextStops and create polyline projection utilities** - `e692a86` (feat)
2. **Task 2: Create useAnimatedPosition hook and refactor BusMarker** - `ca401b5` (feat)

## Files Created/Modified
- `src/hooks/useAnimatedPosition.ts` - Playback buffer interpolation hook with rAF animation loop
- `src/utils/polylineProjection.ts` - Pure math: projectOntoPolyline, interpolateAlongPolyline, tangentAtPoint
- `src/types/gtfs.types.ts` - Added minutesToNextStops field to VehiclePosition interface
- `src/services/etaspotService.ts` - Maps PHP minutesToNextStops array into VehiclePosition
- `src/components/map/BusMarker.tsx` - Uses animated position/heading, toggles tracksViewChanges
- `src/screens/MapScreen.tsx` - Passes routeShape from Redux to each BusMarker
- `src/hooks/useVehicleSubscription.ts` - Default minutesToNextStops to [] in Supabase mapper

## Decisions Made
- Used requestAnimationFrame instead of Reanimated because react-native-maps Marker coordinate is a plain object prop, not an Animated.Value -- rAF with setState is the correct pattern
- Euclidean math for polyline projection (not Haversine) -- campus-scale distances make Earth curvature negligible
- 30-second gap threshold: if two consecutive positions are >30s apart, fall back to a simple 1s lerp rather than ultra-slow crawl animation
- tracksViewChanges set to true only during active animation frames -- false when settled saves significant GPU on iOS/Android native map rendering

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Added minutesToNextStops default in useVehicleSubscription mapper**
- **Found during:** Task 1 (extending VehiclePosition type)
- **Issue:** The Supabase Realtime vehicle mapper (`mapRowToVehiclePosition`) constructs VehiclePosition objects but didn't include the new required `minutesToNextStops` field, causing a type error
- **Fix:** Added `minutesToNextStops: []` default to the mapper (Supabase DB doesn't have this field)
- **Files modified:** src/hooks/useVehicleSubscription.ts
- **Verification:** `npx tsc --noEmit` passes
- **Committed in:** e692a86 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Type error fix required for compilation. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Animated markers operational -- buses follow polyline paths with smooth interpolation
- minutesToNextStops data available for Plan 05-02 callout bubble display
- tracksViewChanges performance pattern established for any future animated map elements

---
*Phase: 05-animated-markers-and-callout-bubbles*
*Completed: 2026-03-28*
