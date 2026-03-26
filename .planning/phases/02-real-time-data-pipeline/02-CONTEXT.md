# Phase 2: Real-Time Data Pipeline (REWORK) - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the client-side GTFS-RT protobuf pipeline with an ETASpot PHP API data source proxied through Supabase. Backend polls ETASpot `get_vehicles` every 5s, deduplicates positions, writes to Supabase DB. Client subscribes to Supabase Realtime for live vehicle updates. No ETA predictions in this phase (model not trained yet) — ETA fields are empty/null. Protobuf code archived (not deleted). Alerts feed (protobuf) deferred to Phase 6.

</domain>

<decisions>
## Implementation Decisions

### Data source
- Primary source: ETASpot PHP API `get_vehicles` endpoint (`auburn.etaspot.net/service.php?service=get_vehicles&includeETAData=1&inService=1&orderedETAArray=1&token=TESTING`)
- PHP provides: lat, lng, heading (`h`), load, capacity, onSchedule (delay seconds), receiveTime, nextStopID, lastStopID, routeID, equipmentID, direction
- ETASpot's `minutesToNextStops` ETAs are NOT used — all ETAs will come from the XGBoost model (future phase). PHP ETAs are garbage.
- Route ID mapping needed for 3 compound IDs: 215→215_202_201_156, 226→226_32, 235→235_93
- Speed/velocity is NOT in the PHP response — must be derived from position history

### Supabase integration (client side)
- Supabase Realtime WebSocket subscription — client subscribes to `vehicles` table changes, no client-side polling loop
- Singleton `supabaseClient.ts` initializes the Supabase client (reads URL + anon key from environment variables, `.env` filled in later)
- `useVehicleSubscription` hook subscribes to Realtime and dispatches to Redux `vehiclesSlice` — follows the same pattern as the existing `useGtfsPolling` hook it replaces
- Supabase credentials via environment variables: `SUPABASE_URL`, `SUPABASE_ANON_KEY`

### Backend proxy worker
- Polls ETASpot PHP API every 5s, transforms and writes to Supabase `vehicles` table
- Position deduplication: compare new lat/lng/heading with previous — skip write if identical (no bus movement)
- Position history: append each new (non-duplicate) position to a `position_history` table for future speed derivation and model training data
- Auto-cleanup of old history rows (configurable retention)
- Route ID mapping happens in the proxy (215→215_202_201_156, etc.) so frontend sees consistent GTFS route IDs
- Worker host: Claude's discretion (Edge Function, standalone Node script, or pg_cron — whatever works best with Supabase local dev)

### ETA computation hook point
- On every new (non-duplicate) position write, the proxy has a hook point to call the FastAPI model
- For now this is a no-op — no trained models exist yet
- When models are trained, the proxy calls `/api/eta/predict` and writes predictions to a `predictions` table
- Each prediction is stored alongside the position that triggered it (for training data evaluation)

### Data mapping (proxy → Redux)
- Proxy transforms PHP fields to match existing `VehiclePosition` type: `lat`→`lat`, `lng`→`lon`, `h`→`heading`, `receiveTime`→`timestamp`, `equipmentID`→`vehicleId`, `routeID`→`routeId` (after compound ID mapping)
- Zero frontend component changes needed — BusMarker, RouteDetailView, RouteOverlay, RouteList all continue reading from `vehiclesSlice` unchanged
- Fields not available from PHP: `speed` (0 until derived from history), `etaSeconds` (0 until model is trained)

### Migration strategy
- Archive existing protobuf code (gtfsRealtimeService.ts, useGtfsPolling.ts, feeds.ts, tripRoutes.ts) — move to an `src/archived/` directory, not deleted
- Replace `useGtfsPolling()` call in MapScreen with `useVehicleSubscription()`
- Stale vehicle filtering (>2 min) handled by proxy (uses `receiveTime` from PHP, which is already in ms) — `inService=1` parameter also pre-filters on ETASpot's side

### Claude's Discretion
- Supabase table schema design (vehicles, position_history, predictions)
- Worker implementation approach (Edge Function vs standalone script vs pg_cron)
- Realtime subscription channel configuration
- Position history auto-cleanup strategy (time-based TTL vs row count)
- How to handle proxy errors (ETASpot down, Supabase write failure)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vehiclesSlice.ts`: `setPositions`, `setConnected`, `clearPositions` actions — can be reused as-is with Supabase data
- `VehiclePosition` type in `gtfs.types.ts`: existing type with vehicleId, routeId, lat, lon, heading, speed, load, capacity, nextStopId, etaSeconds, etc.
- `BusMarker.tsx`: renders from VehiclePosition, accepts opacity prop — no changes needed
- `RouteDetailView.tsx`: reads `vehicles.positions` filtered by routeId — no changes needed
- `RouteOverlay.tsx`: reads `routes.shapes` and `routes.stops` — no changes needed
- `useStaticData.ts` / `useStaticRouteData.ts`: static GTFS data loading — stays as-is

### Established Patterns
- Redux Toolkit slices with `useAppSelector` / `useAppDispatch`
- Hooks that dispatch to Redux on mount/data change (useStaticData, useGtfsPolling)
- AppState awareness for background/foreground transitions
- React.memo on list items for polling-driven re-renders

### Integration Points
- `MapScreen.tsx`: currently calls `useGtfsPolling()` at line 67 — swap to `useVehicleSubscription()`
- `vehiclesSlice.ts`: `setPositions` action receives `VehiclePosition[]` — proxy must produce this exact shape
- `routeColorMap` in MapScreen: reads from `routes.list` — unchanged

</code_context>

<specifics>
## Specific Ideas

- Position deduplication is critical — ETASpot polls GPS devices and the PHP endpoint often returns identical positions on consecutive requests. Only new positions should trigger DB writes and future model predictions.
- The prediction hook point should be designed so enabling model ETAs is a one-line change (uncomment or toggle a config flag), not a restructuring.
- The `inService=1` parameter on the PHP endpoint pre-filters vehicles, but the proxy should still check `receiveTime` for stale vehicles as a safety net.

</specifics>

<deferred>
## Deferred Ideas

- XGBoost model training and deployment — separate workstream, not blocked by Phase 2
- Speed derivation from position history — computed in Supabase when model needs it
- Service alerts from GTFS-RT protobuf alerts feed — Phase 6
- `get_stop_etas` endpoint for Stop Detail View arrival board — Phase 6
- `get_routes` / `get_stops` / `get_patterns` as alternative to bundled GTFS static data — evaluate later

</deferred>

---

*Phase: 02-real-time-data-pipeline*
*Context gathered: 2026-03-26 (rework after PHP API pivot)*
