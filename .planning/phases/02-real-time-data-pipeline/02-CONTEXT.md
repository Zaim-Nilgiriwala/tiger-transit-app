# Phase 2: Real-Time Data Pipeline - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Live bus positions on the map updating every 5 seconds with stale vehicles automatically hidden. Includes GTFS-RT protobuf decoding (position + trip updates), polling service with foreground/background awareness, bus markers on the map with directional heading, and bundled static route data. No route selection, no callouts, no bottom sheet interaction, no stop markers.

</domain>

<decisions>
## Implementation Decisions

### Bus marker design
- Bus icon inside a rounded-square container with 3 filleted corners (radius = half the side length) and 1 sharp 90-degree corner
- Container color matches the specific bus route's color (NOT uniform orange — diverges from PRD's "secondary-fixed orange")
- 5-8px outline around the container using a brighter tint of the same route color (subtle glow effect)
- Navy-tinted drop shadow consistent with Academic Navigator design system (rgba(12, 35, 64, ...))
- ~36px fixed pixel size, does not scale with zoom
- White bus icon inside the container

### Marker heading/rotation
- The entire container rotates so the sharp (90-degree) corner points in the direction of travel
- The bus icon inside stays upright (does not rotate) — container shows heading, icon stays readable

### Marker density & z-ordering
- No clustering — always show individual markers regardless of zoom level or density
- Fixed pixel size at all zoom levels (consistent tap targets)
- Z-ordering: most recently updated marker renders on top when markers overlap

### GTFS static data
- Bundled as a TypeScript module (export const ROUTES: Route[] = [...]) — zero-cost import, no async loading
- Source: convert ETA-Model/gtfs_data/routes.txt to typed .ts file
- Phase 2 only needs routes (routeId, shortName, longName, routeColor) — stops, shapes, trips, calendar deferred to later phases
- Route changes require an app update (Auburn changes routes ~2x per year)

### Stale vehicle handling
- Instant hard removal at 2-minute threshold — no fade, no dimming, no transition
- No freshness/LIVE indicator on the map — marker presence IS the indicator that data is live
- On foreground resume: immediately clear any markers older than 2 minutes, then show fresh data as new polls arrive (brief empty map is acceptable)

### Claude's Discretion
- Protobuf library choice for Hermes/Expo SDK 55 compatibility (validate gtfs-realtime-bindings or alternative)
- Polling service architecture (hook vs service class, RTK Query vs custom)
- Background/foreground detection implementation (AppState API)
- Feed URL configuration approach
- Error handling for failed polls (retry strategy, silent failure)
- Exact bus icon asset design within the described container shape

</decisions>

<specifics>
## Specific Ideas

- The marker shape is inspired by a map pin / callout bubble — three heavily rounded corners with one sharp corner that acts as a directional pointer
- Route-colored markers make the map immediately informative before the user even interacts with a route list (Phase 3)
- The brighter-tint outline creates a subtle glow effect that helps markers pop against the map without being garish
- Reference code in `Code/etaspot_reference.ts` has the complete working protobuf decode flow — trip updates processed before position updates for ETA enrichment

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `vehiclesSlice.ts`: Redux slice already scaffolded with `positions: VehiclePosition[]`, `lastUpdated`, `connected` state and `setPositions`, `setConnected`, `clearPositions` actions
- `gtfs.types.ts`: `VehiclePosition` interface already defined matching the reference code (vehicleId, routeId, lat, lon, heading, speed, etc.)
- `gtfs.types.ts`: `Route` interface already defined (routeId, shortName, longName, routeColor, routeType)
- `Code/etaspot_reference.ts`: Complete working protobuf decode with S3 feed URLs, trip update processing, stale filtering logic
- `ETA-Model/gtfs_data/routes.txt`: Source GTFS static data for route bundling

### Established Patterns
- Redux Toolkit with typed slices (Phase 1 pattern)
- Navy-tinted shadows: rgba(12, 35, 64, opacity) — used on FloatingLocationButton, GlassBottomBar
- BlurView with rgba background fallback for glassmorphism
- Silent failure UX pattern (location permission denied = no-op, no nagging)

### Integration Points
- `FloatingLocationButton.tsx` and `GlassBottomBar.tsx` — bus markers render on the same MapView, must not occlude controls
- Redux store (`src/store/index.ts`) — vehicles slice already wired in, polling service dispatches to it
- S3 feed URLs: position_updates.pb and trip_updates.pb at `s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-real-time-data-pipeline*
*Context gathered: 2026-03-25*
