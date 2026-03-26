# Phase 3: Bottom Sheet and Route List - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Glassmorphic draggable bottom sheet with three snap points (collapsed, half, full) and a scrollable route list as the default sheet content. Users can browse all Tiger Transit routes with live bus counts. No route detail view, no stop list, no ETAs, no callouts, no favorites functionality.

</domain>

<decisions>
## Implementation Decisions

### Route card design
- Left edge stripe (4px vertical bar in route color) AND subtle tinted background (~5-8% opacity route color wash over card surface)
- Compact two-line layout: long name as primary text, short name deemphasized in parentheses (may change later)
- Bus count as simple text label: "2 buses active" or "No active buses" in muted text
- No ETA on route cards — ETAs are a Phase 4 concern (per-stop in Route Detail View)
- Cards are Level 2 surfaces on Level 1 section background — tonal layering only, no border lines

### Sheet snap & interaction
- Three snap points: collapsed (~80px), half (~45%), full (~90%)
- Collapsed state keeps current GlassBottomBar content (grab handle + search bar + settings icon) — Phase 3 wraps it with drag/snap behavior
- Collapsed is the minimum — sheet never fully hides, always one swipe away
- Tapping search bar at half position auto-expands sheet to full
- Route cards render immediately as sheet drags up — no loading skeleton (data already in Redux)
- Spring animation for snap transitions

### Route list organization
- Single section: "Active Routes" header only — no Favorites or Alerts sections until Phase 6
- Alphabetical sort by long name — stable position regardless of bus activity
- Inactive routes (0 active buses) stay in their alphabetical position but dimmed (~50% opacity) with "No active buses" text
- When no buses are running at all: full alphabetical list with every card dimmed — no empty state message, consistent behavior

### ETA approach
- Phase 3 builds no ETA infrastructure — cards show route name + bus count only
- Phase 4 adds Route Detail View with per-stop ML-powered ETAs as a new screen inside the sheet

### Claude's Discretion
- Bottom sheet library choice (react-native-bottom-sheet, reanimated gesture handler, etc.)
- Spring animation parameters (damping, stiffness)
- Exact card spacing and padding within the 8px grid
- Scroll-vs-drag conflict resolution at full position
- Map padding adjustment when sheet is at half/full
- ERR-03 loading state implementation during initial data fetch
- Section header typography and styling

</decisions>

<specifics>
## Specific Ideas

- The GlassBottomBar was intentionally built as a self-contained component for Phase 3 to wrap — not rewrite
- Route cards should feel like a quick glance: "which routes are running right now?" — detailed info comes when you tap into a route (Phase 4)
- Inactive routes staying in their alphabetical position means a student's route is always in the same spot — they build muscle memory for where to look
- The left stripe + tinted background combo gives each card route identity without being garish against the Academic Navigator neutral palette

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `GlassBottomBar.tsx`: Self-contained 80px bar with glassmorphism, grab handle, search, settings — designed to be wrapped with drag/snap
- `routesSlice.ts`: Redux slice with `list: Route[]`, `stops`, `shapes`, `loading`, `error` and all actions
- `uiSlice.ts`: Has `sheetPosition` state (collapsed/half/full), `selectedRouteId`, `setSheetPosition` action
- `vehiclesSlice.ts`: `positions: VehiclePosition[]` — count vehicles per routeId for bus count
- `useStaticData.ts`: Hook that hydrates ROUTES into Redux on mount
- `useGtfsPolling.ts`: Hook that starts 5s polling lifecycle — vehicle positions already flowing

### Established Patterns
- Glassmorphism: BlurView intensity={20} tint="light" + rgba(255,255,255,0.85) fallback
- Navy-tinted shadows: rgba(12, 35, 64, opacity) via `shadows.sheetAbove`
- Design tokens: `surfaces.level1`, `surfaces.level2`, `textColors`, `typography`, `spacing`, `EDGE_MARGIN`
- Silent failure UX: no nagging, no intrusive errors

### Integration Points
- `MapScreen.tsx`: Currently renders MapView + GlassBottomBar + FloatingLocationButton — sheet replaces GlassBottomBar
- Redux store: vehicles.positions needs grouping by routeId to compute per-route bus counts
- `mapPadding` on MapView may need adjustment when sheet is at half/full position

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 03-bottom-sheet-and-route-list*
*Context gathered: 2026-03-25*
