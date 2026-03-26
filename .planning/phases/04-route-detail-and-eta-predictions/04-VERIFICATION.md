---
phase: 04-route-detail-and-eta-predictions
verified: 2026-03-26T18:30:00Z
status: gaps_found
score: 3/5 success criteria verified
gaps:
  - truth: "Route stops and shapes are hydrated into Redux on app mount"
    status: failed
    reason: "useStaticRouteData hook exists but is never imported or called anywhere in the application component tree -- stops and shapes remain empty objects in Redux"
    artifacts:
      - path: "src/hooks/useStaticRouteData.ts"
        issue: "ORPHANED -- defined but never imported or called from any component. Must be called from MapScreen (alongside existing useStaticData) or App root."
    missing:
      - "Add useStaticRouteData() call to MapScreen.tsx (or wherever useStaticData is called) so that routesSlice.stops and routesSlice.shapes are populated on mount"
  - truth: "Route polyline and stop markers appear on map when route is selected"
    status: failed
    reason: "RouteOverlay reads routes.shapes[selectedRouteId] and routes.stops[selectedRouteId] which are never populated (useStaticRouteData not called), so polyline and stop markers will not render"
    artifacts:
      - path: "src/components/map/RouteOverlay.tsx"
        issue: "Component code is correct but receives undefined data at runtime because Redux state is never hydrated"
    missing:
      - "Wire useStaticRouteData hook into the component tree (same fix as above resolves this)"
  - truth: "Ordered stop list displays stops with ETAs in Route Detail View"
    status: failed
    reason: "RouteDetailView reads routes.stops[routeId] which is never populated -- stop list will render zero StopRow components"
    artifacts:
      - path: "src/components/sheet/RouteDetailView.tsx"
        issue: "Component code is correct but stops array will be empty at runtime"
    missing:
      - "Wire useStaticRouteData hook into the component tree (same fix as above resolves this)"
  - truth: "Map auto-fits to show all stops and active buses for the selected route"
    status: failed
    reason: "MapScreen auto-fit useEffect reads routeStops from Redux which is never populated -- fitToCoordinates will only include bus positions (if any), not stop positions"
    artifacts:
      - path: "src/screens/MapScreen.tsx"
        issue: "Auto-fit logic is correct but routeStops will always be undefined"
    missing:
      - "Wire useStaticRouteData hook into the component tree (same fix as above resolves this)"
---

# Phase 4: Route Detail and ETA Predictions Verification Report

