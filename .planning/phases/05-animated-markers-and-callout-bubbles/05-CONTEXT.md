# Phase 5: Animated Markers and Callout Bubbles - Context

**Gathered:** 2026-03-27
**Status:** Ready for planning

<domain>
## Phase Boundary

Bus markers animate smoothly between position updates using a playback buffer approach, and tapping bus or stop markers opens glassmorphic callout panels with live data. No stop detail view, no favorites functionality, no service alerts.

</domain>

<decisions>
## Implementation Decisions

### Position interpolation (playback buffer)
- Bus positions are displayed ~15 seconds "in the past" to create a smooth interpolation buffer
- When a new position arrives, the bus animates from its previous known position to the current one over the real time delta between `receiveTime` timestamps
- The bus follows the actual route polyline path between positions (not straight-line lerp), using route shape data from Redux (`state.routes.shapes`)
- Heading is derived from the polyline tangent at the bus's current interpolated position — bus visually rotates through road curves
- Gap threshold: if `receiveTime` delta > 30 seconds (2 missed cycles), skip polyline interpolation and do a simple 1-second linear lerp to the new position
- First appearance: bus fades in at its initial position over ~300ms (existing `useFade` pattern), no interpolation until second update arrives
- Stale/offline exit: bus fades out over ~300ms matching fade-in
- No idle animation when bus is stationary

### Bus callout content
- Route long name with left-edge color bar in header (matching Route Detail header pattern)
- No bus ID shown — students don't need equipment IDs
- No last-stop info — next stops provide sufficient context
- Passenger load: route-colored capacity bar with count text (e.g. "12 passengers") — no max capacity shown, just the count
- Empty buses show empty bar + "0 passengers" (consistent display, section never hidden)
- Delay status: colored pill badge — "On Time" (muted green) or "DELAYED" (orange), matching DS-06 badge pattern
- Next-stop ETAs: show next 3 stops with ETAs, format "Stop Name — 3 min" for each
- Requires surfacing PHP `minutesToNextStops` array into vehicle data (currently only nextStopId/etaSeconds mapped)
- Callout is informational only — tapping the callout does nothing (no route navigation), tap outside to dismiss

### Stop callout content
- Stop name as title — no stop number shown (reserved for Stop Detail in Phase 6)
- ETAs for ALL routes serving that stop, not just the selected route
- Route badges: colored pills with route short name (e.g. "215", "226") in each route's color
- "View More" link with "Coming soon" toast (consistent with Phase 4 favorite star placeholder pattern) — Phase 6 wires real navigation to Stop Detail

### Callout presentation
- Custom overlay rendered outside MapView (absolutely-positioned View), not native `<Callout>` — full control over glassmorphism, BlurView, animations
- Centered above the tapped marker with a small downward-pointing arrow connecting callout to marker
- Auto-repositions if near screen edge
- Appear animation: scale 0.9→1.0 + fade in over ~200ms, reverse on dismiss
- Only one callout open at a time — tapping another marker swaps callouts, tapping anywhere outside (map, bottom sheet) dismisses
- Callout data refreshes silently with each 5s poll cycle — no visual indicator on refresh

### Selected marker highlight
- Tapped bus marker scales to ~1.2x with a subtle glow ring while its callout is open
- Returns to normal size when callout is dismissed
- Matches Phase 4's focused stop dot pattern (enlarge + glow)

### Claude's Discretion
- Exact polyline projection algorithm (nearest-point-on-segment approach)
- Playback buffer timing tuning (exact delay offset)
- Callout width and internal spacing within the 8px grid
- Callout arrow/triangle exact dimensions
- Edge-repositioning logic (how far to shift when near screen boundary)
- Stop callout ETA data source strategy (which API provides per-stop multi-route ETAs)
- `tracksViewChanges` strategy for animated markers (performance vs. visual updates)

</decisions>

<specifics>
## Specific Ideas

- The playback buffer approach is inspired by Life360 — buses appear ~15 seconds behind real time so there's always a "next position" to animate toward. The animation duration matches the actual time between positions, so buses move at physically accurate speed.
- Polyline-path interpolation means the bus visually follows road curves, and heading rotates naturally through turns rather than snapping or linearly interpolating between two angles.
- The 30-second gap threshold for falling back to linear lerp handles edge cases (bus restart, signal loss) without unrealistic speed bursts along the polyline.
- Next 3 stops with ETAs in the bus callout gives students a quick route preview without opening Route Detail.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `BusMarker.tsx`: Route-colored directional marker with `useFade` hook, heading rotation, brightness helper. Needs position animation added; heading will be derived from polyline tangent instead of raw `vehicle.heading`.
- `RouteOverlay.tsx`: `useFade` hook (duplicated from BusMarker), `lighten()` and `applyOpacity()` color utilities. Callout glassmorphism can reuse `applyOpacity`.
- `hexToRgba` in `RouteCard.tsx`: Shared color utility for tinted backgrounds.
- Route shapes in Redux: `state.routes.shapes[routeId]` — `Coordinate[]` arrays for polyline-path interpolation.
- Route stops in Redux: `state.routes.stops[routeId]` — stop sequence data for stop callout route badge lookup.
- `STOPS_BY_ID` constant: O(1) stop name lookup by stopId for resolving nextStopId to display name.

### Established Patterns
- Always-mounted markers with opacity toggling (never unmount react-native-maps overlays)
- `useFade` hook for 200ms opacity transitions
- `React.memo` on map children for polling-driven re-renders
- Glassmorphism: BlurView + rgba background fallback
- Navy-tinted shadows: `rgba(12, 35, 64, opacity)`
- DS-06 pill badges for status indicators
- "Coming soon" toast for placeholder features

### Integration Points
- `MapScreen.tsx`: Callout overlay rendered as sibling to MapView (outside `<MapView>` children), positioned using marker screen coordinates
- `vehiclesSlice.ts`: May need to store previous position for interpolation buffer, or interpolation logic lives in a custom hook
- `etaspotService.ts`: Needs to surface `minutesToNextStops` array from PHP response (currently only maps `nextStopETA`)
- `VehiclePosition` type: May need `minutesToNextStops` field added
- `uiSlice.ts`: Needs `selectedMarkerId` or `calloutTarget` state for tracking which marker's callout is open

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-animated-markers-and-callout-bubbles*
*Context gathered: 2026-03-27*
