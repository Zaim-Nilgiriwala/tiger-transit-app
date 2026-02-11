# Codebase Structure

**Analysis Date:** 2026-02-11

## Directory Layout

```
Tiger Transit/
├── .planning/              # GSD planning artifacts
│   ├── codebase/           # Codebase analysis documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
│   ├── phases/             # Phase-by-phase implementation plans and summaries
│   └── research/           # Research documents for technologies and patterns
├── backend/                # Node.js + Express API server
│   ├── prisma/             # Database schema and migrations
│   ├── scripts/            # Backend utility scripts (GTFS import)
│   └── src/                # TypeScript application code
│       ├── middleware/     # Express middleware (error-handler)
│       ├── routes/         # API route handlers
│       ├── services/       # Business logic (GTFS-RT polling)
│       ├── types/          # TypeScript type definitions
│       └── utils/          # Shared utilities
├── data/                   # ML pipeline data storage
│   └── processed/          # Parquet files for ML training
├── gtfs_data/              # GTFS static feed CSV files
├── mobile/                 # React Native mobile app
│   ├── assets/             # Images, fonts, icons
│   └── src/                # TypeScript/React code
│       ├── components/     # Reusable UI components
│       ├── config/         # App configuration (API URLs)
│       ├── ETA-Model/      # Legacy ETA model code and raw data
│       ├── hooks/          # Custom React hooks
│       ├── navigation/     # React Navigation setup
│       ├── screens/        # Screen components (Map, Routes, Stops, Settings)
│       ├── store/          # Redux store and RTK Query API
│       ├── theme/          # Color palette and styling
│       ├── types/          # TypeScript type definitions
│       └── utils/          # Shared utilities
├── models/                 # Trained XGBoost models and evaluation outputs
│   ├── diagnostics/        # Feature diagnostics and data quality reports
│   └── evaluation/         # Phase 6 evaluation outputs (SHAP, metrics, comparisons)
├── scripts/                # Python ML pipeline scripts
├── docker-compose.yml      # Development environment (PostgreSQL, Redis)
└── package.json            # Root package.json (workspace marker)
```

## Directory Purposes

**`.planning/`:**
- Purpose: GSD workflow artifacts - plans, research, summaries, codebase analysis
- Contains: codebase/ (ARCHITECTURE.md, STRUCTURE.md, STACK.md, etc.), phases/ (01-06 subdirs with PLAN.md, SUMMARY.md), research/ (technology domain research)
- Key files: `.planning/phases/*/PLAN.md` - phase implementation plans, `.planning/codebase/*.md` - codebase reference docs

**`backend/`:**
- Purpose: RESTful API server for GTFS data and real-time vehicle tracking
- Contains: Express application, Prisma ORM, Socket.IO WebSocket server, GTFS-Realtime feed consumer
- Key files: `src/index.ts` - main entry point, `prisma/schema.prisma` - database schema, `src/services/etaspot.service.ts` - GTFS-RT polling service

**`backend/prisma/`:**
- Purpose: Database schema definition and migration history
- Contains: schema.prisma with GTFS models (Route, Stop, Trip, StopTime, Shape, Calendar, VehiclePosition, ServiceAlert)
- Key files: `schema.prisma` - Prisma schema with PostGIS extension

**`backend/src/routes/`:**
- Purpose: Express route handlers for REST API endpoints
- Contains: routes.routes.ts (GET /routes, GET /routes/:id, GET /routes/:id/shape), stops.routes.ts (GET /stops, GET /stops/nearby, GET /stops/:id), vehicles.routes.ts, health.routes.ts
- Key files: All *`.routes.ts` files export Express Router instances

**`backend/src/services/`:**
- Purpose: Business logic layer separated from HTTP handlers
- Contains: etaspot.service.ts - EventEmitter-based GTFS-Realtime feed poller with vehicle position tracking
- Key files: `etaspot.service.ts` - singleton service instance exported

**`data/processed/`:**
- Purpose: Intermediate and final Parquet datasets for ML training
- Contains: telemetry.parquet (filtered vehicle GPS), arrivals.parquet (ground truth stop arrivals), exploded.parquet (per-stop prediction rows), labeled.parquet (rows with time_to_arrival labels), train/val/test splits, featured datasets with 15-27 engineered features
- Key files: `train_featured_v2.parquet`, `val_featured_v2.parquet`, `test_featured_v2.parquet` - final feature sets for Phase 4+ models

**`gtfs_data/`:**
- Purpose: Static GTFS feed CSV files (routes.txt, stops.txt, trips.txt, stop_times.txt, shapes.txt, calendar.txt)
- Contains: Auburn University transit GTFS feed (40+ routes, 178 stops, 1041+ trips)
- Key files: All `.txt` files follow GTFS specification

