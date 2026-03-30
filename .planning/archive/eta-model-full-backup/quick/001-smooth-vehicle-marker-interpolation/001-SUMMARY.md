---
phase: quick
plan: 001
subsystem: ui
tags: [react-native-maps, AnimatedRegion, MarkerAnimated, smooth-animation, vehicle-tracking]

# Dependency graph
requires: []
provides:
  - "Smooth vehicle marker interpolation on live transit map"
  - "Heading wraparound logic for shortest-path rotation"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "AnimatedRegion + MarkerAnimated for smooth map marker transitions"
    - "Shortest-path heading wraparound via delta normalization"
    - "First-render guard to prevent animate-from-origin on mount"

key-files:
  created: []
  modified:
    - mobile/src/components/Map/VehicleMarker.tsx

key-decisions:
  - "Used MarkerAnimated import (not Marker.Animated) for cleaner import pattern"
  - "toValue: 0 added to AnimatedRegion.timing() config to satisfy TS types (ignored at runtime)"
  - "Used 'as any' type assertions for coordinate and rotation props to bridge AnimatedRegion/Animated.Value with MarkerAnimated prop types"
  - "1000ms animation duration chosen (1/8 of 8s poll interval) for smooth but responsive transitions"

patterns-established:
  - "AnimatedRegion pattern: useRef for stable instance, useEffect for prop-driven animation"
  - "Heading wraparound: delta normalization to [-180, 180] range, accumulated target value"

# Metrics
duration: 5min
completed: 2026-02-18
---

# Quick 001: Smooth Vehicle Marker Interpolation Summary

**AnimatedRegion-based bus marker interpolation with 1000ms coordinate/heading transitions and shortest-path heading wraparound**

## Performance

- **Duration:** 5 min
- **Started:** 2026-02-19T01:46:15Z
- **Completed:** 2026-02-19T01:51:00Z
- **Tasks:** 2 (1 implementation + 1 verification-only)
- **Files modified:** 1

## Accomplishments
- Bus markers glide smoothly to new positions over 1s instead of teleporting every 8s
- Heading rotation takes shortest angular path (no 350-degree spins crossing 0/360 boundary)
- New markers appear at their initial position without animating from (0,0)
- Marker recycling detection snaps immediately if vehicleId changes (defensive)
- Callout popups preserved identically inside MarkerAnimated

## Task Commits

Each task was committed atomically:

1. **Task 1: Convert VehicleMarker to AnimatedRegion with smooth interpolation** - `8f70d87` (feat)
2. **Task 2: Verify MapView stable keys and animated marker rendering** - no commit (verification-only; MapView already correct, no changes needed)

## Files Created/Modified
- `mobile/src/components/Map/VehicleMarker.tsx` - Replaced Marker with MarkerAnimated; added AnimatedRegion for coordinates and Animated.Value for heading with useEffect-driven timing() animations

## Decisions Made
- **MarkerAnimated vs Marker.Animated:** Used `MarkerAnimated` named export directly rather than `Marker.Animated` static property for cleaner import syntax (both resolve to the same component)
- **toValue workaround:** AnimatedRegion.timing() TypeScript types extend TimingAnimationConfig which requires `toValue`, but AnimatedRegion reads latitude/longitude directly. Added `toValue: 0` as a no-op to satisfy the type checker
- **Type assertions:** Used `as any` for `coordinate` and `rotation` props since MarkerAnimated expects `LatLng` and `number` respectively, but we pass AnimatedRegion and Animated.Value (which work at runtime but TypeScript doesn't know about the animated component wrapping)
- **First-render skip:** Added `isFirstRender` ref guard to prevent animation on component mount, ensuring new buses appear at their actual position rather than animating from AnimatedRegion's initial state

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added toValue to AnimatedRegion.timing() config**
- **Found during:** Task 1 (TypeScript compilation)
- **Issue:** `AnimatedRegion.timing()` TypeScript definition requires `toValue` from `TimingAnimationConfig` intersection type, but the runtime implementation ignores it and reads latitude/longitude from the config directly
- **Fix:** Added `toValue: 0` to the timing config object with an explanatory comment
- **Files modified:** mobile/src/components/Map/VehicleMarker.tsx
- **Verification:** `npx tsc --noEmit` passes with zero errors
- **Committed in:** 8f70d87

---

**Total deviations:** 1 auto-fixed (1 blocking TypeScript type mismatch)
**Impact on plan:** Necessary for TypeScript compilation. No scope creep.

## Issues Encountered
None beyond the TypeScript type mismatch documented in deviations.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Smooth marker animation is fully wired up
- Runtime verification on device/simulator recommended to confirm visual smoothness
- If performance becomes an issue with many markers, `tracksViewChanges` can be optimized (set to `false` after initial render via a timeout)

---
*Plan: quick-001*
*Completed: 2026-02-18*
