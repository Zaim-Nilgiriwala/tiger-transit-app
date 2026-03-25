# Tiger Transit Frontend

## What This Is

A real-time bus tracking app for Auburn University's Tiger Transit system, built as a React Native (Expo) mobile app for iOS and Android. The app shows live bus positions on a full-screen map with a glassmorphic draggable bottom sheet for browsing routes, viewing ETAs, and inspecting stops. It connects to GTFS-Realtime protobuf feeds polled every 5 seconds and an XGBoost v1.1 ETA prediction model via a FastAPI backend on Supabase.

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
- [ ] GTFS-RT protobuf decoding (position updates + trip updates, 5s polling)
- [ ] XGBoost model ETA predictions via FastAPI backend
- [ ] Service alerts section from GTFS-RT alerts feed
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
- Backend/API development — Supabase + FastAPI already exist, frontend only

## Context

- **Existing backend:** Supabase (PostgreSQL 17) with GTFS static data loaded. FastAPI inference server for XGBoost ETA predictions already deployed.
- **ETA model:** XGBoost v1.1 with 85.6s MAE (87.9% improvement over naive schedule). 45 input features including vehicle state, route context, temporal, historical, and weather data.
- **Data feeds:** GTFS-RT protobuf feeds from ETA Spot (Auburn's transit provider) hosted on S3. Position updates + trip updates at 5s intervals, alerts at 60s.
- **Scale:** 38 routes, 178 stops across Auburn campus and surrounding area.
- **Design prototypes:** Stitch project "Tiger Transit Map View" (ID: 17502641370854445841) contains the visual source of truth with a detailed "Academic Navigator" design system — glassmorphism, Manrope/Inter typography, tonal layering, no-border philosophy.
- **Reference code:** `Code/etaspot_reference.ts` contains working protobuf decoding logic using `gtfs-realtime-bindings`.
- **Prior work:** ETA model development completed (9 phases, archived in `.planning/archive/eta-model-full-backup/`). This is a greenfield frontend build connecting to the existing backend.

## Constraints

- **Platform:** React Native (Expo) — must work on both iOS and Android
- **Maps:** `react-native-maps` with Apple Maps (iOS) / Google Maps (Android)
- **Design system:** Must follow the "Academic Navigator" design system from Stitch — Manrope/Inter fonts, tonal layering, glassmorphism, no-border rule
- **Polling:** 5s interval for vehicle positions, must stop when app is backgrounded to preserve battery
- **Performance:** Map visible in < 2s, route list in < 1s, marker animation at 60fps, < 150MB memory
- **Data format:** GTFS-RT protobuf binary — must decode client-side or via lightweight proxy
- **ETA display:** Round to nearest minute, "< 1 min" for under 60s, "No buses en route" when empty

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Single-screen map + bottom sheet (no tab bar) | Stitch prototypes evolved away from tabs; map-first philosophy reduces navigation friction | — Pending |
| Manrope + Inter dual-font system | Editorial feel from Manrope headlines, Inter legibility for data; validated in Stitch prototypes | — Pending |
| Glassmorphism for floating elements | Allows map to bleed through, reinforces map-first philosophy, premium feel | — Pending |
| No-border tonal layering | Reduces visual noise, creates editorial breathing room; core principle of Academic Navigator system | — Pending |
| Redux Toolkit for state management | Standard for React Native, handles complex real-time state well (vehicles, predictions, UI) | — Pending |
| GTFS-RT for bus callout ETAs, XGBoost for stop list ETAs | Feed ETAs are low-latency for single next-stop; model provides multi-stop predictions at higher accuracy | — Pending |
| Front End Design skill for component generation | Leverage AI-assisted code generation with Stitch prototypes as visual reference during execution | — Pending |

---
*Last updated: 2026-03-25 after initialization*
