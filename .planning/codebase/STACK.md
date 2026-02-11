# Technology Stack

**Analysis Date:** 2026-02-11

## Languages

**Primary:**
- TypeScript 5.7.2 - Backend API (`backend/`)
- TypeScript 5.9.2 - Mobile app (`mobile/`)
- Python 3.10.2 - ML/data pipeline (`scripts/`)

**Secondary:**
- JavaScript - Data collection scripts (`batchCollector.js`)

## Runtime

**Environment:**
- Node.js v24.12.0 (Backend and mobile)
- Python 3.10.2 (ML pipeline)

**Package Manager:**
- npm - Backend and mobile dependencies
- Lockfiles: `package-lock.json` present in root, `backend/`, and `mobile/`
- pip - Python ML dependencies (no formal requirements.txt in project root; reference requirements in `mobile/src/ETA-Model/temporaryFiles/requirements.txt`)

## Frameworks

**Core:**
- Express.js 4.21.1 - Backend REST API (`backend/src/index.ts`)
- React Native 0.81.5 - Mobile app framework
- Expo ~54.0.31 - React Native development platform
- Prisma ORM 5.20.0 - Database ORM with PostgreSQL

**ML/Data Science:**
- XGBoost 3.1.3 - Gradient boosting ETA prediction model
- Optuna 4.7.0 - Hyperparameter optimization
- scikit-learn (sklearn 0.0, pandas 2.3.3, numpy 2.2.6) - Data preprocessing and time series splitting
- SHAP 0.46.0 - Model explainability
- pandas 2.3.3 - Data processing pipeline
- PyArrow 23.0.0 - Parquet file I/O

**State Management:**
- Redux Toolkit 2.11.2 - Mobile app state management
- React Redux 9.2.0 - React bindings for Redux

**Navigation:**
- React Navigation 7.x - Mobile navigation (`@react-navigation/native`, `@react-navigation/bottom-tabs`, `@react-navigation/native-stack`)

**Testing:**
- Jest (configured but not actively used; `backend/package.json` scripts)

**Build/Dev:**
- ts-node 10.9.2 - TypeScript execution for scripts
- ts-node-dev 2.0.0 - Development server with hot reload
- ESLint 9.17.0 - TypeScript linting (`backend/`)
- TypeScript compiler (tsc) - Build process

## Key Dependencies

**Critical:**
- `@prisma/client` 5.20.0 - Type-safe database client (backend)
- `gtfs-realtime-bindings` 1.1.1 - GTFS-RT protobuf parser for live vehicle positions
- `socket.io` 4.8.3 - WebSocket server for real-time updates (backend)
- `socket.io-client` 4.8.3 - WebSocket client (mobile, backend, root)
- `xgboost` 3.1.3 - ML model core (Python)
- `optuna` 4.7.0 - Hyperparameter tuning (Python)

**Infrastructure:**
- `ioredis` 5.4.1 - Redis client for caching
- `helmet` 8.0.0 - Security middleware
- `cors` 2.8.5 - CORS handling
- `compression` 1.7.4 - Response compression
- `dotenv` 16.4.5 - Environment variable management
- `zod` 3.23.8 - Runtime type validation

**Mobile:**
- `axios` 1.13.2 - HTTP client
- `react-native-maps` 1.20.1 - Map display
- `expo-location` 19.0.8 - Location services
- `@react-native-async-storage/async-storage` 2.2.0 - Persistent storage
- `openmeteo` 1.2.3 - Weather API client

**Data Processing:**
- `csv-parse` 5.5.6 - GTFS CSV parsing (backend)
- `polyline` 0.2.0 - Polyline encoding/decoding

**Python ML:**
- `matplotlib` - Plotting (Agg backend for headless)
- `scipy` - Statistical functions
- `openpyxl` - Excel parsing for timepoint data

## Configuration

**Environment:**
- Backend: `.env` file with `DATABASE_URL`, `REDIS_URL`, `PORT`, `NODE_ENV`, `GPS_ENABLED`, `CORS_ORIGIN`
- Example: `backend/.env.example`
- Mobile: API base URL in `mobile/src/config/api.config.ts` (hardcoded to `http://10.2.1.96:3001`)

**Build:**
- TypeScript configs: `backend/tsconfig.json` (strict mode, ES2022 target, CommonJS modules)
- Mobile TypeScript: `mobile/tsconfig.json` (minimal config, Expo defaults)
- Expo config: `mobile/app.json` (permissions for location, bundler config)
- Prisma schema: `backend/prisma/schema.prisma` (PostgreSQL with PostGIS extension)

**ML Pipeline:**
- No centralized config file; hyperparameters hardcoded in training scripts
- Model artifacts: `.ubj` (XGBoost binary) and `.json` (metrics)
- Data format: Parquet files in `data/processed/`

## Platform Requirements

**Development:**
- Node.js 20+ (currently using 24.12.0)
- Python 3.10+
- Docker and Docker Compose (for Postgres + Redis)
- Expo CLI (for mobile development)

**Production:**
- PostgreSQL 15+ with PostGIS 3.3 extension (geospatial support)
- Redis 7 (caching and real-time features)
- Node.js runtime (backend API)
- Python environment with GPU support for ML training (CUDA preferred; XGBoost configured with `device: "cuda"` in `scripts/train_advanced.py`)
- S3-compatible storage (AWS S3 for GTFS-RT feeds: `auburn.etaspot.net/position_updates.pb`, `trip_updates.pb`)

---

*Stack analysis: 2026-02-11*
