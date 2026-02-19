---
phase: quick
plan: 001
type: execute
wave: 1
depends_on: []
files_modified:
  - mobile/src/components/Map/VehicleMarker.tsx
  - mobile/src/components/Map/MapView.tsx
autonomous: true

must_haves:
  truths:
    - "Bus markers glide smoothly to new positions over ~1s instead of teleporting every 8s"
    - "Bus heading rotates smoothly when direction changes"
    - "Markers that disappear (bus goes out of service) are removed cleanly without animation artifacts"
    - "New markers that appear (bus enters service) render at their initial position without animating from 0,0"
    - "Callout popups still work when tapping an animated marker"
  artifacts:
    - path: "mobile/src/components/Map/VehicleMarker.tsx"
      provides: "AnimatedRegion-based marker with smooth coordinate and heading interpolation"
      contains: "AnimatedRegion"
    - path: "mobile/src/components/Map/MapView.tsx"
      provides: "Renders Animated VehicleMarker components"
  key_links:
    - from: "mobile/src/components/Map/VehicleMarker.tsx"
      to: "react-native-maps AnimatedRegion"
      via: "useRef holding AnimatedRegion, timing() calls on prop change"
      pattern: "AnimatedRegion|timing"
    - from: "mobile/src/components/Map/MapView.tsx"
      to: "mobile/src/components/Map/VehicleMarker.tsx"
      via: "passes vehicle prop; VehicleMarker internally animates on prop changes"
      pattern: "VehicleMarker"
---

<objective>
Add smooth linear interpolation for bus markers on the map so buses glide to new positions
instead of teleporting when the ETASpot API is polled every 8 seconds.

Purpose: Eliminate jarring marker jumps that make the live map feel broken. Smooth animation
makes bus positions feel real-time even with an 8-second poll interval.

Output: VehicleMarker.tsx uses react-native-maps AnimatedRegion with timing() to animate
coordinate and heading changes over ~1000ms.
</objective>

<execution_context>
@C:\Users\ryanp\.claude/get-shit-done/workflows/execute-plan.md
@C:\Users\ryanp\.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@mobile/src/components/Map/VehicleMarker.tsx
@mobile/src/components/Map/MapView.tsx
@mobile/src/hooks/useVehicles.ts
</context>

<tasks>

<task type="auto">
  <name>Task 1: Convert VehicleMarker to use AnimatedRegion with smooth coordinate and heading interpolation</name>
  <files>mobile/src/components/Map/VehicleMarker.tsx</files>
  <action>
Rewrite VehicleMarker.tsx to animate marker position and heading using react-native-maps AnimatedRegion.

Key changes:

1. Import `{ Animated as RNAnimated }` from `react-native` and `{ AnimatedRegion, MarkerAnimated }` from `react-native-maps`. Note: react-native-maps exports `MarkerAnimated` (or use `Marker.Animated` -- check the library's exports; the canonical import for v1.20.x is `import { Marker } from 'react-native-maps'` then use `<Marker.Animated>`). Use the `MapMarkerProps` type if needed.

2. Create an `AnimatedRegion` ref initialized with the vehicle's starting lat/lon:
   ```ts
   const animatedCoordinate = useRef(
     new AnimatedRegion({
       latitude: vehicle.lat,
       longitude: vehicle.lon,
       latitudeDelta: 0,
       longitudeDelta: 0,
     })
   ).current;
   ```

3. Create an `Animated.Value` ref for heading:
   ```ts
   const animatedHeading = useRef(new RNAnimated.Value(vehicle.heading)).current;
   ```

4. Track previous vehicleId to detect when the marker is being reused for a different bus (should NOT happen given key={vehicleId} in parent, but defensive):
   ```ts
   const prevVehicleIdRef = useRef(vehicle.vehicleId);
   ```

5. Add a useEffect that fires when `vehicle.lat`, `vehicle.lon`, or `vehicle.heading` change:
   - If vehicleId changed (marker recycled), snap immediately without animation by calling `animatedCoordinate.setValue({...})` and `animatedHeading.setValue(...)`.
   - Otherwise, animate coordinate via `animatedCoordinate.timing({ latitude: vehicle.lat, longitude: vehicle.lon, latitudeDelta: 0, longitudeDelta: 0, duration: 1000, useNativeDriver: false }).start()`.
   - Animate heading via `RNAnimated.timing(animatedHeading, { toValue: vehicle.heading, duration: 1000, useNativeDriver: false }).start()`.
   - For heading: handle the 360-degree wraparound. If the heading change crosses the 0/360 boundary (e.g., 350 -> 10), adjust the target to avoid spinning the long way around. Compute the shortest angular distance: `let delta = newHeading - currentHeading; if (delta > 180) delta -= 360; if (delta < -180) delta += 360; target = currentHeading + delta;`. Track currentHeading in a ref that updates after each animation.
   - Update prevVehicleIdRef.

6. Replace `<Marker>` with `<Marker.Animated>` (from react-native-maps). Pass:
   - `coordinate={animatedCoordinate}` (the AnimatedRegion object, NOT a plain object)
   - `rotation={animatedHeading}` (Animated.Value -- Marker.Animated accepts this)
   - Keep all other props: `anchor`, `flat`, `tracksViewChanges`

7. For `tracksViewChanges`: set to `true`. This is already set and needed for the custom View children to render. On Android, there may be a perf cost but correctness comes first. (If perf is an issue later, can optimize with `tracksViewChanges={false}` after initial render.)

8. Keep the entire Callout section unchanged. It renders inside the animated marker and should work as-is.

9. Keep the component as a named function (not anonymous) and keep the default export.

IMPORTANT: Do NOT use `useNativeDriver: true` for AnimatedRegion coordinate animations -- native driver does not support layout properties (latitude/longitude). Must be `useNativeDriver: false`.

IMPORTANT: `AnimatedRegion.timing()` is a method on the AnimatedRegion instance, not `Animated.timing()`. The API is `animatedCoordinate.timing({...}).start()`.

IMPORTANT: Do NOT touch the Callout or styling -- only the coordinate/heading animation wiring.
  </action>
  <verify>
    Run `npx tsc --noEmit` from the mobile directory to verify no TypeScript errors.
    Visually inspect the code to confirm:
    - AnimatedRegion is created with useRef
    - useEffect triggers animation on lat/lon/heading changes
    - Marker.Animated is used instead of Marker
    - useNativeDriver is false
    - Heading wraparound logic handles 350->10 correctly
  </verify>
  <done>
    VehicleMarker uses AnimatedRegion.timing() with 1000ms duration for coordinates,
    Animated.timing() with 1000ms for heading (with wraparound handling),
    Marker.Animated replaces Marker, and TypeScript compiles cleanly.
  </done>
</task>

<task type="auto">
  <name>Task 2: Update MapView to ensure stable keys and verify animated markers render correctly</name>
  <files>mobile/src/components/Map/MapView.tsx</files>
  <action>
Minor adjustments to MapView.tsx to ensure animated markers work correctly:

1. Verify that `key={vehicle.vehicleId}` is used on VehicleMarker (already present). This is critical -- React must not recycle marker components between different vehicles, otherwise AnimatedRegion would animate from one bus's position to another's. The current code already uses vehicleId as key, so just confirm this is correct.

2. No other changes should be needed in MapView.tsx. The VehicleMarker component handles all animation internally via useEffect on prop changes. The parent just passes the vehicle prop as before.

3. If for any reason the import of VehicleMarker needs updating (e.g., if the component is now wrapped differently), update the import. But this should not be necessary since VehicleMarker keeps its default export.

4. Run the app to verify: `npx expo start` from the mobile directory. On the device/simulator, watch buses on the map. They should glide smoothly between positions instead of jumping. Heading changes should rotate smoothly. New buses appearing should pop in at their position (no animation from 0,0). Tapping a bus should still show the callout.

If there are TypeScript issues with `Marker.Animated` accepting `AnimatedRegion` as coordinate prop (react-native-maps type definitions can be finicky), the fix is to use a type assertion: `coordinate={animatedCoordinate as any}`. Only do this if tsc actually complains -- try without first.
  </action>
  <verify>
    Run `npx tsc --noEmit` from the mobile directory -- zero errors.
    Run `npx expo start` and verify on device/simulator:
    - Buses glide to new positions (not teleporting)
    - Heading rotates smoothly
    - Callout still appears on tap
    - No console errors about AnimatedRegion
  </verify>
  <done>
    MapView renders animated VehicleMarkers, TypeScript compiles cleanly,
    and the live map shows smooth bus movement on device.
  </done>
</task>

</tasks>

<verification>
1. `npx tsc --noEmit` passes with zero errors from the mobile directory
2. On device/simulator via `npx expo start`:
   - Bus markers glide smoothly (~1s transition) when new positions arrive every 8s
   - Heading rotation is smooth and takes the shortest path (no 350-degree spins)
   - New buses appear at their position without animating from coordinates (0,0)
   - Buses that go offline disappear cleanly (React unmounts the component)
   - Callout popups work when tapping animated markers
   - No JS console warnings/errors related to animation
</verification>

<success_criteria>
Bus markers on the live map animate smoothly between 8-second poll updates using
AnimatedRegion.timing(), with proper heading wraparound handling. The map feels
fluid and real-time rather than showing jarring position jumps.
</success_criteria>

<output>
After completion, create `.planning/quick/001-smooth-vehicle-marker-interpolation/001-SUMMARY.md`
</output>
