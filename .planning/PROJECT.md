# Tiger Transit Frontend

## What This Is

A real-time bus tracking app for Auburn University's Tiger Transit system, built as a React Native (Expo) mobile app for iOS and Android. The app shows live bus positions on a full-screen map with a glassmorphic draggable bottom sheet for browsing routes, viewing ETAs, and inspecting stops. Vehicle positions and multi-stop ETAs come from the ETASpot PHP API (`service.php`) proxied through Supabase, with GTFS-RT protobuf feeds retained only for service alerts.

## Core Value

When a student pulls up the app, they see exactly where their bus is and when it arrives at their stop — accurate to ~85 seconds — with zero navigation complexity. One screen, one glance, answer found.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Full-screen map with animated bus markers (position, heading, route color)
- [ ] Glassmorphic draggable bottom sheet (collapsed / half / full snap points)
- [ ] Route list with sectioned layout (Active Routes cards, Favorites, Alerts)
- [ ] Route detail view with ordered stop list and next 3 ETAs per stop
- [ ] Stop Detail View with LIVE badge, arriving buses, capacity bars, route badges
- [ ] Glass-panel bus callout (route, bus ID, speed, passengers, delay status, ETA)
- [ ] Glass-panel stop callout (name, stop number, ETA, route badges, "View More")
- [ ] Route polyline + stop markers on map when route selected
- [ ] Favorite routes with pill tab toggle and local persistence
- [ ] Floating map controls (my_location, search placeholder, settings placeholder)
- [ ] ETASpot PHP API for vehicle positions and multi-stop ETAs (via Supabase proxy, 5s polling)
- [ ] XGBoost model ETA predictions via FastAPI backend (future upgrade over PHP ETAs)
- [ ] Service alerts from GTFS-RT protobuf alerts feed
- [ ] Stale vehicle filtering (> 2 min timestamp = hidden)
- [ ] Smooth marker animation (AnimatedRegion, 1000ms interpolation)

### Out of Scope

- Dark mode — deferred to v2, light mode only for MVP
- Search functionality — placeholder icon only, implementation in v2
- Settings screen — placeholder icon only, implementation in v2
- Push notifications — requires backend notification service, v2
- Trip planner / multi-route journeys — complex routing engine, v2
- Nearest stop via GPS — requires location permissions flow, v2
- Onboarding tutorial — ship and iterate based on user feedback
- Backend/API development — Supabase proxy worker for ETASpot PHP API is in scope; FastAPI already exists

## Context

- **Existing backend:** Supabase (PostgreSQL 17) with GTFS static data loaded. FastAPI inference server for XGBoost ETA predictions already deployed.
- **ETA model:** XGBoost v1.1 with 85.6s MAE (87.9% improvement over naive schedule). 68 input features including vehicle state, route context, temporal, historical, and weather data. Speed and route progress can be derived from position history stored in Supabase.
- **Primary data source:** ETASpot PHP API (`auburn.etaspot.net/service.php`) — provides vehicle positions, multi-stop ETAs (`minutesToNextStops`), delay status, capacity, heading, and timepoint data. Polled every 5s via Supabase backend proxy (1 request regardless of user count). Available endpoints: `get_vehicles`, `get_routes`, `get_stops`, `get_stop_etas`, `get_patterns`, `get_announcements`.
- **Alerts data:** GTFS-RT protobuf alerts feed from S3 (`position_updates.pb` retained as fallback, `trip_updates.pb` deprecated). Alerts polled at 60s.
- **Scale:** 28 active routes (via PHP API), 207 stops, Auburn campus and surrounding area.
- **Route ID mapping:** PHP API uses numeric route IDs; 3 require mapping to compound GTFS IDs (215→215_202_201_156, 226→226_32, 235→235_93).
- **Design prototypes:** Stitch project "Tiger Transit Map View" (ID: 17502641370854445841) contains the visual source of truth with a detailed "Academic Navigator" design system — glassmorphism, Manrope/Inter typography, tonal layering, no-border philosophy.
- **Reference code:** `Code/etaspot_reference.ts` contains working protobuf decoding logic using `gtfs-realtime-bindings`.
- **Prior work:** ETA model development completed (9 phases, archived in `.planning/archive/eta-model-full-backup/`). This is a greenfield frontend build connecting to the existing backend.

## Constraints

- **Platform:** React Native (Expo) — must work on both iOS and Android
- **Maps:** `react-native-maps` with Apple Maps (iOS) / Google Maps (Android)
- **Design system:** Must follow the "Academic Navigator" design system from Stitch — Manrope/Inter fonts, tonal layering, glassmorphism, no-border rule
- **Polling:** Backend polls ETASpot PHP API every 5s; client subscribes to Supabase Realtime or polls Supabase. Stops when app is backgrounded to preserve battery.
- **Performance:** Map visible in < 2s, route list in < 1s, marker animation at 60fps, < 150MB memory
- **Data format:** ETASpot PHP API returns JSON; GTFS-RT protobuf retained only for alerts feed
- **ETA display:** Round to nearest minute, "< 1 min" for under 60s, "No buses en route" when empty

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Single-screen map + bottom sheet (no tab bar) | Stitch prototypes evolved away from tabs; map-first philosophy reduces navigation friction | — Pending |
| Manrope + Inter dual-font system | Editorial feel from Manrope headlines, Inter legibility for data; validated in Stitch prototypes | — Pending |
| Glassmorphism for floating elements | Allows map to bleed through, reinforces map-first philosophy, premium feel | — Pending |
| No-border tonal layering | Reduces visual noise, creates editorial breathing room; core principle of Academic Navigator system | — Pending |
| Redux Toolkit for state management | Standard for React Native, handles complex real-time state well (vehicles, predictions, UI) | — Pending |
| ETASpot PHP API via Supabase proxy (replacing GTFS-RT protobuf for positions) | PHP provides richer data (multi-stop ETAs, delay, capacity, heading, timepoints) and refreshes ~5-7s. Supabase proxy ensures 1 request to ETASpot regardless of user count. Protobuf retained only for alerts. | — Pending |
| PHP `minutesToNextStops` for ETAs, XGBoost as future upgrade | PHP ETAs available immediately for all stops; XGBoost model upgrade deferred until feature pipeline built in Supabase | — Pending |
| Front End Design skill for component generation | Leverage AI-assisted code generation with Stitch prototypes as visual reference during execution | — Pending |

---
*Last updated: 2026-03-25 after initialization*
