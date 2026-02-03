# Codebase Concerns

**Analysis Date:** 2026-02-03

## Security Considerations

**Hardcoded ETA SPOT Cookie in Production Code:**
- Risk: API credentials embedded directly in source code at `backend/src/services/etaspot.service.ts:58`
- Current: `const cookie = process.env.ETASPOT_COOKIE || 'express.sid=s%3AnRTVo3BbxAnMxmPE_umYo4ngxbdP8Sym...'`
- Impact: Cookie is exposed in git history, published in containers, and visible to anyone with repo access
- Recommendations: Remove hardcoded cookie entirely, require ETASPOT_COOKIE env var to be set, document requirement in README

**Hardcoded API Server IP Address:**
- Risk: Development IP `10.2.1.96:3001` hardcoded in mobile config at `mobile/src/config/api.config.ts:2`
- Current: `BASE_URL: 'http://10.2.1.96:3001'`
- Impact: Cannot connect to production API, mobile app tied to specific dev environment IP
- Recommendations: Use environment-based configuration, support different API endpoints for dev/staging/production

**Missing Authentication/Authorization:**
- Risk: No auth mechanism on backend endpoints
- Files: `backend/src/routes/routes.routes.ts`, `backend/src/routes/stops.routes.ts`, `backend/src/routes/vehicles.routes.ts`
- Impact: Anyone with access to network can query all transit data; no rate limiting; potential for abuse
- Recommendations: Implement API key or JWT authentication, add rate limiting middleware, document security model

**CORS Configured to Accept All Origins:**
- Risk: `origin: '*'` in Socket.IO setup at `backend/src/index.ts:22-27`
- Files: `backend/src/index.ts`
- Impact: Any website can connect to WebSocket and receive real-time vehicle data
- Recommendations: Restrict to known frontend origins in production, implement origin whitelist

**Credentials in .env File Not in .gitignore:**
- Risk: DATABASE_URL and other secrets in `backend/.env` could be committed
- Current: `.env.example` exists but no evidence `.env` is in .gitignore
- Impact: Production credentials exposed if .env accidentally committed
- Recommendations: Verify `.gitignore` excludes `.env`, `.env.local`, `.env.*.local`

## Tech Debt

**Multiple PrismaClient Instances Created per Request:**
- Issue: Each route file creates new PrismaClient (lines in routes files)
- Files: `backend/src/routes/routes.routes.ts:6`, `backend/src/routes/stops.routes.ts:6`
- Impact: Memory leak, connection pool exhaustion, performance degradation under load
- Fix approach: Create singleton PrismaClient instance in separate module, import across routes

**Weather Data Integration Not Integrated:**
- Issue: `mobile/src/ETA-Model/getWeatherData.ts` is standalone script, not connected to app
- Current: Hardcoded dates (2025-11-06 to 2026-01-14), writes to local CSV, not used by any component
- Impact: Weather feature mentioned in model but not functional in app
- Fix approach: Either remove if not needed, or integrate into actual feature with proper date handling and data flow

**Stale Vehicle Data Cleanup Manual, No Automatic Removal:**
- Issue: `backend/src/services/etaspot.service.ts:143-150` filters stale data (>2min) on read, doesn't remove
- Impact: Memory grows unbounded as vehicles accumulate in Map, can cause memory leaks on long-running server
- Fix approach: Implement periodic cleanup interval, auto-remove vehicles older than threshold, add metrics

**No Input Validation on API Endpoints:**
- Issue: Query parameters parsed without validation
- Files: `backend/src/routes/stops.routes.ts:10-30` (north/south/east/west), `backend/src/routes/stops.routes.ts:97-105` (lat/lon/radius)
- Impact: Invalid values cause crashes or undefined behavior (e.g., NaN from parseFloat on non-numeric input)
- Fix approach: Use Zod schema validation (already in dependencies), validate all query/path parameters

**Socket.IO Subscription Not Enforced:**
- Issue: Clients can subscribe to any room without validation
- Files: `backend/src/index.ts:70-106`
- Impact: No access control - user subscribing to `route:1` doesn't mean they should see that data
- Fix approach: Implement authorization check before allowing room subscription

