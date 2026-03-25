# Architecture Patterns

**Domain:** Real-time transit tracking mobile app
**Researched:** 2026-03-25

## Recommended Architecture

Single-screen architecture with a layered component model. The app is one screen (map + bottom sheet) with internal view navigation managed by Redux UI state, not route-based navigation.

### Component Hierarchy

```
App (expo-router root layout)
  |-- FontLoader (useFonts, splash screen)
  |-- ReduxProvider (store with persist)
  |-- SafeAreaProvider
  |     |
  |     |-- MapScreen (the only "screen")
  |           |
  |           |-- MapLayer (react-native-maps MapView, always visible)
  |           |     |-- BusMarkerLayer (animated bus markers)
  |           |     |-- StopMarkerLayer (conditional, when route selected)
  |           |     |-- RoutePolyline (conditional, when route selected)
  |           |     |-- BusCallout (glass panel, on bus marker tap)
  |           |     |-- StopCallout (glass panel, on stop marker tap)
  |           |
  |           |-- FloatingControls (my_location, search, settings)
  |           |
  |           |-- BottomSheet (@gorhom/bottom-sheet)
  |                 |-- RouteListView (default)
  |                 |     |-- StatusBar ("4 buses active")
  |                 |     |-- FavoriteToggle (pill tabs)
  |                 |     |-- RouteCardList (FlashList)
  |                 |     |-- AlertsSection (conditional)
  |                 |
  |                 |-- RouteDetailView (when route selected)
  |                 |     |-- RouteHeader (back, name, color, favorite)
  |                 |     |-- StopList (FlashList, timeline style)
  |                 |
  |                 |-- StopDetailView (when stop selected for detail)
  |                       |-- StopHeader (name, metadata)
  |                       |-- LiveBadge
  |                       |-- ArrivingBusList
  |                       |-- AllRoutesBadges
```

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| MapLayer | Renders map, manages camera region, hosts markers/polylines | Redux (vehicles, selectedRoute) |
| BusMarkerLayer | Renders animated bus markers from vehicle positions | Redux (vehicles), MapLayer (AnimatedRegion) |
| StopMarkerLayer | Renders stop markers for selected route | Redux (selectedRoute, stops) |
| BottomSheet | Draggable container with snap points and glassmorphism | Redux (sheetPosition, UI state) |
| RouteListView | Displays route cards with active status | Redux (routes, vehicles, favorites) |
| RouteDetailView | Displays stop list with ETAs for selected route | Redux (selectedRoute, predictions) |
| StopDetailView | Deep-dive stop info with arriving buses | Redux (selectedStop, vehicles, predictions) |
| GTFSPollingService | Fetches + decodes protobuf feeds on interval | Redux (dispatches vehicle/alert updates) |
| ETAPredictionService | Calls FastAPI for XGBoost predictions | Redux (dispatches prediction updates via RTK Query) |

### Data Flow

```
GTFS-RT Feeds (S3 protobuf)
    |
    v
GTFSPollingService (5s interval)
    |-- fetch() --> arrayBuffer --> FeedMessage.decode()
    |-- Process trip updates FIRST (ETAs available for position enrichment)
    |-- Process position updates (enrich with trip ETA data)
    |-- Filter stale vehicles (> 2 min)
    |
    v
Redux Store (dispatch updateVehicles / updateAlerts)
    |
    +----> MapLayer re-renders bus markers (useSelector)
    +----> RouteListView updates active bus counts (useSelector)
    +----> BusCallout updates ETA data (useSelector)

FastAPI /api/eta/predict (REST JSON)
    |
    v
RTK Query (createApi, 15s refetch when route selected)
    |
    v
Redux Store (predictions.byStop)
    |
    +----> StopList ETAs update (useSelector)
    +----> StopDetailView arrival times update (useSelector)
```

## Patterns to Follow

### Pattern 1: Service Layer for Polling

Separate the polling logic from React components. The polling service is a plain TypeScript class (not a React component) that dispatches to Redux.

**What:** A singleton class that manages `setInterval`, `fetch`, protobuf decoding, and dispatches actions to the Redux store.

**When:** For any data that is fetched on a timer (GTFS-RT feeds, alerts).

**Why:** Keeps polling lifecycle independent of component mount/unmount. The service starts/stops based on AppState (foreground/background), not component lifecycle.

