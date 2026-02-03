# Technology Stack

**Analysis Date:** 2026-02-03

## Languages

**Primary:**
- TypeScript 5.7+ - All backend and mobile source code
- JavaScript - Mobile build scripts and Expo configuration

**Secondary:**
- Python - ETA/ML prediction system (separate; see CLAUDE.md in ETA-Model/)

## Runtime

**Environment:**
- Node.js 20 (Alpine) - Backend production container
- Expo 54.0.31 - Mobile runtime (React Native)
- React Native 0.81.5 - Mobile native runtime

**Package Manager:**
- npm - All Node.js dependencies
- Lockfiles: package-lock.json present in backend and mobile

## Frameworks

**Core:**
- Express 4.21.1 - HTTP/REST API server (`backend/src/index.ts`)
- React 19.1.0 - Mobile UI framework (`mobile/App.tsx`)
- React Native 0.81.5 - Cross-platform mobile (Android/iOS/Web)

**State Management:**
- Redux Toolkit 2.11.2 - Mobile state management (`mobile/src/store/index.ts`)
- Redux Query (RTK Query) - Mobile API data fetching (`mobile/src/store/api/transitApi.ts`)

**Real-time Communication:**
- Socket.IO 4.8.3 (server) - WebSocket API for live vehicle data (`backend/src/index.ts`)
- Socket.IO-Client 4.8.3 (client) - Mobile WebSocket connections (`mobile/src/hooks/useVehicles.ts`)

**Navigation:**
- React Navigation 7.1.27 - Mobile screen navigation
  - Bottom Tabs 7.9.1 - Tab-based navigation
  - Native Stack 7.9.1 - Stack-based navigation
  - Native 7.1.27 - Navigation base

**Maps & Location:**
- React Native Maps 1.20.1 - Map display and markers (`mobile/src/components/Map/`)
- Expo Location 19.0.8 - Device GPS coordinates

**Testing:**
- Jest - Test runner (configured in backend package.json)

**Build/Dev:**
- Expo CLI - Mobile development and building
- ts-node-dev 2.0.0 - Hot-reloading TypeScript development (`backend` dev script)
- TypeScript Compiler (tsc) - Build backend to `dist/`

## Key Dependencies

**Critical Backend:**
- `@prisma/client` 5.20.0 - ORM for PostgreSQL database operations
- `compression` 1.7.4 - HTTP response compression middleware
- `cors` 2.8.5 - CORS handling for mobile client requests
- `helmet` 8.0.0 - Security headers middleware
- `ioredis` 5.4.1 - Redis client for caching/sessions
- `zod` 3.23.8 - Runtime schema validation for API inputs

**Data Processing Backend:**
- `csv-parse` 5.5.6 - GTFS CSV file parsing (in `backend/scripts/import-gtfs.ts`)
- `polyline` 0.2.0 - Encoded polyline encoding/decoding for route shapes

**Mobile HTTP:**
- `axios` 1.13.2 - HTTP client (appears in mobile but no direct imports detected; possibly transitive)

**Mobile Storage:**
- `@react-native-async-storage/async-storage` 2.2.0 - Persistent local storage

**Mobile UI:**
- `@expo/vector-icons` 15.0.3 - Icon library
- `react-dom` 19.1.0 - React DOM for web builds
- `react-native-web` 0.21.0 - React Native web support
- `react-native-safe-area-context` 5.6.0 - Safe area handling
- `react-native-screens` 4.16.0 - Native screen components
- `expo-status-bar` 3.0.9 - Status bar management

**Weather Data:**
- `openmeteo` 1.2.3 - Open-Meteo weather API client (`mobile/src/ETA-Model/getWeatherData.ts`)

## Configuration

**Environment:**
Backend uses dotenv for configuration:
- `DATABASE_URL` - PostgreSQL connection string
- `REDIS_URL` - Redis connection string
- `PORT` - Server port (default: 3000)
- `NODE_ENV` - Environment (development/production)
- `GPS_ENABLED` - Enable GPS data collection (false by default)
- `GPS_PROVIDER` - GPS provider selection (mock/real)
- `CORS_ORIGIN` - Allowed CORS origins
- `ETASPOT_COOKIE` - Authentication cookie for ETA SPOT WebSocket service (required for live vehicle tracking)

Mobile configuration in `mobile/src/config/api.config.ts`:
- `API_CONFIG.BASE_URL` - Backend API base URL (http://10.2.1.96:3001)
- `API_CONFIG.TIMEOUT` - HTTP timeout (10000ms)
- Location constants: `AUBURN_COORDS` (latitude, longitude deltas)

**Build:**
- Backend TypeScript config: `backend/tsconfig.json`
  - Target: ES2022
  - Module: commonjs
  - Output: `dist/` directory
  - Strict mode enabled
  - Source maps enabled
- Mobile TypeScript config: `mobile/tsconfig.json` (extends Expo defaults)

**Database:**
- Prisma schema: `backend/prisma/schema.prisma`
  - PostgreSQL with PostGIS extension for geospatial data
  - Models: Agency, Route, Stop, Trip, StopTime, Shape, Calendar, CalendarDate, RouteGeometry, VehiclePosition, ServiceAlert

## Platform Requirements

**Development:**
- Node.js 20+ with npm
- PostgreSQL 15+ with PostGIS extension
- Redis 7+
- Expo CLI for mobile development
- iOS simulator (macOS) or Android emulator

**Production:**
- Docker & Docker Compose
- PostgreSQL 15 (postgis/postgis:15-3.3)
- Redis 7-alpine
- Node.js 20-alpine runtime
- Port 3000 for backend API

---

*Stack analysis: 2026-02-03*
