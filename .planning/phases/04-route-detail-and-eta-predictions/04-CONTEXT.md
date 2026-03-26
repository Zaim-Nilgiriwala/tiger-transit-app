# Phase 4: Route Detail and ETA Predictions - Context

**Gathered:** 2026-03-26
**Status:** Ready for planning

<domain>
## Phase Boundary

Tapping a route card opens a Route Detail view inside the bottom sheet with an ordered stop list, ETA arrivals from GTFS-RT trip updates, and the route drawn on the map as a polyline with stop markers. Includes batch ETA endpoint stub on the FastAPI server for future model integration. No callout bubbles, no stop detail view, no favorites functionality, no service alerts.

</domain>

<decisions>
## Implementation Decisions

### Route detail transition
- Sheet stays at current snap position when a route card is tapped — content swaps to Route Detail in place (no auto-expand)
- Map auto-fits to show all stops + active buses for the selected route (MAP-07)
- Back button removes polyline + stop markers, restores all bus markers at full opacity, camera stays exactly where it is (no zoom/position change)

### Route detail header
- Sticky header pinned at top of sheet content area — stop list scrolls beneath it
- Left-edge vertical stripe (4px, route color) AND tinted background (~8% opacity route color) — combines both patterns from RouteCard
- Long name only in Headline-LG (32pt Manrope Bold) — no short name in header or route cards
- Back arrow (left) and favorite star (right) in the header
- Favorite star tappable with "Coming soon" toast — consistent with Phase 1 placeholder pattern. Phase 6 wires functionality.

### Stop list presentation
- Stops ordered by route sequence (GTFS stop_times order), not by ETA proximity
- Sequence numbers (1, 2, 3...) displayed as route-colored circled indicators
- Vertical route-colored line (2px) connects stop indicators — transit diagram style
- Each stop row: sequence indicator, stop name (primary text), ETA line below
- ETAs displayed inline: "3 min · 7 min · 12 min" format with middle dot separators
- Stops with no approaching vehicle show "No buses en route" in muted text
- No visual emphasis for "< 1 min" arrivals — consistent text styling
- Tapping a stop centers the map on that stop (ROUTE-09) with persistent selection highlight on the row (route-color tint) until another stop is tapped or back is pressed

### ETA data source
- Primary source: GTFS-RT trip update data already in VehiclePosition (nextStopId + etaSeconds)
- Show only next-stop ETAs — if a vehicle's nextStopId matches the stop, show its ETA. No downstream estimation for stops further along the route.
- ETAs update reactively with the existing 5s GTFS-RT polling cycle (no separate refresh)
- Formats per ROUTE-08: "3 min", "< 1 min", "No buses en route"
- When model API is trained later: model predictions replace GTFS-RT ETAs, GTFS-RT becomes the fallback (ETA-04)

### Batch ETA endpoint
- Add POST /api/eta/predict-route to the existing FastAPI server (ETA-Model/api/server.py)
- Takes routeId + current vehicle positions → returns ETAs for every stop on the route
- This is a stub/scaffold — no trained models exist yet, so frontend doesn't call it in Phase 4
- Designed so future integration is a matter of adding an RTK Query hook, not restructuring

### Map overlays on route select
- Route polyline: solid line in route color, 4-5px width, fixed pixel width regardless of zoom level (does not thin when zooming out), navy-tinted shadow underneath
- Stop markers: ~12px filled circles in route color with thin white border, fixed pixel size
- Focused stop marker (tapped from list): enlarges to ~20px with thicker white border/glow, shrinks back when another stop is tapped
- Non-selected route buses: dimmed to ~30% opacity (not hidden). Selected route's buses at full opacity. All buses return to full opacity when back is pressed.

### Claude's Discretion
- Stop marker and polyline z-ordering relative to bus markers
- Exact animation timing for map auto-fit
- How to load stops and shapes data (bundled like routes or fetched)
- Route Detail → Route List content swap animation (crossfade, slide, instant)
- Stop row height and spacing within the 8px grid
- Back button icon style (arrow, chevron)
- How persistent stop selection highlight is styled (opacity, border, background tint)

</decisions>

<specifics>
## Specific Ideas

- The sheet staying in place on route select means the map is the hero — the polyline, stop markers, and dimmed buses tell the route story visually while the sheet provides the detail. This avoids the jarring experience of the sheet jumping to full and hiding the map.
- The vertical connecting line in the stop list creates a transit diagram feel — students can visually trace the route path both on the map and in the list.
- Using GTFS-RT trip update ETAs first (not model predictions) means Phase 4 ships with real data from day one. The model API is a drop-in upgrade, not a dependency.
- Fixed pixel width on the polyline matches the bus marker approach — consistent visual weight at all zoom levels.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `routesSlice.ts`: Already has `stops: Record<string, Stop[]>` and `shapes: Record<string, Coordinate[]>` with `setRouteStops` and `setRouteShape` actions — ready for per-route data
- `predictionsSlice.ts`: Already has `byStop: Record<string, ArrivalPrediction[]>` — ready for future model predictions
- `uiSlice.ts`: Has `selectedRouteId`, `selectedStopId`, `selectRoute()`, `selectStop()` actions — selection state wired
- `VehiclePosition` type: Already includes `nextStopId`, `etaSeconds`, `isDelayed` — GTFS-RT ETA data ready
- `ArrivalPrediction` type: Has `isModelPrediction` boolean for distinguishing model vs feed ETAs
- `RouteCard.tsx`: `hexToRgba` helper reusable for header tint and stop selection highlight
- `BottomSheet.tsx`: Accepts children — Route Detail can swap in as children replacement
- `BusMarker.tsx`: Route-colored marker with heading rotation — opacity prop needed for dimming
- `mapRef` in MapScreen: Available for `fitToCoordinates()` and `animateToRegion()`

### Established Patterns
- Redux Toolkit typed slices with `useAppSelector` selectors
- Glassmorphism: BlurView + rgba background fallback
- Navy-tinted shadows: `rgba(12, 35, 64, opacity)`
- Design tokens: `surfaces`, `textColors`, `typography`, `spacing`, `EDGE_MARGIN`
- React.memo on list items (RouteCard pattern) for polling-driven re-renders
- "Coming soon" toast for placeholder features

### Integration Points
- `MapScreen.tsx`: Renders MapView + BusMarkers + BottomSheet + FloatingLocationButton — polyline and stop markers added as MapView children
- `RouteList.tsx` → `RouteCard.tsx`: onPress handler needed to dispatch `selectRoute()` and trigger content swap
- `useGtfsPolling.ts`: Vehicle positions with nextStopId/etaSeconds already flowing every 5s
- `ETA-Model/api/server.py`: FastAPI server exists (non-functional, no trained models) — batch endpoint added here
- `ETA-Model/gtfs_data/stops.txt` and `shapes.txt`: Source data for bundling stops and shapes

</code_context>

<deferred>
## Deferred Ideas

- Model-powered ETAs (POST /api/eta/predict-route) — batch endpoint scaffolded in Phase 4 but actual model predictions deferred until models are trained
- Stop Detail View (STOP-01 through STOP-07) — Phase 6
- Bus/stop callout bubbles (CALL-01 through CALL-05) — Phase 5
- ROUTE-02 completion (ETA on route cards in the list) — after model predictions are available

</deferred>

---

*Phase: 04-route-detail-and-eta-predictions*
*Context gathered: 2026-03-26*