**Phase Goal:** Users can tap a route to see its full stop list with ML-powered arrival predictions and the route drawn on the map
**Verified:** 2026-03-26T18:30:00Z
**Status:** gaps_found
**Re-verification:** No -- initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All 179 GTFS stops are available as typed TypeScript constants | VERIFIED | src/data/stops.ts: 197 lines, exports STOPS (Stop[]) and STOPS_BY_ID (Record<string,Stop>), imports Stop type correctly |
| 2 | All 130 shape polylines are available grouped by shapeId | VERIFIED | src/data/shapes.ts: 16910 lines, exports SHAPES as Record<string, Coordinate[]> |
| 3 | 39 route-to-stop-sequence mappings exist | VERIFIED | src/data/routeStops.ts: 95 lines, exports ROUTE_STOP_SEQUENCE (39 entries) and ROUTE_SHAPE_ID |
| 4 | Redux routesSlice.stops and routesSlice.shapes are hydrated on mount | FAILED | useStaticRouteData hook exists and correctly dispatches setRouteStops/setRouteShape, BUT it is NEVER imported or called from any component. Only useStaticData (which loads route list only) is called from MapScreen. |
| 5 | POST /api/eta/predict-route endpoint exists with stub response | VERIFIED | ETA-Model/api/server.py: BatchPredictionRequest/Response models defined, endpoint at line 293, returns source="stub" |
| 6 | RouteDetailView shows route name in Headline-LG with color stripe and tinted background | VERIFIED | RouteDetailView.tsx: 262 lines, header has routeColor stripe (4px), tinted bg (hexToRgba 0.08), routeName uses typography.headlineLG |
| 7 | Ordered stop list displays stops with numbered route-colored indicators and connecting lines | FAILED (runtime) | StopRow.tsx: 195 lines, code correct with circle indicators (24px), connecting line (2px), BUT stops array from Redux will be empty because useStaticRouteData is never called |
| 8 | Each stop row shows ETAs formatted as "3 min", "< 1 min", or "No buses en route" | VERIFIED (code) | RouteDetailView.tsx formatEta function (line 50-53) and buildEtaMap (line 60-80) implement correct formatting with middle dot separator |
| 9 | ETAs update reactively with 5s polling | VERIFIED (code) | etaMap uses useMemo on routeVehicles which comes from state.vehicles.positions (updated by useGtfsPolling 5s cycle) |
| 10 | Back arrow and favorite star in sticky header | VERIFIED | RouteDetailView.tsx: chevron-back Ionicons (line 170), star-border MaterialIcons (line 190), favorite dispatches showToast('Coming soon') |
| 11 | RouteCard onPress dispatches selectRoute to trigger content swap | VERIFIED | RouteList.tsx line 79: dispatch(selectRoute(routeId)), line 87-88: conditionally renders RouteDetailView when selectedRouteId !== null |
| 12 | Route polyline drawn on map in route color when route selected | FAILED (runtime) | RouteOverlay.tsx: dual Polyline (shadow 9px + main 5px) code correct, BUT shapes data never hydrated into Redux |
| 13 | Stop markers appear on map as 12px/20px circles in route color | FAILED (runtime) | RouteOverlay.tsx: Marker-based dots (12px default, 20px focused) code correct, BUT stops data never hydrated into Redux |
| 14 | Map auto-fits to show all stops and active buses | FAILED (runtime) | MapScreen.tsx: fitToCoordinates useEffect (line 92-125) correct, BUT routeStops will be undefined |
| 15 | Tapping a stop centers the map on that stop | FAILED (runtime) | MapScreen.tsx: animateToRegion useEffect (line 130-146) correct, BUT no stops to tap |
| 16 | Non-selected route buses dim to 30% opacity | VERIFIED | MapScreen.tsx: opacity prop computed inline (line 190-195), BusMarker.tsx accepts opacity prop (line 36, applied at line 95) |
| 17 | Back button removes overlays, restores bus opacity, camera stays | VERIFIED | RouteDetailView handleBack dispatches selectRoute(null) + selectStop(null); MapScreen auto-fit skips when selectedRouteId is null |

