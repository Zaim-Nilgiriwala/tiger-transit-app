# Requirements: Tiger Transit Frontend

**Defined:** 2026-03-25
**Core Value:** When a student pulls up the app, they see exactly where their bus is and when it arrives at their stop — accurate to ~85 seconds — with zero navigation complexity.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Map & Markers

- [x] **MAP-01**: User sees a full-screen map centered on Auburn campus (~32.606, -85.487) on app launch
- [ ] **MAP-02**: User sees live bus markers on the map with positions updated every 5 seconds
- [ ] **MAP-03**: Bus markers animate smoothly between position updates (Reanimated-based, 1000ms interpolation)
- [ ] **MAP-04**: Bus markers display directional heading and use secondary-fixed orange color
- [x] **MAP-05**: Stop markers appear on the map in route color when a route is selected
- [x] **MAP-06**: Route polyline is drawn on the map in route color when a route is selected
- [x] **MAP-07**: Map auto-fits to show all stops + buses when a route is selected
- [x] **MAP-08**: Floating glass-panel map controls (my_location, search placeholder, settings placeholder) are visible above the map
- [x] **MAP-09**: Vehicles with timestamps older than 2 minutes are hidden from the map

### Bottom Sheet

- [x] **SHEET-01**: User can drag the bottom sheet between three snap points (collapsed ~80px, half ~45%, full ~90%)
- [x] **SHEET-02**: Bottom sheet uses glassmorphic styling (frosted glass with backdrop blur, 20px top radius, navy-tinted shadow)
- [x] **SHEET-03**: Bottom sheet grab handle is a subtle #C4C6CE pill, 32px wide
- [x] **SHEET-04**: Bottom sheet transitions use smooth spring animation
- [x] **SHEET-05**: Map remains interactive (pan/zoom) when sheet is at half position

### Route Navigation

- [x] **ROUTE-01**: User sees a sectioned route list as the default sheet content (Active Routes, Favorites, Alerts sections)
- [ ] **ROUTE-02**: Each route card shows route color accent, short name, long name, active bus count, and next ETA
- [x] **ROUTE-03**: Route cards are Level 2 surfaces on Level 1 section backgrounds (no border lines, tonal layering only)
- [x] **ROUTE-04**: Inactive routes (0 active buses) are dimmed and sorted to bottom
- [x] **ROUTE-05**: Tapping a route card transitions the sheet to Route Detail View and draws polyline + stop markers on map
- [x] **ROUTE-06**: Route Detail View shows route name in Headline-LG (32pt Manrope Bold) with color bar and favorite button
- [x] **ROUTE-07**: Route Detail View displays an ordered stop list with next 3 arrival ETAs per stop
- [x] **ROUTE-08**: ETAs are rounded to nearest minute ("3 min", "< 1 min", "No buses en route")
- [x] **ROUTE-09**: User can tap a stop in the list to center the map on that stop
- [x] **ROUTE-10**: Back button returns from Route Detail to Route List

### Stop Detail

- [ ] **STOP-01**: User can access Stop Detail View via "View More" from stop callout or direct stop tap
- [ ] **STOP-02**: Stop Detail shows stop name (Headline-LG), stop number (Label-SM), route count, and city
- [ ] **STOP-03**: LIVE status badge pulses in secondary-fixed orange when buses are arriving
- [ ] **STOP-04**: Each arriving bus shows route name, bus ID, delay status badge, ETA, and passenger capacity bar
- [ ] **STOP-05**: Capacity bar visually represents passenger load (secondary-fixed orange fill on surface-container background)
- [ ] **STOP-06**: "All Routes at this stop" footer shows color-coded pill badges for each route serving the stop
- [ ] **STOP-07**: Tapping a route badge in the footer switches to that route's detail view

### Callout Bubbles

