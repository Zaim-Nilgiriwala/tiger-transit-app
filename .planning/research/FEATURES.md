# Feature Landscape

**Domain:** Real-time university transit tracking mobile app
**Researched:** 2026-03-25

## Table Stakes

Features users expect from a transit tracking app. Missing = product feels broken.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Live bus positions on map | Core value prop. Every transit app shows this. | Medium | GTFS-RT position feed + animated markers. 5s polling. |
| Bus arrival ETAs | Second thing users look for after "where is the bus?" | Medium | Dual source: GTFS-RT feed ETAs (bus callout) + XGBoost model (stop list) |
| Route list with active status | Users need to find their route | Low | GTFS static data + vehicle count from real-time feed |
| Stop list per route (ordered) | Users need to find their stop | Low | GTFS stop_times.txt ordered by stop_sequence |
| Route polyline on map | Visual confirmation bus is on expected path | Low | GTFS shapes.txt decoded coordinates |
| Stale data filtering | Showing ghost buses destroys trust | Low | Filter vehicles with timestamp > 2 min old |
| Auto-refresh of real-time data | Users expect fresh data without manual intervention | Low | Already handled by 5s polling architecture |
| Loading and error states | Users need feedback when things fail | Low | Network errors, empty route lists, stale data banners |

## Differentiators

Features that set Tiger Transit apart from generic transit apps.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Glassmorphic bottom sheet with snap points | Premium "Academic Navigator" feel. No other campus transit app has this level of polish. | High | @gorhom/bottom-sheet + expo-blur. Three snap points (collapsed/half/full). |
| Glass-panel callout bubbles | Differentiated visual identity. Map bleeds through UI elements. | Medium | Custom components with BlurView backdrop. |
| XGBoost model ETAs (85.6s MAE) | 87.9% more accurate than naive schedule. Multi-stop predictions. | Medium | FastAPI backend already exists. Frontend needs REST calls + display. |
| Passenger capacity bars | No transit app shows real-time passenger load at a glance | Low | VehiclePosition.load / capacity. Simple fill bar. |
| Smooth animated marker movement | Bus icons glide between positions instead of jumping. Premium feel. | Medium | AnimatedRegion with 1000ms timing interpolation. |
| Dual-font editorial typography | Manrope headlines + Inter data = premium magazine feel, not utility-app feel | Low | @expo-google-fonts packages. Design token decision. |
| No-line tonal layering design | Removes visual noise. Feels modern and intentional. | Low | StyleSheet design tokens. No borders, just background color shifts. |
| Favorite routes with local persistence | Personalization for daily commuters | Low | AsyncStorage + redux-persist. Pill tab toggle. |

## Anti-Features

Features to explicitly NOT build in MVP.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Dark mode | Doubles design system work. PRD explicitly defers to v2. | Light mode only. Structure design tokens for easy dark mode later. |
| Search functionality | Complex text matching across routes/stops. PRD defers to v2. | Show search icon placeholder only. |
| Push notifications | Requires backend notification service. PRD defers to v2. | Alerts section in route list shows current disruptions. |
| Trip planner | Requires complex routing engine. PRD defers to v2. | One route at a time is sufficient for campus transit. |
| Nearest stop via GPS | Requires location permissions flow + distance logic. PRD defers to v2. | "My Location" button centers map. Users visually identify nearest stop. |
| Background location tracking | Battery drain. PRD explicitly prohibits. | Stop all polling when backgrounded. Resume on foreground. |
| Full offline mode | Complex caching strategy. | Show last known positions (dimmed) + "No connection" banner. |
| Tab bar navigation | Design evolved away from tabs. | Bottom sheet IS the navigation surface. |

## Feature Dependencies

```
GTFS Static Data Load --> Route List --> Route Detail --> Stop Detail
                     --> Route Polylines
                     --> Stop Markers on Map

GTFS-RT Feed Polling --> Vehicle Positions --> Bus Markers on Map
                    --> Trip Updates --> Bus Callout ETAs
                    --> Alerts Feed --> Alerts Section

Vehicle Positions + Route Selection --> XGBoost ETA API --> Stop List ETAs

Bottom Sheet Component --> Route List View --> Route Detail View --> Stop Detail View

Favorites (AsyncStorage) --> Route List Sort Order --> Favorites Section
```

## MVP Recommendation

Prioritize in this order:

1. **Map + bus markers with animated positions** -- Core value. Users see buses immediately.
2. **Bottom sheet with route list** -- Users need to find their route.
3. **Route detail with stop list + XGBoost ETAs** -- Users need arrival times.
4. **GTFS-RT polling service** -- Powers all real-time data.
5. **Glassmorphism + design system** -- The differentiator. Apply Academic Navigator tokens.
6. **Callout bubbles (bus + stop)** -- Tap interactions on map markers.
7. **Stop detail view** -- Deep-dive with LIVE badge, capacity bars.
8. **Favorites** -- Personalization for daily riders.
9. **Alerts section** -- Conditional section, lowest priority table-stakes feature.

Defer: Search, dark mode, notifications, trip planner, nearest stop, settings.

## Sources

- PRD.md -- Feature specifications and design system
- PROJECT.md -- Scope, constraints, and out-of-scope decisions
