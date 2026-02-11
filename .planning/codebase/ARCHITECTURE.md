# Architecture

**Analysis Date:** 2026-02-11

## Pattern Overview

**Overall:** Three-tier hybrid architecture with ML pipeline

**Key Characteristics:**
- Backend API layer (Node.js/TypeScript + Express) serving GTFS transit data and real-time vehicle positions
- Mobile frontend (React Native + Redux) consuming REST APIs and WebSocket feeds
- Offline ML training pipeline (Python/XGBoost) for ETA prediction model development
- Data flows from external GTFS-RT feeds → backend cache → WebSocket broadcast → mobile client
- ML model trained offline from historical telemetry/arrivals data, deployed separately from API

## Layers

**Data Layer (PostgreSQL + Redis):**
- Purpose: Persistent storage of GTFS static data and caching of real-time vehicle positions
- Location: `backend/prisma/schema.prisma`
- Contains: GTFS entities (routes, stops, trips, stop_times, shapes), vehicle positions, service alerts
- Depends on: PostGIS extension for geospatial queries
- Used by: Backend services layer via Prisma ORM

**Backend Service Layer (Node.js):**
- Purpose: Business logic for GTFS data access, real-time feed polling, and WebSocket broadcasting
- Location: `backend/src/services/`
- Contains: `etaspot.service.ts` - GTFS-Realtime feed consumer, vehicle position tracking
- Depends on: Prisma client, gtfs-realtime-bindings, Redis client
- Used by: Express route handlers, Socket.IO event emitters

**Backend API Layer (Express):**
- Purpose: REST endpoints for transit data queries (routes, stops, shapes) and WebSocket connections
- Location: `backend/src/routes/`, `backend/src/index.ts`
- Contains: Route handlers (routes.routes.ts, stops.routes.ts, vehicles.routes.ts, health.routes.ts), middleware (error-handler), main application bootstrap
- Depends on: Service layer, Prisma client
- Used by: Mobile app via HTTP/WebSocket

**Mobile Presentation Layer (React Native):**
- Purpose: User interface for viewing transit maps, routes, stops, and real-time vehicle positions
- Location: `mobile/src/screens/`, `mobile/src/components/`
- Contains: Screen components (MapScreen, RouteDetailScreen, StopDetailScreen), UI components (MapView, VehicleMarker, RoutePolyline)
- Depends on: Redux store, React Navigation, react-native-maps
- Used by: End users on iOS/Android/Web

**Mobile State Management (Redux Toolkit):**
- Purpose: Client-side state management and API data caching
- Location: `mobile/src/store/api/transitApi.ts`
- Contains: RTK Query API slice with endpoints for routes, stops, shapes
- Depends on: Backend API endpoints
- Used by: React components via hooks (useGetRoutesQuery, useGetStopsQuery)

**ML Training Pipeline (Python/Pandas/XGBoost):**
- Purpose: Offline training of ETA prediction models from historical telemetry and arrival data
- Location: `scripts/`
- Contains: Data parsers (parse_gtfs.py, parse_arrivals.py, parse_telemetry.py), feature engineering (build_features.py, build_differentiator_features.py), training scripts (train_baseline.py, train_advanced.py, train_asymmetric_quantile.py), evaluation (evaluate.py)
- Depends on: Parquet files in `data/processed/`, GTFS static files in `gtfs_data/`
- Used by: Offline model development process, outputs to `models/` directory

## Data Flow

**Real-Time Vehicle Position Flow:**

1. ETASpotService polls GTFS-RT feeds (position_updates.pb, trip_updates.pb) every 5 seconds
2. Service decodes Protocol Buffer feeds using gtfs-realtime-bindings
3. Trip updates are processed to extract next stop ETAs and delay information
4. Position updates are merged with trip ETA data to create VehiclePosition objects
5. Positions are stored in in-memory Map and emitted as 'vehicle' events
6. Socket.IO server broadcasts vehicle updates to subscribed clients (by route or stop)
7. Mobile app receives vehicle positions via WebSocket and updates map markers in real-time

**GTFS Static Data Flow:**

1. GTFS CSV files imported via `backend/scripts/import-gtfs.ts`
2. Data loaded into PostgreSQL via Prisma ORM
3. REST API endpoints query Prisma for routes, stops, trips, shapes
4. Mobile app requests data via RTK Query API layer
5. Results cached in Redux store for offline access

**ML Model Training Flow (Offline):**

1. Raw telemetry JSONL files parsed into `data/processed/telemetry.parquet` (parse_telemetry.py)
2. Arrival CSVs parsed into `data/processed/arrivals.parquet` (parse_arrivals.py)
3. GTFS static files parsed into route/stop/shape parquets (parse_gtfs.py)
4. Telemetry downsampled to 60s intervals and exploded into per-stop prediction rows (explode_rows.py)
5. Exploded rows joined with actual arrivals via merge_asof to create ground truth labels (label_join.py)
6. Labeled data split temporally into train/val/test (temporal_split.py)
7. Features engineered from GTFS schedules, weather, and telemetry (build_features.py, build_differentiator_features.py)
8. XGBoost models trained with hyperparameter tuning (train_baseline.py → train_advanced.py)
9. Final model evaluated on test set with sliced metrics and SHAP explanations (evaluate.py)
10. Trained model artifacts saved to `models/*.ubj` for potential deployment