- [ ] **CALL-01**: Tapping a bus marker opens a glass-panel callout showing route, bus ID, speed, passengers, delay status, ETA to next stop
- [ ] **CALL-02**: Tapping a stop marker opens a glass-panel callout showing stop name, stop number, ETA, route badges, "View More"
- [ ] **CALL-03**: Callouts use glassmorphic styling (backdrop blur, surface-container-lowest at ~95% opacity)
- [ ] **CALL-04**: Only one callout can be open at a time; tapping outside dismisses it
- [ ] **CALL-05**: Callout data refreshes with each 5s polling cycle

### Favorites & Personalization

- [ ] **FAV-01**: User can favorite a route via star button in Route Detail header
- [ ] **FAV-02**: Favorited routes are pinned to top of route list and shown in Favorites section
- [ ] **FAV-03**: User can toggle between "All Routes" and "Favorites" via pill tab control (999px full-round)
- [ ] **FAV-04**: Favorite selections persist across app sessions via AsyncStorage

### Real-Time Data

- [x] **DATA-01**: App decodes GTFS-RT protobuf binary feeds (position updates + trip updates) client-side
- [x] **DATA-02**: Position and trip update feeds are polled every 5 seconds while app is in foreground
- [x] **DATA-03**: Polling stops when app is backgrounded and resumes immediately on foreground
- [x] **DATA-04**: Trip updates are processed before position updates so ETA enrichment is available
- [x] **DATA-05**: GTFS static data (routes, stops, shapes, trips, calendar) loads on app launch

### ETA Predictions

- [ ] **ETA-01**: Bus callout shows GTFS-RT feed ETA for next stop (low-latency, single stop)
- [x] **ETA-02**: Stop list shows XGBoost model predictions for next 3 arrivals (multi-stop, higher accuracy)
- [x] **ETA-03**: ETA predictions refresh every 15 seconds while viewing a route
- [x] **ETA-04**: If model prediction times out, app falls back to GTFS-RT trip update ETAs or shows "ETA unavailable"

### Alerts & Error States

- [ ] **ALERT-01**: Service alerts from GTFS-RT alerts feed are displayed in the Alerts section of the route list
- [ ] **ALERT-02**: Alerts feed is polled every 60 seconds
- [ ] **ERR-01**: No network connection shows last known positions dimmed to surface-dim + "No connection" glass-panel banner
- [x] **ERR-02**: Routes with no active buses show "No active buses" in on-surface-variant color
- [x] **ERR-03**: Loading states provide visual feedback during data fetch

### Design System

- [x] **DS-01**: App implements the Academic Navigator design system with tonal layering (Level 0/1/2 surfaces, no border lines)
- [x] **DS-02**: Typography uses Manrope (headlines, bold) + Inter (body, labels) dual-font system
- [x] **DS-03**: Type scale follows Headline-LG (32pt), Title-MD (18pt), Body-MD (14pt), Label-SM (11pt uppercase)
- [x] **DS-04**: All shadows use navy-tinted color (rgba(12, 35, 64, ...)), never pure black
- [x] **DS-05**: Minimum 20px margins from screen edges; 8px base grid for spacing
- [x] **DS-06**: Status badges use pill shape: LIVE (orange pulse), DELAYED (orange), On Time (muted green)
- [x] **DS-07**: All interactive elements have minimum 44x44pt tap targets
- [x] **DS-08**: ETA text meets WCAG AA contrast ratio (4.5:1)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Search & Discovery

- **SRCH-01**: User can search for routes and stops by name
- **SRCH-02**: "Nearest stop" feature using device GPS

### Settings & Preferences

- **SET-01**: Settings screen for app preferences
- **SET-02**: Dark mode toggle and dark color scheme

### Notifications

- **NOTF-01**: Push notifications for delays on favorited routes

### Advanced Features

- **ADV-01**: Trip planner for multi-route journeys
- **ADV-02**: Onboarding / first-launch tutorial
- **ADV-03**: Accessibility audit and VoiceOver/TalkBack optimization