**`mobile/src/components/`:**
- Purpose: Reusable React components organized by feature area
- Contains: Common/ (Badge, Card, LoadBar, ScreenContainer, SectionHeader), Map/ (MapView, RoutePolyline, StopMarker, VehicleMarker)
- Key files: `Map/MapView.tsx` - main transit map component, `Map/VehicleMarker.tsx` - real-time vehicle position marker

**`mobile/src/screens/`:**
- Purpose: Top-level screen components rendered by React Navigation
- Contains: MapScreen.tsx, RoutesScreen.tsx, RouteDetailScreen.tsx, StopDetailScreen.tsx, SettingsScreen.tsx
- Key files: `MapScreen.tsx` - renders TransitMapView, entry point for map tab

**`mobile/src/store/api/`:**
- Purpose: RTK Query API slice for backend data fetching
- Contains: transitApi.ts with endpoints for routes, stops, shapes, nearby stops
- Key files: `transitApi.ts` - exports API slice and React hooks (useGetRoutesQuery, useGetStopsQuery, etc.)

**`mobile/src/ETA-Model/`:**
- Purpose: Legacy data collection code and raw historical data
- Contains: batchCollector.js, getWeatherData.ts, processTrainingData.js, raw_data/ subdirectory with arrivals CSVs and telemetry JSONL
- Key files: Historical reference only - not used in current ML pipeline

**`models/`:**
- Purpose: Trained XGBoost model artifacts and evaluation outputs
- Contains: baseline_v1.ubj, differentiator_v1.ubj, tuned_v1.ubj, asymmetric_v1.ubj, quantile_p{20,50,75}_v1.ubj, *_metrics.json, evaluation/ subdirectory
- Key files: `tuned_v1.ubj` - Phase 5 Optuna-tuned model, `evaluation/eval_report.md` - Phase 6 comprehensive evaluation

**`models/evaluation/`:**
- Purpose: Phase 6 evaluation outputs (EVAL-01 through EVAL-04)
- Contains: eval_metrics_sliced.json, eval_shap_global.png, eval_shap_waterfall_*.png, eval_comparison.json, eval_residuals*.png, eval_report.md
- Key files: `eval_report.md` - master evaluation report

**`scripts/`:**
- Purpose: Python ML pipeline for ETA model training
- Contains: Data parsers (parse_gtfs.py, parse_arrivals.py, parse_telemetry.py, parse_weather.py), row processing (explode_rows.py, label_join.py, temporal_split.py), feature engineering (build_features.py, build_differentiator_features.py), training (train_baseline.py, train_differentiator.py, train_advanced.py, train_asymmetric_quantile.py), evaluation (evaluate.py)
- Key files: Pipeline executed sequentially: parse_* → explode_rows → label_join → temporal_split → build_features → train_* → evaluate

## Key File Locations

**Entry Points:**
- `backend/src/index.ts`: Express server entry point, Socket.IO initialization, ETASpotService startup
- `mobile/App.tsx`: React Native root component with Redux Provider
- `mobile/index.ts`: Expo entry point, imports App.tsx
- `scripts/train_baseline.py`: Phase 3 baseline XGBoost training
- `scripts/train_advanced.py`: Phase 5 Optuna hyperparameter tuning
- `scripts/evaluate.py`: Phase 6 comprehensive model evaluation

