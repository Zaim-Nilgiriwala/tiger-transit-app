# Testing Patterns

**Analysis Date:** 2026-02-03

## Test Framework

**Runner:**
- Jest configured for backend
- Not detected for mobile

**Assertion Library:**
- Jest (built-in assertions)

**Run Commands:**
```bash
npm run test              # Run all tests (backend only)
npm run lint             # Run ESLint on backend
```

**Config Location:**
- Backend: `jest.config.ts` or `jest.config.js` (not found in repo - using Jest defaults)
- Mobile: No test configuration

## Test File Organization

**Current State:**
- Backend: No test files found in repository
- Mobile: No test files found in repository

**Convention (not yet established):**

**Recommended Location Pattern:**
- Backend: Co-located with source, named `[filename].test.ts` or `__tests__/[filename].test.ts`
- Mobile: Co-located with source, named `[filename].test.tsx` or `__tests__/[filename].test.tsx`

**Example paths (following TypeScript convention):**
- `backend/src/routes/__tests__/routes.routes.test.ts`
- `backend/src/services/__tests__/etaspot.service.test.ts`
- `mobile/src/hooks/__tests__/useVehicles.test.ts`
- `mobile/src/components/Map/__tests__/MapView.test.tsx`

## Test Structure

No existing tests to reference. However, based on codebase patterns, recommended structure:

**Suite Organization:**

Backend route handler:
```typescript
import { Router, Request, Response, NextFunction } from 'express';

describe('Routes API', () => {
  let router: Router;

  beforeEach(() => {
    // Setup
  });

  afterEach(() => {
    // Cleanup
  });

  describe('GET /routes', () => {
    it('should return all active routes', async () => {
      // Test implementation
    });

    it('should include agency information', async () => {
      // Test implementation
    });

    it('should handle errors gracefully', async () => {
      // Test implementation
    });
  });

  describe('GET /routes/:id', () => {
    it('should return route details with stops', async () => {
      // Test implementation
    });

    it('should throw 404 for non-existent route', async () => {
      // Test implementation
    });
  });
});
```

Mobile hook:
```typescript
import { renderHook, act, waitFor } from '@testing-library/react';
import { useVehicles } from '../useVehicles';

describe('useVehicles hook', () => {
  beforeEach(() => {
    // Setup Socket.IO mock
  });

  afterEach(() => {
    // Cleanup
  });

  it('should connect to WebSocket on mount', () => {
    // Test implementation
  });

  it('should filter vehicles by routeId when provided', () => {
    // Test implementation
  });

  it('should update vehicles on vehicle event', async () => {
    // Test implementation
  });
});
```

**Patterns:**
- Setup: `beforeEach()` to initialize mocks and state
- Teardown: `afterEach()` to clean up connections and mocks
- Assertion: Use Jest matchers (e.g., `expect().toEqual()`, `expect().rejects.toThrow()`)

## Mocking

**Framework:** Jest built-in mocking

**Patterns to implement:**

Database (Prisma):
```typescript
jest.mock('@prisma/client', () => ({
  PrismaClient: jest.fn().mockImplementation(() => ({
    route: {
      findMany: jest.fn(),
      findUnique: jest.fn(),
    },
    stop: {
      findMany: jest.fn(),
    },
    // ... other models
  })),
}));
```

Socket.IO (backend service):
```typescript
jest.mock('socket.io-client', () => ({
  io: jest.fn().mockReturnValue({
    on: jest.fn(),
    emit: jest.fn(),
    disconnect: jest.fn(),
  }),
}));
```

Socket.IO (mobile hook):
```typescript
jest.mock('socket.io-client', () => ({
  io: jest.fn(() => mockSocket),
}));

const mockSocket = {
  on: jest.fn(),
  emit: jest.fn(),
  disconnect: jest.fn(),
  connected: true,
};
```

Express (request/response):
```typescript
import { Request, Response, NextFunction } from 'express';

const mockRequest = {
  params: { id: '123' },
  query: { limit: '200' },
} as unknown as Request;

const mockResponse = {
  json: jest.fn().mockReturnThis(),
  status: jest.fn().mockReturnThis(),
} as unknown as Response;

const mockNext = jest.fn() as NextFunction;
```

**What to Mock:**
- Database connections (Prisma)
- External WebSocket connections (Socket.IO, ETA SPOT)
- Express Request/Response objects in route tests
- API calls (fetch, axios)
- React Navigation (for screens)

**What NOT to Mock:**
- Core utility functions (e.g., `calculateDistance`, `decodePolyline`)
- Type definitions
- Theme/constants
- Pure data transformation logic

## Fixtures and Factories

**Test Data:**

Database fixtures for route testing:
```typescript
const mockRoute = {
  id: 'route-1',
  shortName: '1',
  longName: 'Main Street Route',
  color: 'FF0000',
  textColor: '000000',
  routeType: 3,
  agencyId: 'auburn',
};

const mockStop = {
  id: 'stop-123',
  name: 'Auburn Station',
  code: 'AUB',
  lat: 32.609,
  lon: -85.4809,
  wheelchairBoarding: 1,
  isMajorStop: true,
};
```