```typescript
// services/gtfsPollingService.ts
class GTFSPollingService {
  private positionTimer: ReturnType<typeof setInterval> | null = null;
  private alertTimer: ReturnType<typeof setInterval> | null = null;

  start(dispatch: AppDispatch) {
    this.poll(dispatch);
    this.positionTimer = setInterval(() => this.poll(dispatch), 5000);
    this.alertTimer = setInterval(() => this.pollAlerts(dispatch), 60000);
  }

  stop() {
    if (this.positionTimer) clearInterval(this.positionTimer);
    if (this.alertTimer) clearInterval(this.alertTimer);
  }

  private async poll(dispatch: AppDispatch) {
    // fetch, decode, dispatch
  }
}
```

### Pattern 2: Design Token System

All visual values (colors, spacing, typography) defined in a single theme file. Components import tokens, never hardcode hex values.

**What:** A `theme/` directory with `colors.ts`, `typography.ts`, `spacing.ts`, `shadows.ts` files exporting the Academic Navigator design system.

**When:** Every component that has visual styling.

```typescript
// theme/colors.ts
export const colors = {
  primary: '#000D21',
  primaryContainer: '#0C2340',
  secondary: '#994700',
  secondaryContainer: '#FF8934',
  secondaryFixed: '#FFB68B',
  background: '#F8F9FA',
  surfaceContainer: '#EDEEEF',
  surfaceContainerLowest: '#FFFFFF',
  surfaceDim: '#D9DADB',
  onSurface: '#191C1D',
  onSurfaceVariant: '#44474D',
  outline: '#74777E',
  outlineVariant: '#C4C6CE',
  error: '#BA1A1A',
} as const;
```

### Pattern 3: Bottom Sheet View Navigation via Redux

The bottom sheet shows different "views" (RouteList, RouteDetail, StopDetail) based on Redux UI state. No React Navigation stack inside the sheet.

**What:** A `ui.selectedRouteId` and `ui.selectedStopId` in Redux determines which view the bottom sheet shows.

**When:** User taps a route card, taps "View More" on a stop callout, or taps the back button.

```typescript
// Inside BottomSheet content
const selectedRouteId = useSelector(state => state.ui.selectedRouteId);
const selectedStopId = useSelector(state => state.ui.selectedStopId);

if (selectedStopId) return <StopDetailView />;
if (selectedRouteId) return <RouteDetailView />;
return <RouteListView />;
```

### Pattern 4: Animated Marker Refs

Store AnimatedRegion refs in a Map keyed by vehicleId. On each poll cycle, animate existing refs to new positions rather than re-creating markers.

**What:** A `useRef<Map<string, AnimatedRegion>>()` that persists across renders.

**When:** Bus marker position updates.

**Why:** Re-creating Animated values on each render kills animation. The ref map preserves animation state across poll cycles.

### Pattern 5: RTK Query for REST APIs Only

Use RTK Query (`createApi`) exclusively for the FastAPI ETA prediction endpoint. Use the custom polling service for GTFS-RT protobuf feeds.

**What:** Two data-fetching patterns coexisting -- RTK Query for JSON REST, custom service for binary protobuf.

**When:** Any REST API call (ETA predictions, future endpoints). Never for protobuf feeds.

**Why:** RTK Query cannot decode protobuf. Forcing it to would require custom `fetchBaseQuery` overrides that fight the library's design.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Polling Inside useEffect

**What:** Putting `setInterval` inside a React component's `useEffect`.

**Why bad:** Component unmount/remount during bottom sheet transitions can orphan intervals or create duplicate timers. The polling lifecycle should be tied to app foreground/background state, not component lifecycle.

**Instead:** Use a singleton service class. Start/stop from the root layout's `AppState` listener.

### Anti-Pattern 2: Storing Vehicles in Component State

**What:** Using `useState` for vehicle positions instead of Redux.

**Why bad:** Multiple components need vehicle data (map markers, route cards, bus callouts, status bar count). Local state requires prop drilling or context that re-renders the entire tree on every 5s update.

**Instead:** Redux store with `vehicles.positions` slice. Components use fine-grained `useSelector` to subscribe to only the data they need.

### Anti-Pattern 3: React Navigation Stack Inside Bottom Sheet

**What:** Embedding a React Navigation `Stack.Navigator` inside the bottom sheet for RouteList -> RouteDetail -> StopDetail transitions.

**Why bad:** Navigation stack fights the bottom sheet's gesture system. Back swipe conflicts with sheet drag. Navigation state becomes desynchronized from sheet snap position.

**Instead:** Simple conditional rendering based on Redux `ui.selectedRouteId` / `ui.selectedStopId`. Back button dispatches a Redux action to clear the selection.

### Anti-Pattern 4: Complex Marker Components on Android

**What:** Using deeply nested React components with Reanimated animations as map marker children on Android.