## Out of Scope

| Feature | Reason |
|---------|--------|
| Backend / API development | Supabase + FastAPI already exist; this is frontend only |
| Background location tracking | Battery drain; PRD explicitly prohibits |
| Tab bar navigation | Design evolved to single-screen map + bottom sheet |
| Full offline mode | Complex caching; show dimmed last-known state instead |
| Authentication / user accounts | Not needed for transit tracking |
| Dark mode | Doubles design system work; structure tokens for easy v2 addition |
| Push notifications | Requires backend notification infrastructure |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| MAP-01 | Phase 1 | Complete |
| MAP-02 | Phase 2 | Pending |
| MAP-03 | Phase 5 | Pending |
| MAP-04 | Phase 2 | Pending |
| MAP-05 | Phase 4 | Complete |
| MAP-06 | Phase 4 | Complete |
| MAP-07 | Phase 4 | Complete |
| MAP-08 | Phase 1 | Complete |
| MAP-09 | Phase 2 | Complete |
| SHEET-01 | Phase 3 | Complete |
| SHEET-02 | Phase 3 | Complete |
| SHEET-03 | Phase 3 | Complete |
| SHEET-04 | Phase 3 | Complete |
| SHEET-05 | Phase 3 | Complete |
| ROUTE-01 | Phase 3 | Complete |
| ROUTE-02 | Phase 3+4 | Partial (ETA deferred to Phase 4) |
| ROUTE-03 | Phase 3 | Complete |
| ROUTE-04 | Phase 3 | Complete |
| ROUTE-05 | Phase 4 | Complete |
| ROUTE-06 | Phase 4 | Complete |
| ROUTE-07 | Phase 4 | Complete |
| ROUTE-08 | Phase 4 | Complete |
| ROUTE-09 | Phase 4 | Complete |
| ROUTE-10 | Phase 4 | Complete |
| STOP-01 | Phase 6 | Pending |
| STOP-02 | Phase 6 | Pending |
| STOP-03 | Phase 6 | Pending |
| STOP-04 | Phase 6 | Pending |
| STOP-05 | Phase 6 | Pending |
| STOP-06 | Phase 6 | Pending |
| STOP-07 | Phase 6 | Pending |
| CALL-01 | Phase 5 | Pending |
| CALL-02 | Phase 5 | Pending |
| CALL-03 | Phase 5 | Pending |
| CALL-04 | Phase 5 | Pending |
| CALL-05 | Phase 5 | Pending |
| FAV-01 | Phase 6 | Pending |
| FAV-02 | Phase 6 | Pending |
| FAV-03 | Phase 6 | Pending |
| FAV-04 | Phase 6 | Pending |
| DATA-01 | Phase 2 | Complete |
| DATA-02 | Phase 2 | Complete |
| DATA-03 | Phase 2 | Complete |
| DATA-04 | Phase 2 | Complete |
| DATA-05 | Phase 2 | Complete |
| ETA-01 | Phase 5 | Pending |
| ETA-02 | Phase 4 | Complete |
| ETA-03 | Phase 4 | Complete |
| ETA-04 | Phase 4 | Complete |
| ALERT-01 | Phase 6 | Pending |
| ALERT-02 | Phase 6 | Pending |
| ERR-01 | Phase 6 | Pending |
| ERR-02 | Phase 3 | Complete |
| ERR-03 | Phase 3 | Complete |
| DS-01 | Phase 1 | Complete |
| DS-02 | Phase 1 | Complete |
| DS-03 | Phase 1 | Complete |
| DS-04 | Phase 1 | Complete |
| DS-05 | Phase 1 | Complete |
| DS-06 | Phase 1 | Complete |
| DS-07 | Phase 1 | Complete |
| DS-08 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 62 total
- Mapped to phases: 62
- Unmapped: 0

---
*Requirements defined: 2026-03-25*
*Last updated: 2026-03-25 after roadmap creation*
