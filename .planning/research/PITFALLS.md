# Domain Pitfalls

**Domain:** Real-time transit tracking mobile app (React Native / Expo)
**Researched:** 2026-03-25

## Critical Pitfalls

Mistakes that cause rewrites or major issues.

### Pitfall 1: Android Marker Bitmap Rendering

**What goes wrong:** On Android, react-native-maps renders custom marker views as bitmaps (screenshots). Complex React component markers with Reanimated animations, deeply nested views, or frequent re-renders cause severe frame drops. Markers may appear blank or stale.

**Why it happens:** Android's Google Maps SDK does not support live React views as markers. It takes a snapshot of the React view and displays it as a bitmap image.

**Consequences:** 60fps animated marker movement becomes impossible. Bus markers may flicker, show stale positions, or appear as blank squares. The entire premium animation feel is lost on Android.

**Prevention:**
- Use simple SVG-based markers or pre-rendered images (not complex React component trees)
- Apply heading rotation as a `transform` on the outer Marker, not as an internal Reanimated animation
- Use `tracksViewChanges={false}` after initial render to prevent continuous bitmap re-rendering
- Set `tracksViewChanges={true}` only momentarily when marker content changes, then set it back to `false`
- Test on a mid-range Android device early (not just iOS Simulator)

**Detection:** Frame rate drops below 30fps during marker animation on Android. Markers appear as blank rectangles.

### Pitfall 2: Bottom Sheet Gesture Conflict with Map

**What goes wrong:** The bottom sheet's drag gesture conflicts with the map's pan gesture. Users try to drag the sheet but accidentally pan the map, or try to pan the map but accidentally trigger the sheet.

**Why it happens:** Both the bottom sheet and map respond to vertical touch gestures. Without explicit gesture boundaries, the gesture system cannot determine user intent.

**Consequences:** Frustrating UX where users fight the interface. The "map-first" philosophy breaks when the map is unresponsive during sheet interactions.

**Prevention:**
- @gorhom/bottom-sheet handles this well with its built-in gesture handler, but verify the `enableContentPanningGesture` prop is configured correctly
- Ensure the map is still interactive at the "half" snap point (sheet covers bottom 45%, map covers top 55%)
- Use `simultaneousHandlers` if needed to allow map panning while sheet is at half position
- The sheet's grab handle should be the primary drag target; scrollable content inside the sheet should scroll, not drag the sheet

**Detection:** User testing shows confusion about whether to drag the handle or the content area. Map becomes unresponsive when sheet is at half position.

### Pitfall 3: Orphaned Polling Intervals

**What goes wrong:** Multiple `setInterval` timers accumulate when the app transitions between foreground/background states or when components remount. Each creates a new interval without clearing the old one.

**Why it happens:** Using `setInterval` inside `useEffect` without proper cleanup. React Strict Mode double-invoking effects. AppState listener not reliably clearing intervals on background.

**Consequences:** Multiple concurrent polling intervals. 2x, 3x, 10x the network requests. Battery drain. Server load. Duplicate vehicle updates causing jitter.

**Prevention:**
- Use a singleton service class (not useEffect) for polling
- Clear intervals in a single place tied to AppState changes
- Use a `isPolling` flag to prevent duplicate starts
- The service class pattern from `etaspot_reference.ts` is the correct approach

**Detection:** Network inspector shows multiple simultaneous requests to the same feed URL. Console logs show duplicate "poll" messages.

### Pitfall 4: Protobuf Decoding in React Native Environment

**What goes wrong:** `gtfs-realtime-bindings` uses `protobufjs` which has known require-cycle warnings in React Native. In some configurations, the module fails to initialize or produces incorrect decoded output.

**Why it happens:** `protobufjs` uses dynamic `require()` calls and circular dependencies between utility files. React Native's Metro bundler handles these differently than Node.js.

**Consequences:** Protobuf decoding silently returns empty/malformed data, or throws runtime errors on specific devices/OS versions.

**Prevention:**
- Use the `protobufjs/light` or `protobufjs/minimal` variant if possible
- Test protobuf decoding on both iOS and Android early in development
- Add explicit error handling around `FeedMessage.decode()` calls
- Consider pre-compiling the GTFS-RT .proto definition into a static JS module rather than relying on dynamic loading
- Validate decoded output structure (check that `feed.entity` is an array with expected fields)

**Detection:** Vehicle list is always empty despite feeds being accessible via browser. Console warnings about require cycles from protobufjs.

## Moderate Pitfalls

### Pitfall 5: AnimatedRegion Memory Leak

**What goes wrong:** Creating new `AnimatedRegion` instances on every poll cycle (every 5s) without cleaning up old ones. Each AnimatedRegion allocates native animation resources.

**Prevention:**
- Store AnimatedRegion refs in a `useRef(new Map())` keyed by vehicleId
- Reuse existing refs, only create new ones for new vehicles
- Remove refs for vehicles that disappear (stale filter removes them)

### Pitfall 6: Bottom Sheet Glassmorphism Blur Disappearing

**What goes wrong:** expo-blur's `BlurView` inside @gorhom/bottom-sheet's `backgroundComponent` works initially, then the blur effect disappears after the sheet animates between snap points.