Vehicle data for hook testing:
```typescript
const mockVehicle = {
  vehicleId: 'v-001',
  routeId: 'route-1',
  lat: 32.609,
  lon: -85.4809,
  heading: 180,
  speed: 25,
  load: 15,
  capacity: 40,
  nextStopId: 'stop-124',
  etaSeconds: 300,
  onTime: 0,
  lastStopId: 'stop-123',
  isDelayed: false,
  timestamp: Date.now(),
};
```

API response fixture:
```typescript
const mockApiResponse = {
  success: true,
  data: [...],
  meta: {
    timestamp: new Date().toISOString(),
    count: 5,
  },
};
```

**Location:**
- Backend: `backend/src/__fixtures__/` or `backend/src/routes/__fixtures__/`
- Mobile: `mobile/src/__fixtures__/` or `mobile/src/hooks/__fixtures__/`

## Coverage

**Requirements:** Not enforced (no coverage config found)

**Recommended targets:**
- Business logic: 80%+
- Components: 70%+
- Hooks: 80%+
- Utilities: 95%+

**View Coverage:**
```bash
npm run test -- --coverage
```

## Test Types

**Unit Tests:**
- Scope: Individual functions, services, hooks in isolation
- Approach: Mock all dependencies; test one unit at a time
- Examples:
  - `calculateDistance()` with various coordinates
  - `decodePolyline()` with encoded polyline string
  - `transformVehicle()` SysRptMessage transformation
  - Redux slice reducers with sample payloads
  - Hook state updates on event emissions

**Integration Tests:**
- Scope: Multiple units working together
- Approach: Real or closer-to-real dependencies
- Examples:
  - Route handler + Prisma + error handler
  - useVehicles hook + Socket.IO + Redux dispatch
  - MapView component + useVehicles + useGetStopsQuery

**E2E Tests:**
- Framework: Not implemented
- Potential: Expo for mobile E2E testing
- Potential: Supertest or similar for API E2E testing

## Common Patterns

**Async Testing:**

Backend route handler (using Express test pattern):
```typescript
it('should fetch routes successfully', async () => {
  // Arrange
  const mockRoutes = [{ id: '1', shortName: 'A', longName: 'Route A' }];
  prisma.route.findMany.mockResolvedValue(mockRoutes);

  // Act
  await request(app).get('/routes');

  // Assert
  expect(prisma.route.findMany).toHaveBeenCalled();
});
```

Mobile hook async state update:
```typescript
it('should update vehicles when socket emits vehicle event', async () => {
  const { result } = renderHook(() => useVehicles());

  act(() => {
    mockSocket.emit('vehicle', mockVehicle);
  });

  await waitFor(() => {
    expect(result.current.vehicles).toContainEqual(mockVehicle);
  });
});
```

**Error Testing:**

Backend error handler:
```typescript
it('should return 404 when route not found', async () => {
  prisma.route.findUnique.mockResolvedValue(null);

  const res = await request(app).get('/routes/invalid-id');

  expect(res.status).toBe(404);
  expect(res.body.success).toBe(false);
  expect(res.body.error.code).toBe('ROUTE_NOT_FOUND');
});
```

Service error event:
```typescript
it('should emit error event on connection failure', (done) => {
  service.on('error', (error) => {
    expect(error.message).toContain('Connection failed');
    done();
  });

  // Trigger connection error
  mockSocket.emit('connect_error', new Error('Connection failed'));
});
```

Hook error state:
```typescript
it('should set error on connection failure', async () => {
  const { result } = renderHook(() => useVehicles());

  act(() => {
    mockSocket.emit('connect_error', new Error('Network error'));
  });

  await waitFor(() => {
    expect(result.current.error).toBe('Network error');
    expect(result.current.connected).toBe(false);
  });
});
```

## Testing Utilities Needed

Based on codebase dependencies and patterns, recommended test setup packages:

```json
{
  "devDependencies": {
    "jest": "^29.0.0",
    "@testing-library/react": "^14.0.0",
    "@testing-library/react-native": "^12.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "jest-mock-socket": "^0.0.1",
    "ts-jest": "^29.0.0",
    "supertest": "^6.0.0"
  }
}
```

**Jest Config (recommended for backend):**
```javascript
module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  roots: ['<rootDir>/src'],
  testMatch: ['**/__tests__/**/*.test.ts', '**/*.test.ts'],
  collectCoverageFrom: [
    'src/**/*.ts',
    '!src/**/*.d.ts',
    '!src/index.ts'
  ],
  coverageThreshold: {
    global: {
      branches: 60,
      functions: 60,
      lines: 60,
      statements: 60
    }
  }
};
```

---

*Testing analysis: 2026-02-03*
