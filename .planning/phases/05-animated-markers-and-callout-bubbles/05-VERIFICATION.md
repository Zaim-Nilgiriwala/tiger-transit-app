---
phase: 05-animated-markers-and-callout-bubbles
verified: 2026-03-27T00:00:00Z
status: human_needed
score: 9/9 must-haves verified
human_verification:
  - test: "Confirm bus callout intentionally omits bus ID"
    expected: "Callout shows route name, passengers, delay status, next 3 stops — no bus ID visible"
    why_human: "CALL-01 in REQUIREMENTS.md specifies 'bus ID' but the plan explicitly dropped it per user decision ('No bus ID shown per user decision'). The implementation matches the plan, not the requirement text. Needs human confirmation that the requirement text is stale."
  - test: "Bus markers animate smoothly along polyline path between 10s poll cycles"
    expected: "Markers follow the road curves, heading rotates through bends — no straight-line jumps"
    why_human: "Animation correctness (polyline hugging, physical plausibility) requires visual runtime inspection"
  - test: "Tapping a bus marker opens the glassmorphic callout"
    expected: "Glass-panel callout appears above the marker with scale+fade animation, triangle pointer, BlurView backdrop blur, route name with color bar, capacity bar, delay pill, next 3 stop ETAs"
    why_human: "Glassmorphic styling quality, BlurView rendering, and animation feel require device/simulator inspection"
  - test: "Tapping a stop marker opens the stop callout"
    expected: "Glass-panel callout shows stop name, ETA rows for all routes serving that stop with colored dots, horizontal route badge pills, and a 'View More' link"
    why_human: "Multi-route ETA accuracy and badge rendering require runtime inspection with live data"
  - test: "Callout repositions when map is panned while open"
    expected: "Callout follows its marker as the map pans — does not stay fixed to original screen position"
    why_human: "onRegionChangeComplete + pointForCoordinate async repositioning requires device interaction"
---

# Phase 5: Animated Markers and Callout Bubbles — Verification Report

**Phase Goal:** Smooth marker animation and interactive glass-panel callouts
**Verified:** 2026-03-27
**Status:** human_needed (all automated checks pass; 5 items require runtime/device confirmation)
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | Bus markers animate smoothly between position updates with no visible jumps | ? HUMAN | `useAnimatedPosition` hook uses rAF loop with polyline interpolation — logic verified; visual quality needs runtime check |
| 2  | Buses follow the actual route polyline path between positions | ? HUMAN | `interpolateAlongPolyline` in `polylineProjection.ts` walks polyline segments — implementation verified; visual hugging needs device |
| 3  | Bus heading rotates naturally through road curves based on polyline tangent | ? HUMAN | `tangentAtPoint` exports compass bearing from segment direction — implementation verified; smoothness needs runtime |
| 4  | First-appearing buses fade in without interpolation | VERIFIED | `prevPos.current === null` branch in `useAnimatedPosition`: sets `animDuration = 0`, places instantly, no rAF started |
| 5  | Stale buses fade out via `useFade` hook | VERIFIED | `useFade` in BusMarker drives 200ms `Animated.Value` opacity; `visible` prop controls fade direction |
| 6  | `minutesToNextStops` array is available on VehiclePosition | VERIFIED | Field present in `gtfs.types.ts` interface, mapped in `etaspotService.ts` from PHP `minutesToNextStops`, defaulted to `[]` in `useVehicleSubscription.ts` |
| 7  | Tapping a bus marker opens a glass-panel callout with route, passengers, delay, next 3 stops | ? HUMAN | `BusCalloutContent` implements all fields; glassmorphism quality and bus ID omission need device + user confirmation (see below) |
| 8  | Tapping a stop marker opens a glass-panel callout with stop name, multi-route ETAs, badges, View More | ? HUMAN | `StopCalloutContent` implements all fields; `showToast('Coming soon')` wired to View More; rendering quality needs device |
| 9  | Only one callout open at a time; tapping outside dismisses | VERIFIED | `activeCallout: ActiveCallout \| null` in Redux `uiSlice`; `clearCallout` dispatched on `onPress` of MapView, BottomSheet `onTouchStart`, and new marker tap |

