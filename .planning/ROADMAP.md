# Roadmap: Tiger Transit Frontend

## Overview

This roadmap delivers a real-time bus tracking app for Auburn University's Tiger Transit system. The build progresses from proving the hardest integration risk (maps on Expo SDK 55) through establishing the real-time data pipeline (ETASpot PHP API via Supabase proxy), then layering the glassmorphic bottom sheet UI, route detail with ETAs, animated markers with callouts, and finally completing the feature set with stop detail, favorites, alerts, and error handling. Each phase delivers a coherent, testable capability that the next phase builds on.

**Data pipeline pivot (2026-03-26):** Replaced GTFS-RT protobuf feeds with ETASpot PHP API for vehicle positions and ETAs. PHP provides richer data (multi-stop ETAs, delay, capacity, heading, timepoints) and is proxied through Supabase for scalability. Protobuf retained only for service alerts. Phase 2 requires replanning.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation and Map Shell** - Expo SDK 55 project with full-screen map, design token system, and Redux store scaffold (completed 2026-03-25)
- [ ] **Phase 2: Real-Time Data Pipeline** - ETASpot PHP API via Supabase proxy, live bus markers on map (rework: replacing protobuf with PHP API)
- [x] **Phase 3: Bottom Sheet and Route List** - Glassmorphic draggable bottom sheet with sectioned route browsing (completed 2026-03-26)
- [x] **Phase 4: Route Detail and ETA Predictions** - Route detail view with ordered stop list, XGBoost ETAs, polyline and stop markers on map (completed 2026-03-26)
- [x] **Phase 5: Animated Markers and Callout Bubbles** - Smooth marker animation and interactive glass-panel callouts (completed 2026-03-28)
- [ ] **Phase 6: Stop Detail, Favorites, Alerts, and Polish** - Remaining features to complete the MVP

## Phase Details

### Phase 1: Foundation and Map Shell
**Goal**: User opens the app and sees a full-screen map of Auburn campus with the Academic Navigator design system fully established
**Depends on**: Nothing (first phase)
**Requirements**: MAP-01, MAP-08, DS-01, DS-02, DS-03, DS-04, DS-05, DS-06, DS-07, DS-08
**Success Criteria** (what must be TRUE):
  1. App launches on both iOS and Android and displays a full-screen map centered on Auburn campus (~32.606, -85.487) within 2 seconds
  2. Floating glass-panel map controls (my_location, search placeholder, settings placeholder) are visible and tappable above the map
  3. Manrope and Inter fonts render correctly in test labels with the full type scale (Headline-LG, Title-MD, Body-MD, Label-SM)
  4. Design tokens (tonal layering colors, navy-tinted shadows, 8px grid spacing, 20px edge margins) are applied to test components and produce the Academic Navigator look
  5. Redux store initializes with all six slices (routes, vehicles, predictions, ui, preferences, alerts) and renders without errors on both platforms
**Plans:** 2/2 plans complete

Plans:
- [x] 01-01-PLAN.md -- Expo project init, design system tokens, fonts, Redux store scaffold
- [x] 01-02-PLAN.md -- Full-screen map, splash screen, glassmorphic bottom bar, floating location button

### Phase 2: Real-Time Data Pipeline (REWORK)
**Goal**: Users see live bus positions on the map updating every 5 seconds via ETASpot PHP API proxied through Supabase
**Depends on**: Phase 1
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, MAP-02, MAP-04, MAP-09
**Success Criteria** (what must be TRUE):
  1. Supabase backend proxy polls ETASpot PHP `get_vehicles` every 5s and upserts vehicle data into a `vehicles` table with route ID mapping
  2. Client reads vehicle positions from Supabase (Realtime subscription or polling) and renders bus markers at correct positions
  3. Bus markers show directional heading (from PHP `h` field) and use route-colored markers
  4. Polling stops when the app is backgrounded and resumes immediately when foregrounded
  5. Vehicles with `receiveTime` older than 2 minutes are filtered out
  6. Multi-stop ETAs from PHP `minutesToNextStops` are available in Redux for Route Detail View
**Plans:** 2 plans

Plans:
- [ ] 02-01-PLAN.md -- Supabase Edge Function + DB migrations (vehicles table, position_history, pg_cron 5s polling, ETASpot PHP transform with route ID mapping and deduplication)
- [ ] 02-02-PLAN.md -- Client Supabase integration (SDK install, Realtime subscription hook, MapScreen rewire, protobuf code archival)

### Phase 3: Bottom Sheet and Route List
**Goal**: Users can browse all routes via a glassmorphic draggable bottom sheet with active bus counts and visual polish
**Depends on**: Phase 2
**Requirements**: SHEET-01, SHEET-02, SHEET-03, SHEET-04, SHEET-05, ROUTE-01, ROUTE-02, ROUTE-03, ROUTE-04, ERR-02, ERR-03
**Success Criteria** (what must be TRUE):
  1. Bottom sheet drags smoothly between three snap points (collapsed ~80px, half ~45%, full ~90%) with spring animation and a visible grab handle pill
  2. Bottom sheet uses frosted-glass glassmorphic styling with backdrop blur and the map remains fully interactive (pan/zoom) when the sheet is at half position
  3. Route list displays sectioned layout (Active Routes, Favorites placeholder, Alerts placeholder) with each card showing route color accent, short name, long name, active bus count, and next ETA
  4. Route cards use Level 2 surfaces on Level 1 section backgrounds with no border lines (tonal layering only)
  5. Inactive routes (0 active buses) appear dimmed, sorted to bottom, and show "No active buses" message