**Raw SQL Query in Production Code:**
- Issue: `backend/src/routes/stops.routes.ts:66-70` uses raw SQL for stop-route mappings
- Impact: Requires exact table/column names to match schema, breaks with schema changes, harder to maintain
- Fix approach: Use Prisma query builder to construct equivalent query

**No Error Recovery for WebSocket Connection:**
- Issue: ETASpotService reconnects but never clears old socket reference
- Files: `backend/src/services/etaspot.service.ts:136-141`
- Impact: Multiple socket instances can accumulate, event listeners duplicate, memory leak
- Fix approach: Properly clean up old socket listeners before creating new connection

**API Response Format Inconsistent:**
- Issue: Some endpoints return `data` array, some objects, no consistent error format
- Files: Multiple route files inconsistent error handling
- Impact: Mobile client must handle different shapes, harder to write generic error handling
- Fix approach: Define standard response envelope format, document in OpenAPI/Swagger

## Performance Bottlenecks

**Stop-Route Mapping Query Not Cached:**
- Problem: Raw SQL query executed on every request to `/stops/route-mappings`
- Files: `backend/src/routes/stops.routes.ts:61-92`
- Impact: Expensive query on every app load, multiple clients cause repeated database hits
- Improvement path: Cache result with 1-hour TTL, invalidate on GTFS import, use Redis (already in dependencies)

**All Stops Loaded Without Limit:**
- Problem: `GET /stops` default limit is 200 but query fetches all when used
- Files: `backend/src/routes/stops.routes.ts:32-36`
- Impact: Transferring entire stop database to mobile app on first load (likely 2000+ stops)
- Improvement path: Implement pagination, use bounding-box filtering by default, lazy load stops

**Real-time Vehicles Broadcast Every 3 Seconds:**
- Problem: `backend/src/index.ts:138-143` sends all vehicles to all clients every 3 seconds
- Impact: High bandwidth, increases latency, wasted updates when no changes
- Improvement path: Only emit when vehicle data actually changes, use diffs instead of full payload

**Stop Detail Screen Does Multiple Redundant Queries:**
- Problem: `mobile/src/screens/StopDetailScreen.tsx` queries routes serving stop, but also runs useStopArrivals
- Impact: Multiple API calls for same stop, could be consolidated
- Improvement path: Bundle route info and arrivals into single endpoint

**MapView Renders All Routes/Stops/Vehicles Even When Zoomed Out:**
- Problem: `mobile/src/components/Map/MapView.tsx:106-121` renders all visible polylines and markers
- Impact: Performance degrades as more routes/stops added, no level-of-detail or viewport culling
- Improvement path: Implement clustering, only render items in current viewport, defer distant items

## Fragile Areas

**ETASpotService Event Emitter Can't Handle Connection Loss:**
- Files: `backend/src/services/etaspot.service.ts`
- Why fragile: Complex state management with socket lifecycle, reconnection counts, emit events - multiple ways to get out of sync
- Safe modification: Wrap state changes in try-catch, add integration tests for connection/disconnect cycles, document state diagram
- Test coverage: No tests for socket connection scenarios, reconnection behavior untested

**Stop-Route Mapping Dependency on Exact Schema:**
- Files: `backend/src/routes/stops.routes.ts:66-70`
- Why fragile: Raw SQL assumes exact table names (stop_times, trips), column names (stop_id, route_id, trip_id)
- Safe modification: Create migration tests, generate SQL from Prisma schema, document table contract
- Test coverage: No test coverage for this query, would fail silently if schema changes

**Mobile Redux Store Not Type-Safe:**
- Files: `mobile/src/store/slices/routesSlice.ts`, `mobile/src/store/index.ts`
- Why fragile: Redux slices can be modified without type checking, serialization issues possible
- Safe modification: Use type guards, validate state shape on deserialization from AsyncStorage
- Test coverage: No store tests, serialization untested

