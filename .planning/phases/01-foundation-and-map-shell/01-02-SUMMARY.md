---
phase: 01-foundation-and-map-shell
plan: 02
subsystem: ui
tags: [react-native-maps, expo-location, expo-blur, glassmorphism, mapview, location-permission, bottom-bar]

# Dependency graph
requires:
  - phase: 01-01
    provides: Design system tokens, fonts, Redux store, Expo project skeleton
provides:
  - Full-screen MapView centered on Auburn campus with rotation and 3D tilt
  - useLocation hook with foreground permission request and GPS tracking
  - FloatingLocationButton with glassmorphism and map centering
  - GlassBottomBar with grab handle, search placeholder, settings icon
  - Splash-to-map transition via font loading gate
  - showToast utility for placeholder feedback
affects: [02-01, 03-01, 03-02, 05-01]

# Tech tracking
tech-stack:
  added: []
  patterns: [absolute-overlay-components, blur-view-glassmorphism, location-permission-silent-denial, map-ref-forwarding]

key-files:
  created:
    - src/hooks/useLocation.ts
    - src/screens/MapScreen.tsx
    - src/components/map/FloatingLocationButton.tsx
    - src/components/map/GlassBottomBar.tsx
    - src/utils/toast.ts
  modified:
    - App.tsx

key-decisions:
  - "MapView uses default provider (Apple Maps iOS, Google Maps Android) -- no explicit provider prop set"
  - "Location button is no-op when permission denied, matching silent-denial UX pattern"
  - "GlassBottomBar built as self-contained component for Phase 3 drag/snap wrapping"
  - "BlurView with rgba background fallback for glassmorphism on both platforms"

patterns-established:
  - "Overlay components: Absolute-positioned children over MapView with correct z-order (map, bar, button)"
  - "Glass styling: BlurView intensity={20} with rgba background at 85-95% opacity for glass-panel effect"
  - "Silent permission denial: Request once, no re-prompt, no banner, no nagging on denial"
  - "Map ref pattern: useRef<MapView> passed as prop for programmatic map control"

requirements-completed: [MAP-01, MAP-08]

# Metrics
duration: 3min
completed: 2026-03-25
---

# Phase 1 Plan 02: Full-Screen Map, Splash Screen, Glassmorphic Bottom Bar, and Floating Location Button Summary

**Full-screen MapView on Auburn campus with glassmorphic bottom bar (search/settings placeholders), floating location FAB with BlurView blur, and silent location permission handling**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-25T22:07:35Z
- **Completed:** 2026-03-25T22:10:32Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- Full-screen MapView centered on Auburn campus (32.606, -85.487) with two-finger rotate and 3D tilt enabled
- useLocation hook requests foreground permission once; shows blue dot if granted, silently proceeds if denied
- FloatingLocationButton: 48x48 glass-panel FAB with BlurView backdrop blur, centers map on GPS, no-op when denied
- GlassBottomBar: 80px fixed bar with glassmorphism (blur + 85% opacity), grab handle pill, search placeholder, settings icon
- App.tsx now renders MapScreen after fonts load, with splash-to-map transition via onLayout callback
- All design system tokens exercised: tonal layering, navy shadows, 20px margins, 8px grid, WCAG AA contrast

## Task Commits

Each task was committed atomically:

1. **Task 1: Create location hook, MapScreen with full-screen map, and splash-to-map transition** - `fea74f1` (feat)
2. **Task 2: Create FloatingLocationButton and GlassBottomBar with glassmorphism styling** - `8ae2af2` (feat)

## Files Created/Modified
- `src/hooks/useLocation.ts` - Location permission request and GPS position tracking hook
- `src/screens/MapScreen.tsx` - Full-screen MapView with overlay components
- `src/components/map/FloatingLocationButton.tsx` - Glass-panel my_location FAB with BlurView
- `src/components/map/GlassBottomBar.tsx` - Static glassmorphic bottom bar with search and settings
- `src/utils/toast.ts` - Alert.alert wrapper for "Coming soon" placeholder feedback
- `App.tsx` - Updated to render MapScreen after fonts load

## Decisions Made
- MapView uses default provider (no explicit `provider="google"`) so Apple Maps on iOS and Google Maps on Android are used automatically -- matches user decision from context
- BlurView with rgba background color (not createGlassStyle) used directly for glass components since BlurView handles blur internally and we need the rgba alpha for the semi-transparent overlay
- showToast uses Alert.alert as a simple placeholder -- will be replaced with a proper toast library in later phases
- mapPadding bottom set to 80px to prevent Google/Apple map attribution from being obscured by the bottom bar

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Map shell is complete with all Phase 1 UI elements rendering
- GlassBottomBar is self-contained and ready for Phase 3 to wrap with drag/snap behavior
- MapView ref is available for Phase 2 to add bus markers and polylines
- useLocation hook provides GPS coordinates for any future location-dependent features
- All design system tokens from Plan 01 are now exercised by real UI components

## Self-Check: PASSED

All 7 created/modified files verified on disk. Both task commits (fea74f1, 8ae2af2) verified in git log.

---
*Phase: 01-foundation-and-map-shell*
*Completed: 2026-03-25*
