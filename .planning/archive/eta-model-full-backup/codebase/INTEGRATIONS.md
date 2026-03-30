# External Integrations

**Analysis Date:** 2026-03-25

## APIs & External Services

**ETA SPOT (Primary Data Source):**
- ETA SPOT GTFS-RT Feed (Auburn University transit) - Real-time vehicle positions and trip updates
  - Position feed URL: `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/position_updates.pb`
  - Trip updates feed URL: `https://s3.amazonaws.com/etatransit.gtfs/auburn.etaspot.net/trip_updates.pb`
  - Protocol: Protobuf binary (GTFS-Realtime format)
  - Poll interval: 5000ms
  - Client: `gtfs-realtime-bindings` (TypeScript), `google.transit.gtfs_realtime_pb2` (Python)
  - Reference implementation: `Code/etaspot_reference.ts`
  - Stale vehicle filter: excludes vehicles older than 2 minutes

- ETA SPOT IRM (Instant Replay Manager) - Historical playback for training data collection
  - Base URL: `https://auburn.etaspot.com`
  - Protocol: WebSocket via Socket.IO
  - Auth: Session cookie (`express.sid` cookie header)
  - Client: `socket.io-client ^4.8.3` (Node.js)
  - Implementation: `ETA-Model/batchCollector.js`
  - Supports configurable playback speeds (1x, 5x, 10x, 20x)

**Open-Meteo (Weather Data):**
- Historical and forecast weather API - precipitation, temperature for feature engineering
  - URL: `https://api.open-meteo.com/v1/forecast`
  - Coordinates: 32.61°N, -85.48°E (Auburn, AL campus)
  - Timezone: America/Chicago (CST)
  - Fields: `precipitation`, `precipitation_probability`, `temperature_2m` (hourly)
  - Client: `openmeteo` npm package (`fetchWeatherApi`)
  - Implementation: `ETA-Model/getWeatherData.ts`
  - Auth: None (free tier, no API key required)
  - Output: CSV written to `ETA-Model/raw_data/weather_data.csv`

## Data Storage

**Databases:**
- Supabase (PostgreSQL 17) - Primary structured data store
  - Local dev connection: `postgresql://postgres:postgres@127.0.0.1:54322/postgres`
  - Local API: `http://127.0.0.1:54321`
  - Client (Python): `supabase` package (`Code/pushing_data_to_db_test.py`)
  - Supabase config: `supabase/config.toml`
  - Schemas exposed via REST API: `public`, `graphql_public`, `gtfs`, `position_updates`, `trip_updates`

**Database Schemas:**
- `gtfs` schema - GTFS static schedule data
  - `gtfs.calendar` - Service calendar (days of week, date ranges); `supabase/migrations/20260323023315_create_gtfs_calendar.sql`
- `position_updates` schema - Real-time vehicle position telemetry
  - `position_updates.position_updates` - Vehicle positions from GTFS-RT feed; `supabase/migrations/20260319025850_position_updates_table.sql`
  - Columns: `vehicle_id`, `position_timestamp`, `trip_id`, `latitude`, `longitude`, `next_stop_id`, `current_stop_sequence`, `current_stop_status`, `vehicle_label`
  - Primary key: `(vehicle_id, position_timestamp)`
  - Anonymous read/write access granted (`GRANT USAGE ON SCHEMA position_updates TO anon`)
- `trip_updates` schema - GTFS-RT trip delay/ETA data (schema created, tables not yet migrated)

**File Storage (local filesystem):**
- Raw telemetry JSONL: `ETA-Model/raw_data/raw_data_YYYY-MM-DD.jsonl.gz` - Gzip-compressed daily dumps from IRM
- Processed parquet files: `data/processed/*.parquet` - Pandas DataFrames for ML pipeline
  - `gtfs_routes.parquet`, `gtfs_stops.parquet`, `gtfs_stop_times.parquet`, `gtfs_shapes.parquet`
  - `arrivals.parquet` - Parsed arrival/departure records
  - `timepoint_mapping.json` - Stop ID to timepoint mapping
- GTFS static files: `gtfs_data/` - agency.txt, routes.txt, stops.txt, trips.txt, stop_times.txt, shapes.txt, calendar.txt, etc.
- NumPy arrays: `ETA-Model/processed_data_v{10,11}/features.npy`, `labels.npy`, `vehicle_ids.npy` - Normalized feature vectors for PyTorch training
- XGBoost models: `models/baseline_v1.ubj`, `models/v1_1_residual.ubj` - Trained model binaries (UBJSON format)
- PyTorch models: `ETA-Model/models/route_{id}/best_model.pt`
- Optuna study: `models/optuna_study.db` - SQLite database persisting hyperparameter trials across sessions

**Caching:**
- SQLite (Optuna) - Hyperparameter study persistence at `models/optuna_study.db`
- SQLite (ETA SPOT temporary) - `ETA-Model/temporaryFiles/.cache.sqlite`

## Authentication & Identity

**Supabase Auth:**
- Built-in Supabase Auth (configured but minimal use in current codebase)
  - Email/password signup: enabled
  - JWT expiry: 3600s (1 hour) with refresh token rotation
  - Anonymous sign-ins: disabled
  - SMS via Twilio: disabled
  - OAuth providers: Apple configured but disabled
  - MFA: disabled

**ETA SPOT IRM:**
- Session cookie authentication for WebSocket connection
  - Cookie: `express.sid` value hardcoded in `ETA-Model/batchCollector.js`
  - Not parameterized via environment variable - requires manual update

## Monitoring & Observability

**Error Tracking:**
- Not detected - no Sentry, Rollbar, or similar service

**Logs:**
- Console logging only (Python `print()`, Node.js `console.log()`)
- Collection log file: `ETA-Model/temporaryFiles/collector.log`
- FastAPI startup logs model load status and count

## CI/CD & Deployment

**Hosting:**
- Supabase cloud (project name: `Senior_Design`) for production database
- Supabase local dev stack (Docker-based) for development
- FastAPI server: intended for `0.0.0.0:8000`, deployment platform not specified

**CI Pipeline:**
- Not detected - no GitHub Actions, CircleCI, or similar

## Environment Configuration

**Required env vars (Supabase local dev):**
- `OPENAI_API_KEY` - Optional, for Supabase Studio AI assistant
- `S3_HOST`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` - Optional, for experimental OrioleDB S3 storage

**Hardcoded credentials (needs remediation):**
- ETA SPOT IRM session cookie is hardcoded in `ETA-Model/batchCollector.js` (line 11)
- Supabase local URL and publishable key hardcoded in `Code/pushing_data_to_db_test.py` (lines 4-5) - these are local dev values, not production secrets

**Secrets location:**
- Supabase secrets managed via `env()` substitution in `supabase/config.toml`
- No `.env` file detected in current branch state

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## GTFS Static Data

**Tiger Transit GTFS Feed (Auburn University):**
- Files stored locally in `gtfs_data/` directory
- Includes: agency, routes, stops, trips, stop_times, shapes, calendar, calendar_dates, frequencies, fare_attributes, fare_rules, transfers, feed_info
- Used by Python scripts to build stop sequences, route shapes, and scheduled ETAs
- Parsed into parquet format via `scripts/parse_gtfs.py`

---

*Integration audit: 2026-03-25*
