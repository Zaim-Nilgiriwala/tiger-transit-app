# External Integrations

**Analysis Date:** 2026-02-11

## APIs & External Services

**Transit Data:**
- ETA SPOT GTFS-RT Feed - Live vehicle positions and trip updates
  - Position feed: `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb`
  - Trip updates feed: `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb`
  - SDK/Client: `gtfs-realtime-bindings` 1.1.1 (Protocol Buffers decoder)
  - Polling: 5-second interval (`backend/src/services/etaspot.service.ts`)
  - Auth: None (public S3 endpoints)

**Weather:**
- Open-Meteo API - Historical weather data for ETA model features
  - SDK/Client: `openmeteo` 1.2.3 (mobile app), custom fetch in Python scripts
  - Auth: None (free API)
  - Used for: `precipitation_mm`, `temperature_c` features in ML pipeline (`scripts/parse_weather.py`)

## Data Storage

**Databases:**
- PostgreSQL 15 with PostGIS 3.3
  - Connection: `DATABASE_URL` env var (`postgresql://transit:transit_dev@localhost:5432/tigertransit`)
  - Client: Prisma ORM 5.20.0 (`@prisma/client`)
  - Schema: GTFS tables (routes, stops, trips, stop_times, shapes, calendar) + real-time tables (vehicle_positions, service_alerts, route_geometries)
  - PostGIS extension: Geospatial queries for nearby stops, route shapes

**File Storage:**
- Local filesystem - Parquet files for ML pipeline
  - Data location: `data/processed/` (gitignored, reproducible)
  - Formats: `.parquet` (PyArrow), `.ubj` (XGBoost binary), `.json` (metrics)
  - Model artifacts: `models/` directory (gitignored)
- GTFS static data: `gtfs_data/` (committed)

**Caching:**
- Redis 7
  - Connection: `REDIS_URL` env var (`redis://localhost:6379`)
  - Client: `ioredis` 5.4.1
  - Purpose: Real-time vehicle position caching, API response caching

## Authentication & Identity

**Auth Provider:**
- None (public transit app)
  - Implementation: No authentication system implemented
  - Future consideration: User accounts for saved routes, notifications

## Monitoring & Observability

**Error Tracking:**
- None (console logging only)
  - Current: `console.log` and `console.error` in backend (`backend/src/index.ts`)
  - Future: Sentry or similar recommended

**Logs:**
- Console output with timestamps
  - Backend: Request logging middleware in `backend/src/index.ts`
  - ML pipeline: Print statements in Python scripts
  - No log aggregation or persistence

## CI/CD & Deployment

**Hosting:**
- Not deployed (development only)
  - Local Docker Compose environment (`docker-compose.yml`)
  - Services: Postgres (port 5432), Redis (port 6379), Backend (port 3000)

**CI Pipeline:**
- None
  - No GitHub Actions, CircleCI, or similar
  - No automated testing or deployment

## Environment Configuration

**Required env vars:**

Backend (`backend/.env`):
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `PORT` - API server port (default 3000)
- `NODE_ENV` - Environment (development/production)
- `GPS_ENABLED` - Enable/disable GPS features (boolean)
- `CORS_ORIGIN` - CORS allowed origin (default *)

Mobile:
- None (API base URL hardcoded in `mobile/src/config/api.config.ts`)

**Secrets location:**
- `.env` files (gitignored)
- No secrets management system (Vault, AWS Secrets Manager, etc.)

## Webhooks & Callbacks

**Incoming:**
- None
  - No webhook endpoints implemented

**Outgoing:**
- None
  - No outbound webhooks to external services

## Real-Time Communication

**WebSocket:**
- Socket.IO 4.8.3 - Bidirectional real-time updates
  - Server: Backend (`backend/src/index.ts`)
  - Clients: Mobile app (`mobile/`), root-level socket client
  - Channels:
    - `all-vehicles` - Subscribe to all vehicle position updates
    - `route:{routeId}` - Subscribe to specific route vehicles
    - `stop:{stopId}` - Subscribe to arrivals at specific stop
  - Events emitted:
    - `vehicles` - Vehicle position array
    - `arrivals` - Arrival predictions for stop
    - `connected` / `disconnected` - Connection status

## ML Model Data Pipeline

**Input Data Sources:**
- ETA SPOT IRM API (historical playback)
  - Collector: `batchCollector.js` (Node.js script)
  - Output: JSONL files (`sysRpt_*.jsonl`) with telemetry records
  - Gitignored (reproduced by running collector)

**Processing Pipeline:**
1. Parse raw JSONL → Parquet (`scripts/parse_telemetry.py`, `parse_arrivals.py`, `parse_timepoints.py`, `parse_weather.py`)
2. Build features → `{train,val,test}_featured_v2.parquet` (`scripts/build_features.py`, `build_differentiator_features.py`)
3. Train XGBoost models (`scripts/train_baseline.py`, `train_advanced.py`, `train_asymmetric_quantile.py`)
4. Evaluate → JSON metrics + PNG plots (`scripts/evaluate.py`)

**Model Serving:**
- Not implemented (models saved as `.ubj` files, no inference endpoint)
- Future: FastAPI server or integration into backend Express API

## GTFS Static Data

**Source:**
- Auburn University GTFS feed
  - Format: ZIP archive (`gtfs_109.zip`, gitignored)
  - Extracted to: `gtfs_data/` (CSV files, committed)
  - Import script: `backend/scripts/import-gtfs.ts` (loads into Postgres via Prisma)

**Contents:**
- 40+ routes, 178 stops, 1,041+ trips, 8,269+ stop times, 16,638+ shape points
- Files: `routes.txt`, `stops.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`, `calendar.txt`, `calendar_dates.txt`, `agency.txt`

---

*Integration audit: 2026-02-11*