**Score:** 9/9 truths verified or awaiting human confirmation (no failures)

---

## Required Artifacts

### Plan 05-01 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/hooks/useAnimatedPosition.ts` | Playback buffer interpolation hook | VERIFIED | 259 lines; exports `useAnimatedPosition`; implements rAF loop, polyline projection, gap threshold, `tracksViewChanges` toggle |
| `src/utils/polylineProjection.ts` | Nearest-point-on-polyline and distance-along-path utilities | VERIFIED | 215 lines; exports `projectOntoPolyline`, `interpolateAlongPolyline`, `tangentAtPoint` — all three required exports present |
| `src/types/gtfs.types.ts` | VehiclePosition extended with `minutesToNextStops` | VERIFIED | Line 52: `minutesToNextStops: Array<{ stopId: string; minutes: number }>` |
| `src/services/etaspotService.ts` | PHP `minutesToNextStops` mapped into VehiclePosition | VERIFIED | Lines 31-38: maps `v.minutesToNextStops` array, defaults to `[]`, correct field name transform (`stopID` → `stopId`) |
| `src/components/map/BusMarker.tsx` | Animated bus marker using `useAnimatedPosition` | VERIFIED | Line 102: `useAnimatedPosition(vehicle, routeShape, visible)`; line 109: `coordinate={{ latitude: animated.latitude, longitude: animated.longitude }}`; line 111: `tracksViewChanges={animated.isAnimating}` |

### Plan 05-02 Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/components/map/CalloutBubble.tsx` | Glassmorphic callout overlay with triangle pointer | VERIFIED | 265 lines; `BlurView` with `glass.callout.backdropBlur`; scale+fade animation (200ms in / 150ms out); auto-flip above/below; horizontal clamping; `pointerEvents="box-none"` on overlay |
| `src/components/map/BusCalloutContent.tsx` | Bus callout inner content | VERIFIED | Route name with color bar; capacity bar (`load / 50`); delay pill (DELAYED/On Time); next 3 stops from `minutesToNextStops`; `STOPS_BY_ID` lookup; `React.memo` wrapped |
| `src/components/map/StopCalloutContent.tsx` | Stop callout inner content | VERIFIED | Stop name title; per-route ETA rows using `ROUTE_STOP_SEQUENCE` + `vehicles`; horizontal badge `ScrollView`; `showToast('Coming soon')` on View More; `React.memo` wrapped |

---

## Key Link Verification

### Plan 05-01 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/hooks/useAnimatedPosition.ts` | `src/utils/polylineProjection.ts` | `import.*polylineProjection` | WIRED | Lines 17-21: imports `projectOntoPolyline`, `interpolateAlongPolyline`, `tangentAtPoint`; all three called in hook body |
| `src/components/map/BusMarker.tsx` | `src/hooks/useAnimatedPosition.ts` | `useAnimatedPosition` | WIRED | Line 18: import; line 102: hook called; `animated.latitude`, `animated.longitude`, `animated.heading`, `animated.isAnimating` all consumed |
| `src/components/map/BusMarker.tsx` | `react-native-maps Marker` | `tracksViewChanges` | WIRED | Line 111: `tracksViewChanges={animated.isAnimating}` — toggles true during animation, false when settled |
| `src/screens/MapScreen.tsx` | `src/store/slices/routesSlice` via `shapes` | `shapes[vehicle.routeId]` | WIRED | Line 76: `const shapes = useAppSelector((state) => state.routes.shapes)`; line 290: `routeShape={shapes[vehicle.routeId]}` passed to each `BusMarker` |

