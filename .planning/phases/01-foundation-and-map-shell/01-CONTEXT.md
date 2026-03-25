# Phase 1: Foundation and Map Shell - Context

**Gathered:** 2026-03-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Expo SDK 55 project with full-screen map centered on Auburn campus, the Academic Navigator design system tokens fully established, floating glass-panel controls, a static glassmorphic bottom bar (search + settings), and Redux store scaffold with all six slices. No route data, no live buses, no draggable sheet behavior.

</domain>

<decisions>
## Implementation Decisions

### Map appearance
- Default Apple Maps (iOS) / Google Maps (Android) styling — no custom map style JSON. The UI elements (glass panels, bottom bar, design tokens) carry the Academic Navigator identity, not the map tiles.
- Full campus overview zoom (~14.5) centered on ~32.606, -85.487 on launch
- Free rotation and tilt enabled (two-finger rotate, two-finger 3D tilt)
- Show user's current location as blue dot — request location permission on first launch

### Location permission
- Request once on first launch
- If denied: silent proceed — no blue dot, my_location button becomes no-op
- No re-prompt, no banner, no nagging. User can grant via device settings later.

### Control layout (diverges from PRD)
- **my_location button**: floating on the map, bottom-left, positioned above the collapsed bottom bar. Glass-panel styling with backdrop blur and navy-tinted shadow.
- **Search bar**: full-width text input inside the static bottom bar. Placeholder text: "Search routes or stops". Tapping shows "Coming soon" toast in Phase 1.
- **Settings icon**: top-right inside the static bottom bar. Tapping shows "Coming soon" toast in Phase 1.
- This layout replaces the PRD's three floating buttons in top-right. Only the location button floats on the map.

### Static bottom bar (Phase 1 sheet precursor)
- Fixed glassmorphic bar at the bottom (~80px), not draggable
- Contains: grab handle pill (top center), search bar (left), settings icon (right)
- Full glassmorphism applied: backdrop blur(20px), surface-container-lowest at ~85% opacity, navy-tinted shadow above, 20px top border radius
- Phase 3 converts this into the full draggable bottom sheet with snap points

### Launch experience
- Branded splash screen using existing logo file: `C:\Users\ryanp\Downloads\TT Logo.png`
- Background styling: Claude's discretion
- Include a subtle loading animation on the splash screen
- Hold splash until fonts are loaded AND map is initialized, then cross-fade (~300ms) to the map
- No intermediate states — user sees: splash with logo + animation -> fade -> map

### Design token fidelity
- Use PRD values as the starting point for all tokens (colors, shadows, spacing, blur values)
- Claude may adapt values if they look off on actual iOS/Android device rendering
- Goal: match the FEEL of the Academic Navigator design, not the exact numbers
- Document all deviations from PRD values

### Design system validation
- No extra test components needed beyond the real scoped UI elements
- The glass-panel location button, search bar, settings icon, grab handle, and bottom bar collectively exercise: glassmorphism, Manrope/Inter fonts, navy-tinted shadows, tonal layering, 8px grid spacing, 20px edge margins, 44x44pt tap targets, and WCAG AA contrast

### Claude's Discretion
- Splash screen background color/styling
- Loading animation style on splash
- Exact blur/shadow values if PRD values need device adaptation
- Redux slice initial shapes (must include all 6: routes, vehicles, predictions, ui, preferences, alerts)
- File/folder structure for the Expo project
- Font loading strategy implementation

</decisions>

<specifics>
## Specific Ideas

- The static bottom bar is a precursor to the Phase 3 draggable sheet — build it so Phase 3 can wrap it with drag/snap behavior without rewriting
- Splash screen uses an existing logo PNG, not a generated design
- The control layout diverges from the PRD intentionally — search and settings belong in the sheet context, not floating on the map

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `Code/etaspot_reference.ts`: Contains VehiclePosition interface and GTFS-RT feed URLs — useful for typing the Redux vehicle slice shape, but actual data fetching is Phase 2
- `ETA-Model/gtfs_data/`: GTFS static data files (routes.txt, stops.txt, shapes.txt) — needed for Redux route/stop slice shapes
- `C:\Users\ryanp\Downloads\TT Logo.png`: Splash screen logo asset

### Established Patterns
- No existing React Native code — this is a greenfield build
- ETA-Model uses Node.js/Python but none of that code carries over to the mobile app

### Integration Points
- Stitch project "Tiger Transit Map View" (ID: 17502641370854445841) is the visual source of truth for the design system
- GTFS-RT feed URLs (S3) will be consumed starting Phase 2
- FastAPI inference server for XGBoost ETAs will be consumed starting Phase 4

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-and-map-shell*
*Context gathered: 2026-03-25*