**Plans:** 3/3 plans complete

Plans:
- [x] 03-01-PLAN.md -- Draggable glassmorphic bottom sheet with three snap points, spring animation, and map interaction
- [x] 03-02-PLAN.md -- Route list with color-accented cards, active bus counts, and alphabetical sorting
- [x] 03-03-PLAN.md -- Gap closure: inactive sort-to-bottom, Favorites/Alerts section placeholders, ROUTE-02 requirement correction

### Phase 4: Route Detail and ETA Predictions
**Goal**: Users can tap a route to see its full stop list with ML-powered arrival predictions and the route drawn on the map
**Depends on**: Phase 3
**Requirements**: ROUTE-05, ROUTE-06, ROUTE-07, ROUTE-08, ROUTE-09, ROUTE-10, MAP-05, MAP-06, MAP-07, ETA-02, ETA-03, ETA-04
**Success Criteria** (what must be TRUE):
  1. Tapping a route card transitions the sheet to Route Detail View showing route name in Headline-LG (32pt Manrope Bold) with color bar, and draws the route polyline plus stop markers on the map in route color
  2. Map auto-fits to show all stops and active buses for the selected route
  3. Ordered stop list displays next 3 arrival ETAs per stop from XGBoost model predictions, formatted as "3 min", "< 1 min", or "No buses en route"
  4. Tapping a stop in the list centers the map on that stop, and a back button returns to the route list
  5. If model prediction times out, ETAs fall back to GTFS-RT trip update data or show "ETA unavailable"
**Plans:** 3/3 plans complete

Plans:
- [x] 04-01-PLAN.md -- GTFS static data bundling (stops, shapes, routeStops as TypeScript constants), useStaticRouteData hook, FastAPI batch ETA endpoint stub
- [x] 04-02-PLAN.md -- Route Detail View with sticky header, transit-diagram stop list, GTFS-RT ETAs, RouteCard onPress wiring
- [x] 04-03-PLAN.md -- Route polyline, stop markers, map auto-fit, stop-tap-to-center, bus dimming on route select

### Phase 5: Animated Markers and Callout Bubbles
**Goal**: Bus markers animate smoothly between positions and tapping markers opens informative glass-panel callouts
**Depends on**: Phase 4
**Requirements**: MAP-03, CALL-01, CALL-02, CALL-03, CALL-04, CALL-05, ETA-01
**Success Criteria** (what must be TRUE):
  1. Bus markers animate smoothly between position updates with 1000ms Reanimated-based interpolation (no visible jumps) on both iOS and Android
  2. Tapping a bus marker opens a glass-panel callout showing route, bus ID, passengers, delay status, and next-stop ETA from PHP `nextStopETA`
  3. Tapping a stop marker opens a glass-panel callout showing stop name, stop number, ETA, route badges, and a "View More" link
  4. Only one callout can be open at a time, tapping outside dismisses it, and callout data refreshes with each 5-second polling cycle
**Plans:** 2/2 plans complete

Plans:
- [x] 05-01-PLAN.md -- Animated bus markers with playback buffer polyline interpolation, minutesToNextStops data surfacing
- [ ] 05-02-PLAN.md -- Glassmorphic callout bubbles for bus and stop markers, marker onPress wiring, dismiss behavior

### Phase 6: Stop Detail, Favorites, Alerts, and Polish
**Goal**: All remaining MVP features are complete -- users can inspect stop details, manage favorite routes, view service alerts, and encounter graceful error handling
**Depends on**: Phase 5
**Requirements**: STOP-01, STOP-02, STOP-03, STOP-04, STOP-05, STOP-06, STOP-07, FAV-01, FAV-02, FAV-03, FAV-04, ALERT-01, ALERT-02, ERR-01, ETA-05
**Success Criteria** (what must be TRUE):
  1. Stop Detail View shows stop name, stop number, route count, city, a pulsing LIVE badge when buses are arriving, arriving bus cards with delay status and ETA (from PHP `get_stop_etas`), passenger capacity bars, and color-coded route pill badges in the footer
  2. User can favorite a route via star button in Route Detail, see favorites pinned to top of route list in a Favorites section, toggle between "All Routes" and "Favorites" via pill tab, and favorites persist across app sessions
  3. Service alerts from the GTFS-RT protobuf alerts feed appear in the Alerts section of the route list, polled every 60 seconds
  4. When network is lost, the app shows last known positions dimmed with a "No connection" glass-panel banner
  5. Tapping a route badge in the Stop Detail footer switches to that route's detail view
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2 -> 3 -> 4 -> 5 -> 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and Map Shell | 2/2 | Complete   | 2026-03-25 |
| 2. Real-Time Data Pipeline (REWORK) | 0/2 | Planned (2 plans, 2 waves) | - |
| 3. Bottom Sheet and Route List | 3/3 | Complete | 2026-03-26 |
| 4. Route Detail and ETA Predictions | 3/3 | Complete | 2026-03-26 |
| 5. Animated Markers and Callout Bubbles | 2/2 | Complete   | 2026-03-28 |
| 6. Stop Detail, Favorites, Alerts, and Polish | 0/? | Not started | - |