**Prevention:**
- Use @gorhom/bottom-sheet v5.2+ (blur fix was addressed in recent versions)
- Set `overflow: 'hidden'` on the BlurView container
- Apply `borderRadius` to the BlurView container, not the BlurView itself
- If blur still disappears, use a `pointerEvents="none"` absolute-positioned BlurView behind the sheet content as a fallback

### Pitfall 7: 5-Second Polling Overwhelming UI Re-renders

**What goes wrong:** Every 5s poll dispatches a Redux action that updates `vehicles.positions`. Every component subscribed via `useSelector` re-renders, including the entire route list, all markers, and all callouts.

**Prevention:**
- Use memoized selectors (`createSelector` from reselect, included in RTK)
- Select only the specific data each component needs (e.g., `selectVehiclesByRoute(routeId)` not `selectAllVehicles`)
- Use `React.memo` on marker components with a custom comparator
- The route list doesn't need every vehicle's position -- it only needs the count per route. Create a derived selector.

### Pitfall 8: CORS Issues Fetching GTFS-RT Feeds

**What goes wrong:** The GTFS-RT feeds are hosted on S3 (`s3.amazonaws.com`). If S3 CORS headers are not configured, `fetch()` from the mobile app may fail during development.

**Prevention:**
- React Native's `fetch()` does NOT enforce CORS the same way browsers do -- native apps typically bypass CORS entirely. This is usually NOT an issue for production builds.
- If using Expo Go for development, CORS may apply. Test with a development build (`npx expo run:ios`) if Expo Go has issues.
- As a fallback, proxy feeds through the existing Supabase/FastAPI backend

### Pitfall 9: Map Camera Conflicts with Automatic Fitting

**What goes wrong:** The PRD says "when a route is selected, map fits to show all stops + active buses." But users also freely pan/zoom. Auto-fitting on every 5s poll update would constantly yank the map back.

**Prevention:**
- Auto-fit ONLY on route selection (user taps a route card), not on every poll update
- After the initial auto-fit, let users freely pan/zoom without interference
- Use a flag like `hasUserInteractedWithMap` to prevent auto-fit after manual pan
- "My Location" button resets the flag and centers on user

### Pitfall 10: Stale Static Data After Route Changes

**What goes wrong:** GTFS static data (routes, stops, shapes) is cached locally. If Auburn's transit team adds/removes routes between semesters, the app shows phantom routes or misses new ones.

**Prevention:**
- Check a version hash or last-modified header on app launch
- If hash differs, re-fetch full static data
- Show a subtle refresh indicator during the background update
- Consider bundling a baseline GTFS static snapshot for instant first-load

## Minor Pitfalls

### Pitfall 11: Font Loading Flash

**What goes wrong:** Manrope and Inter fonts take 200-500ms to load. Text renders in the system default font, then visibly jumps to the custom font.

**Prevention:** Keep splash screen visible until `useFonts` reports loaded. Use `expo-splash-screen` `preventAutoHideAsync()` + `hideAsync()` on font load complete.

### Pitfall 12: ETA Display Rounding Edge Cases

**What goes wrong:** PRD says "round to nearest minute" and "< 1 min for under 60s." Edge case: 89 seconds rounds to 1 min, but 30 seconds also rounds to 1 min. Users see "1 min" for a bus that's 30 seconds away.

**Prevention:** Use `Math.ceil(seconds / 60)` for values >= 60s (round up to be conservative). For values < 60s, show "< 1 min" as PRD specifies. For 0 seconds, show "Arriving."

### Pitfall 13: Heading Wraparound During Animation

**What goes wrong:** Bus heading goes from 350 degrees to 10 degrees (a 20-degree turn). Naive interpolation animates through 340 degrees the wrong way around.

**Prevention:** Calculate shortest-path rotation before animating. If the difference is > 180 degrees, adjust the target by +/- 360 degrees to ensure the animation takes the short path.

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Map + markers setup | Android bitmap rendering (#1) | Test on Android device immediately after markers work on iOS |
| Bottom sheet implementation | Gesture conflict with map (#2) | Verify gesture boundaries at each snap point |
| GTFS-RT polling service | Orphaned intervals (#3) + protobuf decode (#4) | Singleton service pattern + thorough decode error handling |
| Animated markers | Memory leak (#5) + heading wraparound (#13) | Ref-based AnimatedRegion management |
| Glassmorphism styling | Blur disappearing (#6) | Test on both platforms early, have fallback ready |
| Performance tuning | Re-render storm (#7) | Memoized selectors from the start, not as afterthought |
| Real-time data integration | CORS (#8) + stale data (#10) | Test mobile fetch early, cache static data with version check |

## Sources

- [react-native-maps#2382](https://github.com/react-native-maps/react-native-maps/issues/2382) -- Marker animation issues
- [gorhom/bottom-sheet#1192](https://github.com/gorhom/react-native-bottom-sheet/issues/1192) -- Glassmorphism challenges
- [gorhom/bottom-sheet#2388](https://github.com/gorhom/react-native-bottom-sheet/issues/2388) -- Blur effect bug
- [protobufjs#1137](https://github.com/protobufjs/protobuf.js/issues/1137) -- Expo require cycle warnings
- [react-native-maps#4551](https://github.com/react-native-maps/react-native-maps/issues/4551) -- MarkerAnimated issues
- Code/etaspot_reference.ts -- Reference polling service pattern
- PRD.md section 8.10 -- Performance targets