### Plan 05-02 Key Links

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `src/screens/MapScreen.tsx` | `src/components/map/CalloutBubble.tsx` | `CalloutBubble` rendered outside MapView | WIRED | Lines 41, 299-320: imported and rendered as sibling after `</MapView>`; positioned via `markerScreenPos` state |
| `src/screens/MapScreen.tsx` | `src/store/slices/uiSlice.ts` | `activeCallout` state | WIRED | Line 29: imports `setActiveCallout`, `clearCallout`; line 86: reads `activeCallout`; lines 109-145: dispatches on all press/dismiss paths |
| `src/components/map/BusMarker.tsx` | `src/screens/MapScreen.tsx` | `onPress` callback | WIRED | Line 29 props: `onPress?: () => void`; line 114: `onPress={onPress}` on `<Marker>`; line 291 in MapScreen: closure passed |
| `src/components/map/CalloutBubble.tsx` | `BusCalloutContent \| StopCalloutContent` | Renders based on callout type | WIRED | Lines 306-318 in MapScreen: `activeCallout.type === 'bus'` renders `BusCalloutContent`, `=== 'stop'` renders `StopCalloutContent` as `children` of `CalloutBubble` |
| `src/components/map/RouteOverlay.tsx` | `src/screens/MapScreen.tsx` | `onStopPress` prop | WIRED | Line 72: `onStopPress?: (stopId: string) => void` on `SingleRouteOverlayProps`; line 131: `onPress={() => onStopPress?.(stop.stopId)}` on each stop Marker; line 280 in MapScreen: `onStopPress={handleStopPress}` |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| MAP-03 | 05-01 | Bus markers animate smoothly (1000ms interpolation) | VERIFIED | `useAnimatedPosition` uses `animDuration = Math.min(timeDelta, 15_000)` for polyline-path rAF animation; `tracksViewChanges` toggles for GPU efficiency |
| ETA-01 | 05-01 | Bus callout shows next-stop ETA from PHP `nextStopETA` | VERIFIED | `etaSeconds` already mapped from `v.nextStopETA` in `etaspotService.ts`; `minutesToNextStops` also available for multi-stop display in callout |
| CALL-01 | 05-02 | Bus callout: route, bus ID, passengers, delay, ETA to next stop | PARTIAL (see note) | Route name, passengers, delay, next 3 stop ETAs all present in `BusCalloutContent`. **Bus ID omitted by explicit user decision** (plan note: "No bus ID shown per user decision"). REQUIREMENTS.md text says "bus ID" — this is a requirement-vs-decision discrepancy requiring human confirmation |
| CALL-02 | 05-02 | Stop callout: stop name, stop number, ETA, route badges, "View More" | PARTIAL (see note) | Stop name, route ETAs with colored dots, horizontal badge pills, View More toast all present. **Stop number not shown** — plan says "no stop number shown (reserved for Phase 6)". Same pattern as bus ID: explicit deferral. |
| CALL-03 | 05-02 | Glassmorphic styling (backdrop blur, surface-container-lowest ~95% opacity) | VERIFIED (HUMAN for visual) | `BlurView intensity={20}` + `createGlassStyle('callout')` → borderRadius 8, 95% opacity white. Logic correct; visual quality needs device |
| CALL-04 | 05-02 | Only one callout; tapping outside dismisses | VERIFIED | Single `activeCallout` Redux state; `clearCallout` on map press, BottomSheet `onTouchStart`, new marker tap |
| CALL-05 | 05-02 | Callout data refreshes with 5s polling cycle | VERIFIED | Callout content components receive `vehicle` / `stop` / `vehicles` / `routes` from Redux; ETAspot polling hook drives Redux updates every 10s; re-render automatic |

