---
phase: 01-foundation-and-map-shell
plan: 01
subsystem: ui
tags: [expo, react-native, redux, design-tokens, typography, glassmorphism, manrope, inter]

# Dependency graph
requires: []
provides:
  - Expo SDK 55 project skeleton with TypeScript, all RN dependencies installed
  - Complete Academic Navigator design system tokens (colors, surfaces, text, status, shadows, spacing, glassmorphism)
  - Manrope + Inter dual-font loading via expo-google-fonts
  - Redux store with 6 typed slices (routes, vehicles, predictions, ui, preferences, alerts)
  - Typed GTFS data interfaces (Route, Stop, VehiclePosition, ArrivalPrediction, ServiceAlert)
  - App.tsx with Redux Provider, splash screen control, and font loading
affects: [01-02, 02-01, 02-02, 03-01, 03-02, 04-01, 04-02, 05-01, 05-02, 06-01, 06-02]

# Tech tracking
tech-stack:
  added: [expo@55, react-native@0.83.2, react@19.2, @reduxjs/toolkit, react-redux, react-native-maps, expo-font, expo-splash-screen, expo-location, expo-blur, react-native-reanimated, react-native-gesture-handler, @expo-google-fonts/manrope, @expo-google-fonts/inter]
  patterns: [redux-toolkit-slices, typed-hooks, barrel-exports, design-tokens-as-const, expo-google-fonts-loading]

key-files:
  created:
    - src/theme/tokens.ts
    - src/theme/typography.ts
    - src/theme/shadows.ts
    - src/theme/spacing.ts
    - src/theme/glassmorphism.ts
    - src/theme/index.ts
    - src/hooks/useFonts.ts
    - src/store/index.ts
    - src/store/slices/routesSlice.ts
    - src/store/slices/vehiclesSlice.ts
    - src/store/slices/predictionsSlice.ts
    - src/store/slices/uiSlice.ts
    - src/store/slices/preferencesSlice.ts
    - src/store/slices/alertsSlice.ts
    - src/types/gtfs.types.ts
    - app.json
    - babel.config.js
  modified:
    - App.tsx
    - package.json
    - tsconfig.json
    - .gitignore

key-decisions:
  - "Used @expo-google-fonts packages instead of manual TTF downloads for reliable font loading"
  - "Excluded pre-existing Code/, ETA-Model/, scripts/ directories from tsconfig to isolate RN project"
  - "Font family keys use expo-google-fonts naming convention (Manrope_700Bold) for direct compatibility"
  - "Shadow shadowColor uses rgba(12, 35, 64, 1) with separate shadowOpacity for cross-platform behavior"

patterns-established:
  - "Design tokens as const: All color/surface/text exports use 'as const' for literal type inference"
  - "Typed Redux hooks: useAppDispatch and useAppSelector for type-safe store access"
  - "Theme barrel export: Import all design tokens from src/theme"
  - "Slice pattern: Each slice in its own file with named action exports and default reducer export"

requirements-completed: [DS-01, DS-02, DS-03, DS-04, DS-05, DS-06, DS-07, DS-08]

# Metrics
duration: 9min
completed: 2026-03-25
---

# Phase 1 Plan 01: Expo Project Init, Design System, and Redux Store Summary

**Expo SDK 55 project with complete Academic Navigator design system (Manrope/Inter fonts, navy-tinted shadows, tonal layering tokens, glassmorphism presets) and 6-slice Redux store scaffold matching PRD AppState shape**

## Performance

- **Duration:** 9 min
- **Started:** 2026-03-25T21:54:08Z
- **Completed:** 2026-03-25T22:03:44Z
- **Tasks:** 3
- **Files modified:** 30

## Accomplishments
- Expo SDK 55 blank-typescript project created with all 14 dependencies installed (react-native-maps, redux, fonts, blur, reanimated, gesture-handler, location)
- Complete design system: color palette (7 core colors), surface hierarchy (4 levels), text colors (4 tones), status badge colors, navy-tinted shadows (3 presets), 8px grid spacing, glassmorphism presets with createGlassStyle helper
- Font loading: Manrope Bold/Medium + Inter Regular/Medium via @expo-google-fonts with expo-font hook
- Redux store: 6 slices (routes, vehicles, predictions, ui, preferences, alerts) with typed hooks, matching PRD Section 7.1 AppState exactly
- App.tsx wired with Redux Provider, splash screen held until fonts load, renders "Tiger Transit" in Manrope Bold 32pt
- All TypeScript compiles with zero errors

## Task Commits

Each task was committed atomically:

1. **Task 1: Initialize Expo project, install dependencies, configure TypeScript** - `c8a56e6` (feat)
2. **Task 2: Create design system tokens, typography, shadows, spacing, glassmorphism, and font loading** - `73c3087` (feat)
3. **Task 3: Create Redux store with all 6 slices and wire into App.tsx with font loading** - `d37d297` (feat)

## Files Created/Modified
- `package.json` - Expo SDK 55 project with 14 dependencies
- `app.json` - Tiger Transit app config with navy splash, bundle IDs, New Architecture enabled
- `tsconfig.json` - Strict TypeScript with non-RN directories excluded
- `babel.config.js` - Reanimated plugin configured
- `.gitignore` - Updated with Expo/RN patterns
- `App.tsx` - Redux Provider, font loading, splash screen, Manrope Bold title
- `index.ts` - Expo entry point
- `assets/splash.png` - Tiger Transit logo for splash screen
- `src/theme/tokens.ts` - Colors, surfaces, textColors, statusColors, MIN_TAP_TARGET
- `src/theme/typography.ts` - fontFamilies, typography scale (headlineLG, titleMD, bodyMD, labelSM)
- `src/theme/shadows.ts` - Navy-tinted ambient, sheetAbove, subtle shadow presets
- `src/theme/spacing.ts` - GRID, EDGE_MARGIN, spacing scale, cardPadding, listItemGap, pillRadius
- `src/theme/glassmorphism.ts` - Panel, sheet, callout presets with createGlassStyle()
- `src/theme/index.ts` - Barrel export for entire design system
- `src/hooks/useFonts.ts` - Custom font loading hook for 4 Google Font variants
- `src/types/gtfs.types.ts` - Route, Stop, Coordinate, VehiclePosition, ArrivalPrediction, ServiceAlert
- `src/store/index.ts` - Redux store with typed hooks (useAppDispatch, useAppSelector)
- `src/store/slices/routesSlice.ts` - Route list, stops, shapes, loading state
- `src/store/slices/vehiclesSlice.ts` - Vehicle positions, connection state
- `src/store/slices/predictionsSlice.ts` - ETA predictions by stop
- `src/store/slices/uiSlice.ts` - Selected route/stop, sheet position, callout state
- `src/store/slices/preferencesSlice.ts` - Favorite routes/stops with toggle and hydrate
- `src/store/slices/alertsSlice.ts` - Service alerts with fetch timestamp

## Decisions Made
- Used @expo-google-fonts/manrope and @expo-google-fonts/inter packages instead of manually downloading TTF files -- ensures correct font format and expo-font compatibility
- Excluded Code/, ETA-Model/, scripts/, data/, gtfs_data/, reports/, supabase/ from tsconfig.json to prevent TypeScript errors from pre-existing non-RN code
- Font keys use expo-google-fonts naming (Manrope_700Bold, Inter_400Regular) which directly matches what the useFonts hook expects
- Shadow shadowColor uses fully opaque rgba with separate shadowOpacity property for correct cross-platform behavior on both iOS and Android

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] tsconfig exclusion for pre-existing directories**
- **Found during:** Task 1 (TypeScript verification)
- **Issue:** TypeScript was picking up Code/etaspot_reference.ts and ETA-Model/getWeatherData.ts which have their own uninstalled dependencies, causing compilation errors
- **Fix:** Added exclude array to tsconfig.json for Code, ETA-Model, scripts, data, gtfs_data, reports, supabase, .planning
- **Files modified:** tsconfig.json
- **Verification:** npx tsc --noEmit passes with zero errors
- **Committed in:** c8a56e6 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Essential fix to isolate the Expo project TypeScript scope from pre-existing repository code. No scope creep.

## Issues Encountered
None beyond the tsconfig exclusion noted above.

## User Setup Required
None - no external service configuration required. Google Maps API key placeholder is in app.json but not needed until Phase 2.

## Next Phase Readiness
- Project skeleton, design tokens, fonts, and Redux store are all in place for Plan 02 (full-screen map, splash screen, glassmorphic bottom bar, floating location button)
- All theme imports available via `import { colors, typography, ... } from './src/theme'`
- Redux store accessible via typed useAppSelector/useAppDispatch hooks
- react-native-maps, expo-location, expo-blur all installed and ready for Plan 02

## Self-Check: PASSED

All 21 created files verified on disk. All 3 task commits (c8a56e6, 73c3087, d37d297) verified in git log.

---
*Phase: 01-foundation-and-map-shell*
*Completed: 2026-03-25*