**State Management:**
- Backend: In-memory Map for vehicle positions (2-minute staleness window), Redis for future caching
- Mobile: Redux Toolkit for API data cache, AsyncStorage for user preferences
- ML Pipeline: Parquet files for intermediate data, no state persistence between scripts

## Key Abstractions

**VehiclePosition (Backend):**
- Purpose: Real-time transit vehicle state with ETA prediction
- Examples: `backend/src/services/etaspot.service.ts`, `backend/prisma/schema.prisma`
- Pattern: Interface defining vehicleId, routeId, lat/lon, heading, speed, load, nextStopId, etaSeconds, delay, timestamp

**GTFS Entity Models (Backend):**
- Purpose: Static transit network structure (routes, stops, trips, schedules)
- Examples: `backend/prisma/schema.prisma` - Route, Stop, Trip, StopTime, Shape, Calendar models
- Pattern: Prisma schema matching GTFS specification with PostGIS extensions for geospatial columns

**Feature Vector (ML Pipeline):**
- Purpose: 15-27 engineered features representing a vehicle's state for ETA prediction
- Examples: `scripts/build_features.py` (FEATURE_COLS), `scripts/build_differentiator_features.py` (FEATURE_COLS_V2)
- Pattern: Pandas DataFrame columns combining distance_to_target, scheduled_time, speed, lateness, temporal, weather, and differentiator features (dwell times, segment times)

**XGBoost DMatrix (ML Pipeline):**
- Purpose: Optimized data structure for gradient boosted tree training with categorical features
- Examples: `scripts/train_baseline.py`, `scripts/train_advanced.py` - xgb.DMatrix creation with enable_categorical=True
- Pattern: Conversion from Pandas DataFrame with explicit categorical column types, used for all train/val/test splits

**RTK Query Endpoint (Mobile):**
- Purpose: Type-safe API data fetching with automatic caching and invalidation
- Examples: `mobile/src/store/api/transitApi.ts` - getRoutes, getStops, getRouteShape endpoints
- Pattern: RTK Query builder pattern with typed request/response, transformResponse for unwrapping ApiResponse wrapper

## Entry Points

**Backend API Server:**
- Location: `backend/src/index.ts`
- Triggers: `npm run dev` or `npm start` from backend directory
- Responsibilities: Initialize Express app with middleware (helmet, cors, compression), mount route handlers, start Socket.IO server, initialize ETASpotService polling, listen on port 3000

**Mobile Application:**
- Location: `mobile/App.tsx`, `mobile/index.ts`
- Triggers: `expo start` from mobile directory
- Responsibilities: Initialize Redux store, wrap app in Provider and RoutePreferencesProvider, render RootNavigator with tab navigation

**ML Training Scripts:**
- Location: `scripts/train_baseline.py`, `scripts/train_advanced.py`, `scripts/evaluate.py`
- Triggers: Manual execution via `python scripts/<script>.py` after data preparation
- Responsibilities: Load featured parquet splits, train XGBoost models with early stopping, compute metrics, generate SHAP visualizations, save model artifacts to models/ directory

**Data Processing Pipeline:**
- Location: `scripts/parse_*.py`, `scripts/build_*.py`, `scripts/explode_rows.py`, `scripts/label_join.py`, `scripts/temporal_split.py`
- Triggers: Manual sequential execution in dependency order (parse → explode → label → split → build_features → train)
- Responsibilities: Transform raw telemetry/arrivals/GTFS data through staged processing to create train/val/test feature sets

## Error Handling

**Strategy:** Centralized middleware for backend, try-catch with error events for services, manual error handling in ML scripts

**Patterns:**
- Backend API: Express error-handler middleware (`backend/src/middleware/error-handler.ts`) catches thrown errors, returns standardized JSON with success: false, error code, message
- GTFS-RT Service: Try-catch in poll() method emits 'error' and 'disconnected' events, logs to console, continues polling on next interval
- ML Scripts: Assertions for data quality checks (type mismatches, missing columns), sys.exit(1) on critical failures, print() logging for progress/diagnostics

## Cross-Cutting Concerns

**Logging:** Console logging with timestamps for backend requests (middleware), service events (ETASpotService), and ML script progress (print statements)

**Validation:** Zod schemas for API request validation (not yet implemented), Pandas dtype checks and assertions in ML pipeline (e.g., label_join.py type validation), query parameter parsing in route handlers

**Authentication:** None implemented - open API endpoints and WebSocket connections (future: JWT tokens, API keys)

---

*Architecture analysis: 2026-02-11*
