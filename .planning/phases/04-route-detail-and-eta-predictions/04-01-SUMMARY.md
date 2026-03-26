---
phase: 04-route-detail-and-eta-predictions
plan: 01
subsystem: data
tags: [gtfs, typescript, redux, fastapi, static-data]

requires:
  - phase: 01-data-foundation
    provides: "Route list (ROUTES), gtfs.types.ts (Stop, Coordinate), routesSlice, useStaticData pattern"
provides:
  - "179 GTFS stops as typed Stop[] constant with O(1) lookup map (STOPS_BY_ID)"
  - "130 GTFS shapes as Record<string, Coordinate[]> grouped by shape_id"
  - "39 route-to-stop-sequence mappings (ROUTE_STOP_SEQUENCE, ROUTE_SHAPE_ID)"
  - "useStaticRouteData hook hydrating routesSlice.stops and routesSlice.shapes"
  - "POST /api/eta/predict-route batch ETA endpoint stub with typed request/response contract"
affects: [04-02-route-detail-view, 04-03-map-overlays, phase-5-eta-integration]

tech-stack:
  added: []
  patterns: [gtfs-csv-to-ts-generator, static-data-bundling, batch-prediction-stub]

key-files:
  created:
    - src/data/stops.ts
    - src/data/shapes.ts
    - src/data/routeStops.ts
    - src/hooks/useStaticRouteData.ts
    - scripts/generate-gtfs-data.js
  modified:
    - ETA-Model/api/server.py

key-decisions:
  - "Generator script approach: Node.js script parses GTFS CSVs and produces hardcoded TS constants (same pattern as routes.ts)"
  - "STOPS_BY_ID as Record<string, Stop> for O(1) stop lookup by ID in hook and future components"
  - "First-encountered trip used as canonical stop sequence per route (consistent with GTFS convention)"
  - "Batch ETA endpoint returns stub with source='stub' field for clear model/stub distinction"

patterns-established:
  - "GTFS data bundling: parse CSV with generator script, export typed constants, import synchronously"
  - "Route data hydration: useStaticRouteData hook dispatches stops + shapes per route on mount"

requirements-completed: [ETA-02, ETA-04]

duration: 3min
completed: 2026-03-26
---

# Phase 4 Plan 1: GTFS Static Data Foundation Summary

**179 GTFS stops, 130 shape polylines, and 39 route-stop-sequences bundled as TypeScript constants with Redux hydration hook and FastAPI batch ETA endpoint stub**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-26T17:37:41Z
- **Completed:** 2026-03-26T17:40:41Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- All GTFS static data (stops, shapes, route-stop-sequences) bundled as typed TypeScript constants matching existing routes.ts pattern
- useStaticRouteData hook hydrates Redux routesSlice.stops and routesSlice.shapes for all 39 routes on mount
- POST /api/eta/predict-route endpoint scaffolded with clear BatchPredictionRequest/Response contract for future model integration
- Generator script (scripts/generate-gtfs-data.js) created for future GTFS data updates

## Task Commits

Each task was committed atomically:

1. **Task 1: Bundle GTFS stops, shapes, and route-stop-sequence data as TypeScript constants** - `3501638` (feat)
2. **Task 2: Create useStaticRouteData hook and add batch ETA endpoint stub** - `3efd582` (feat)

## Files Created/Modified

- `src/data/stops.ts` - 179 GTFS stops as Stop[] with STOPS_BY_ID Record lookup
- `src/data/shapes.ts` - 130 shapes grouped by shape_id as Record<string, Coordinate[]>
- `src/data/routeStops.ts` - ROUTE_STOP_SEQUENCE (routeId -> stopId[]) and ROUTE_SHAPE_ID (routeId -> shapeId)
- `src/hooks/useStaticRouteData.ts` - Hook hydrating routesSlice.stops and routesSlice.shapes on mount
- `scripts/generate-gtfs-data.js` - One-time CSV-to-TS generator for GTFS data updates
- `ETA-Model/api/server.py` - Added POST /api/eta/predict-route batch prediction endpoint stub

## Decisions Made

- Used generator script approach (Node.js parsing CSVs to produce hardcoded TS) matching the existing routes.ts pattern for consistency
- STOPS_BY_ID exported as Record<string, Stop> for O(1) lookup rather than array searching
- First-encountered trip used as canonical stop sequence per route (GTFS convention for representative trip)
- Batch ETA endpoint returns `source: "stub"` field so clients can distinguish stub vs model predictions

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Route Detail View (04-02) can now consume stops and shapes from Redux via routesSlice.stops[routeId] and routesSlice.shapes[routeId]
- Map overlays can render route polylines from SHAPES data
- ETA integration can call POST /api/eta/predict-route once models are trained and deployed

## Self-Check: PASSED

All 6 files verified present. Both task commits (3501638, 3efd582) verified in git log.

---
*Phase: 04-route-detail-and-eta-predictions*
*Completed: 2026-03-26*