**Navigation Type Safety Incomplete:**
- Files: `mobile/src/navigation/RootNavigator.tsx`, `mobile/src/types/navigation.types.ts`
- Why fragile: RootStackParamList is separate from actual route definitions, can diverge
- Safe modification: Generate types from route definitions, add lint rule to prevent mismatched params
- Test coverage: No navigation tests, param passing untested

**useRoutePreferences Hook Persists to AsyncStorage Without Error Handling:**
- Files: `mobile/src/hooks/useRoutePreferences.tsx`
- Why fragile: AsyncStorage write failures silent, corrupted data not detected, can break route visibility on app restart
- Safe modification: Add error callbacks, validate persisted data on load, add migration function
- Test coverage: No tests for persistence layer, failure scenarios untested

## Missing Critical Features

**No Real-time ETA Predictions:**
- Problem: App shows next stop ETA from ETASpot raw data, but has trained ML models for predictions
- Files: `mobile/src/ETA-Model/` exists but never integrated
- Blocks: Cannot show predicted arrival times, only reactive ETAs
- Impact: Core feature promised in CLAUDE.md never implemented in app

**No Scheduled vs Actual Comparison:**
- Problem: App shows live vehicle data but not scheduled arrival times
- Impact: Users can't tell if bus is early/late vs schedule
- Solution: Add trip/stop_time schedule data to responses, compare against actual

**No Offline Support:**
- Problem: App requires constant connection to backend
- Impact: Cannot view routes/stops without internet, poor UX in tunnels or remote areas
- Solution: Cache routes/stops/shapes locally, sync when online

## Scaling Limits

**Single Server Architecture:**
- Current capacity: One backend instance on `10.2.1.96:3001`
- Limit: Cannot handle more than ~50 concurrent WebSocket connections before degradation
- Scaling path: Containerize backend, add load balancer, distribute Socket.IO using Redis adapter (already in dependencies)

**ETA SPOT Service Single Connection:**
- Current capacity: One socket connection to auburn.etaspot.com
- Limit: If connection drops, all clients receive no vehicle updates
- Scaling path: Implement fallback data source, add connection redundancy, queue updates during disconnect

**Hardcoded Auburn Coordinates:**
- Current capacity: Fixed to Auburn University location
- Limit: Cannot support multiple transit systems or locations
- Scaling path: Make location configurable, generalize GTFS import, support multiple agencies

**PostgreSQL Connection Pool:**
- Current capacity: Default Prisma pool ~5-10 connections
- Limit: With multiple route files creating PrismaClient, exhausts pool quickly
- Scaling path: Fix singleton PrismaClient, configure appropriate pool size, monitor connection usage

## Test Coverage Gaps

**No Backend Integration Tests:**
- What's not tested: API endpoints, database queries, WebSocket subscriptions, error handling
- Files: All route files (`backend/src/routes/*.ts`), services (`backend/src/services/etaspot.service.ts`)
- Risk: Breaking changes in routes undetected, database queries untested, integration failures
- Priority: High - foundational layer should have test coverage

**No Mobile Navigation Tests:**
- What's not tested: Screen transitions, param passing, deeplinks
- Files: `mobile/src/navigation/*.ts`, navigation-dependent screens
- Risk: Navigation bugs introduced silently, breaking user flow undetected
- Priority: High - core app flow should be tested

**No WebSocket Connection Tests:**
- What's not tested: Connect/disconnect flows, reconnection logic, room subscription
- Files: `backend/src/index.ts`, `mobile/src/hooks/useVehicles.ts`
- Risk: Connection failures in production, reconnection hangs, duplicate events
- Priority: High - real-time feature is critical path

**No API Contract Tests:**
- What's not tested: Response schema validation, field presence/types
- Files: All API endpoints
- Risk: Mobile app gets unexpected response shape, crashes
- Priority: Medium - prevents runtime errors in production

**No Data Validation Tests:**
- What's not tested: Input validation, edge cases (negative coords, NaN values, empty strings)
- Files: `backend/src/routes/*.ts`
- Risk: Invalid inputs cause crashes or undefined behavior
- Priority: Medium - affects API resilience

---

*Concerns audit: 2026-02-03*
