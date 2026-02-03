# Coding Conventions

**Analysis Date:** 2026-02-03

## Naming Patterns

**Files:**
- Backend routes: `[resource].routes.ts` (e.g., `routes.routes.ts`, `stops.routes.ts`)
- Backend services: `[service].service.ts` (e.g., `etaspot.service.ts`)
- Backend middleware: `[feature]-handler.ts` (e.g., `error-handler.ts`)
- Mobile screens: `[Screen]Screen.tsx` (e.g., `MapScreen.tsx`, `RoutesScreen.tsx`)
- Mobile components: `[Component].tsx` (e.g., `Card.tsx`, `StopMarker.tsx`)
- Mobile hooks: `use[Feature].ts` or `use[Feature].tsx` (e.g., `useVehicles.ts`, `useRoutePreferences.tsx`)
- Mobile store slices: `[feature]Slice.ts` (e.g., `routesSlice.ts`)
- Types: `[domain].types.ts` (e.g., `gtfs.types.ts`, `navigation.types.ts`)

**Functions:**
- camelCase for all functions and methods
- Async functions that are route handlers: prefix with resource name (e.g., in `routes.routes.ts`: `router.get('/', async (req, res, next) => {}`)
- Helper functions: descriptive names (e.g., `calculateDistance`, `decodePolyline`, `transformVehicle`)
- React component functions: PascalCase (components are functions returning JSX)
- Hook functions: camelCase, prefixed with `use` (e.g., `useVehicles`, `useStopArrivals`)

**Variables:**
- camelCase for all variables and constants
- Redux state variables: camelCase (e.g., `selectedRoute`, `visibleRoutes`)
- Interface/type properties: camelCase (e.g., `vehicleId`, `routeId`, `wheelchairAccessible`)
- Constants (exports): camelCase (e.g., `Colors`, `Typography`, `Spacing`, `AUBURN_COORDS`)
- Private class properties: camelCase with underscore prefix (e.g., `_socket`, `_vehicles`)

**Types:**
- Interface names: PascalCase, prefixed with I for basic interfaces, omitted for domain types (e.g., `interface CardProps`, `interface VehiclePosition`, `interface ApiError`)
- Type aliases: PascalCase (e.g., `type ApiResponse<T>`)
- Enum names: PascalCase (none observed, but convention follows TypeScript style)

## Code Style

**Formatting:**
- No enforced formatter (Prettier not configured)
- Indent: 2 spaces (observed throughout)
- Line length: No strict limit observed, but generally kept reasonable
- Quotes: Single quotes for strings (observed in mobile and backend)
- Semicolons: Required (TypeScript strict mode)
- Trailing commas: Used in multi-line objects/arrays

**Linting:**
- ESLint configured in backend only
- Config: `eslint` v9.17.0 with `@typescript-eslint` parser v8.18.0
- Rules: No custom eslint config file found, using defaults
- Mobile project: No ESLint configured
- Backend: `npm run lint` lints `src/**/*.ts`

## Import Organization

**Order:**
1. External dependencies (node modules, installed packages)
2. Relative imports from other parts of codebase
3. Type imports (typically last in a group)

**Examples:**

Backend (from `stops.routes.ts`):
```typescript
import { Router, Request, Response, NextFunction } from 'express';
import { PrismaClient } from '@prisma/client';
import { createError } from '../middleware/error-handler';
```

Mobile (from `MapView.tsx`):
```typescript
import React, { useRef, useState, useMemo, useEffect } from 'react';
import { StyleSheet, View, Text } from 'react-native';
import MapView, { Region } from 'react-native-maps';
import { AUBURN_COORDS } from '../../config/api.config';
import { useGetStopsQuery, useGetRoutesQuery, useGetStopRouteMappingsQuery } from '../../store/api/transitApi';
import { useVehicles } from '../../hooks/useVehicles';
import { useRoutePreferences } from '../../hooks/useRoutePreferences';
import StopMarker from './StopMarker';
import RoutePolyline from './RoutePolyline';
import VehicleMarker from './VehicleMarker';
import { Colors, Typography, Radius, Shadows, Spacing } from '../../theme';
```

**Path Aliases:**
- None observed. All imports use relative paths

## Error Handling

**Patterns:**

Backend uses custom error wrapper:
```typescript
export interface ApiError extends Error {
  statusCode?: number;
  code?: string;
}

export const createError = (message: string, statusCode: number, code: string): ApiError => {
  const error = new Error(message) as ApiError;
  error.statusCode = statusCode;
  error.code = code;
  return error;
};
```

Thrown errors include:
- `statusCode`: HTTP status code (e.g., 404, 400)
- `code`: Machine-readable error code (e.g., 'ROUTE_NOT_FOUND', 'MISSING_PARAMETERS')
- `message`: Human-readable message

