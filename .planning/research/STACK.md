# Technology Stack

**Project:** Tiger Transit Frontend
**Researched:** 2026-03-25
**Overall Confidence:** MEDIUM-HIGH (SDK 55 maps integration has active issues being resolved; all other areas HIGH)

## SDK Version Decision: Expo SDK 55

Use **Expo SDK 55** (React Native 0.83, React 19.2). This is the current stable release as of March 2026.

**Why not SDK 54 or 52:**
- SDK 55 is the latest stable. Greenfield projects should not start on older SDKs.
- SDK 55 dropped Legacy Architecture entirely -- New Architecture only. This is the direction of the ecosystem and avoids future migration pain.
- SDK 55 includes Hermes bytecode diffing (75% smaller OTA updates), stable expo-blur on Android (critical for glassmorphism), and Expo Router v7.
- SDK 54 was the last to support Legacy Architecture. Starting there means an inevitable forced migration.

**Confidence:** HIGH -- Expo changelog and docs confirm SDK 55 is current stable.

---

## Recommended Stack

### Core Framework

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Expo SDK | 55 | App framework | Latest stable. RN 0.83, React 19.2. New Architecture only. Hermes bytecode diffing for smaller OTA updates. | HIGH |
| React Native | 0.83 | Runtime | Bundled with SDK 55. New Architecture mandatory. No breaking changes from 0.82. | HIGH |
| TypeScript | ~5.7 | Type safety | Bundled with Expo SDK 55 template. Non-negotiable for a real-time app with complex state. | HIGH |

