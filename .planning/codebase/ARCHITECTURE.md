# Architecture

**Analysis Date:** 2026-02-03

## Pattern Overview

**Overall:** Client-Server with Real-time WebSocket Communication

**Key Characteristics:**
- **Backend:** Express.js REST API with PostgreSQL database and real-time WebSocket server
- **Frontend:** React Native mobile app with Redux state management
- **Communication:** RESTful HTTP for data queries, WebSocket for real-time vehicle tracking
- **Database:** PostgreSQL with PostGIS extension for geospatial queries
- **Real-time Integration:** Custom ETA Spot vehicle tracking service via WebSocket

## Layers

**Presentation Layer (Mobile):**
- Purpose: User interface for viewing routes, stops, and real-time vehicle locations
- Location: `mobile/src/screens/`, `mobile/src/components/`
- Contains: Screen components (MapScreen, RoutesScreen, StopDetailScreen), reusable UI components (Badge, Card, LoadBar)
- Depends on: Redux store, custom hooks (useVehicles, useRoutePreferences), API client
- Used by: Navigation system (RootNavigator, TabNavigator)

**State Management Layer (Mobile):**
- Purpose: Centralized Redux store for transit data and user preferences
- Location: `mobile/src/store/`
- Contains: Redux slices (routesSlice), RTK Query API client (transitApi)
- Depends on: @reduxjs/toolkit, redux-persist (via AsyncStorage)
- Used by: All screen components via React-Redux hooks

**API Data Layer (Mobile):**
- Purpose: RTK Query generated API hooks and real-time WebSocket connections
- Location: `mobile/src/store/api/transitApi.ts`, `mobile/src/hooks/useVehicles.ts`
- Contains: Query definitions (getRoutes, getRouteDetail, getStops), vehicle subscription hooks
- Depends on: `mobile/src/config/api.config.ts`, Socket.IO client
- Used by: Map components and detail screens

**Route/API Layer (Backend):**
- Purpose: Express route handlers that serve transit data
- Location: `backend/src/routes/`
- Contains: Routes for /routes, /stops, /vehicles, /health endpoints
- Depends on: Prisma ORM, error-handler middleware
- Used by: Express app in index.ts

**Service Layer (Backend):**
- Purpose: Business logic and external integrations
- Location: `backend/src/services/etaspot.service.ts`
- Contains: ETASpotService class for WebSocket connection to vehicle tracking provider
- Depends on: Socket.IO client, EventEmitter
- Used by: Server index.ts for vehicle position broadcasts

**Middleware Layer (Backend):**
- Purpose: Cross-cutting concerns and error handling
- Location: `backend/src/middleware/error-handler.ts`
- Contains: Global error handler, API error factory
- Depends on: Express
- Used by: Express app in index.ts

**Data Access Layer (Backend):**
- Purpose: Database interactions via Prisma ORM
- Location: Prisma models in `backend/prisma/schema.prisma`
- Contains: Models for Route, Stop, Trip, StopTime, Shape, VehiclePosition, ServiceAlert
- Depends on: PostgreSQL, PostGIS extension
- Used by: Route handlers and services

## Data Flow

**Query Flow (Static Data):**

1. Mobile app calls Redux query hook (e.g., `useGetRoutesQuery()`)
2. RTK Query fetches from backend API endpoint (`/routes`, `/stops`, etc.)
3. Backend route handler queries Prisma ORM
4. Prisma executes SQL against PostgreSQL
5. Results returned through route handler response middleware
6. RTK Query caches result in Redux store
7. Component renders from cached Redux state

**Real-time Vehicle Updates Flow:**

1. Backend ETASpotService connects to Auburn ETA Spot WebSocket
2. Receives vehicle position updates (sysRpt messages) with coordinates, route ID, ETA
3. Emits 'vehicle' event with transformed VehiclePosition
4. Express server broadcasts to subscribed WebSocket clients via Socket.IO
5. Mobile app `useVehicles` hook receives 'vehicle' or 'vehicles' events
6. Updates React state with new vehicle positions
7. Map components re-render with updated vehicle markers

**Stop Subscription Flow:**

1. Mobile app subscribes to stop via Socket.IO: `socket.emit('subscribe:stop', stopId)`
2. Backend creates Socket.IO room `stop:{stopId}`
3. Backend checks which vehicles are heading to that stop (nextStopId match)
4. Broadcasts 'arrival' events only for relevant vehicles
5. Mobile receives updates for ETAs at specific stop

**Route Subscription Flow:**