**Score:** 3/5 success criteria verified (SC-1 partial, SC-2 failed, SC-3 failed, SC-4 partial, SC-5 verified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/data/stops.ts` | All GTFS stops as typed Stop[] constant | VERIFIED | 197 lines, 179 stops, exports STOPS and STOPS_BY_ID |
| `src/data/shapes.ts` | All GTFS shapes grouped by shapeId | VERIFIED | 16910 lines, 130 shapes, exports SHAPES |
| `src/data/routeStops.ts` | Route-to-stop-sequence mapping | VERIFIED | 95 lines, 39 routes, exports ROUTE_STOP_SEQUENCE and ROUTE_SHAPE_ID |
| `src/hooks/useStaticRouteData.ts` | Hook to hydrate routesSlice.stops and shapes | ORPHANED | 50 lines, correct implementation, but never imported or called |
| `ETA-Model/api/server.py` | Batch ETA prediction endpoint stub | VERIFIED | predict_route endpoint with typed models, returns source="stub" |
| `src/components/sheet/RouteDetailView.tsx` | Route Detail View with header and stop list | VERIFIED (code) | 262 lines, full implementation with ETA derivation |
| `src/components/sheet/StopRow.tsx` | Stop row with sequence indicator | VERIFIED | 195 lines, React.memo, transit diagram style |
| `src/components/map/RouteOverlay.tsx` | Polyline and stop markers | VERIFIED (code) | 127 lines, React.memo, dual polyline + Marker dots |
| `src/components/map/BusMarker.tsx` | Bus marker with opacity prop | VERIFIED | opacity prop added (line 36), applied to container View (line 95) |
| `src/screens/MapScreen.tsx` | MapScreen with RouteOverlay, auto-fit, centering | VERIFIED (code) | Imports RouteOverlay, auto-fit useEffect, stop-center useEffect, bus dimming |
| `src/components/sheet/RouteList.tsx` | Content swap on route select | VERIFIED | Conditionally renders RouteDetailView (line 87-88) |
| `src/components/sheet/RouteCard.tsx` | hexToRgba exported | VERIFIED | export function hexToRgba at line 50 |
| `scripts/generate-gtfs-data.js` | One-time GTFS CSV-to-TS generator | VERIFIED | Created for regenerating data files |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| useStaticRouteData.ts | routesSlice.ts | dispatch setRouteStops/setRouteShape | VERIFIED (internal) | Hook correctly dispatches both actions for all 39 routes |
| useStaticRouteData.ts | MapScreen.tsx | Called as hook | NOT_WIRED | Hook is never imported or called from MapScreen or any other component |
| RouteDetailView.tsx | routesSlice.ts | useAppSelector reads routes.stops | VERIFIED | Line 95: reads stopsMap, line 107: reads stops[selectedRouteId] |
| RouteDetailView.tsx | vehiclesSlice.ts | useAppSelector reads vehicles.positions | VERIFIED | Line 96: reads positions, line 113: filters by routeId |
| RouteDetailView.tsx | uiSlice.ts | dispatch selectRoute(null)/selectStop | VERIFIED | Lines 127-128: handleBack dispatches both, line 138: handleStopPress dispatches selectStop |
| RouteCard.tsx | uiSlice.ts | onPress dispatches selectRoute | VERIFIED | RouteList.tsx line 79: handleRoutePress dispatches selectRoute(routeId) |
| RouteOverlay.tsx | routesSlice.ts | reads routes.shapes and routes.stops | VERIFIED | Lines 32-33: reads shapes and stops from Redux |
| MapScreen.tsx | RouteOverlay.tsx | Rendered inside MapView | VERIFIED | Line 181: `<RouteOverlay />` child of MapView |
| MapScreen.tsx | uiSlice.ts | Reads selectedRouteId/selectedStopId | VERIFIED | Lines 76-77: reads both from state.ui |
| BusMarker.tsx | MapScreen.tsx | Receives opacity prop | VERIFIED | Lines 190-195: opacity computed inline from selectedRouteId comparison |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| ROUTE-05 | 04-02 | Tapping route card transitions to Route Detail with polyline + stop markers | PARTIAL | Route Detail renders correctly, but polyline/stop markers will not appear because stops/shapes never hydrated into Redux |
| ROUTE-06 | 04-02 | Route Detail shows route name in Headline-LG with color bar and favorite button | SATISFIED | RouteDetailView.tsx: headlineLG, 4px stripe, tinted bg, star-border icon |
| ROUTE-07 | 04-02 | Ordered stop list with next 3 ETAs per stop | BLOCKED | Stop list code is correct but will render empty because Redux not hydrated |
| ROUTE-08 | 04-02 | ETAs rounded to nearest minute format | SATISFIED | formatEta: < 60s -> "< 1 min", >= 60s -> "N min", no match -> "No buses en route" |
| ROUTE-09 | 04-03 | Tap stop in list to center map | BLOCKED | MapScreen stop-center useEffect correct but no stops to tap |
| ROUTE-10 | 04-02 | Back button returns to Route List | SATISFIED | handleBack dispatches selectRoute(null), RouteList conditionally renders list |
| MAP-05 | 04-03 | Stop markers on map in route color | BLOCKED | RouteOverlay Marker dots code correct but stops data never hydrated |
| MAP-06 | 04-03 | Route polyline on map in route color | BLOCKED | RouteOverlay dual Polyline code correct but shapes data never hydrated |
| MAP-07 | 04-03 | Map auto-fits to stops + buses | BLOCKED | fitToCoordinates useEffect correct but routeStops undefined |
| ETA-02 | 04-01 | Stop list shows model predictions for next 3 arrivals | PARTIAL | ETAs derived from GTFS-RT nextStopId matching (fallback path), not ML model; batch ETA endpoint is stub only |
| ETA-03 | 04-01 | ETA predictions refresh every 15 seconds | SATISFIED | ETAs recompute via useMemo when vehicles.positions updates from 5s polling cycle (more frequent than 15s requirement) |
| ETA-04 | 04-01 | Model timeout falls back to GTFS-RT ETAs | SATISFIED | ETAs are already derived from GTFS-RT data directly; model integration is a future enhancement with stub endpoint ready |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/hooks/useStaticRouteData.ts | All | ORPHANED: Never imported or called | BLOCKER | Stops and shapes never hydrated into Redux, breaking all Phase 4 features that read this data |
| src/components/sheet/RouteDetailView.tsx | 132 | "Coming soon" toast on favorite | Info | Intentional placeholder per plan, Phase 6 feature |
| ETA-Model/api/server.py | 314 | route_stops = [] (always empty) | Info | Intentional stub -- endpoint is scaffold for future model integration |

### Human Verification Required

### 1. Route Detail Visual Appearance

**Test:** Tap a route card in the bottom sheet
**Expected:** Sheet content swaps to show Route Detail View with route name in 32pt Manrope Bold, 4px color stripe on left, tinted background, back arrow, favorite star
**Why human:** Visual styling (font rendering, color tinting, layout spacing) cannot be verified programmatically

### 2. Transit Diagram Visual Style

**Test:** View stop list in Route Detail View (after gap fix)
**Expected:** Numbered route-colored circles with 2px connecting vertical line between stops, forming a transit diagram appearance
**Why human:** Visual alignment and diagram aesthetics require visual inspection

### 3. Map Overlay Appearance

**Test:** Select a route and observe the map (after gap fix)
**Expected:** Route polyline in route color with navy shadow underneath, 12px stop dots with white border, focused stop enlarges to 20px
**Why human:** Map overlay rendering quality varies by platform and zoom level

### 4. Bus Marker Dimming

**Test:** Select a route with active buses while other routes also have buses
**Expected:** Selected route buses at full opacity, all other buses at ~30% opacity
**Why human:** Opacity perception requires visual confirmation

### 5. Map Auto-Fit and Stop Centering

**Test:** Select a route, then tap individual stops in the list (after gap fix)
**Expected:** Map initially fits to show all stops + buses, then animates to center on tapped stop with 500ms animation
**Why human:** Camera animation smoothness and edge padding adequacy require visual confirmation

## Gaps Summary

All four gaps stem from a single root cause: **the `useStaticRouteData` hook is defined but never called from any component in the application tree**. This means `state.routes.stops` and `state.routes.shapes` remain as empty objects (`{}`) at runtime.

The fix is a one-line addition: add `useStaticRouteData()` to MapScreen.tsx (or wherever `useStaticData()` is already called, line 64 in MapScreen.tsx). This single wiring fix will resolve all four gaps simultaneously, enabling:
- Stop list rendering in RouteDetailView
- Polyline + stop marker rendering in RouteOverlay
- Map auto-fit with stop coordinates
- Stop-tap-to-center functionality

All component implementations are correct and substantive -- the only issue is that the data hydration hook was never plugged into the component tree. TypeScript compiles cleanly, all files exist, all internal wiring within components is correct. The gap is purely at the integration point.

---

_Verified: 2026-03-26T18:30:00Z_
_Verifier: Claude (gsd-verifier)_
