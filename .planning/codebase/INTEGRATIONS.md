# External Integrations

**Analysis Date:** 2026-02-03

## APIs & External Services

**ETA SPOT Live Vehicle Tracking:**
- Service: ETA SPOT (auburn.etaspot.com)
  - What it's used for: Real-time vehicle position, speed, heading, occupancy, and ETA data
  - SDK/Client: socket.io-client 4.8.3
  - Auth: Cookie-based via `ETASPOT_COOKIE` environment variable
  - Connection: `backend/src/services/etaspot.service.ts` connects to `https://auburn.etaspot.com` via WebSocket
  - Protocol: Custom binary protocol with `sysRpt` messages containing vehicle telemetry
  - Implementation: ETASpotService singleton emits vehicle position events to backend Socket.IO

**Open-Meteo Weather API:**
- Service: api.open-meteo.com/v1/forecast
  - What it's used for: Historical and forecast weather data (precipitation, temperature)
  - SDK/Client: openmeteo 1.2.3
  - Auth: None (free public API)
  - Implementation: `mobile/src/ETA-Model/getWeatherData.ts` fetches Auburn coordinates weather data
  - Data: Hourly precipitation, precipitation probability, temperature (Auburn, AL)

## Data Storage

**Databases:**
- PostgreSQL 15 + PostGIS
  - Connection: `DATABASE_URL` environment variable
  - Host (docker): postgres:5432
  - Host (local): localhost:5432
  - Credentials: `transit:transit_dev`
  - Database: `tigertransit`
  - Client: Prisma ORM (`@prisma/client` 5.20.0)
  - Models: Agency, Route, Stop, Trip, StopTime, Shape, Calendar, CalendarDate, RouteGeometry, VehiclePosition, ServiceAlert
  - Extension: PostGIS for geospatial queries (points, distance calculations)

**Caching:**
- Redis 7
  - Connection: `REDIS_URL` environment variable
  - Host (docker): redis:6379
  - Host (local): localhost:6379
  - Client: ioredis 5.4.1
  - Purpose: Session storage, real-time vehicle position cache (implied by service architecture)

**File Storage:**
- Local filesystem only
  - GTFS static feed files: `backend/` directory (imported via `scripts/import-gtfs.ts`)
  - CSV import: Uses csv-parse 5.5.6 for parsing GTFS files
  - Route polylines: Encoded as `polyline` format in `RouteGeometry` model

**Mobile Local Storage:**
- React Native Async Storage (`@react-native-async-storage/async-storage` 2.2.0)
  - Purpose: Persist user preferences and cached API responses

## Authentication & Identity

**Auth Provider:**
- Custom/None - Application uses environment-based authentication
  - ETA SPOT: Cookie-based authentication (session ID)
  - Backend API: No authentication layer (development mode)
  - CORS: Configured per environment via `CORS_ORIGIN` variable

## Monitoring & Observability

**Error Tracking:**
- Not detected - No Sentry, Rollbar, or similar configured

**Logs:**
- Console-based logging
  - Backend: `console.log()` calls for HTTP requests, WebSocket connections, ETA SPOT events
  - Mobile: No explicit logging framework detected
  - Implementation: `backend/src/index.ts` logs all requests with ISO timestamp

**Health Check:**
- HTTP: `GET /health` endpoint (`backend/src/routes/health.routes.ts`)
- WebSocket status: ETA SPOT connection status tracked in `etaSpotService.isServiceConnected()`

## CI/CD & Deployment

**Hosting:**
- Docker & Docker Compose (local development)
  - `docker-compose.yml` orchestrates: PostgreSQL, Redis, Node.js backend
  - Backend: node:20-alpine image
  - Production deployment: Not specified (intended for Docker)

**CI Pipeline:**
- Not detected - No GitHub Actions, GitLab CI, or similar

**Package Management:**
- npm for dependencies
- Prisma migrations: `prisma migrate dev` command in backend scripts

## Environment Configuration

**Required env vars:**

Backend (`backend/.env.example`):
- `DATABASE_URL` - PostgreSQL connection string (CRITICAL)
- `REDIS_URL` - Redis connection string (CRITICAL)
- `PORT` - Server port (default 3000)
- `NODE_ENV` - development/production
- `GPS_ENABLED` - Enable GPS provider (false for mock data)
- `GPS_PROVIDER` - mock or actual provider
- `CORS_ORIGIN` - Allowed origins (default http://localhost:19006)
- `ETASPOT_COOKIE` - Authentication for live vehicle data (optional but required for real tracking)
  - Format: `express.sid=s%3A...` cookie string
  - Default fallback: Hardcoded example cookie in `etaspot.service.ts` line 58

Mobile:
- API base URL: Hardcoded in `mobile/src/config/api.config.ts` as `http://10.2.1.96:3001`

**Secrets location:**
- Backend: `.env` file (NOT committed, use `.env.example` as template)
- Mobile: Hardcoded URL in config file (security concern for production)

## Webhooks & Callbacks

**Incoming:**
- Not detected - No webhook receivers configured

**Outgoing:**
- ETA SPOT WebSocket: Bidirectional communication
  - Client events: `subscribe:all`, `subscribe:route`, `subscribe:stop`, `unsubscribe:route`, `unsubscribe:stop`
  - Server events: `sysRpt` (vehicle telemetry)

**Socket.IO Rooms:**
Backend broadcasts vehicle data through Socket.IO rooms:
- `all-vehicles` - All active vehicles
- `route:{routeId}` - Vehicles on specific route
- `stop:{stopId}` - Vehicles approaching specific stop

Mobile subscription:
- `subscribe:all` - Get all vehicle updates
- `subscribe:route` - Get vehicles on specific route
- `subscribe:stop` - Get vehicles approaching stop
- Events received: `vehicles` (batch), `vehicle` (single update), `arrival`, `vehicle:removed`

## Real-time Data Flow

**Vehicle Position Updates:**
1. ETA SPOT sends `sysRpt` WebSocket message to backend service
2. ETASpotService transforms raw ETA SPOT message format to normalized VehiclePosition
3. Backend emits events:
   - `io.to('all-vehicles').emit('vehicle', vehicle)` - All subscribers
   - `io.to('route:{routeId}').emit('vehicle', vehicle)` - Route subscribers
   - `io.to('stop:{stopId}').emit('arrival', vehicle)` - Stop subscribers
4. Mobile receives via `socket.io-client` hooks (`useVehicles`, `useStopArrivals`)
5. Mobile displays on map (`react-native-maps`) with real-time updates

**Periodic Broadcasts:**
- Every 3 seconds: Backend broadcasts all active vehicles to `all-vehicles` room
- Vehicle data filtered by 2-minute staleness threshold

## GTFS Data Integration

**Source:**
- Static GTFS feed files (location not specified in codebase)
- Assumed: Auburn Transit agency GTFS data

**Import Process:**
- Backend script: `backend/scripts/import-gtfs.ts`
- Tools: csv-parse 5.5.6 for CSV parsing
- Destination: PostgreSQL via Prisma
- Tables populated: Agency, Route, Stop, Trip, StopTime, Shape, Calendar, CalendarDate

**Tables Queried by API:**
- `routes` - GET /routes, /routes/:id
- `stops` - GET /stops, /stops/:id, /stops/nearby
- `trips` - Referenced in route details
- `stop_times` - Stop arrival schedules
- `shapes` - Route geometry/polylines
- `calendar` - Service schedules

---

*Integration audit: 2026-02-03*
