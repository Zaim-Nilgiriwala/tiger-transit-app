---
phase: 03-bottom-sheet-and-route-list
plan: 02
subsystem: ui
tags: [react-native, redux, route-list, route-card, tonal-layering, bottom-sheet-content]

# Dependency graph
requires:
  - phase: 03-bottom-sheet-and-route-list
    provides: BottomSheet component with ScrollView children wrapper, sheet snap points
  - phase: 02-real-time-data-pipeline
    provides: Redux vehiclesSlice with live positions, routesSlice with route data
  - phase: 01-foundation
    provides: Design tokens (surfaces, typography, spacing, cardRadius, cardPadding)
provides:
  - RouteCard component with color stripe, tinted background, bus count, React.memo
  - RouteList component with alphabetical sorting, section header, live bus counts
  - MapScreen wired with RouteList as BottomSheet children
affects: [04-route-detail, 06-favorites]

# Tech tracking
tech-stack:
  added: []
  patterns: [hex-to-rgba-tint, memoized-bus-count-map, alphabetical-sort-with-inactive-dimming]

key-files:
  created: [src/components/sheet/RouteCard.tsx, src/components/sheet/RouteList.tsx]
  modified: [src/screens/MapScreen.tsx]

key-decisions:
  - "hexToRgba helper converts route color to 6% opacity tint for card background"
  - "React.memo on RouteCard to prevent re-renders during 5s polling updates"
  - "gap property on cardList container for spacing instead of marginBottom on each card"

patterns-established:
  - "Route color identity: 4px left stripe + 6% opacity tinted background"
  - "Bus count derivation: useMemo Map<routeId, count> from vehicles.positions"
  - "Inactive dimming: opacity 0.5 on card, routes stay in alphabetical position"

requirements-completed: [ROUTE-01, ROUTE-02, ROUTE-03, ROUTE-04, ERR-02]

# Metrics
duration: 2min
completed: 2026-03-26
---

# Phase 3 Plan 2: Route List Summary

**Route list with color-accented cards showing live bus counts, alphabetical sorting, and inactive dimming inside the glassmorphic bottom sheet**

## Performance

- **Duration:** 2 min
- **Started:** 2026-03-26T03:15:44Z
- **Completed:** 2026-03-26T03:17:51Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Built RouteCard with 4px color stripe, 6% opacity tinted background, two-line text layout (long name + short name + pluralized bus count), and 50% opacity dimming for inactive routes
- Built RouteList reading from both routes.list and vehicles.positions Redux slices with memoized bus count computation and alphabetical sort by longName
- Wired RouteList as BottomSheet children in MapScreen for the complete route browsing experience

## Task Commits

Each task was committed atomically:

1. **Task 1: Create RouteCard component with color stripe, tinted background, and bus count** - `618bce8` (feat)
2. **Task 2: Create RouteList component and wire into MapScreen as BottomSheet children** - `b111911` (feat)

## Files Created/Modified
- `src/components/sheet/RouteCard.tsx` - Individual route card with color stripe, tinted background, two-line text, inactive dimming, Pressable wrapper, React.memo
- `src/components/sheet/RouteList.tsx` - Sectioned route list with ACTIVE ROUTES header, memoized bus count map, alphabetical sort, level1 background
- `src/screens/MapScreen.tsx` - Added RouteList import and renders it as BottomSheet children

## Decisions Made
- Used hexToRgba helper to convert route hex color to rgba with 0.06 alpha for the tinted card background, keeping the implementation self-contained
- Applied React.memo on RouteCard since vehicle positions update every 5 seconds and most cards won't change between polls
- Used CSS gap property on the card list container rather than marginBottom on each card for cleaner spacing
- Middle dot separator (U+00B7) between short name and bus count for visual rhythm

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Route list is fully functional inside the bottom sheet
- RouteCard onPress prop is ready for Phase 4 route detail navigation
- Bus count derivation pattern (memoized Map from positions) can be reused in route detail
- Phase 3 is complete - all bottom sheet + route list requirements delivered

## Self-Check: PASSED

All created files exist. All commit hashes verified in git log.

---
*Phase: 03-bottom-sheet-and-route-list*
*Completed: 2026-03-26*