### Maps

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| react-native-maps | ~1.27 (via `npx expo install`) | Map rendering | The PRD specifies Apple Maps (iOS) / Google Maps (Android). react-native-maps supports this split natively. Use default Apple Maps provider on iOS (no config needed) and Google Maps on Android (requires API key). The SDK 55 Google Maps iOS config plugin issue (expo/expo#42423) has been resolved via PR #43884. | MEDIUM-HIGH |

**Critical note on maps:** The PRD says "Apple Maps (iOS) / Google Maps (Android)." This is actually the simplest configuration for react-native-maps -- Apple Maps is the default iOS provider (zero config), and Google Maps is the only Android option. Do NOT set `provider={PROVIDER_GOOGLE}` on iOS unless you need feature parity. Apple Maps on iOS avoids the entire Google Maps iOS config plugin headache.

**Why not expo-maps:** expo-maps requires iOS 17+ minimum and does not support React components as custom markers. The PRD requires custom animated bus markers with rotation, color changes, and animated position interpolation. This rules out expo-maps entirely.

### Animation & Gestures

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| react-native-reanimated | ~4.2 | UI thread animations | Bundled with SDK 55. Required by @gorhom/bottom-sheet. Runs animations on UI thread for 60fps marker interpolation. v4 is New Architecture only (perfect for SDK 55). | HIGH |
| react-native-gesture-handler | ~2.30 | Gesture system | Bundled with SDK 55. Required by @gorhom/bottom-sheet for drag gestures. | HIGH |

### Bottom Sheet

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @gorhom/bottom-sheet | ~5.2 | Draggable bottom sheet | Industry standard for React Native bottom sheets. Supports snap points (collapsed/half/full as PRD requires), custom background components (for glassmorphism), and smooth spring animations. v5.1.8+ supports Reanimated v4. Active maintenance confirmed through 2026. | HIGH |

**Glassmorphism integration:** Use @gorhom/bottom-sheet's `backgroundComponent` prop with expo-blur's `BlurView`. There is a known issue (gorhom/bottom-sheet#2388) where blur disappears after animation in v5.1.6. Fix: use v5.2+ or wrap BlurView in a container with `overflow: 'hidden'` and explicit `borderRadius`.

### Blur / Glassmorphism

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| expo-blur | ~55.0 | Backdrop blur for glass panels | First-party Expo package. SDK 55 brought stable Android support via RenderNode API. Provides `BlurView` component for bottom sheet background, callout bubbles, and floating map controls. | HIGH |

### State Management

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @reduxjs/toolkit | ~2.11 | Global state management | PRD explicitly specifies Redux Toolkit. RTK provides createSlice, createAsyncThunk for ETA API calls, and structured state shape matching the PRD's AppState interface. | HIGH |
| react-redux | ~9.2 | React bindings | Standard Redux-React bridge. useSelector/useDispatch hooks. | HIGH |
| redux-persist | ~6.0 | Persist favorites to disk | Persists favoriteRouteIds/favoriteStopIds to AsyncStorage across app restarts. PRD requires local persistence for favorites. Stable at 6.0.0 for years -- battle-tested. | HIGH |

**Why not RTK Query for GTFS-RT polling:** RTK Query is designed for REST API caching, not binary protobuf feed polling. The GTFS-RT feeds return protobuf binary that needs custom decoding. Use a custom polling service (like the reference `etaspot_reference.ts` pattern) with `setInterval` + `createAsyncThunk` dispatches. RTK Query IS appropriate for the XGBoost ETA prediction REST API calls.

### Data Fetching & Protobuf

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| gtfs-realtime-bindings | ~1.1 | GTFS-RT protobuf decoding | Official MobilityData bindings for GTFS-Realtime spec. Uses protobufjs internally. Reference code in `Code/etaspot_reference.ts` already uses this exact library. Proven pattern: `FeedMessage.decode(new Uint8Array(buffer))`. | MEDIUM-HIGH |
| RTK Query (built into @reduxjs/toolkit) | ~2.11 | ETA prediction API calls | Use `createApi` for the FastAPI `/api/eta/predict` endpoint. Provides automatic caching, refetch-on-focus, and loading/error states. Perfect for REST JSON endpoints. | HIGH |

**Protobuf in React Native note:** `gtfs-realtime-bindings` uses `protobufjs` internally, which is a pure JS implementation. No native modules needed. Works in React Native's Hermes engine without issues. Fetch the binary feed with `fetch()` -> `arrayBuffer()` -> `Uint8Array` -> `FeedMessage.decode()`.

### Navigation

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| expo-router | ~4.x (bundled with SDK 55) | File-based routing | This is a single-screen app (map + bottom sheet), so navigation is minimal. But expo-router provides: deep linking for future v2 features, transparent modal presentation for future overlays, and is the Expo-recommended default. Use a single `app/index.tsx` route. | MEDIUM |

**Why expo-router over bare React Navigation:** Expo SDK 55 template ships with expo-router by default. For a single-screen app, the overhead is negligible, and it provides future-proofing for v2 features (search overlay, settings screen). Fighting the default template wastes time.

### Typography & Fonts

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @expo-google-fonts/manrope | ~0.2 | Manrope font family | Provides all 7 weights (200-800). PRD requires Manrope Bold for headlines and Manrope Medium for titles. Install via `npx expo install`. | HIGH |
| @expo-google-fonts/inter | ~0.2 | Inter font family | Provides all weights. PRD requires Inter Regular for body and Inter Medium for labels. | HIGH |
| expo-font | ~13.x | Font loading | `useFonts` hook loads both font families. Bundled with SDK 55. | HIGH |

**Font loading strategy:** Use `expo-font` with `useFonts` hook in root layout. Show splash screen until fonts load. Do NOT use `expo-splash-screen` `preventAutoHideAsync` pattern with a timeout -- use the font loaded callback directly.

### Storage

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @react-native-async-storage/async-storage | ~2.1 | Local key-value storage | redux-persist storage engine. Stores favorite routes/stops. Simple, well-tested, no native linking needed in Expo. | HIGH |

**Why not react-native-mmkv:** MMKV is faster (30x) but requires native modules and Nitro. For storing a few favorite IDs, AsyncStorage is perfectly adequate. MMKV is overkill for this use case and adds native complexity.

### Location

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| expo-location | ~18.x | User GPS position | "My Location" floating button needs `getCurrentPositionAsync()`. Foreground permissions only (PRD explicitly says no background location). | HIGH |

### Icons & Graphics

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @expo/vector-icons | ~14.x | Material icons | Bundled with Expo. Provides `MaterialIcons` for my_location, search, settings icons. | HIGH |
| react-native-svg | ~16.x | Custom SVG rendering | Bus marker icons, stop circles, route color accents, capacity bars. Custom SVG components for the Academic Navigator design system. | HIGH |

### Lists

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| @shopify/flash-list | ~2.x | High-performance lists | Drop-in FlatList replacement for route list and stop list. 60fps scrolling guaranteed. v2 is New Architecture native. Critical for smooth bottom sheet scroll performance. | HIGH |

### App Lifecycle

| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| expo-splash-screen | ~0.29 | Splash screen | Hold splash while fonts load and initial GTFS data fetches. | HIGH |
| react-native-safe-area-context | ~5.x | Safe area insets | Bundled with SDK 55. Floating map controls must respect notch/dynamic island. | HIGH |

---

## What NOT to Use (and Why)

| Technology | Why Not |
|------------|---------|
| **expo-maps** | Requires iOS 17+. Does NOT support React components as custom markers -- the animated bus markers with rotation and color are impossible. Dead end for this PRD. |
| **react-native-map-clustering** | Premature optimization. 38 routes, maybe 15-20 active buses max. Clustering adds complexity for zero benefit at this scale. |
| **Socket.IO / WebSockets** | The GTFS-RT feeds are static protobuf files on S3 (not a WebSocket server). Polling with `fetch()` is the correct pattern. |
| **Zustand / Jotai / MobX** | PRD specifies Redux Toolkit. The team has committed to RTK. Switching adds risk for no benefit. RTK handles complex real-time state well. |
| **react-native-mmkv** | Overkill for storing favorite IDs. Adds native module complexity. AsyncStorage is sufficient. |
| **NativeWind / Tailwind** | The Academic Navigator design system uses specific hex values, pixel measurements, and tonal layering. A utility-first CSS approach fights this precise design system. Use StyleSheet.create with design tokens. |
| **Expo SDK 52/53/54** | Outdated. SDK 55 is stable. Starting on old SDKs means a forced migration later. New Architecture is mandatory going forward. |
| **react-native-bottom-sheet (non-gorhom)** | Various community alternatives exist but none match @gorhom/bottom-sheet's stability, snap point control, and Reanimated integration. |
| **Tanstack Query** | Would require running alongside Redux (PRD requires RTK). RTK Query covers the REST API case. Custom polling covers protobuf. Adding TanStack creates two data-fetching paradigms. |
| **redux-persist-expo-filesystem** | AsyncStorage engine is simpler and sufficient for small data (favorite IDs). File system storage is for large datasets. |

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| Maps | react-native-maps | expo-maps | No custom marker support, iOS 17+ only |
| Bottom Sheet | @gorhom/bottom-sheet | Expo Router modal | No snap points, no drag gestures, no glassmorphism |
| State | Redux Toolkit | Zustand | PRD specifies RTK; complex real-time state benefits from RTK's structure |
| Animations | Reanimated 4 | RN Animated API | UI thread animations critical for 60fps markers; Reanimated is the standard |
| Lists | FlashList v2 | FlatList | FlashList guarantees 60fps scroll; stop list inside bottom sheet needs peak performance |
| Blur | expo-blur | @react-native-community/blur | expo-blur is first-party, stable on Android in SDK 55, zero config |
| Protobuf | gtfs-realtime-bindings | protobufjs raw | gtfs-realtime-bindings wraps protobufjs with GTFS-RT schema pre-loaded. Less config. |
| SDK Version | 55 | 54 | 54 is legacy-capable (unnecessary), 55 is current stable with better tooling |

---

## Installation

```bash
# Initialize project
npx create-expo-app tiger-transit --template tabs

# Core dependencies (auto-resolved to SDK 55 compatible versions)
npx expo install react-native-maps
npx expo install react-native-reanimated
npx expo install react-native-gesture-handler
npx expo install expo-blur
npx expo install expo-location
npx expo install expo-font
npx expo install expo-splash-screen
npx expo install react-native-svg
npx expo install react-native-safe-area-context
npx expo install @react-native-async-storage/async-storage
npx expo install @shopify/flash-list

# Fonts
npx expo install @expo-google-fonts/manrope @expo-google-fonts/inter

# State management (npm, not expo install)
npm install @reduxjs/toolkit react-redux redux-persist

# Bottom sheet
npm install @gorhom/bottom-sheet

# Protobuf decoding
npm install gtfs-realtime-bindings

# Dev dependencies
npm install -D @types/react @types/react-native
```

**Important:** Always use `npx expo install` for Expo-managed packages. It resolves the correct version for your SDK. Use `npm install` for non-Expo packages like RTK and gorhom/bottom-sheet.

---

## Version Matrix Summary

| Package | Version | SDK 55 Compatible | New Arch Support |
|---------|---------|-------------------|------------------|
| expo | ~55.0 | Yes (is SDK 55) | Required |
| react-native | 0.83 | Yes | Required |
| react-native-maps | ~1.27 | Yes (PR #43884 merged) | Yes (Fabric) |
| react-native-reanimated | ~4.2 | Yes | v4 is New Arch only |
| react-native-gesture-handler | ~2.30 | Yes | Yes |
| @gorhom/bottom-sheet | ~5.2 | Yes (v5.1.8+) | Yes (via Reanimated 4) |
| expo-blur | ~55.0 | Yes | Yes (stable Android) |
| @reduxjs/toolkit | ~2.11 | Yes (pure JS) | N/A (JS only) |
| @shopify/flash-list | ~2.x | Yes | v2 is New Arch native |
| gtfs-realtime-bindings | ~1.1 | Yes (pure JS) | N/A (JS only) |
| expo-location | ~18.x | Yes | Yes |

---

## Key Integration Notes

### Marker Animation Strategy
react-native-maps provides `AnimatedRegion` for smooth position interpolation. On each 5s poll:
1. Receive new lat/lon from GTFS-RT feed
2. Call `coordinate.timing({ latitude, longitude, duration: 1000 }).start()`
3. This creates smooth 1-second animation between position updates

**Android caveat:** Android renders markers as bitmaps. Complex React component markers may not animate smoothly. Use simple SVG-based markers or native image markers for best performance. Test on Android early.

### Glassmorphism Implementation Pattern
```typescript
// Bottom sheet background component
const GlassBackground: React.FC<BottomSheetBackgroundProps> = ({ style }) => (
  <BlurView
    intensity={20}
    tint="light"
    style={[style, { borderTopLeftRadius: 20, borderTopRightRadius: 20, overflow: 'hidden' }]}
  />
);

// Usage
<BottomSheet backgroundComponent={GlassBackground} />
```

### Polling Architecture
```
App Foreground:
  - Start 5s interval for position_updates.pb + trip_updates.pb
  - Start 60s interval for alerts.pb
  - Start 15s interval for XGBoost ETA predictions (when route selected)

App Background:
  - Clear ALL intervals (AppState listener)
  - Resume on foreground return
```

---

## Sources

- [Expo SDK 55 Changelog](https://expo.dev/changelog/sdk-55) -- SDK 55 release details
- [Expo react-native-maps docs](https://docs.expo.dev/versions/latest/sdk/map-view/) -- Map installation
- [react-native-maps GitHub](https://github.com/react-native-maps/react-native-maps) -- Maps library
- [react-native-maps v1.21.0 Release](https://github.com/react-native-maps/react-native-maps/releases/tag/v1.21.0) -- New Architecture support
- [expo/expo#42423](https://github.com/expo/expo/issues/42423) -- SDK 55 maps fix (resolved)
- [@gorhom/bottom-sheet npm](https://www.npmjs.com/package/@gorhom/bottom-sheet) -- Bottom sheet versions
- [gorhom/bottom-sheet#2546](https://github.com/gorhom/react-native-bottom-sheet/issues/2546) -- Reanimated v4 compat
- [@reduxjs/toolkit npm](https://www.npmjs.com/package/@reduxjs/toolkit) -- RTK versions
- [RTK Query Overview](https://redux-toolkit.js.org/rtk-query/overview) -- Data fetching
- [react-native-reanimated docs](https://docs.swmansion.com/react-native-reanimated/docs/fundamentals/getting-started/) -- Animation library
- [expo-blur docs](https://docs.expo.dev/versions/latest/sdk/blur-view/) -- BlurView component
- [Expo fonts docs](https://docs.expo.dev/develop/user-interface/fonts/) -- Font loading
- [@expo-google-fonts/manrope npm](https://www.npmjs.com/package/@expo-google-fonts/manrope) -- Manrope font
- [gtfs-realtime-bindings npm](https://www.npmjs.com/package/gtfs-realtime-bindings) -- Protobuf decoding
- [@shopify/flash-list](https://shopify.github.io/flash-list/) -- FlashList v2
- [Expo Maps intro](https://expo.dev/blog/introducing-expo-maps-a-modern-maps-api-for-expo-developers) -- Why we rejected expo-maps
