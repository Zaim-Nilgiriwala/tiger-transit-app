# Tiger Transit App - Frontend PRD

## 1. Overview

Tiger Transit is a real-time bus tracking app for the Auburn University Tiger Transit system. The app displays live bus positions on a map, provides ETA predictions for upcoming arrivals at each stop, and lets riders quickly find and favorite the routes they care about.

**Target platform:** React Native (Expo) - iOS & Android
**Primary data source:** GTFS-Realtime protobuf feeds (position updates + trip updates), polled every 5 seconds
**ETA engine:** XGBoost v1.1 model (85.6s MAE, 87.9% improvement over naive schedule)
**Backend:** Supabase (PostgreSQL 17) + FastAPI inference server

---

## 2. Product Vision

The app lives on a **single screen**: a full-bleed map with a **draggable bottom sheet** that serves as the primary navigation and information surface. There are no tab bars, no hamburger menus, no screen transitions in the traditional sense - just the map and the sheet. Users interact by pulling the sheet up to browse routes, tapping into routes to see stops, and tapping map markers to see callout bubbles with contextual info.

**Design Philosophy: "The Academic Navigator"**

This is not a utility-only transit app. It is a **premium concierge experience** for the Auburn campus. The design blends collegiate authority with modern iOS glassmorphism to create a "Soft Minimalist" environment. The UI feels like a transparent lens resting over campus geography - significant white space, intentional asymmetry in card layouts, and a map-first philosophy where the interface never competes with the geography beneath it.

---

## 3. Information Architecture

```
Map (always visible, full screen)
├── Route polylines (all visible routes — see Visibility Trio Rule)
├── Stop markers (all visible routes — see Visibility Trio Rule)
├── Bus markers (all visible routes — see Visibility Trio Rule)
├── Floating controls (my_location, search, settings)
│
Bottom Sheet (draggable: collapsed / half / full)
├── Route List View (default)
│   ├── Status bar ("4 buses active")
│   ├── Active Routes section (route cards with ETAs)
│   ├── Favorites section (starred stops/routes)
│   └── Alerts section (conditional - service disruptions)
│
├── Route Detail View (after tapping a route)
│   ├── Route header + favorite button
│   └── Stop list with next 3 arrival ETAs per stop
│
└── Stop Detail View (after tapping a stop / "View More")
    ├── Stop name, stop number, route count, city
    ├── LIVE status badge
    ├── Arriving buses (route, bus ID, delay status, ETA, passengers)
    └── All Routes at this stop (color-coded badges)
```

---

## 4. Screen & View Specifications

### 4.1 Map Layer (Always Visible)

The map fills the entire screen behind the bottom sheet. It uses Apple Maps (iOS) / Google Maps (Android) via `react-native-maps`.

#### Visibility Trio Rule

**Route polylines, stop markers, and bus markers are ALWAYS shown or hidden together. There is never a case where only one or two of the three are visible for a given route. No exceptions.**

The map has three visibility states:

| State | Trigger | What's visible on the map |
|-------|---------|--------------------------|
| **All Routes** (default) | App launch, or "All Routes" pill tab | Polylines + stops + buses for every active route |
| **Favorites Only** | "Favorites" pill tab toggle | Polylines + stops + buses for favorited routes only |
| **Single Route** | Tapping a route card in the bottom sheet | Polyline + stops + buses for the selected route only; everything else hidden |

Deselecting a route (back button) returns to the previous toggle state (All Routes or Favorites Only).

#### 4.1.1 Bus Markers