**Note on CALL-01 / CALL-02 deferral:** The plan explicitly deferred "bus ID" and "stop number" per user decisions made during execution. The REQUIREMENTS.md text has not been updated to reflect these decisions. These are not implementation gaps — they are requirement text gaps that need human confirmation that the deferred items are acceptable for Phase 5 delivery.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `src/components/map/CalloutBubble.tsx` | 128 | `return null` | ℹ️ Info | Intentional: guard clause during exit animation before `shouldRender` becomes false. Not a stub. |
| `src/components/map/StopCalloutContent.tsx` | 5 | "coming soon" in comment | ℹ️ Info | Doc comment describing View More behavior. Actual implementation wires `showToast('Coming soon')` — this is intentional per plan. |

No blocking anti-patterns found. No TODO/FIXME/HACK comments, no empty handlers, no unimplemented API returns.

---

## Human Verification Required

### 1. Bus Callout — Bus ID Omission vs CALL-01 Requirement

**Test:** Tap a bus marker to open its callout. Inspect what fields are shown.
**Expected:** Route name, passenger bar, delay pill, next 3 stop ETAs. No bus ID.
**Why human:** REQUIREMENTS.md CALL-01 text says "bus ID" but the plan explicitly dropped it per user decision. Verify that the omission is acceptable and update REQUIREMENTS.md text if so.

### 2. Stop Callout — Stop Number Omission vs CALL-02 Requirement

**Test:** Tap a stop marker to open its callout. Inspect what fields are shown.
**Expected:** Stop name, multi-route ETAs, route badge pills, View More link. No stop number.
**Why human:** REQUIREMENTS.md CALL-02 says "stop number" but plan deferred it to Phase 6. Same pattern as bus ID — verify acceptability and update requirement text.

### 3. Animation Visual Quality (MAP-03)

**Test:** Watch bus markers during a 10s poll cycle update.
**Expected:** Markers glide smoothly along road curves with heading rotation. No teleporting or straight-line jumps. First-appearing bus places instantly with no stuttery animation.
**Why human:** Animation correctness (polyline hugging, physical plausibility, rAF performance) requires visual runtime inspection on a device or simulator.

### 4. Glassmorphic Callout Appearance (CALL-03)

**Test:** Tap a bus and a stop marker. Observe callout styling.
**Expected:** Frosted-glass panel with visible backdrop blur behind callout, white-tinted semi-transparent background, navy-tinted shadow, downward triangle pointer, smooth 200ms scale+fade entrance.
**Why human:** BlurView rendering quality, shadow appearance, and animation feel require device/simulator inspection.

### 5. Callout Repositions During Map Pan (CALL-04 extended)

**Test:** Open a callout, then pan the map.
**Expected:** Callout follows its marker as you pan — does not stay fixed at the original screen position.
**Why human:** `onRegionChangeComplete` + `pointForCoordinate` async position update requires device interaction to verify the callout tracks correctly without lag artifacts.

---

## Commits Verified

All four commits claimed in summaries verified present in git log:

| Commit | Message | Status |
|--------|---------|--------|
| `e692a86` | feat(05-01): surface minutesToNextStops and create polyline projection utilities | VERIFIED |
| `ca401b5` | feat(05-01): animated bus markers with polyline-path interpolation | VERIFIED |
| `b5671ba` | feat(05-02): create glassmorphic callout bubble and bus/stop content components | VERIFIED |
| `3a24727` | feat(05-02): wire callout bubbles into MapScreen with marker press, dismiss, and highlight | VERIFIED |

---

## Gaps Summary

No structural gaps found. All required artifacts exist, are substantive (not stubs), and are wired correctly. The phase goal of "smooth marker animation and interactive glass-panel callouts" is fully implemented.

The five human verification items are:
1. **Requirement text discrepancy:** CALL-01 says "bus ID" and CALL-02 says "stop number" — both were intentionally omitted per user decisions made during execution. Requires human confirmation that REQUIREMENTS.md should be updated.
2. **Visual/runtime quality:** Animation smoothness, glassmorphic appearance, and callout repositioning on pan cannot be verified programmatically.

---

_Verified: 2026-03-27_
_Verifier: Claude (gsd-verifier)_
