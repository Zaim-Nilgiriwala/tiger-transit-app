# Project Research Summary

**Project:** Tiger Transit Frontend
**Domain:** Real-time university transit tracking mobile app (React Native / Expo)
**Researched:** 2026-03-25
**Confidence:** MEDIUM-HIGH

---

## Executive Summary

Tiger Transit is a greenfield React Native (Expo) frontend for Auburn University's campus bus system. The backend infrastructure is already complete — Supabase stores GTFS static data, a FastAPI service hosts a trained XGBoost ETA model (85.6-second MAE), and S3 serves GTFS-Realtime protobuf feeds. The entire project scope is a single-screen mobile app: a full-screen map with animated bus markers layered under a glassmorphic draggable bottom sheet that surfaces routes, stops, and ML-powered arrival predictions.

The recommended stack centers on Expo SDK 55 (React Native 0.83, New Architecture only), which is the current stable release. This choice locks out Legacy Architecture, forces Hermes bytecode diffing for smaller OTA updates, and gives stable Android blur via expo-blur. The map layer uses react-native-maps (Apple Maps on iOS by default, Google Maps on Android), the bottom sheet uses @gorhom/bottom-sheet v5.2+, animation uses Reanimated 4 (UI thread, 60fps), and state management is Redux Toolkit with a custom singleton polling service for binary protobuf feeds and RTK Query for the JSON ETA API.

Three risks dominate the technical landscape. First, Android renders custom map markers as bitmap snapshots — complex React component markers will break 60fps animation and must be simplified to SVG with `tracksViewChanges={false}`. Second, the bottom sheet and map compete for vertical pan gestures; @gorhom/bottom-sheet handles this well but requires configuration validation at each snap point. Third, `gtfs-realtime-bindings` uses `protobufjs` with known require-cycle warnings in Metro; protobuf decoding must be validated on both platforms in Phase 2 before the rest of the data pipeline is built on top of it. All three risks have documented mitigations and are manageable with proactive testing.

The app's scale is intentionally small (38 routes, 178 stops, ~15-20 active buses). This means clean architecture and visual polish matter more than performance optimization. The recommended strategy is to build working functionality first, add animation second, and defer all non-MVP features (search, dark mode, notifications, trip planner) to v2.

---

## Key Findings

### Recommended Stack

The stack is well-defined by the PRD and reference code. Expo SDK 55 is the correct starting point — there is no reason to start on SDK 54 or earlier, as SDK 55 is stable, New Architecture is mandatory going forward, and starting on old SDKs creates an inevitable migration. React Native 0.83 and React 19.2 are bundled with SDK 55 and require no additional configuration.

The most consequential library decisions are react-native-maps (not expo-maps, which does not support custom animated markers), @gorhom/bottom-sheet v5.2+ (not ad-hoc modals or Expo Router sheets, which lack snap-point control), and the split data-fetching architecture (custom polling service for protobuf binary, RTK Query for REST JSON). The PRD explicitly requires Redux Toolkit, making Zustand/Jotai non-options.