| Property | Detail |
|----------|--------|
| **Data source** | GTFS-RT position feed, polled every 5s |
| **Icon** | Directional bus icon, rotated to match `heading`. Uses `secondary-fixed` orange (#FF8934) for active buses to ensure they "pop" against the navy map elements |
| **Visibility** | Follows the Visibility Trio Rule — shown for all visible routes. Hidden for routes not in the current visibility set. |
| **Animation** | Smooth interpolation between position updates (AnimatedRegion, 1000ms duration) with shortest-path heading wraparound |
| **Stale filtering** | Vehicles with timestamps > 2 minutes old are hidden |
| **Tap behavior** | Opens a **bus callout bubble** (see 4.2) |

#### 4.1.2 Stop Markers

| Property | Detail |
|----------|--------|
| **Visibility** | Follows the Visibility Trio Rule — shown for all visible routes, not just the selected route |
| **Icon** | Small circle in the route color, with a subtle navy-tinted ambient shadow |
| **Tap behavior** | Opens a **stop callout bubble** (see 4.3) |

#### 4.1.3 Route Polylines

| Property | Detail |
|----------|--------|
| **Visibility** | Follows the Visibility Trio Rule — all visible routes have polylines drawn |
| **Data source** | GTFS `shapes.txt` decoded polyline coordinates |
| **Style** | Solid line in the route's `route_color`, ~4px width. Selected route draws thicker (~5px) with a shadow polyline for emphasis. |
| **Multiple routes** | All routes in the current visibility set are drawn simultaneously. When a single route is selected, only that route's polyline is drawn. |

#### 4.1.4 Floating Map Controls

Three icon buttons float above the map in the top-right corner, styled as glass panels with backdrop blur:

| Control | Icon | Action |
|---------|------|--------|
| **My Location** | `my_location` | Centers map on user's GPS position |
| **Search** | `search` | Opens search overlay (v2) |
| **Settings** | `settings` | Opens settings (v2) |

**Style:** Surface-container-lowest background with 20px backdrop blur, navy-tinted ambient shadow (`0 8px 24px rgba(12, 35, 64, 0.08)`), 8px border radius.

#### 4.1.5 Map Behavior

- On app launch, the map centers on Auburn University campus (~32.606, -85.487) at a zoom level that shows the full transit service area. All route polylines, stop markers, and bus markers are visible immediately.
- When a route is selected, the map fits to show all stops + active buses on that route. All other routes' polylines, stops, and buses are hidden.
- When a specific stop is tapped, the map centers/zooms to that stop
- User can freely pan/zoom at any time; selecting a route or stop re-centers the map
- Deselecting a route restores the previous visibility state (all routes or favorites only)

---

### 4.2 Bus Callout Bubble

Triggered by tapping a bus marker on the map. Appears as a glass-panel callout anchored to the bus marker.

**Visual Style:** Surface-container-lowest background with 20px backdrop blur, 8px border radius, navy-tinted shadow. No pointed tail - use a floating card style anchored near the marker.

**Contents:**

| Field | Source | Format |
|-------|--------|--------|
| **Route name** | GTFS `route_short_name` + `route_long_name` | e.g. "CL - Central Loop" |
| **Bus ID** | `VehiclePosition.vehicleId` | e.g. "Bus 1042" (Label-SM style: 11pt uppercase) |
| **Speed** | `VehiclePosition.speed` | e.g. "18 mph" (converted from m/s) |
| **Passenger count** | `VehiclePosition.load` / `VehiclePosition.capacity` | e.g. "18/40" with visual fill bar |
| **On-time status** | `VehiclePosition.onTime` / `isDelayed` | "On Time" (green) / "DELAYED" (secondary orange badge) |
| **ETA to next stop** | `VehiclePosition.etaSeconds` | e.g. "3 min to Student Center" |

**Behavior:**
- Tapping outside the callout dismisses it
- Only one callout can be open at a time (bus or stop)
- Callout data refreshes with each 5s poll cycle

---

### 4.3 Stop Callout Bubble

Triggered by tapping a stop marker on the map. Appears as a glass-panel callout anchored to the stop marker.

**Visual Style:** Same glass-panel treatment as bus callout.

**Contents:**

| Field | Source | Format |
|-------|--------|--------|
| **Stop name** | GTFS `stop_name` | e.g. "Student Center" |
| **Stop number** | GTFS `stop_id` | e.g. "Stop #142" (Label-SM style) |
| **ETA range** | ETA model prediction for next arriving bus | e.g. "Next bus: 3 min" |
| **All routes at this stop** | GTFS `stop_times` cross-referenced with `routes` | Color-coded route badges (e.g. "CL", "TR", "EC") using pill-shaped badges |
| **"View More" button** | Navigation action | Opens Stop Detail View in the bottom sheet |

**Behavior:**
- Shows a compact summary (not full arrival table)
- Route badges are tappable - tapping one switches the selected route
- "View More" scrolls/navigates the bottom sheet to the Stop Detail View

---

### 4.4 Bottom Sheet

The bottom sheet is the primary navigation surface. It is a draggable panel overlaid on the map with three snap points:

| Position | Height | Use Case |
|----------|--------|----------|
| **Collapsed** | ~80px (grab handle + peek content) | Map is the focus; sheet shows bus count status bar |
| **Half** | ~45% of screen | Default resting position. Enough to browse the route list while still seeing the map |
| **Full** | ~90% of screen | Full content browsing. Route detail / stop detail views |

**Visual Style:**
- Background: `surface-container-lowest` (#FFFFFF) with **20px backdrop blur** (frosted glass effect allowing map colors to bleed through)
- Top corners: **20px border radius**
- Grab handle: Subtle `#C4C6CE` pill, 32px wide, recessed 8px from top
- Shadow: Extra-diffused navy-tinted shadow (`0 -4px 24px rgba(12, 35, 64, 0.08)`)
- **No border lines** at the top edge - depth is communicated solely through shadow and blur

**Behavior:**
- User drags via the handle at the top of the sheet
- Swiping down from Half snaps to Collapsed
- Swiping up from Half snaps to Full
- The map remains interactive (pan/zoom) even with the sheet at Half
- Smooth spring animation between snap points (cubic-bezier 0.33, 1, 0.68, 1)

---

### 4.5 Route List View (Bottom Sheet Default)

This is the default content of the bottom sheet when no route is selected. Content is organized into **distinct sections** separated by background color shifts (no divider lines).

#### 4.5.1 Status Bar

| Property | Detail |
|----------|--------|
| **Content** | Active bus count: "4 buses active" |
| **Style** | Displayed prominently at top of sheet content, using Title-MD (18pt Manrope Medium) |
| **Live indicator** | Small pulsing dot in secondary-fixed orange next to the count |

#### 4.5.2 Active Routes Section

Route cards displayed in a sectioned layout. Each card is a **Level 2 surface** (`#FFFFFF`) sitting on a **Level 1 section background** (`#EDEEEF`), creating natural lift without borders.

**Route Card:**

| Property | Detail |
|----------|--------|
| **Layout** | Route color accent (left edge or top bar) + route short name (bold Manrope) + long name (Inter regular) + active bus count + next arrival ETA |
| **Active indicator** | Number of buses currently running (e.g. "3 buses active") |
| **ETA preview** | Next arrival time for the nearest stop |
| **Inactive routes** | Routes with 0 active buses are dimmed (surface-dim background) and sorted to bottom |
| **Tap behavior** | Selects route -> transitions to Route Detail View + isolates that route on the map (polyline + stops + buses only for that route) |
| **Spacing** | 16px vertical white space between cards (no horizontal dividers) |
| **Border radius** | 8px (round-eight) |

**Sort order:** Favorited routes pinned to top (within Active Routes), then remaining routes alphabetical.

#### 4.5.3 Favorites Section

| Property | Detail |
|----------|--------|
| **Position** | Below Active Routes section |
| **Background** | Level 1 surface (`#EDEEEF`) |
| **Content** | Starred stops or routes with quick-access cards |
| **Empty state** | Subtle prompt: "Star routes to pin them here" |
| **Toggle** | Pill tab toggle: "All Routes" / "Favorites" using full-round (999px) pill shape, mimicking Apple Maps aesthetic |

#### 4.5.4 Alerts Section (Conditional)

| Property | Detail |
|----------|--------|
| **Visibility** | Only shown when there are active service alerts |
| **Position** | Below Favorites section |
| **Style** | Warning icon + alert title + brief description. Uses secondary orange for warning emphasis |
| **Content** | e.g. "Construction on Samford Ave - Expect delays on CL, TR routes" |
| **Tap behavior** | Expands to show full alert details |
| **No amber banner** | Alerts are integrated as a content section, not an intrusive banner |

---

### 4.6 Route Detail View (Bottom Sheet After Route Selection)

Displayed when a user taps a route from the Route List. Replaces the Route List content in the bottom sheet.

#### 4.6.1 Route Header

| Element | Detail |
|---------|--------|
| **Back button** | Returns to Route List View |
| **Route name** | Short name + long name (e.g. "CL - Central Loop") in Headline-LG (32pt Manrope Bold) |
| **Route color bar** | Full-width thin bar in route color, positioned below the route name |
| **Favorite button** | Star icon toggle. Filled = favorited. Persists to AsyncStorage. |
| **Share button** | Share icon for deep linking (v2) |

#### 4.6.2 Stop List

An ordered list of all stops on the selected route, in route-sequence order. Items separated by **16px vertical white space** (no horizontal dividers, per the No-Line rule).

**Stop List Item:**

| Property | Detail |
|----------|--------|
| **Stop indicator** | Small circle in route color, connected by a subtle vertical line (timeline style) |
| **Stop name** | Inter Medium, on-surface color (#191C1D) |
| **ETA display** | Next 3 bus arrival predictions, displayed as horizontal bus-icon + time chips |
| **ETA source** | XGBoost v1.1 model predictions (85.6s MAE) |
| **ETA format** | Rounded to nearest minute (e.g. "3 min", "18 min"). Under 1 min shows "< 1 min". If no buses are approaching, show "No buses en route" in on-surface-variant color |
| **Tap behavior** | Centers map on this stop + opens the stop callout bubble on the map |
| **Scroll** | List scrolls independently within the sheet |

---

### 4.7 Stop Detail View (Bottom Sheet - Extended Info)

Displayed when a user taps "View More" from a stop callout bubble, or taps a stop directly from the map. This is the deep-dive view for a single stop.

**Header:**

| Element | Detail |
|---------|--------|
| **Dismiss gesture** | Swipe down or back button |
| **Location icon** | Map pin icon in primary navy |
| **Stop name** | Headline-LG (32pt Manrope Bold) |
| **Stop metadata** | "Stop #142 - 3 routes - Auburn, AL" in Label-SM (11pt Inter, uppercase, 5% letter spacing) |
| **Actions** | Star (favorite) + Share icons |

**LIVE Status Section:**

| Element | Detail |
|---------|--------|
| **Badge** | "LIVE" pill badge in secondary-fixed orange (#FF8934), pulsing subtly |
| **Subheading** | "Arriving Now" or "Next Arrival" in Title-MD |

**Arriving Buses List:**

Each arriving bus is displayed as a card (Level 2 surface on Level 1 background):

| Field | Detail |
|-------|--------|
| **Route name** | e.g. "Central Loop" with route color accent |
| **Bus ID** | Label-SM style: "BUS 1042" |
| **Delay status** | "DELAYED" badge in secondary orange, or "On Time" in a muted green |
| **ETA** | Large prominent number: "3 min" using Headline-LG styling |
| **Passenger count** | "18/40" with a visual capacity fill bar (secondary-fixed orange fill on surface-container background) |
| **Spacing** | 16px between bus cards (no dividers) |

**All Routes at This Stop (Footer):**

| Element | Detail |
|---------|--------|
| **Label** | "All Routes at this stop" in Label-SM uppercase |
| **Route badges** | Pill-shaped badges with route short name (e.g. "CL", "TR", "EC"), color-coded by route_color |
| **Tap behavior** | Tapping a badge switches to that route's Route Detail View |

---

## 5. Data Model & Sources

### 5.1 Feed URLs

| Feed | URL |
|------|-----|
| **GTFS Static** | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/gtfs.zip` |
| **Alerts** | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/alerts.pb` |
| **Position Updates** | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb` |
| **Trip Updates** | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb` |

### 5.2 GTFS-RT Protobuf Feeds

| Feed | URL | Interval | Data |
|------|-----|----------|------|
| Position Updates | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb` | 5000ms | Vehicle locations, heading, speed, next stop |
| Trip Updates | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb` | 5000ms | Stop time predictions, delays |
| Alerts | `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/alerts.pb` | 60000ms | Service alerts |

### 5.3 GTFS Static Data

| File | Key Fields | Use |
|------|------------|-----|
| `routes.txt` | route_id, short_name, long_name, route_color | Route list, colors |
| `stops.txt` | stop_id, stop_name, lat, lon | Stop markers, names |
| `stop_times.txt` | trip_id, stop_id, stop_sequence | Stop ordering per route, scheduled times |
| `shapes.txt` | shape_id, lat, lon, sequence | Route polylines |
| `trips.txt` | trip_id, route_id, shape_id | Route-trip-shape mapping |
| `calendar.txt` | service_id, days of week | Active service determination |

**Scale:** 38 routes, 178 stops across the Auburn campus and surrounding area.

### 5.4 Vehicle Position Object

From the GTFS-RT position feed, enriched with trip update data:

```typescript
interface VehiclePosition {
  vehicleId: string;
  routeId: string;
  lat: number;
  lon: number;
  heading: number;      // degrees, 0 = north
  speed: number;        // m/s (convert to mph for display: * 2.237)
  load: number;         // passenger count
  capacity: number;     // vehicle capacity
  nextStopId: string;   // next stop the vehicle will arrive at
  etaSeconds: number;   // seconds until arrival at next stop
  onTime: number;       // 1 = on time, 0 = delayed
  isDelayed: boolean;   // true if delay > 300s (5 min)
  timestamp: number;    // milliseconds since epoch
}
```

### 5.5 ETA Predictions

The XGBoost v1.1 model predicts `time_to_arrival_seconds` for any vehicle-to-stop pair using a residual approach:

```
predicted_arrival = baseline_ETA + predicted_residual
```

**Input features (45):** vehicle state (speed, heading, load, progress), route context (distance_to_target, stops_remaining), temporal (time_of_day, day_of_week, is_rush_hour), historical (segment medians, dwell times), weather (precipitation, temperature), baseline ETAs.

**Output:** Seconds until arrival. Displayed to users as rounded minutes.

---

## 6. User Interactions & Flows

### 6.1 Core Flow: "When does my bus arrive?"

1. User opens app -> sees map with all route polylines, stop markers, and active buses visible
2. Pulls up bottom sheet -> sees sectioned route list with active bus count
3. Taps their route (e.g. "CL - Central Loop") -> sheet shows stop list with ETAs, map isolates that route (polyline + stops + buses); all other routes hidden
4. Finds their stop -> sees "Next 3 arrivals: 3 min, 18 min, 34 min"
5. Optionally taps stop -> map centers on stop with glass-panel callout

### 6.2 Favoriting Flow

1. User taps a route -> Route Detail View
2. Taps the star favorite button -> route is saved
3. Next time user opens Route List, favorited routes appear in Favorites section
4. Toggle "Favorites" pill tab -> only see favorited routes

### 6.3 Bus Inspection Flow

1. User sees an orange bus marker on the map
2. Taps the bus -> glass-panel callout shows route, bus ID, speed, passenger capacity bar, on-time status, ETA to next stop
3. Taps outside -> callout dismisses

### 6.4 Stop Discovery Flow

1. User taps a stop on the map (visible for all routes by default, or for the selected route)
2. Glass-panel callout shows stop name, stop number, ETA, and all route badges at that stop
3. User sees another route badge and taps it -> switches to that route's detail view
4. Alternatively, taps "View More" -> sheet navigates to Stop Detail View with LIVE arrivals and passenger counts

---

## 7. State Management

### 7.1 Application State (Redux Toolkit)

```typescript
interface AppState {
  // Route data (loaded once from GTFS static, refreshed on app start)
  routes: {
    list: Route[];           // all routes from routes.txt
    stops: Record<string, Stop[]>;  // stops per route, ordered by sequence
    shapes: Record<string, Coordinate[]>;  // polyline per route
    loading: boolean;
    error: string | null;
  };

  // Real-time vehicle positions (updated every 5s)
  vehicles: {
    positions: VehiclePosition[];
    lastUpdated: number;
    connected: boolean;
  };

  // ETA predictions (updated on route/stop selection)
  predictions: {
    byStop: Record<string, ArrivalPrediction[]>;  // next 3 arrivals per stop
    loading: boolean;
  };

  // UI state
  ui: {
    selectedRouteId: string | null;
    selectedStopId: string | null;
    sheetPosition: 'collapsed' | 'half' | 'full';
    showFavoritesOnly: boolean;
    activeCallout: { type: 'bus' | 'stop'; id: string } | null;
  };

  // User preferences (persisted to AsyncStorage)
  preferences: {
    favoriteRouteIds: string[];
    favoriteStopIds: string[];
  };

  // Alerts
  alerts: {
    active: ServiceAlert[];
    lastFetched: number;
  };
}
```

### 7.2 Data Refresh Strategy

| Data | Refresh | Method |
|------|---------|--------|
| GTFS static (routes, stops, shapes) | On app launch + pull-to-refresh | REST API or bundled |
| Vehicle positions | Every 5 seconds | Protobuf feed polling |
| Trip updates (ETAs from feed) | Every 5 seconds | Protobuf feed polling |
| Model ETA predictions | On route selection + every 15 seconds while viewing | FastAPI POST `/api/eta/predict` |
| Favorites | Persisted locally | AsyncStorage read on launch |
| Alerts | Every 60 seconds | GTFS-RT alerts feed polling |

---

## 8. Design System: "The Academic Navigator"

### 8.1 Creative North Star

The design moves away from the "utility-only" feel of standard transit apps toward a **High-End Editorial** experience. Tiger Transit is treated as a premium concierge service for the Auburn campus. By blending the authoritative weight of collegiate heritage with sleek, airy principles of modern iOS glassmorphism, we create a "Soft Minimalist" environment that feels intentional and high-contrast.

We avoid the "template" look through significant white space, intentional asymmetry in card layouts, and a "Map-First" philosophy.

### 8.2 Color Palette

Our palette is rooted in Auburn Navy and Burnt Orange, executed with sophisticated tonal depth.

#### Core Colors

| Token | Hex | Usage |
|-------|-----|-------|
| **Primary (Navy)** | `#000D21` | High-authority typography, deep backgrounds |
| **Primary Container** | `#0C2340` | Button fills, navigation elements |
| **Secondary (Burnt Orange)** | `#994700` | Critical action highlights, real-time status |
| **Secondary Container** | `#FF8934` | Active bus icons, LIVE badges |
| **Secondary Fixed** | `#FFB68B` | Warm accents, capacity bars |
| **Background** | `#F8F9FA` | Soft off-white base, reduces eye strain |
| **Error** | `#BA1A1A` | Error states only |

#### Surface Hierarchy (Tonal Layering)

Treat the UI as physical layers. **No 1px borders** - boundaries are defined solely through background color shifts.

| Level | Token | Hex | Usage |
|-------|-------|-----|-------|
| **Level 0 (Base)** | `background` | `#F8F9FA` | Map background, app base |
| **Level 1 (Section)** | `surface-container` | `#EDEEEF` | Grouped content areas |
| **Level 2 (Cards)** | `surface-container-lowest` | `#FFFFFF` | Individual interactive elements |
| **Dim** | `surface-dim` | `#D9DADB` | Inactive/disabled states |

#### Text Colors

| Token | Hex | Usage |
|-------|-----|-------|
| `on-surface` | `#191C1D` | Primary text |
| `on-surface-variant` | `#44474D` | Secondary text, metadata |
| `outline` | `#74777E` | Subtle structural hints |
| `outline-variant` | `#C4C6CE` | Ghost borders (15% opacity only), grab handle |

#### The "No-Line" Rule

**Do not use 1px solid borders to section content.** Boundaries must be defined solely through background color shifts. A transit card (`surface-container-lowest`) sits on a section background (`surface-container`). The contrast between these two shades is sufficient to perceive a boundary without the visual noise of a stroke.

**Ghost Border Fallback:** If a border is absolutely required for accessibility, use `outline-variant` at **15% opacity**. It should be felt, not seen.

### 8.3 Typography

Dual-font strategy balancing collegiate authority with modern readability.

| Role | Font | Usage |
|------|------|-------|
| **Display & Headlines** | **Manrope** (Bold) | Route names, "Welcome" headers, screen titles. Geometric nature provides custom editorial feel |
| **Body & Labels** | **Inter** (Regular/Medium) | All utility data: timestamps, stop names, metadata. Maximum legibility at small sizes |

#### Type Scale

| Style | Size | Weight | Usage |
|-------|------|--------|-------|
| **Headline-LG** | 32pt | Manrope Bold | Primary screen titles, ETA large numbers |
| **Title-MD** | 18pt | Manrope Medium | Card headings, section titles |
| **Body-MD** | 14pt | Inter Regular | Descriptions, secondary content |
| **Label-SM** | 11pt | Inter Medium, Uppercase, 5% letter spacing | Metadata: "BUS ID", "DISTANCE", stop numbers |

### 8.4 Elevation & Depth

Depth is achieved through **Tonal Layering**, not borders or heavy shadows.

| Element | Treatment |
|---------|-----------|
| **Cards on sections** | `#FFFFFF` card on `#EDEEEF` background = natural lift (like fine paper stacked on a desk) |
| **Floating elements (FABs, map controls)** | Navy-tinted ambient shadow: `0 8px 24px rgba(12, 35, 64, 0.08)` |
| **Bottom sheet** | Frosted glass: `backdrop-filter: blur(20px)` with surface-container-lowest at ~95% opacity |
| **Callout bubbles** | Same frosted glass treatment as bottom sheet |

**Shadow tinting:** Always use Primary Navy (`rgba(12, 35, 64, ...)`) for shadows, never pure black. This creates a more natural, luminous depth.

### 8.5 Components

#### Buttons

| Type | Style | Usage |
|------|-------|-------|
| **Primary (Action)** | Burnt Orange gradient (Secondary -> Secondary Container), 10px radius | "Plan Route", primary CTAs |
| **Secondary (Context)** | Navy (Primary Container) fill, 10px radius | Secondary actions |
| **Pill Tabs** | Full-round (999px), surface-container background | "All Routes" / "Favorites" toggle (Apple Maps style) |

#### Draggable Bottom Sheet

- Background: `surface-container-lowest` with 20px top-corner radius
- Grabber handle: `#C4C6CE` pill, 32px wide, recessed 8px from top
- Frosted glass effect: `backdrop-filter: blur(20px)`

#### Cards & Lists

- **No dividers between items.** Use 16px vertical white space or background color shift to separate list items
- **Bus icons:** Use `secondary-fixed` orange for active bus icons
- **Route color accents:** Thin left-edge bar or top bar using route's GTFS `route_color`
- **Card radius:** 8px (round-eight)

#### Status Badges

| Badge | Style |
|-------|-------|
| **LIVE** | Pill badge, secondary-fixed orange (#FF8934) background, white text, subtle pulse animation |
| **DELAYED** | Pill badge, secondary orange (#994700) background, white text |
| **On Time** | Pill badge, muted green background, dark text |
| **Route badge** | Pill badge, route_color background, white text (e.g. "CL", "TR") |

#### Capacity Bar

Visual representation of passenger load:
- Background: `surface-container` (#EDEEEF)
- Fill: `secondary-fixed` orange (#FF8934)
- Height: 4px, border-radius: 2px
- Label: "18/40" in Label-SM style

### 8.6 Spacing & Layout

| Rule | Value |
|------|-------|
| **Base grid** | 8px |
| **Minimum screen-edge margins** | 20px |
| **Card internal padding** | 16px |
| **Between list items** | 16px vertical white space |
| **Section separation** | Background color shift (Level 1 -> Level 0) |
| **Asymmetric padding** | Headers get more top-room (Spacing 12 = 96px) than side-room (Spacing 6 = 48px) for editorial breathing effect |

### 8.7 Glassmorphism Rules

For floating elements (bottom sheet, map overlays, callout bubbles):

- `backdrop-filter: blur(20px)`
- Surface color at ~95% opacity
- Navy-tinted shadow underneath
- **No opaque backgrounds on floating elements** - the map must bleed through subtly

### 8.8 Do's and Don'ts

**Do:**
- Use asymmetric padding for editorial breathing effect
- Use glassmorphism for the status bar area and bottom sheet
- Use Burnt Orange exclusively for "Live" or "Active" states
- Use generous white space (minimum 20px from screen edges)
- Separate content with background color shifts, not lines

**Don't:**
- Use pure black `#000000` for shadows (always navy-tinted)
- Use 1px dividers between route times or list items
- Crowd the edges - the premium aesthetic relies on generous margins
- Use more than 2 font families
- Mix border styles (no borders period, except ghost borders at 15% opacity)

### 8.9 Accessibility

- All interactive elements must have accessible labels
- ETA text must meet WCAG AA contrast ratio (4.5:1)
- Bus markers should be distinguishable by shape, not just color
- VoiceOver/TalkBack support for route list and stop list navigation
- Minimum tap target: 44x44 points
- Ghost borders (outline-variant at 15%) as fallback when tonal contrast alone is insufficient

### 8.10 Performance Targets

| Metric | Target |
|--------|--------|
| App launch to map visible | < 2 seconds |
| Route list populated | < 1 second after launch |
| Vehicle position update render | < 100ms after data received |
| Route selection to stop list display | < 500ms |
| ETA prediction response | < 1 second |
| Smooth marker animation | 60fps during interpolation |
| Memory usage | < 150MB |
| Battery impact | Minimal (5s polling only while app is foregrounded) |

---

## 9. Technical Considerations

### 9.1 Protobuf Decoding

The app must decode GTFS-Realtime protobuf binary data client-side (or via a lightweight API proxy). The reference implementation in `Code/etaspot_reference.ts` uses `gtfs-realtime-bindings` to decode feeds. Trip updates must be processed before position updates so that ETA enrichment is available.

### 9.2 ETA Prediction Integration

Two ETA sources are available:

1. **GTFS-RT trip updates** - provides `etaSeconds` to next stop only. Low latency, available directly from feed.
2. **XGBoost model** - provides predicted arrival times for all remaining stops on a route. Higher accuracy (85.6s MAE) but requires a backend inference call.

**Recommendation:** Use GTFS-RT `etaSeconds` for the bus callout bubble (next stop only). Use the XGBoost model for the stop list view (next 3 arrivals across all stops on a route).

### 9.3 Offline / Error States

| Scenario | Behavior |
|----------|----------|
| No network connection | Show last known vehicle positions (dimmed to surface-dim) + glass-panel "No connection" banner |
| Feed returns no vehicles | Show "No active buses" in route cards using on-surface-variant color |
| Model prediction timeout | Fall back to GTFS-RT trip update ETAs or show "ETA unavailable" |
| Stale vehicle data (> 2 min) | Hide marker from map |

### 9.4 Background Behavior

- Stop polling when app is backgrounded to preserve battery
- Resume polling immediately when app returns to foreground
- Do not use background location or background fetch

---

## 10. Feature Prioritization

### MVP (v1)

- [ ] Full-screen map with bus markers (position + heading + secondary-fixed orange)
- [ ] Smooth bus marker animation between updates (AnimatedRegion)
- [ ] Glassmorphic draggable bottom sheet (collapsed / half / full)
- [ ] Route list with sectioned layout (Active Routes, Favorites, Alerts)
- [ ] Route cards with color accent, active bus count, next ETA
- [ ] Favorite routes (persist locally, pill tab toggle)
- [ ] Route detail view with ordered stop list (timeline style)
- [ ] Next 3 arrival ETAs per stop (XGBoost model)
- [ ] Route polylines on map for all visible routes (Visibility Trio Rule)
- [ ] Stop markers on map for all visible routes (Visibility Trio Rule)
- [ ] Glass-panel stop callout (name, stop number, ETA, route badges, "View More")
- [ ] Glass-panel bus callout (route, bus ID, speed, passenger capacity bar, delay status)
- [ ] Stop Detail View (LIVE badge, arriving buses with capacity bars, all-routes footer)
- [ ] Stale vehicle filtering (> 2 min)
- [ ] Floating map controls (my_location, search placeholder, settings placeholder)
- [ ] Alerts section in route list (GTFS-RT alerts feed)

### v2 (Post-MVP)

- [ ] Search functionality (find a stop or route by name)
- [ ] Settings screen
- [ ] Push notifications for delays on favorited routes
- [ ] Dark mode support
- [ ] "Nearest stop" using device GPS
- [ ] Trip planner (multi-route journeys)
- [ ] Accessibility audit and VoiceOver optimization
- [ ] Onboarding / first-launch tutorial

---

## 11. Stitch Design Reference

The visual designs for this app are prototyped in Google Stitch:

| Resource | Stitch Project ID |
|----------|-------------------|
| **Tiger Transit Map View** (primary) | `17502641370854445841` |
| **Real-time Transit Map** (earlier iteration) | `3380881994904053551` |
| **Route Details - Dark** (dark mode reference) | `13443534689515722492` |

**Key screens in primary project:**
- Route List / Home view (sectioned layout with Active Routes, Favorites, Alerts)
- Stop Detail View ("Student Center, Stop #142" with LIVE badge, arriving buses, capacity bars)
- Multiple iteration variants (No Tabs V2, V3, Reordered Sections)

The design system document in the Stitch project is the visual source of truth. This PRD is the functional/behavioral source of truth.

---

## 12. Glossary

| Term | Definition |
|------|------------|
| **GTFS** | General Transit Feed Specification - standard format for transit schedule data |
| **GTFS-RT** | GTFS Realtime - protobuf-based extension for live vehicle positions and predictions |
| **ETA Spot** | Third-party transit tracking service used by Auburn; provides GTFS-RT feeds |
| **Bottom sheet** | Draggable glassmorphic panel overlaid on the map, the primary navigation UI |
| **Callout bubble** | Glass-panel popup anchored near a map marker showing contextual info |
| **Route color** | Hex color assigned to each route in GTFS `route_color` field |
| **Stale vehicle** | A vehicle whose last position update is older than 2 minutes |
| **Residual model** | The XGBoost v1.1 approach where the model predicts deviation from a historical baseline ETA |
| **Tonal layering** | Depth technique using background color shifts instead of borders or heavy shadows |
| **Glass panel** | Frosted glass UI element with backdrop blur allowing underlying map to bleed through |
| **No-Line rule** | Design constraint: no 1px borders; use background color contrast for boundaries |

---

*Last updated: 2026-03-25 - Updated design system from Stitch "Tiger Transit Map View" prototype*
