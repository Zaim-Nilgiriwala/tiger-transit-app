# Testing Patterns

**Analysis Date:** 2026-02-11

## Test Framework

**Runner:**
- Backend: Jest (inferred from `backend/package.json` script `"test": "jest"`)
- Python ML pipeline: No test framework detected

**Assertion Library:**
- Backend: Jest built-in assertions (assumed)
- Python: Built-in `assert` statements used for data integrity checks, not formal unit tests

**Run Commands:**
```bash
npm test                   # Backend tests (not implemented yet)
npm run lint               # Backend linting
```

## Test File Organization

**Location:**
- No test files found in codebase (searched for `*.test.*`, `*.spec.*`, `test_*.py`)
- Jest configured in `backend/package.json` but no test suite exists
- Python ML scripts have no corresponding test files

**Naming:**
- Expected pattern: `{module}.test.ts` or `{module}.spec.ts` (TypeScript)
- Expected pattern: `test_{module}.py` (Python)

**Structure:**
```
Not applicable - no test files exist
```

## Test Structure

**Suite Organization:**
- No test suites exist in codebase

**Patterns:**
- Python ML scripts use inline assertions for data validation:
```python
assert len(df) == n_before, f"Row count changed! Before={n_before}, After={len(df)}"
assert max(train_df["date"]) < min(val_df["date"]), "Train/val date overlap!"
```
- These are runtime checks, not unit tests

**Coverage Analysis:**
- No test coverage for ETA prediction ML algorithm
- No test coverage for TypeScript backend
- No test coverage for data processing pipeline
- Production code relies on runtime assertions and manual verification

## Mocking

**Framework:**
- Not applicable (no tests exist)

**Patterns:**
- No mocking patterns detected

**What to Mock:**
- External APIs: GTFS-RT feeds (`POSITION_FEED_URL`, `TRIP_UPDATES_FEED_URL`)
- Database: Prisma client queries
- Redis: Cache operations
- File I/O: Parquet file reads/writes

**What NOT to Mock:**
- Core ML model logic (XGBoost predictions)
- Data transformations (haversine distance, GPS speed calculations)
- Feature engineering logic

## Fixtures and Factories

**Test Data:**
- No test fixtures exist
- ML pipeline uses actual production data from `data/processed/` directory
- Temporal data splits used for train/val/test (see `scripts/temporal_split.py`)

**Location:**
- Not applicable

## Coverage

**Requirements:**
- None enforced

**View Coverage:**
```bash
# No coverage tooling configured
```

## Test Types

**Unit Tests:**
- Not implemented

**Integration Tests:**
- Not implemented

**E2E Tests:**
- Not implemented

## Common Patterns

**Async Testing:**
- Not applicable (no tests exist)
- Expected pattern for TypeScript:
```typescript
test('should fetch vehicle positions', async () => {
  const vehicles = await etaSpotService.getVehicles();
  expect(vehicles).toBeDefined();
});
```

**Error Testing:**
- Not applicable (no tests exist)
- Expected pattern:
```typescript
test('should handle fetch errors', async () => {
  await expect(fetchFeed('invalid-url')).rejects.toThrow();
});
```

## ML Pipeline Validation

**Current Approach:**
- Comprehensive evaluation pipeline in `scripts/evaluate.py` produces 4 deliverables:
  - EVAL-01: Sliced metrics (overall, per-route, per-stops, per-TOD, per-distance)
  - EVAL-02: SHAP explainability (global bar + 3 waterfall plots)
  - EVAL-03: Comparison table vs naive baseline
  - EVAL-04: Residual bias detection
- Runtime assertions validate data integrity throughout pipeline
- Manual inspection of metrics JSON files (e.g., `models/tuned_metrics.json`)
- Progressive improvement validation: Each phase must beat previous (e.g., Tuned MAE < Differentiator MAE)

**Validation Examples:**
```python
# From scripts/train_advanced.py
if xgb_mae < diff_mae:
    print(f"PASS: Tuned MAE ({xgb_mae:.1f}s) < Differentiator MAE ({diff_mae:.1f}s)")
else:
    print(f"WARN: Tuned MAE ({xgb_mae:.1f}s) >= Differentiator MAE ({diff_mae:.1f}s)")

# From scripts/temporal_split.py
assert len(train_df) + len(val_df) + len(test_df) + gap_count == total_rows
assert max(train_df["date"]) < min(val_df["date"]), "Train/val date overlap!"
```

**Data Integrity Checks:**
- Row count preservation through transformations (e.g., `assert len(df) == n_before`)
- Date range validation (no temporal leakage between splits)
- Feature NaN rate reporting after each processing stage
- Historical aggregate sparsity checks (minimum observation thresholds)

## Recommendations for Testing

**High Priority:**
1. Unit tests for feature engineering functions (`compute_gps_speed()`, `haversine_meters()`, `compute_rolling_speed_features()`)
2. Integration tests for ML pipeline stages (feature assembly → training → evaluation)
3. Backend route tests (health check, vehicle endpoints, WebSocket handlers)
4. Mock GTFS-RT feed responses for `etaspot.service.ts`

**Medium Priority:**
5. Data validation tests (schema checks for parquet files)
6. Model serialization/deserialization tests (XGBoost model save/load)
7. Historical aggregate computation tests (edge cases: sparse data, missing routes)

**Low Priority:**
8. E2E tests for full API flows
9. Performance regression tests for ML training pipeline
10. Load tests for WebSocket broadcasts

---

*Testing analysis: 2026-02-11*