Route handlers use try-catch with `next(error)` to pass to error handler middleware:
```typescript
router.get('/:id', async (req: Request, res: Response, next: NextFunction) => {
  try {
    // logic
  } catch (error) {
    next(error);
  }
});
```

Mobile uses state for errors:
```typescript
const [error, setError] = useState<string | null>(null);
// Set error on connection failure:
socket.on('connect_error', (err) => {
  setError(err.message);
});
```

## Logging

**Framework:** `console` (standard JavaScript console methods)

**Patterns:**
- Development info: `console.log()` (connection status, socket events, initialization)
- Warnings: `console.warn()` (missing environment variables)
- Errors: `console.error()` (connection errors, exceptions)

**Examples:**
```typescript
console.log('Connected to ETA SPOT WebSocket');
console.error('ETA SPOT connection error:', error.message);
console.log(`${new Date().toISOString()} ${req.method} ${req.path}`);
```

Error handler includes stack traces in development:
```typescript
...(process.env.NODE_ENV === 'development' && { stack: err.stack })
```

## Comments

**When to Comment:**
- Complex algorithms (e.g., polyline decoding in `routes.routes.ts`, Haversine formula in `stops.routes.ts`)
- Multi-step logic (e.g., "Extract unique stops from the first trip")
- Non-obvious conditional logic (e.g., fallback patterns for finding trip shapes)

**Code block comments:**
```typescript
// Decode Google encoded polyline to array of coordinates
function decodePolyline(encoded: string): Array<{ lat: number; lon: number }> { }

// Filter by bounding box
stops = await prisma.stop.findMany({...})

// Skip vehicles not on a route
if (!msg.serviceState?.rID) {
  return null;
}
```

**Inline comments:** Rarely used; comments are typically block-level

**JSDoc/TSDoc:** Not observed in codebase. Comments use single-line `//` format

## Function Design

**Size:** Functions typically 20-50 lines; larger ones extract sub-logic

**Parameters:**
- Route handlers: standard Express signature `(req: Request, res: Response, next: NextFunction)`
- Utilities: accept structured parameters when multiple options needed
- Hooks: accept options object (e.g., `useVehicles(options: UseVehiclesOptions = {})`)
- React components: destructure props interface (e.g., `const Card: React.FC<CardProps> = ({ children, variant = 'default', style })`)

**Return Values:**
- Routes: return JSON via `res.json()` with standard format:
  ```typescript
  {
    success: true|false,
    data: T,
    meta: { timestamp, count?, cached? }
  }
  ```
- Hooks: return object with state and handlers (e.g., `{ vehicles, connected, error, refresh }`)
- Utilities: return typed values (e.g., `VehiclePosition | null`)

## Module Design

**Exports:**

Backend routes export named export at end of file:
```typescript
export { router as routesRouter };
```

Services export singleton instances:
```typescript
export const etaSpotService = new ETASpotService();
```

Mobile hooks export named functions:
```typescript
export const useVehicles = (options: UseVehiclesOptions = {}) => { }
export const useStopArrivals = (stopId: string, enabled = true) => { }
```

Redux slices export actions and reducer:
```typescript
export const { setSelectedRoute, setVisibleRoutes } = routesSlice.actions;
export default routesSlice.reducer;
```

Theme exports as const object:
```typescript
export const Colors = { /* ... */ } as const;
export const Typography = { /* ... */ } as const;
export const Spacing = { /* ... */ } as const;
```

**Barrel Files:** Not observed; components are imported directly

**Re-exports:** API hooks barrel export from `transitApi.ts`:
```typescript
export const {
  useGetRoutesQuery,
  useGetRouteDetailQuery,
  // ...
} = transitApi;
```

## TypeScript Patterns

**Strict Mode:** Enabled in both `backend/tsconfig.json` and `mobile/tsconfig.json`

**Key compiler options:**
- `noUnusedLocals: true`
- `noUnusedParameters: true`
- `noImplicitReturns: true`
- `noFallthroughCasesInSwitch: true`

**Type usage:**
- Interfaces for component props and service interfaces
- Type aliases for domain types and union types
- Generic types for API responses: `ApiResponse<T>`
- Proper typing of event handlers and callbacks

**React.FC vs function components:**
- Observed pattern: `const ComponentName: React.FC = () => {}` or `const ComponentName: React.FC<Props> = (props) => {}`
- Destructuring props inline is preferred

## Response Format

All API responses follow consistent format:
```typescript
{
  success: boolean,
  data: T,
  meta: {
    timestamp: ISO8601 string,
    count?: number,
    cached?: boolean,
    pointCount?: number,
    radius?: number
  }
}
```

---

*Convention analysis: 2026-02-03*