**Why bad:** Android renders map markers as bitmaps. Complex component trees cause expensive re-renders on each position update. 60fps becomes impossible.

**Instead:** Use simple SVG icons or pre-rendered images for markers. Apply rotation (heading) as a transform on the outer marker container. Test on Android devices early.

### Anti-Pattern 5: Fetching Full Static Data on Every App Launch

**What:** Downloading all GTFS static data (routes, stops, shapes) from Supabase on every cold start.

**Why bad:** 38 routes, 178 stops, thousands of shape points. Downloading all of it blocks the route list from appearing within the < 1s performance target.

**Instead:** Cache GTFS static data locally after first fetch. Only re-fetch when a version hash changes or on explicit pull-to-refresh.

## Scalability Considerations

| Concern | At Current Scale (38 routes, ~20 buses) | At 100 buses | At 500 buses |
|---------|---------------------------------------|--------------|--------------|
| Map markers | Direct rendering, no clustering needed | Still fine, test frame rate | Need marker clustering |
| Polling load | 2 fetch calls per 5s = trivial | Same (server-side aggregation) | Same |
| Redux updates | 20 vehicles every 5s, negligible | 100 vehicles, still fine with memoized selectors | Consider normalized entity adapter |
| Bottom sheet list | FlashList handles 38 routes easily | Still fine | Still fine |
| ETA predictions | 1 API call per route selection | Same | May need batch endpoint |

Auburn's scale (38 routes, 178 stops, ~15-20 active buses) is small enough that performance optimization is rarely the bottleneck. The architecture should be clean and maintainable, not prematurely optimized.

## File Structure

```
src/
  app/                     # expo-router (just index.tsx)
    _layout.tsx            # Root layout: fonts, Redux, SafeArea
    index.tsx              # MapScreen (the single screen)

  components/
    map/
      MapLayer.tsx         # MapView wrapper
      BusMarkerLayer.tsx   # All animated bus markers
      BusMarker.tsx        # Single animated bus marker
      StopMarkerLayer.tsx  # All stop markers for selected route
      RoutePolyline.tsx    # Polyline for selected route
      BusCallout.tsx       # Glass panel bus callout
      StopCallout.tsx      # Glass panel stop callout
    sheet/
      BottomSheetContainer.tsx  # @gorhom/bottom-sheet with glass background
      RouteListView.tsx         # Default sheet content
      RouteCard.tsx             # Single route card
      RouteDetailView.tsx       # Stop list for selected route
      StopListItem.tsx          # Single stop with ETAs
      StopDetailView.tsx        # Deep-dive stop view
      AlertsSection.tsx         # Conditional alerts
    common/
      GlassPanel.tsx       # Reusable glass container (BlurView)
      Badge.tsx            # Status badges (LIVE, DELAYED, On Time, Route)
      CapacityBar.tsx      # Passenger load bar
      FloatingControls.tsx # Map control buttons
      StatusBar.tsx        # "4 buses active" header

  services/
    gtfsPollingService.ts  # GTFS-RT feed polling + protobuf decode
    types.ts               # VehiclePosition, TripEta, etc.

  store/
    index.ts               # configureStore with persist
    slices/
      routesSlice.ts       # GTFS static data (routes, stops, shapes)
      vehiclesSlice.ts     # Real-time vehicle positions
      predictionsSlice.ts  # XGBoost ETA predictions
      uiSlice.ts           # UI state (selectedRoute, sheetPosition, etc.)
      preferencesSlice.ts  # Favorites (persisted)
      alertsSlice.ts       # Service alerts
    api/
      etaApi.ts            # RTK Query API for FastAPI predictions

  theme/
    colors.ts              # Academic Navigator color palette
    typography.ts          # Manrope + Inter type scale
    spacing.ts             # 8px grid, margins, padding
    shadows.ts             # Navy-tinted shadow definitions
    index.ts               # Unified theme export

  hooks/
    useAppState.ts         # Foreground/background detection
    usePolling.ts          # Start/stop polling based on app state
    useAnimatedMarkers.ts  # AnimatedRegion ref management

  utils/
    formatEta.ts           # "3 min", "< 1 min", "No buses en route"
    speedConvert.ts        # m/s to mph
    staleFilter.ts         # 2-minute timestamp filter
```

## Sources

- PRD.md sections 3-7 -- Information architecture, state management, data flows
- Code/etaspot_reference.ts -- Existing polling service pattern
- @gorhom/bottom-sheet documentation -- Custom background, snap points
- Redux Toolkit documentation -- createSlice, createApi patterns
- react-native-maps documentation -- AnimatedRegion, marker rendering
