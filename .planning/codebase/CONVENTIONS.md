# Coding Conventions

**Analysis Date:** 2026-02-11

## Naming Patterns

**Files:**
- Python: snake_case (e.g., `train_advanced.py`, `build_differentiator_features.py`)
- TypeScript: kebab-case with suffix (e.g., `health.routes.ts`, `etaspot.service.ts`, `error-handler.ts`)
- Route handlers: `{resource}.routes.ts`
- Services: `{name}.service.ts`
- Middleware: `{name}-{action}.ts`

**Functions:**
- Python: snake_case (e.g., `compute_gps_speed()`, `load_featured_v2()`, `haversine_meters()`)
- TypeScript: camelCase (e.g., `getVehicles()`, `fetchFeed()`, `processPositionUpdates()`)

**Variables:**
- Python: SCREAMING_SNAKE_CASE for constants (e.g., `GPS_SPEED_CAP_MPS`, `IDLE_SPEED_THRESHOLD`, `MIN_OBS`)
- Python: snake_case for locals (e.g., `pings_featured`, `hist_segments`, `split_name`)
- TypeScript: SCREAMING_SNAKE_CASE for constants (e.g., `POLL_INTERVAL_MS`, `POSITION_FEED_URL`)
- TypeScript: camelCase for locals (e.g., `vehicleId`, `pollTimer`, `isConnected`)

**Types:**
- TypeScript: PascalCase for interfaces (e.g., `VehiclePosition`, `TripEta`)
- Python: No explicit type classes, but uses type hints with standard types

## Code Style

**Formatting:**
- Python: No formatter config detected; follows PEP 8 style manually
- TypeScript: Prettier likely used (inferred from consistent 2-space indentation)
- TypeScript indentation: 2 spaces
- Python indentation: 4 spaces
- String quotes: Python uses double quotes predominantly; TypeScript uses single quotes

**Linting:**
- TypeScript: ESLint configured in `backend/package.json` with `@typescript-eslint/eslint-plugin` and `@typescript-eslint/parser`
- TypeScript strict mode enabled in `tsconfig.json`: `"strict": true`, `noUnusedLocals`, `noUnusedParameters`, `noImplicitReturns`, `noFallthroughCasesInSwitch`
- Python: No linting config detected (no `.pylintrc`, `.flake8`, or `pyproject.toml` with tool configs)
- Run linting: `npm run lint` (TypeScript backend)

## Import Organization

**Order:**
- Python standard library first, then third-party, then local imports
- Example from `scripts/train_advanced.py`:
  1. Standard library: `argparse`, `json`, `sys`, `time`, `warnings`, `pathlib`
  2. Third-party: `numpy`, `optuna`, `sklearn`, `xgboost`
  3. Local: `from build_differentiator_features import ...`
- TypeScript: External packages first, then local imports
- Example from `backend/src/index.ts`:
  1. External: `express`, `http`, `socket.io`, `cors`, `helmet`, `compression`, `dotenv`
  2. Local: `./middleware/error-handler`, `./routes/*`, `./services/etaspot.service`

**Path Aliases:**
- Not detected in this codebase

## Error Handling

**Patterns:**
- Python ML scripts: Minimal explicit error handling; rely on exceptions bubbling up
- Python data processing: Assert statements for data integrity checks (e.g., `assert len(df) == n_before`)
- TypeScript async functions: try/catch with `next(error)` pattern for Express routes
- Example from `backend/src/routes/health.routes.ts`:
```typescript
try {
  await prisma.$queryRaw`SELECT 1`;
  await redis.ping();
  res.json({ success: true, data: {...} });
} catch (error) {
  next(error);
}
```
- TypeScript services: Emit 'error' events for async failures (e.g., `this.emit('error', err)` in `etaspot.service.ts`)

## Logging

**Framework:**
- Python: `print()` statements for console output
- TypeScript: `console.log()` / `console.error()`

**Patterns:**
- Python scripts use structured print sections with decorators:
```python
print(f"\n{'='*60}")
print("SECTION TITLE")
print(f"{'='*60}")
```
- Python uses f-strings for formatted output with alignment (e.g., `f"{value:>8.1f}"`)
- TypeScript logs timestamps with ISO format: `console.log(\`${new Date().toISOString()} ${req.method} ${req.path}\`)`
- TypeScript service logs events: "Client connected", "ETA SPOT service connected", etc.

## Comments

**When to Comment:**
- Python docstrings at top of every script file describing purpose, usage, inputs, outputs
- Python docstrings for complex functions (e.g., `compute_gps_speed()`, `compute_historical_segments()`)
- Inline comments for non-obvious logic (e.g., GPS jitter filtering, temporal gap handling)
- Section dividers in Python scripts (e.g., `# ---------------------------------------------------------------------------`)

**JSDoc/TSDoc:**
- Not consistently used in TypeScript code
- Interfaces have inline comments for clarity (e.g., `VehiclePosition` fields)

## Function Design

**Size:**
- Python: Functions range from 20-150 lines; complex pipelines broken into helper functions
- TypeScript: Methods are concise (10-50 lines); event handlers are small

**Parameters:**
- Python: Explicit DataFrame parameters with type hints (e.g., `def compute_gps_speed(pings: pd.DataFrame) -> pd.DataFrame`)
- Python config passed as module-level constants, not function parameters
- TypeScript: Interface-typed parameters (e.g., `routeId: string`, `vehicle: VehiclePosition`)

**Return Values:**
- Python: DataFrames for transformations, dict for aggregates, explicit return types in signatures
- TypeScript: Typed returns (e.g., `Promise<void>`, `VehiclePosition[]`, `boolean`)
- TypeScript services: Void for side-effect methods (e.g., `start(): void`, `stop(): void`)

## Module Design

**Exports:**
- Python: Functions and constants exported via `__all__` or defined at module level (e.g., `FEATURE_COLS_V2`, `load_featured_v2()`)
- Python scripts check `if __name__ == "__main__":` for entry point
- TypeScript: Named exports for routers (e.g., `export { router as healthRouter }`)
- TypeScript services: Singleton pattern with exported instance (e.g., `export const etaSpotService = new ETASpotService()`)

**Barrel Files:**
- Not used in this codebase

---

*Convention analysis: 2026-02-11*
