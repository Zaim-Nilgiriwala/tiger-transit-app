---
phase: 04-route-detail-and-eta-predictions
plan: 03
subsystem: ui
tags: [react-native-maps, polyline, markers, redux, map-overlay]

requires:
  - phase: 04-route-detail-and-eta-predictions
    provides: "GTFS stops, shapes, route-stop-sequences as TS constants + useStaticRouteData hook hydrating routesSlice"
provides:
  - "RouteOverlay component rendering polyline with shadow and stop markers inside MapView"
  - "Map auto-fit to show all stops + buses when route selected (MAP-07)"
  - "Stop-tap-to-center map animation on selectedStopId change (ROUTE-09)"
  - "Bus marker opacity dimming (30%) for non-selected routes"
affects: [phase-5-callout-bubbles, phase-5-animated-markers]

tech-stack:
  added: []
  patterns: [map-overlay-via-redux-children, marker-based-fixed-pixel-dots, fitToCoordinates-auto-fit]

key-files:
  created:
    - src/components/map/RouteOverlay.tsx
  modified:
    - src/components/map/BusMarker.tsx
    - src/screens/MapScreen.tsx

key-decisions:
  - "Marker-based stop dots instead of Circle (Circle uses meters not pixels, cannot produce fixed-pixel-size markers)"
  - "Shadow polyline (9px navy-tinted) underneath main polyline (5px route color) for depth effect"
  - "useEffect with selectedRouteId dependency for auto-fit; skips when null (camera stays on deselect)"
  - "Separate useEffect for selectedStopId to center map with 500ms animateToRegion"

patterns-established:
  - "Map overlay pattern: propless component inside MapView reads all state from Redux via useAppSelector"
  - "Bus dimming pattern: opacity prop on BusMarker computed inline from selectedRouteId comparison"
  - "Auto-fit pattern: fitToCoordinates with edgePadding accounting for bottom sheet at half position"

requirements-completed: [ROUTE-09, MAP-05, MAP-06, MAP-07]

duration: 2min
completed: 2026-03-26
---

# Phase 4 Plan 3: Map Overlays Summary

**Route polyline with shadow effect, stop dot markers (12px/20px focused), map auto-fit, stop-tap-to-center, and bus dimming for selected route**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T17:43:51Z
- **Completed:** 2026-03-26T17:46:36Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- RouteOverlay component renders shadow polyline + main polyline + stop markers as MapView children, all driven by Redux state
- Map auto-fits to show all stops and active buses when a route is selected, with edge padding accounting for the bottom sheet
- Stop-tap-to-center animates map to the tapped stop with a closer zoom level (0.008 delta)
- Non-selected route buses dim to 30% opacity; selected route buses at full; back button restores all

## Task Commits

Each task was committed atomically:

1. **Task 1: Create RouteOverlay component with polyline and stop circle markers** - `70cad27` (feat)
2. **Task 2: Wire RouteOverlay into MapScreen with auto-fit, stop centering, and bus dimming** - `fe0644f` (feat)

## Files Created/Modified

- `src/components/map/RouteOverlay.tsx` - New component: polyline (with shadow) + Marker-based stop dots, reads Redux state, returns null when no route selected
- `src/components/map/BusMarker.tsx` - Added optional `opacity` prop (default 1) for dimming non-selected route buses
- `src/screens/MapScreen.tsx` - Integrated RouteOverlay, auto-fit useEffect, stop-center useEffect, bus dimming via opacity prop

## Decisions Made

- Used Marker with child View for stop dots instead of Circle component, because Circle uses radius in meters (not pixels), making fixed-pixel-size markers impossible
- Shadow polyline rendered as a separate wider Polyline (9px, navy-tinted rgba) behind the main polyline (5px, route color) for the depth effect
- Auto-fit fires only when selectedRouteId changes to a non-null value; deselect (null) intentionally skips fit so camera stays in place per user decision
- Stop centering uses animateToRegion with 0.008 lat/lon delta for a closer zoom and 500ms duration for smooth animation

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Route polyline and stop markers now appear on map when route is selected, completing the spatial visualization
- Phase 5 (callout bubbles) can add onPress handlers to stop Markers and bus Markers to show glass-panel callouts
- Phase 5 (animated markers) can add Reanimated-based interpolation to BusMarker positions

## Self-Check: PASSED

All 3 files verified present. Both task commits (70cad27, fe0644f) verified in git log.

---
*Phase: 04-route-detail-and-eta-predictions*
*Completed: 2026-03-26*