**Configuration:**
- `backend/prisma/schema.prisma`: Database schema for GTFS and real-time data
- `backend/package.json`: Backend dependencies (express, prisma, socket.io, gtfs-realtime-bindings, ioredis)
- `mobile/package.json`: Mobile dependencies (expo, react-native, redux, react-navigation, react-native-maps)
- `docker-compose.yml`: PostgreSQL (PostGIS), Redis, and backend service definitions
- `mobile/src/config/api.config.ts`: API base URL and endpoint definitions
- `.gitignore`: Excludes node_modules, data/processed (large parquet files), models/*.ubj (binary models)

**Core Logic:**
- `backend/src/services/etaspot.service.ts`: GTFS-Realtime feed polling, vehicle position tracking, ETA computation
- `backend/src/routes/routes.routes.ts`: Route queries, stop sequences, polyline shape decoding
- `backend/src/routes/stops.routes.ts`: Stop queries, nearby search with Haversine distance, route-stop mappings
- `mobile/src/store/api/transitApi.ts`: RTK Query API slice with typed endpoints
- `scripts/build_features.py`: Feature engineering (distance, scheduled time, lateness, temporal, weather)
- `scripts/build_differentiator_features.py`: Phase 4 differentiator features (historical dwell/segment times)
- `scripts/label_join.py`: merge_asof join to create ground truth labels

**Testing:**
- Not present - no test files or test framework configuration detected

## Naming Conventions

**Files:**
- Backend routes: `<entity>.routes.ts` (routes.routes.ts, stops.routes.ts)
- Backend services: `<service>.service.ts` (etaspot.service.ts)
- Python scripts: `<verb>_<noun>.py` (parse_gtfs.py, build_features.py, train_baseline.py)
- React components: PascalCase.tsx (MapScreen.tsx, VehicleMarker.tsx)
- Parquet datasets: `<stage>.parquet` or `<split>_featured.parquet` (telemetry.parquet, train_featured_v2.parquet)
- Model artifacts: `<variant>_v<version>.ubj` (baseline_v1.ubj, tuned_v1.ubj, quantile_p20_v1.ubj)

**Directories:**
- Backend: lowercase (routes, services, middleware, types, utils)
- Mobile: lowercase (components, screens, hooks, store, navigation)
- React component subdirs: PascalCase (Map/, Common/)
- Data processing: lowercase (data/processed/, gtfs_data/, models/)

## Where to Add New Code

**New Backend API Endpoint:**
- Primary code: `backend/src/routes/<entity>.routes.ts` - create new Router, define GET/POST handlers
- Mount route: `backend/src/index.ts` - add `app.use('/<path>', <entity>Router)`
- Business logic: `backend/src/services/<entity>.service.ts` if logic is complex
- Types: `backend/src/types/<entity>.types.ts` for request/response interfaces

**New Mobile Screen:**
- Implementation: `mobile/src/screens/<ScreenName>Screen.tsx` - create React.FC component
- Navigation: `mobile/src/navigation/TabNavigator.tsx` or `RootNavigator.tsx` - add Screen to navigator
- API data: `mobile/src/store/api/transitApi.ts` - add RTK Query endpoint if needed
- Components: `mobile/src/components/<Feature>/` - extract reusable components

**New ML Training Variant:**
- Implementation: `scripts/train_<variant>.py` - follow pattern from train_baseline.py or train_advanced.py
- Feature engineering: `scripts/build_<variant>_features.py` if new features needed
- Input: Load from `data/processed/train_featured*.parquet`, `val_featured*.parquet`, `test_featured*.parquet`
- Output: Save model to `models/<variant>_v1.ubj`, metrics to `models/<variant>_metrics.json`

**New Data Processing Step:**
- Implementation: `scripts/<verb>_<noun>.py` - add to pipeline between existing steps
- Input: Read from `data/processed/<previous_step>.parquet`
- Output: Write to `data/processed/<new_step>.parquet`
- Update README: Document new step in pipeline execution order

**Utilities:**
- Backend shared helpers: `backend/src/utils/` - create new .ts files, export functions
- Mobile shared helpers: `mobile/src/utils/` - create new .ts files
- Python ML helpers: Define in existing scripts or create `scripts/<helper>.py` and import in other scripts

## Special Directories

**`.planning/`:**
- Purpose: GSD workflow artifacts for project planning and codebase documentation
- Generated: No - manually created via GSD commands
- Committed: Yes

**`data/processed/`:**
- Purpose: Intermediate ML pipeline datasets (parquet files)
- Generated: Yes - by Python scripts in scripts/
- Committed: No - .gitignore excludes data/processed/ (files are large, 100MB+)

**`models/`:**
- Purpose: Trained XGBoost model binaries and evaluation outputs
- Generated: Yes - by training and evaluation scripts
- Committed: Partial - .ubj model files excluded (large binaries), JSON metrics and PNG plots committed

**`mobile/src/ETA-Model/raw_data/`:**
- Purpose: Historical raw telemetry JSONL and arrivals CSV files
- Generated: No - collected from live ETA SPOT system
- Committed: No - .gitignore excludes raw_data/ (large files)

**`backend/node_modules/`, `mobile/node_modules/`:**
- Purpose: Installed npm dependencies
- Generated: Yes - by npm install
- Committed: No - .gitignore excludes node_modules/

**`mobile/.expo/`:**
- Purpose: Expo build cache and metadata
- Generated: Yes - by Expo CLI during development
- Committed: No - .gitignore excludes .expo/

**`models/diagnostics/`:**
- Purpose: Feature diagnostics and data quality analysis from Phase 4
- Generated: Yes - by scripts/diagnose_features.py
- Committed: Yes - diagnostic outputs are analysis artifacts

**`models/evaluation/`:**
- Purpose: Phase 6 comprehensive evaluation outputs (EVAL-01 through EVAL-04)
- Generated: Yes - by scripts/evaluate.py
- Committed: Yes - evaluation reports and visualizations are deliverables

---

*Structure analysis: 2026-02-11*
