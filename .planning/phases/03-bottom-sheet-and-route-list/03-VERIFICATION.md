---
phase: 03-bottom-sheet-and-route-list
verified: 2026-03-26T00:00:00Z
status: passed
score: 11/11 must-haves verified
re_verification:
  previous_status: gaps_found
  previous_score: 8/11
  gaps_closed:
    - "Inactive routes now sorted to bottom (active-first two-key sort implemented in sortedRoutes useMemo)"
    - "Favorites and Alerts placeholder sections added with 'No favorites yet' / 'No active alerts' empty-state text"
    - "ROUTE-02 un-checked in REQUIREMENTS.md with ETA portion correctly deferred to Phase 4"
  gaps_remaining: []
  regressions: []
---

# Phase 3: Bottom Sheet and Route List — Verification Report

**Phase Goal:** Build a draggable bottom sheet with snap positions and populate it with an alphabetically-sorted route list showing color identity and live bus counts. Users can browse all routes via a glassmorphic draggable bottom sheet with active bus counts and visual polish.
**Verified:** 2026-03-26
**Status:** passed
**Re-verification:** Yes — after gap closure plan 03-03 addressed 3 gaps (ROUTE-01 missing sections, ROUTE-02 re-scoped, ROUTE-04 sort-to-bottom)

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | User can drag bottom sheet between collapsed (~80px), half (~45%), full (~90%) positions | VERIFIED | BottomSheet.tsx: collapsedY/halfY/fullY computed from screenHeight; translateY clamped between fullY and collapsedY |
| 2 | Sheet snaps to nearest snap point with spring animation when released | VERIFIED | snapToNearest() worklet uses withSpring(SPRING_CONFIG) with velocity projection (0.15 factor) |
| 3 | Sheet has frosted-glass glassmorphic styling with backdrop blur and 20px top radius | VERIFIED | BlurView intensity=20, rgba(255,255,255,0.85) background, borderTopLeftRadius/borderTopRightRadius=20 |
| 4 | Grab handle is a #C4C6CE pill, 32px wide, visible at all sheet positions | VERIFIED | handle: width=32, height=4, borderRadius=2, backgroundColor=textColors.outlineVariant |
| 5 | Map remains fully interactive when sheet is at half position | VERIFIED | Sheet absolutely positioned; GestureDetector only captures within sheet bounds |
| 6 | A loading spinner shows briefly while initial route data loads | VERIFIED | loading prop triggers ActivityIndicator; routesLoading wired from state.routes.loading in MapScreen |
| 7 | User sees three section headers: ACTIVE ROUTES, FAVORITES, ALERTS | VERIFIED | RouteList.tsx lines 75, 89-91, 95-96: three Text headers with sectionHeader style; FAVORITES + ALERTS have sectionDivider marginTop |
| 8 | Favorites section shows "No favorites yet"; Alerts section shows "No active alerts" | VERIFIED | RouteList.tsx line 92: `No favorites yet` placeholderText; line 96: `No active alerts` placeholderText |
| 9 | Each route card shows color stripe, tinted background, long name, short name, bus count | VERIFIED | RouteCard.tsx: 4px stripe (route.routeColor), hexToRgba tint at 0.06 alpha, titleMD longName, bodyMD secondaryLine |
| 10 | Route cards use Level 2 surfaces on Level 1 section background with no border lines | VERIFIED | container=surfaces.level1, card=surfaces.level2; no border/borderWidth in StyleSheet |
| 11 | Inactive routes (0 active buses) are dimmed AND sorted to bottom of the list | VERIFIED | RouteList.tsx lines 60-67: two-key sort — aActive/bActive binary flag (0 or 1) compared first, then localeCompare within each group; dependency array includes busCountMap |

**Score:** 11/11 truths verified

---

## Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `src/components/sheet/BottomSheet.tsx` | Draggable sheet, 3 snap points, glassmorphism, spring animation | VERIFIED | 350 lines; GestureDetector, useSharedValue, withSpring, BlurView all present and wired; no regression |
| `src/components/sheet/RouteCard.tsx` | Color stripe, tinted bg, text layout, bus count, React.memo | VERIFIED | 162 lines; React.memo, hexToRgba, formatBusCount, stripe + tint views, inactive opacity; no regression |
| `src/components/sheet/RouteList.tsx` | Three section headers, active-first sort, placeholder empty-states | VERIFIED | 131 lines; busCountMap two-key sort (lines 60-67), ACTIVE ROUTES (line 75), FAVORITES (line 89), ALERTS (line 95), placeholderText style (lines 123-130) |
| `.planning/REQUIREMENTS.md` | ROUTE-02 un-checked, traceability shows Phase 3+4 Partial | VERIFIED | Line 33: `- [ ] **ROUTE-02**`; traceability row: `ROUTE-02 | Phase 3+4 | Partial (ETA deferred to Phase 4)` |
| `src/screens/MapScreen.tsx` | Renders BottomSheet with RouteList children, dynamic mapPadding | VERIFIED | Lines 31-32 import BottomSheet + RouteList; lines 113-115 render BottomSheet + RouteList; no regression |

---

## Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| RouteList.tsx | vehiclesSlice.ts | busCountMap used in sortedRoutes sort comparator (dependency: `[routes, busCountMap]`) | WIRED | Lines 62-63: busCountMap.get() inside sort; line 67: `[routes, busCountMap]` dependency array |
| BottomSheet.tsx | react-native-gesture-handler + react-native-reanimated | GestureDetector + useSharedValue + withSpring | WIRED | Imports at lines 29-38 verified; no regression |
| BottomSheet.tsx | src/store/slices/uiSlice.ts | dispatch(setSheetPosition) on snap settle | WIRED | runOnJS(syncSheetPosition) calls dispatch; no regression |
| MapScreen.tsx | BottomSheet.tsx + RouteList.tsx | BottomSheet wrapping RouteList as children | WIRED | Lines 113-115 in MapScreen.tsx confirmed present |
| RouteList.tsx | routesSlice.ts | useAppSelector reads routes.list | WIRED | Line 43; no regression |
| RouteList.tsx | vehiclesSlice.ts | useAppSelector reads vehicles.positions | WIRED | Line 44; no regression |

---

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| SHEET-01 | 03-01 | Drag between 3 snap points (~80px, ~45%, ~90%) | SATISFIED | collapsedY/halfY/fullY computed from screenHeight; pan gesture clamps between them |
| SHEET-02 | 03-01 | Glassmorphic styling (blur, 20px top radius, navy shadow) | SATISFIED | BlurView intensity=20, borderTopRadius=20, shadows.sheetAbove applied |
| SHEET-03 | 03-01 | #C4C6CE grab handle pill, 32px wide | SATISFIED | handle: width=32, height=4, backgroundColor=textColors.outlineVariant |
| SHEET-04 | 03-01 | Spring animation between snap points | SATISFIED | withSpring(snapPoints[closestIndex], SPRING_CONFIG) in snapToNearest worklet |
| SHEET-05 | 03-01 | Map interactive at half position | SATISFIED | Absolute positioning; gesture handler only captures sheet bounds |
| ROUTE-01 | 03-02 + 03-03 | Sectioned route list (Active Routes, Favorites, Alerts) | SATISFIED | All three sections rendered: ACTIVE ROUTES with cards, FAVORITES with "No favorites yet", ALERTS with "No active alerts" |
| ROUTE-02 | 03-02 (partial) | Card shows color accent, short name, long name, bus count, next ETA | PARTIAL — documented | Color, shortName, longName, busCount shown. ETA deferred to Phase 4. REQUIREMENTS.md correctly marks as unchecked with Phase 3+4 traceability. |
| ROUTE-03 | 03-02 | Level 2 cards on Level 1 background, no border lines | SATISFIED | surfaces.level2 cards, surfaces.level1 container, no border styles |
| ROUTE-04 | 03-02 + 03-03 | Inactive routes dimmed AND sorted to bottom | SATISFIED | Dimming via opacity 0.5 on inactive cards; two-key sort places busCount=0 routes after all active routes |
| ERR-02 | 03-02 | "No active buses" in on-surface-variant color | SATISFIED | formatBusCount(0) returns "No active buses"; secondaryLine uses textColors.onSurfaceVariant |
| ERR-03 | 03-01 | Loading states provide visual feedback during data fetch | SATISFIED | loading prop shows ActivityIndicator; MapScreen passes routesLoading from Redux |

