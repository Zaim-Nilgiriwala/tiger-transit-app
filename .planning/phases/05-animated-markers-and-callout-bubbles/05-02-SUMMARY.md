---
phase: 05-animated-markers-and-callout-bubbles
plan: 02
subsystem: ui
tags: [react-native-maps, callout, glassmorphism, expo-blur, overlay, marker-interaction]

# Dependency graph
requires:
  - phase: 05-animated-markers-and-callout-bubbles
    provides: "Animated bus markers with minutesToNextStops data, polyline projection utilities"
  - phase: 04-route-detail-and-eta-predictions
    provides: "STOPS_BY_ID, ROUTE_STOP_SEQUENCE, etaspotService, route shapes"
provides:
  - "CalloutBubble glassmorphic overlay component with auto-positioning and animation"
  - "BusCalloutContent showing route, passengers, delay status, next 3 stop ETAs"
  - "StopCalloutContent showing stop name, all-route ETAs, route badges, View More"
  - "Marker onPress -> callout system with single-callout enforcement and dismiss behavior"
affects: [06-polish, future-stop-detail]

# Tech tracking
tech-stack:
  added: []
  patterns: [pointForCoordinate screen-space positioning, overlay outside MapView, onTouchStart callout dismiss]

key-files:
  created:
    - src/components/map/CalloutBubble.tsx
    - src/components/map/BusCalloutContent.tsx
    - src/components/map/StopCalloutContent.tsx
  modified:
    - src/screens/MapScreen.tsx
    - src/components/map/BusMarker.tsx
    - src/components/map/RouteOverlay.tsx
    - src/components/sheet/BottomSheet.tsx

key-decisions:
  - "Custom overlay outside MapView instead of native Callout for full glassmorphism and content control"
  - "pointForCoordinate async call to convert marker lat/lon to screen coordinates for overlay positioning"
  - "Callout repositions on onRegionChangeComplete to follow marker during map pan"
  - "BottomSheet onTouchStart prop for callout dismiss integration without breaking gesture handler"
  - "Hardcoded 50px safe area top inset to avoid adding react-native-safe-area-context dependency"

patterns-established:
  - "Screen-space overlay: render outside MapView, position via pointForCoordinate, update on region change"
  - "Single-callout enforcement: Redux activeCallout state drives which callout to show, clearCallout on dismiss"
  - "BusMarker highlight: isHighlighted prop scales to 1.2x with glow ring via increased shadow"

requirements-completed: [CALL-01, CALL-02, CALL-03, CALL-04, CALL-05]

# Metrics
duration: 4min
completed: 2026-03-28
---

# Phase 5 Plan 2: Callout Bubbles Summary

**Glassmorphic callout overlay system with bus/stop content, single-callout enforcement, screen-space positioning, and automatic data refresh**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-28T00:45:34Z
- **Completed:** 2026-03-28T00:50:17Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- Tapping a bus marker opens a glass-panel callout showing route name, passenger capacity bar, delay status pill, and next 3 stop ETAs
- Tapping a stop marker opens a glass-panel callout showing stop name, ETAs for all routes serving that stop, route color badges, and View More (coming soon) link
- Only one callout open at a time; tapping another marker swaps, tapping map/sheet dismisses
- Callout repositions on map pan via onRegionChangeComplete + pointForCoordinate
- Tapped bus marker scales to 1.2x with glow ring highlight while callout is open
- Callout data refreshes automatically with each 10s poll cycle via Redux re-render

## Task Commits

Each task was committed atomically:

1. **Task 1: Create CalloutBubble container and bus/stop content components** - `b5671ba` (feat)
2. **Task 2: Wire callouts into MapScreen with marker onPress, dismiss, and highlight** - `3a24727` (feat)

## Files Created/Modified
- `src/components/map/CalloutBubble.tsx` - Glassmorphic overlay with triangle pointer, auto-flip positioning, scale+fade animation
- `src/components/map/BusCalloutContent.tsx` - Bus callout inner content (route name, capacity bar, delay pill, next 3 stops)
- `src/components/map/StopCalloutContent.tsx` - Stop callout inner content (stop name, multi-route ETAs, route badges, View More toast)
- `src/screens/MapScreen.tsx` - Callout state management, marker press handlers, pointForCoordinate positioning, dismiss behavior
- `src/components/map/BusMarker.tsx` - Added onPress and isHighlighted props (1.2x scale + glow ring)
- `src/components/map/RouteOverlay.tsx` - Added onStopPress prop passed through to stop markers
- `src/components/sheet/BottomSheet.tsx` - Added onTouchStart prop for callout dismiss integration

## Decisions Made
- Used custom overlay outside MapView instead of native Callout component for full control over glassmorphism, animations, and content layout
- pointForCoordinate (async) converts marker lat/lon to screen coordinates for absolute overlay positioning
- Callout repositions on onRegionChangeComplete to follow its marker when the map pans
- BottomSheet accepts onTouchStart prop to dismiss callout without wrapping in additional View (which would break absolute positioning)
- Hardcoded 50px safe area top inset rather than adding react-native-safe-area-context dependency

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] BottomSheet onTouchStart prop instead of View wrapper**
- **Found during:** Task 2 (wiring dismiss behavior)
- **Issue:** Plan suggested wrapping BottomSheet in a View with onTouchStart, but BottomSheet is absolutely positioned so wrapping in a plain View breaks layout
- **Fix:** Added onTouchStart prop to BottomSheet component and wired it to the Animated.View container
- **Files modified:** src/components/sheet/BottomSheet.tsx
- **Verification:** `npx tsc --noEmit` passes, BottomSheet retains absolute positioning
- **Committed in:** 3a24727 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Layout fix required to avoid breaking BottomSheet absolute positioning. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 5 CALL requirements complete -- callout bubbles fully operational
- Phase 5 (Animated Markers and Callout Bubbles) is now complete
- Ready for Phase 6 polish or any future stop detail expansion

---
*Phase: 05-animated-markers-and-callout-bubbles*
*Completed: 2026-03-28*

## Self-Check: PASSED

All 3 created files verified present. Both task commits (b5671ba, 3a24727) verified in git log.
