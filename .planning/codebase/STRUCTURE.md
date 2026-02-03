# Codebase Structure

**Analysis Date:** 2026-02-03

## Directory Layout

```
Tiger Transit/
├── backend/                    # Express.js REST API + WebSocket server
│   ├── src/
│   │   ├── index.ts           # Server entry point, Express app, Socket.IO setup
│   │   ├── middleware/        # Cross-cutting concerns
│   │   │   └── error-handler.ts
│   │   ├── routes/            # Express route handlers
│   │   │   ├── health.routes.ts
│   │   │   ├── routes.routes.ts
│   │   │   ├── stops.routes.ts
│   │   │   └── vehicles.routes.ts
│   │   ├── services/          # Business logic & external integrations
│   │   │   └── etaspot.service.ts
│   │   ├── types/             # TypeScript type definitions
│   │   ├── utils/             # Shared utilities
│   │   └── (dist/built files)
│   ├── prisma/
│   │   ├── schema.prisma      # Database schema & ORM models
│   │   └── migrations/        # Database migration history
│   ├── scripts/               # Utility scripts
│   │   └── import-gtfs.ts
│   ├── package.json
│   └── tsconfig.json
│
├── mobile/                     # React Native Expo app
│   ├── src/
│   │   ├── components/        # Reusable UI components
│   │   │   ├── Common/        # Generic UI (Badge, Card, LoadBar, etc.)
│   │   │   ├── Map/           # Map-specific components
│   │   │   │   ├── MapView.tsx
│   │   │   │   ├── RoutePolyline.tsx
│   │   │   │   ├── StopMarker.tsx
│   │   │   │   └── VehicleMarker.tsx
│   │   │   └── RouteList/     # Route list components
│   │   ├── screens/           # Top-level screen components
│   │   │   ├── MapScreen.tsx
│   │   │   ├── RoutesScreen.tsx
│   │   │   ├── RouteDetailScreen.tsx
│   │   │   ├── StopDetailScreen.tsx
│   │   │   └── SettingsScreen.tsx
│   │   ├── navigation/        # React Navigation setup
│   │   │   ├── RootNavigator.tsx
│   │   │   └── TabNavigator.tsx
│   │   ├── store/             # Redux state management
│   │   │   ├── index.ts       # Store configuration
│   │   │   ├── api/           # RTK Query API definitions
│   │   │   │   └── transitApi.ts
│   │   │   └── slices/        # Redux slices
│   │   │       └── routesSlice.ts
│   │   ├── hooks/             # Custom React hooks
│   │   │   ├── useVehicles.ts
│   │   │   └── useRoutePreferences.tsx
│   │   ├── config/            # Configuration files
│   │   │   └── api.config.ts
│   │   ├── types/             # TypeScript interfaces
│   │   │   ├── gtfs.types.ts
│   │   │   └── navigation.types.ts
│   │   ├── theme/             # Design tokens
│   │   │   └── index.ts
│   │   ├── utils/             # Utility functions
│   │   ├── ETA-Model/         # Machine learning model (Python)
│   │   └── assets/            # App icons and images
│   ├── App.tsx                # App root component
│   ├── package.json
│   ├── tsconfig.json
│   └── .expo/
│
├── gtfs_data/                 # GTFS feed data
├── .planning/                 # GSD planning documents
│   └── codebase/
├── docker-compose.yml         # Local development database setup
├── README.md
└── QUICKSTART.md
```

## Directory Purposes

**backend/src:**
- Purpose: TypeScript source code for REST API and WebSocket server
- Contains: Route handlers, middleware, services, data models
- Key files: `index.ts` (entry point), route handlers, ETASpotService

**backend/prisma:**
- Purpose: Database schema and migrations
- Contains: schema.prisma (ORM model definitions), migration files
- Key files: `schema.prisma` (defines all database tables and relationships)

**mobile/src/components:**
- Purpose: Reusable React Native UI building blocks
- Contains: Presentational components that render UI
- Subdirectories: `Common/` (generic components), `Map/` (map-specific), `RouteList/` (list components)

**mobile/src/screens:**
- Purpose: Full-screen components representing navigation destinations
- Contains: MapScreen (main map), RoutesScreen (route list), DetailScreens
- Maps to: Tab navigator and stack navigator routes

**mobile/src/store:**
- Purpose: Redux state management
- Contains: RTK Query API client, Redux slices, store configuration
- Key files: `transitApi.ts` (API query definitions), `routesSlice.ts` (route preferences)

**mobile/src/hooks:**
- Purpose: Custom React hooks for shared logic
- Contains: useVehicles (WebSocket connection), useRoutePreferences (AsyncStorage persistence)
- Pattern: Encapsulate complex state/side-effect logic

**mobile/src/navigation:**
- Purpose: React Navigation setup and configuration
- Contains: RootNavigator (main stack), TabNavigator (bottom tabs)
- Pattern: Centralized navigation structure

**mobile/src/types:**
- Purpose: TypeScript interfaces shared across mobile app
- Contains: GTFS types (Route, Stop, Trip), API response types
- Key files: `gtfs.types.ts`, `navigation.types.ts`

**mobile/src/config:**
- Purpose: Application configuration (API endpoints, constants)
- Contains: API endpoint URLs, Auburn coordinates, timeout settings
- Key files: `api.config.ts`

**mobile/src/theme:**
- Purpose: Design tokens (colors, typography, spacing)
- Contains: Centralized style constants
- Key files: `index.ts`

**mobile/src/ETA-Model:**
- Purpose: Machine learning model for ETA prediction (Python)
- Contains: PyTorch models, training data, data preparation scripts
- Note: Separate ML stack from main app; includes versioned model files