**Note on ROUTE-02:** This requirement remains partially open by design — the ETA clause defers to Phase 4. This is correctly reflected in REQUIREMENTS.md (unchecked, traceability row shows "Phase 3+4 | Partial"). The Phase 3 goal (visual card with color identity and bus count) is fully achieved.

**Orphaned requirements:** None. All Phase 3 IDs (SHEET-01 through SHEET-05, ROUTE-01 through ROUTE-04, ERR-02, ERR-03) are accounted for in plan frontmatter.

---

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| BottomSheet.tsx | 202, 241 | showToast('Coming soon') for search/settings press | Info | Intentional placeholder for out-of-scope features (Phase 5+). Not a Phase 3 blocker. |
| RouteList.tsx | — | No onPress handler passed to RouteCard | Info | Intentional — Phase 4 adds route detail navigation. Cards render correctly without it. |

No TODOs, FIXMEs, empty implementations, return-null stubs, or console.log-only handlers detected in any modified file. TypeScript compiles with zero errors.

---

## Human Verification Required

### 1. Drag Feel and Snap Behavior

**Test:** Run the app on a device or simulator. Drag the sheet from collapsed to half, half to full. Release mid-drag and fling quickly.
**Expected:** Sheet snaps to nearest position with a natural spring rebound. Fling toward full reaches full position.
**Why human:** Cannot verify spring physics feel (damping=20, stiffness=150 values) or gesture responsiveness programmatically.

### 2. Active-First Sort Visible in Route List

**Test:** Open the app when some bus routes have active vehicles and some do not. Scroll the route list.
**Expected:** Routes with at least one active bus appear at the top (alphabetically within group). Routes with zero buses appear below (also alphabetically within group), rendered at 50% opacity.
**Why human:** Requires live vehicle position data to exercise the sort path with real bus counts.

### 3. Map Interactivity at Half Position

**Test:** Drag sheet to half position. Pan and pinch-zoom the map in the area above the sheet.
**Expected:** Map responds to touch in the uncovered top area. Sheet does not intercept these gestures.
**Why human:** Gesture boundary correctness on real touch hardware cannot be verified by static analysis.

### 4. BlurView Glassmorphism Visual

**Test:** Open the app and observe the bottom sheet over the map.
**Expected:** Sheet shows frosted glass effect — map content blurred/visible through the sheet.
**Why human:** expo-blur BlurView rendering quality varies by platform; cannot be verified statically.

---

## Re-Verification Summary

All three gaps from the initial verification are closed:

| Gap | Previous Status | Current Status | Evidence |
|-----|----------------|----------------|----------|
| ROUTE-04: inactive routes sorted to bottom | FAILED | VERIFIED | Two-key sort (aActive/bActive flag + localeCompare) in sortedRoutes useMemo; busCountMap in dependency array; commit 1149a7d |
| ROUTE-01: Favorites and Alerts section placeholders | FAILED | VERIFIED | FAVORITES section with "No favorites yet" at line 92; ALERTS section with "No active alerts" at line 96; commit 1149a7d |
| ROUTE-02: requirement text vs. implementation scope | FAILED | VERIFIED (documented) | REQUIREMENTS.md: `- [ ] **ROUTE-02**`; traceability: "Phase 3+4 | Partial (ETA deferred to Phase 4)"; commit ea58ee4 |

No regressions detected. All 8 previously-verified truths remain intact (BottomSheet 350 lines stable, MapScreen wiring unchanged, RouteCard 162 lines stable).

**The phase goal is fully achieved.** The bottom sheet drags, snaps with spring animation, has glassmorphic styling, and displays a color-accented route list with three sections (Active Routes with bus counts, Favorites placeholder, Alerts placeholder). Inactive routes are dimmed and sorted below active routes. Requirements documentation accurately reflects what was implemented vs. what is deferred.

---

_Verified: 2026-03-26_
_Verifier: Claude (gsd-verifier)_
