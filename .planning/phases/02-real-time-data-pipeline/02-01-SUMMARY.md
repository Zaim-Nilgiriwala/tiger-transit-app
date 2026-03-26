---
phase: 02-real-time-data-pipeline
plan: 01
subsystem: data
tags: [gtfs-rt, protobufjs, polling, appstate, redux, real-time, hermes]

# Dependency graph
requires:
  - phase: 01-foundation-and-map-shell
    provides: Redux store with vehiclesSlice and routesSlice, VehiclePosition and Route type interfaces
provides:
  - GTFS-RT protobuf decode service (fetchAndDecodeFeeds) with trip update enrichment and stale filtering
  - 5-second polling hook (useGtfsPolling) with AppState foreground/background awareness
  - Bundled static route data (39 routes) as typed TypeScript constant
  - Feed configuration constants (URLs, poll interval, stale threshold)
  - Static data hook (useStaticData) to hydrate routesSlice on mount
affects: [02-02, 03-01, 03-02, 04-01, 05-01, 06-01]

# Tech tracking
tech-stack:
  added: [protobufjs]
  patterns: [protobuf-json-descriptor, appstate-polling-lifecycle, stale-vehicle-filtering, trip-before-position-processing]

key-files:
  created:
    - src/config/feeds.ts
    - src/data/routes.ts
    - src/services/gtfsRealtimeService.ts
    - src/hooks/useGtfsPolling.ts
    - src/hooks/useStaticData.ts
  modified:
    - package.json
    - package-lock.json

key-decisions:
  - "Used protobufjs with Root.fromJSON() embedded descriptor instead of gtfs-realtime-bindings (avoids CommonJS require() and eval() issues on Hermes)"
  - "Embedded minimal GTFS-RT proto definition as JSON descriptor rather than loading .proto file at runtime"
  - "Store access via store.getState() in AppState resume handler to avoid stale closure over positions"

patterns-established:
  - "Protobuf JSON descriptor: Embed proto definitions as INamespace objects for Root.fromJSON() -- Hermes-safe, no eval"
  - "AppState polling lifecycle: start on mount, stop on background, resume+stale-clear on foreground"
  - "Trip-before-position processing: always decode trip updates first so ETA enrichment is available for position mapping"
  - "Silent failure polling: failed polls set connected=false but never throw to consumer"

requirements-completed: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, MAP-09]

# Metrics
duration: 4min
completed: 2026-03-26
---

# Phase 2 Plan 01: GTFS-RT Protobuf Decode Service and Polling Hook Summary

**GTFS-RT protobuf decoding via protobufjs with embedded JSON descriptor, 5s polling with AppState foreground/background lifecycle, 39 bundled static routes, and stale vehicle filtering at 2-minute threshold**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-26T00:03:50Z
- **Completed:** 2026-03-26T00:07:42Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- GTFS-RT protobuf decode service with embedded JSON proto descriptor using protobufjs Root.fromJSON() -- Hermes-safe, no eval(), no CommonJS require()
- Trip updates processed before position updates so ETA enrichment (nextStopId, etaSeconds, delay/onTime) is available when mapping vehicle positions
- 5-second polling hook with AppState awareness: pauses on background, resumes on foreground with immediate stale vehicle clearing
- All 39 Tiger Transit routes bundled as typed TypeScript constant from GTFS routes.txt with '#'-prefixed routeColor values
- useStaticData hook for one-shot dispatch of static route data into Redux routesSlice

## Task Commits

Each task was committed atomically:

1. **Task 1: Create feed config, bundled static routes, and GTFS-RT decode service** - `565ad63` (feat)
2. **Task 2: Create polling hook with AppState awareness and wire static routes into Redux** - `77f3f35` (feat)

## Files Created/Modified
- `src/config/feeds.ts` - Feed URL constants, poll interval (5s), stale threshold (2min)
- `src/data/routes.ts` - All 39 Tiger Transit routes as typed Route[] constant
- `src/services/gtfsRealtimeService.ts` - fetchAndDecodeFeeds() with protobuf decode, trip update processing, position mapping, stale filtering
- `src/hooks/useGtfsPolling.ts` - Polling hook with setInterval lifecycle, AppState listener, stale clearing on resume
- `src/hooks/useStaticData.ts` - One-shot hook to dispatch ROUTES into routesSlice
- `package.json` - Added protobufjs dependency
- `package-lock.json` - Lock file updated with protobufjs and its 12 transitive dependencies

## Decisions Made
- Used protobufjs with Root.fromJSON() and an embedded GTFS-RT proto descriptor instead of gtfs-realtime-bindings -- avoids CommonJS require() which breaks Metro/Hermes, and avoids eval() which Hermes CSP can block
- Embedded only the minimal GTFS-RT types needed (FeedMessage, FeedEntity, VehiclePosition, TripUpdate, etc.) as a JSON INamespace object rather than loading a .proto file at runtime
- Used direct store.getState() access in the AppState resume handler to read current positions for stale filtering, avoiding stale closure issues with useCallback

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required. The S3 GTFS-RT feeds are publicly accessible.

## Next Phase Readiness
- fetchAndDecodeFeeds() is ready for useGtfsPolling to call every 5 seconds
- useGtfsPolling and useStaticData hooks are ready to mount in MapScreen (Plan 02-02)
- ROUTES data is ready for route-colored bus markers in Plan 02-02
- vehiclesSlice.positions will be populated with live VehiclePosition[] once polling starts
- Protobuf decoding on Hermes should be validated on-device in Plan 02-02 integration

## Self-Check: PASSED

All 5 created files verified on disk. Both task commits (565ad63, 77f3f35) verified in git log.

---
*Phase: 02-real-time-data-pipeline*
*Completed: 2026-03-26*