1. Mobile app subscribes to route via Socket.IO: `socket.emit('subscribe:route', routeId)`
2. Backend creates Socket.IO room `route:{routeId}`
3. Backend broadcasts vehicle updates only for vehicles on that route
4. Mobile filters vehicles in local state

## State Management

**Redux Store Structure:**
- `transitApi`: RTK Query cache and middleware for API queries
- `routes`: Manual slice for route preferences (which routes to display)

**Mobile Local State:**
- `useVehicles`: Maintains vehicle array and connection status
- `useRoutePreferences`: AsyncStorage-backed preferences for route visibility
- `MapView`: Region state for map viewport

**Backend State:**
- `ETASpotService`: In-memory Map of vehicle positions
- Socket.IO rooms: Dynamic subscription management

## Key Abstractions

**VehiclePosition Interface:**
- Purpose: Standardized vehicle data across backend and mobile
- Examples: `backend/src/services/etaspot.service.ts`, `mobile/src/hooks/useVehicles.ts`
- Pattern: Shared interface definition for type safety

**ApiResponse Wrapper:**
- Purpose: Consistent API response format with metadata
- Examples: `mobile/src/types/gtfs.types.ts` (ApiResponse generic)
- Pattern: All backend routes return `{ success, data, meta }`

**Route Preferences Context:**
- Purpose: Track which routes user has toggled on/off
- Examples: `mobile/src/hooks/useRoutePreferences.tsx`
- Pattern: Context provider with AsyncStorage persistence

**ETASpotService:**
- Purpose: Encapsulate external ETA Spot WebSocket protocol
- Examples: `backend/src/services/etaspot.service.ts`
- Pattern: EventEmitter class that transforms external messages to internal events

## Entry Points

**Backend Server:**
- Location: `backend/src/index.ts`
- Triggers: `npm run dev` (development) or `npm start` (production)
- Responsibilities: Express app setup, middleware config, Socket.IO setup, route mounting, ETA Spot connection

**Mobile App:**
- Location: `mobile/App.tsx`
- Triggers: Expo start
- Responsibilities: Redux Provider setup, Route Preferences Provider, Navigation initialization

**Map View (Primary Mobile Screen):**
- Location: `mobile/src/screens/MapScreen.tsx` → `mobile/src/components/Map/MapView.tsx`
- Triggers: User opens "Map" tab in tab navigator
- Responsibilities: Coordinate map display, fetch routes/stops/vehicles, manage visibility preferences

## Error Handling

**Strategy:** Centralized error middleware with structured error responses

**Backend Patterns:**
- Route handlers wrap database calls in try-catch
- Errors passed to `next(error)` → caught by global errorHandler
- errorHandler returns consistent JSON: `{ success: false, error: { code, message }, meta }`
- ApiError interface allows statusCode and code properties for HTTP semantics

**Mobile Patterns:**
- RTK Query transformResponse handles API error payloads
- useVehicles hook catches Socket.IO connection errors in state
- Screens display connection status banners when error state is set

**Cross-Cutting Concerns**

**Logging:**
- Backend: console.log at key points (startup, connections, requests)
- Mobile: console.log in useVehicles and Socket.IO event handlers

**Validation:**
- Backend: Query parameter parsing in route handlers (e.g., bbox bounds)
- Mobile: RTK Query transforms response to typed models

**Authentication:**
- Backend: ETA Spot cookie-based auth (passed in Socket.IO extraHeaders)
- Mobile: No API authentication (public transit data, but hardcoded server IP)

**CORS:**
- Backend: express-cors middleware with configurable origin (env var)
- Mobile: Direct Socket.IO connection to backend server

## Architecture Decisions

**Why Express + Socket.IO:**
- Express handles REST queries for static GTFS data
- Socket.IO adds real-time push for vehicle positions without polling
- Clean separation: query-based REST for data, event-based WebSocket for streaming

**Why Redux + RTK Query:**
- RTK Query provides automatic caching for routes/stops queries
- Redux persists route preferences to AsyncStorage
- Scales better than prop drilling for deeply nested map components

**Why PostgreSQL + PostGIS:**
- GTFS data is already normalized relational schema
- PostGIS enables spatial queries (nearby stops by distance)
- Proven for transit applications

**Why Prisma ORM:**
- Type-safe SQL generation from schema
- Automatic migrations
- Works well with TypeScript

**Why Custom ETA Spot Service:**
- Auburn's vehicle data comes from proprietary ETA Spot system
- Service wraps WebSocket protocol, transforms external format to internal VehiclePosition
- EventEmitter pattern allows flexible subscription handling