## Key File Locations

**Entry Points:**

| File | Purpose |
|------|---------|
| `backend/src/index.ts` | Backend server startup, Express app, Socket.IO setup |
| `mobile/App.tsx` | Mobile app root, Redux provider, navigation root |
| `mobile/src/screens/MapScreen.tsx` | Primary user-facing screen |

**Configuration:**

| File | Purpose |
|------|---------|
| `backend/package.json` | Backend dependencies and scripts |
| `mobile/package.json` | Mobile dependencies and scripts |
| `backend/prisma/schema.prisma` | Database models and migrations |
| `mobile/src/config/api.config.ts` | API endpoints, base URL, coordinates |

**Core Logic:**

| File | Purpose |
|------|---------|
| `backend/src/services/etaspot.service.ts` | Vehicle tracking WebSocket client |
| `backend/src/routes/*.routes.ts` | REST endpoints for routes/stops/vehicles |
| `mobile/src/store/api/transitApi.ts` | RTK Query API client definition |
| `mobile/src/hooks/useVehicles.ts` | Real-time vehicle WebSocket hook |
| `mobile/src/components/Map/MapView.tsx` | Main map display and interaction |

**Testing:**

| File | Purpose |
|------|---------|
| (Not yet implemented) | Jest/Vitest tests for backend |
| (Not yet implemented) | Jest/Expo tests for mobile |

## Naming Conventions

**Files:**

- `*.routes.ts`: Express route handler files (e.g., `routes.routes.ts`, `stops.routes.ts`)
- `*.service.ts`: Service classes with business logic (e.g., `etaspot.service.ts`)
- `*.slice.ts`: Redux slices (e.g., `routesSlice.ts`)
- `*.types.ts`: TypeScript interface/type definitions (e.g., `gtfs.types.ts`, `navigation.types.ts`)
- `*.config.ts`: Configuration constants (e.g., `api.config.ts`)
- Hooks: `use*.ts` or `use*.tsx` (e.g., `useVehicles.ts`, `useRoutePreferences.tsx`)
- Screens: `*Screen.tsx` (e.g., `MapScreen.tsx`, `RoutesScreen.tsx`)
- Components: PascalCase (e.g., `MapView.tsx`, `VehicleMarker.tsx`)

**Directories:**

- Feature-based: `screens/`, `components/`, `hooks/` group by functionality
- Layer-based: `middleware/`, `routes/`, `services/` group by architectural layer
- Data/config: `config/`, `types/`, `store/`, `theme/` group by purpose

## Where to Add New Code

**New Feature - Complete Path (e.g., new "Favorites" screen):**

1. **Screen component**: `mobile/src/screens/FavoritesScreen.tsx`
2. **Navigation**: Add to `mobile/src/navigation/TabNavigator.tsx`
3. **Redux slice** (if needed): `mobile/src/store/slices/favoritesSlice.ts`
4. **Types**: Add to `mobile/src/types/gtfs.types.ts` or new `mobile/src/types/favorites.types.ts`
5. **Components**: `mobile/src/components/Favorites/*.tsx` if building reusable parts

**New Backend Endpoint (e.g., `/alerts`):**

1. **Route handler**: `backend/src/routes/alerts.routes.ts`
2. **Service** (if business logic): `backend/src/services/alerts.service.ts`
3. **Database model**: Add to `backend/prisma/schema.prisma`
4. **Types**: `backend/src/types/alerts.types.ts` (if complex)
5. **Mount route**: Add to `backend/src/index.ts`: `app.use('/alerts', alertsRouter);`

**New Reusable Component (e.g., RouteColorBadge):**

- **If generic**: `mobile/src/components/Common/RouteColorBadge.tsx`
- **If map-specific**: `mobile/src/components/Map/RouteColorBadge.tsx`
- **If feature-specific**: `mobile/src/components/FeatureName/ComponentName.tsx`

**New Custom Hook (e.g., useRouteTracking):**

- Location: `mobile/src/hooks/useRouteTracking.ts`
- Export from: `mobile/src/hooks/index.ts` (barrel export if created)

**Utilities:**

- **Backend shared**: `backend/src/utils/`
- **Mobile shared**: `mobile/src/utils/`

## Special Directories

**backend/prisma/migrations:**
- Purpose: Stores database migration history
- Generated: Yes (auto-generated by `prisma migrate dev`)
- Committed: Yes (version control for schema evolution)

**mobile/.expo:**
- Purpose: Expo CLI configuration and cache
- Generated: Yes (auto-generated by Expo)
- Committed: No (in .gitignore)

**mobile/src/ETA-Model:**
- Purpose: Machine learning model for ETA prediction
- Generated: Partially (output directories for processed data/models)
- Committed: Selectively (model .pt files may be excluded from git)
- Note: Python-based, separate from main React Native app

**backend/node_modules, mobile/node_modules:**
- Purpose: Installed dependencies
- Generated: Yes (from package-lock.json)
- Committed: No (in .gitignore)

## Import Path Aliases

**Backend:**
- No aliases configured (uses relative paths)

**Mobile:**
- Check `tsconfig.json` for baseUrl/paths configuration
- Likely uses `@/` or `~` for absolute paths to `src/`

## Project Structure Rationale

- **Monorepo**: Single repo for frontend and backend allows easy synchronization of data models
- **Layered Backend**: Routes → Services → Prisma ORM follows clean architecture
- **Redux + Hooks**: Combination handles both complex async queries (RTK Query) and local preferences (custom hooks)
- **Feature-Based Frontend**: Screens and components organized by user-facing feature, not technical layer
- **Centralized Config**: api.config.ts and theme/index.ts prevent scattered magic strings