**Core technologies:**
- **Expo SDK 55:** App framework — latest stable, New Architecture only, Hermes bytecode diffing
- **react-native-maps ~1.27:** Map rendering — supports Apple Maps iOS / Google Maps Android split; SDK 55 config plugin issue resolved (PR #43884)
- **@gorhom/bottom-sheet ~5.2:** Draggable sheet — snap points, glassmorphism backgroundComponent, Reanimated 4 support
- **react-native-reanimated ~4.2:** UI-thread animations — 60fps marker interpolation, bundled with SDK 55, New Architecture native
- **expo-blur ~55.0:** Glassmorphism — stable Android support arrived in SDK 55 via RenderNode API
- **Redux Toolkit ~2.11 + react-redux ~9.2:** State management — PRD-specified, handles complex real-time state across multiple consumers
- **redux-persist ~6.0 + AsyncStorage ~2.1:** Favorites persistence — simple key-value storage for favorite route/stop IDs
- **gtfs-realtime-bindings ~1.1:** Protobuf decoding — official MobilityData bindings, pure JS, Hermes-compatible with caveats
- **@shopify/flash-list ~2.x:** High-performance lists — 60fps scroll inside bottom sheet, New Architecture native
- **RTK Query (via @reduxjs/toolkit):** ETA predictions — `createApi` for FastAPI `/api/eta/predict` REST endpoint

**What not to use:** expo-maps (no custom marker support, iOS 17+ only), Socket.IO (feeds are S3 static files, not WebSocket), NativeWind (fights the precise Academic Navigator design system), react-native-mmkv (overkill for storing a few IDs), Expo SDK 52/53/54.

### Expected Features

The feature landscape is tightly defined by the PRD. The core value proposition is visible bus positions + ML-powered ETAs, wrapped in a premium Academic Navigator visual identity. No other campus transit app delivers this level of design polish.

**Must have (table stakes):**
- Live bus positions on map — core value; animated markers updating every 5 seconds
- Bus arrival ETAs — dual source: GTFS-RT callout ETAs + XGBoost stop list ETAs
- Route list with active status — GTFS static data + vehicle count from real-time feed
- Stop list per route (ordered) — GTFS stop_times.txt by stop_sequence
- Route polyline on map — GTFS shapes.txt decoded coordinates
- Stale data filtering — filter vehicles with timestamp older than 2 minutes
- Auto-refresh without user intervention — 5-second polling architecture
- Loading and error states — network errors, empty states, stale data banners

**Should have (differentiators):**
- Glassmorphic bottom sheet with three snap points — collapsed / half / full; premium Academic Navigator identity
- Glass-panel callout bubbles — BlurView backdrop on bus and stop taps
- XGBoost model ETAs (85.6s MAE) — 87.9% more accurate than naive schedule
- Passenger capacity bars — VehiclePosition.load / capacity fill bar
- Smooth animated marker movement — AnimatedRegion with 1000ms position interpolation
- Dual-font editorial typography — Manrope headlines + Inter data labels
- Favorite routes with local persistence — personalization for daily commuters
- No-line tonal layering design — background color shifts replace borders

**Defer (v2+):**
- Search — complex text matching, placeholder icon only in MVP
- Dark mode — doubles design system work, structure tokens for easy addition later
- Push notifications — requires backend notification service
- Trip planner — requires routing engine
- Nearest stop via GPS — visual identification from "My Location" button is sufficient
- Background location tracking — PRD explicitly prohibits

### Architecture Approach

This is a single-screen app with internal view navigation driven by Redux UI state, not route-based navigation. The map layer (react-native-maps MapView) renders full-screen and is always visible. The bottom sheet sits on top of the map and shows one of three views — RouteListView, RouteDetailView, or StopDetailView — based on `ui.selectedRouteId` and `ui.selectedStopId` in the Redux store. There is no React Navigation stack inside the sheet; embedding one would create gesture conflicts and state desynchronization.

Real-time data arrives through two channels: a singleton polling service fetches GTFS-RT protobuf feeds every 5 seconds and dispatches to Redux, and RTK Query manages the XGBoost ETA prediction REST API with 15-second refetch intervals when a route is selected. AppState listeners start and stop polling based on foreground/background — not component lifecycle — to prevent orphaned intervals.

**Major components:**
1. **MapLayer** — Full-screen MapView; hosts BusMarkerLayer, StopMarkerLayer, RoutePolyline, BusCallout, StopCallout; reads from Redux vehicles and selectedRoute
2. **BusMarkerLayer** — Animates bus markers using AnimatedRegion refs stored in a `useRef(Map)` keyed by vehicleId; reuses refs across poll cycles to prevent memory leaks
3. **BottomSheet + Views** — @gorhom/bottom-sheet container with GlassBackground; conditionally renders RouteListView / RouteDetailView / StopDetailView based on Redux UI state; FlashList inside for 60fps list scroll
4. **GTFSPollingService** — Singleton TypeScript class (not a React component); manages `setInterval` lifecycle tied to AppState; fetches and decodes two protobuf feeds (position_updates.pb every 5s, alerts.pb every 60s); dispatches to Redux
5. **ETAPredictionService (RTK Query)** — `createApi` pointing at FastAPI; 15-second refetch when route is selected; provides automatic caching and loading/error states
6. **Redux Store** — Six slices: routesSlice (GTFS static, cached), vehiclesSlice (real-time positions), predictionsSlice (XGBoost ETAs), uiSlice (selectedRouteId, selectedStopId, sheetPosition), preferencesSlice (favorites, persisted), alertsSlice (service alerts)
7. **Theme System** — Design token files in `theme/` for colors, typography, spacing, shadows; all components import tokens, no hardcoded hex values; Academic Navigator color palette

### Critical Pitfalls

1. **Android bitmap marker rendering** — Android does not support live React views as map markers; it takes a bitmap snapshot. Complex component markers will cause blank/stale markers and frame drops below 30fps. Prevention: use simple SVG markers, `tracksViewChanges={false}` after initial render, set it `true` only momentarily on content change. Test on a mid-range Android device immediately after markers work on iOS Simulator.

2. **Orphaned polling intervals** — `setInterval` inside `useEffect` accumulates multiple concurrent timers when components remount during bottom sheet transitions or in React Strict Mode. Prevention: singleton service class; `isPolling` guard flag; start/stop tied exclusively to AppState, not component lifecycle.

3. **Protobuf decoding in Hermes** — `gtfs-realtime-bindings` uses `protobufjs` dynamic `require()` calls that generate Metro require-cycle warnings. In some configurations, decoding silently returns malformed output. Prevention: validate decode output structure (confirm `feed.entity` is an array with expected fields), add explicit error handling around every `FeedMessage.decode()` call, test on both platforms in Phase 2 before building on top of it.

4. **Bottom sheet + map gesture conflict** — Both the sheet and the map respond to vertical pan gestures. Prevention: configure `enableContentPanningGesture` correctly on @gorhom/bottom-sheet; verify the map remains interactive at the "half" snap point (sheet covers 45%, map covers 55%); the grab handle is the primary drag target, not the content area.

5. **AnimatedRegion memory leak** — Creating new `AnimatedRegion` instances on every 5-second poll cycle allocates native animation resources that are never freed. Prevention: store refs in `useRef(new Map())` keyed by vehicleId; reuse existing refs; remove refs for vehicles removed by the stale filter.

---

## Implications for Roadmap

Based on the combined research, the recommended phase structure has 6 phases ordered by dependency chain and risk exposure.

### Phase 1: Foundation and Map Shell

**Rationale:** Prove the hardest dependency first — react-native-maps integration with Expo SDK 55 New Architecture. The config plugin issue (expo/expo#42423) has been resolved but should be validated immediately before anything else is built on top of it. Establish the design token system and Redux store structure while scaffolding, so all subsequent phases inherit a clean foundation.

**Delivers:** Running Expo SDK 55 project with full-screen map, static test markers, design token system, Redux store configured with all six slices (initially empty), FloatingControls layout, expo-blur confirmed working on both platforms.

**Addresses features:** Route polyline (static), stop markers (static), map layout.

**Avoids pitfalls:** Discovering SDK 55 / react-native-maps incompatibility late (Pitfall #1 setup), font loading flash (Pitfall #11) via splash screen hold.

### Phase 2: GTFS-RT Polling and Data Pipeline

**Rationale:** All interactive features depend on real-time vehicle data. The protobuf decoding risk (Pitfall #4) must be resolved before any UI is built around vehicle positions. Discovering a silent decode failure after building 3 phases of UI on top of it would be catastrophic. Build the polling service, decode both feeds, populate Redux, and render non-animated bus markers to confirm end-to-end data flow.

**Delivers:** GTFSPollingService singleton; GTFS-RT position + trip update feeds decoded and dispatched to Redux; non-animated bus markers on map (functional, not pretty); stale vehicle filtering; AppState polling lifecycle; CORS and network error handling validated.

**Uses:** gtfs-realtime-bindings, Redux vehiclesSlice, singleton service pattern from ARCHITECTURE.md.

**Avoids pitfalls:** Protobuf decode failure (Pitfall #4) — validate on both iOS and Android early; orphaned intervals (Pitfall #3) — singleton service from day one.

### Phase 3: Bottom Sheet and Route List

**Rationale:** The bottom sheet is the primary navigation surface. It must be in place before route detail, stop detail, or ETA views can be built inside it. This phase also delivers the most visible differentiator (glassmorphism) and validates gesture boundaries with the live map — the gesture conflict pitfall is discovered and resolved here.

**Delivers:** @gorhom/bottom-sheet with three snap points; GlassBackground (expo-blur backgroundComponent); RouteListView with FlashList of route cards; active bus count derived selectors; favorites pill toggle; AlertsSection (conditional); gesture conflict between map and sheet resolved.

**Uses:** @gorhom/bottom-sheet v5.2, expo-blur, FlashList, Redux routesSlice and vehiclesSlice, memoized selectors.

**Avoids pitfalls:** Glassmorphism blur disappearing (Pitfall #6) — test on both platforms; gesture conflict (Pitfall #2) — verified at each snap point; re-render storm (Pitfall #7) — memoized selectors from the start.

### Phase 4: Route Detail, Stop List, and XGBoost ETAs

**Rationale:** Once the route list works and the data pipeline is proven, add the second layer of navigation (RouteDetailView) and integrate the ML ETA API. This phase delivers the highest-value differentiator: multi-stop XGBoost ETAs displayed in a stop timeline. The RTK Query ETA API integration should be straightforward once the FastAPI contract is confirmed.

**Delivers:** RouteDetailView inside bottom sheet; stop list timeline with XGBoost ETAs; RTK Query ETA API integration; route polyline and stop markers activating on route selection; map camera auto-fit on route selection; back navigation (Redux state clear).

**Uses:** RTK Query (createApi), predictionsSlice, uiSlice, GTFS stop_times data, react-native-maps polylines.

**Avoids pitfalls:** Map camera conflict (Pitfall #9) — auto-fit on selection only, not on every poll; stale static data (Pitfall #10) — version hash check on GTFS cache.

### Phase 5: Animated Markers and Callout Bubbles

**Rationale:** Marker animation is a polish feature, not a functional requirement. Non-animated markers with position jumps are functional. Adding animation after core features work means the Android bitmap pitfall (Pitfall #1) is isolated to this phase — if animation causes Android issues, it can be tuned or simplified without blocking the rest of the app. This is the highest-risk phase technically.

**Delivers:** AnimatedRegion-based bus marker position interpolation (1000ms); heading rotation with wraparound correction; BusCallout glass-panel bubble (tap bus marker); StopCallout glass-panel bubble (tap stop marker); `tracksViewChanges` management; per-vehicleId AnimatedRegion ref map.

**Uses:** react-native-maps AnimatedRegion, useAnimatedMarkers hook, Reanimated 4.

**Avoids pitfalls:** Android bitmap rendering (Pitfall #1) — simple SVG markers, tracksViewChanges off; AnimatedRegion memory leak (Pitfall #5) — ref-based management; heading wraparound (Pitfall #13).

### Phase 6: Stop Detail, Favorites, Alerts, and Polish

**Rationale:** These are lower-complexity features that complete the MVP feature set. Stop detail view, favorites persistence, and alerts are independent of each other and can be built in any order. Performance tuning (memoized selectors, React.memo) and edge case handling (error states, empty states, ETA display rounding) are addressed here as finishing work.

**Delivers:** StopDetailView with LIVE badge, capacity bars, arriving buses list; favorites persistence (AsyncStorage + redux-persist); AlertsSection populated from alerts feed; capacity bars in route detail; ETA display edge cases (< 1 min, Arriving, rounding); error states and empty state screens; performance audit with createSelector.

**Uses:** preferencesSlice + redux-persist, AsyncStorage, alertsSlice, CapacityBar component.

**Avoids pitfalls:** ETA rounding edge cases (Pitfall #12) — Math.ceil for >= 60s, "< 1 min" for < 60s, "Arriving" for 0; re-render storm (Pitfall #7) — final selector audit.

### Phase Ordering Rationale

- Map before data: Proves the most opaque compatibility constraint (SDK 55 + react-native-maps New Architecture) before building anything on top of it.
- Data before bottom sheet: The route list shows active bus counts; without a working vehicle data pipeline, the route list is a static mock that will need to be re-tested after integration anyway.
- Bottom sheet before ETAs: The stop list view must exist before ETA data can be displayed inside it. Building ETA API integration before the UI container exists inverts the dependency order.
- Animation last: Animated markers are premium polish, not functional requirements. Bus positions displaying with a jump every 5 seconds is usable. Animation adds the two highest-risk pitfalls (Android bitmap, memory leaks) and should be isolated to its own phase where it cannot block other features.
- Favorites/stop detail at the end: These are additive features with no dependencies from other phases. They can be built in any order after core navigation works.

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 1:** Validate exact `npx expo install react-native-maps` version output against SDK 55 and confirm Fabric renderer is enabled in the generated native project. The PR #43884 fix may have edge cases with the config plugin.
- **Phase 2:** Validate `gtfs-realtime-bindings` / `protobufjs` behavior in Hermes v1 (SDK 55 optional engine). Confirm the Auburn S3 feed URLs, payload format, and update cadence before implementing the polling service.
- **Phase 4:** Confirm the FastAPI `/api/eta/predict` request/response schema before building the RTK Query createApi definition. The ETA model exists but the API contract needs to be reviewed against the existing FastAPI source.
- **Phase 5:** Android marker animation performance must be validated on a real mid-range Android device. The iOS Simulator does not exercise the bitmap rendering constraint. Cannot assess final marker quality until tested on hardware.

Phases with standard patterns (skip research-phase):

- **Phase 3:** @gorhom/bottom-sheet glassmorphism is a documented pattern with known solutions. expo-blur is first-party. Standard implementation.
- **Phase 6:** Favorites with AsyncStorage + redux-persist, capacity bars, and error state handling are all established patterns with no unknown variables.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM-HIGH | All libraries are established and version-compatible. The one partially-unverified item is react-native-maps behavior after the SDK 55 config plugin fix — the PR merged but downstream edge cases are possible. All other stack decisions are HIGH confidence. |
| Features | HIGH | PRD.md and PROJECT.md define the feature scope with exceptional specificity. No ambiguity about what is in vs. out of MVP. Feature dependencies are explicitly mapped. |
| Architecture | HIGH | Single-screen + bottom sheet is a well-established React Native pattern. Redux + singleton polling service is proven by the existing `Code/etaspot_reference.ts` reference code. Component hierarchy is fully designed. |
| Pitfalls | HIGH | All identified pitfalls have root cause analysis, detection signals, and concrete mitigations. The Android bitmap issue and protobuf decode issues are well-documented in GitHub issues and have known workarounds. No unknown unknowns surfaced. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **react-native-maps SDK 55 exact version pairing:** Run `npx expo install react-native-maps` at project init and immediately confirm the output version, run on both platforms, and validate that the Fabric/New Architecture renderer is active. Do this in Phase 1 before any marker work.
- **Protobuf in Hermes v1 (SDK 55 optional engine):** It is unclear whether SDK 55's optional Hermes v1 engine changes `protobufjs` require-cycle behavior. Test `gtfs-realtime-bindings` decode output on both platforms with a sample protobuf payload at the start of Phase 2.
- **FastAPI ETA endpoint contract:** The XGBoost model and FastAPI service exist but the exact `/api/eta/predict` request schema (required fields, format of vehicleId, routeId, stopId) and response schema need to be reviewed against FastAPI source before building the RTK Query `createApi` definition in Phase 4.
- **expo-blur in @gorhom/bottom-sheet backgroundComponent on Android:** SDK 55 brought stable Android blur, but the specific `backgroundComponent` integration with @gorhom/bottom-sheet v5.2 may still surface the blur-disappearing-after-animation bug (Pitfall #6). Test in Phase 3 with a fallback strategy ready (absolute-positioned BlurView behind sheet content).
- **Auburn S3 GTFS-RT feed URL structure:** The reference code hints at the feed URL pattern but the exact S3 bucket URLs for `position_updates.pb`, `trip_updates.pb`, and `alerts.pb` should be confirmed against the existing backend configuration before Phase 2.

---

## Sources

### Primary (HIGH confidence)

- PRD.md — Full feature specification, design system, state shape, performance targets
- Code/etaspot_reference.ts — Existing polling service reference implementation
- [Expo SDK 55 Changelog](https://expo.dev/changelog/sdk-55) — SDK 55 features and breaking changes
- [react-native-maps GitHub](https://github.com/react-native-maps/react-native-maps) — v1.27 compatibility, New Architecture support
- [@gorhom/bottom-sheet npm](https://www.npmjs.com/package/@gorhom/bottom-sheet) — v5.2 Reanimated 4 support
- [Redux Toolkit docs](https://redux-toolkit.js.org/) — RTK Query, createSlice patterns
- [react-native-reanimated docs](https://docs.swmansion.com/react-native-reanimated/) — v4 UI thread animation
- [expo-blur docs](https://docs.expo.dev/versions/latest/sdk/blur-view/) — Android stable support in SDK 55
- [@expo-google-fonts packages](https://github.com/expo/google-fonts) — Manrope and Inter font loading
- [Expo Maps introduction](https://expo.dev/blog/introducing-expo-maps-a-modern-maps-api-for-expo-developers) — Why expo-maps was rejected

### Secondary (MEDIUM confidence)

- [expo/expo#42423](https://github.com/expo/expo/issues/42423) — SDK 55 Google Maps config plugin issue (PR #43884 resolved)
- [gorhom/bottom-sheet#2388](https://github.com/gorhom/react-native-bottom-sheet/issues/2388) — Blur disappearing after animation
- [gorhom/bottom-sheet#2546](https://github.com/gorhom/react-native-bottom-sheet/issues/2546) — Reanimated v4 compatibility
- [react-native-maps#2382](https://github.com/react-native-maps/react-native-maps/issues/2382) — Marker animation Android issues
- [react-native-maps#4551](https://github.com/react-native-maps/react-native-maps/issues/4551) — MarkerAnimated issues
- [protobufjs#1137](https://github.com/protobufjs/protobuf.js/issues/1137) — Expo require cycle warnings

### Tertiary (LOW confidence — validate during implementation)

- Hermes v1 + protobufjs behavior — not yet tested in this configuration
- FastAPI ETA endpoint schema — assumed from ETA model design but requires code review
- Auburn S3 feed URL structure — inferred from reference code, not confirmed

---

*Research completed: 2026-03-25*
*Ready for roadmap: yes*
