# Codebase Concerns

**Analysis Date:** 2026-03-25

---

## Tech Debt

**Hardcoded session cookie in data collector:**
- Issue: `ETA-Model/batchCollector.js` (line 11) contains a hardcoded `express.sid` session cookie directly in source code. This is a real authentication token that authenticates against `auburn.etaspot.com`.
- Files: `ETA-Model/batchCollector.js`
- Impact: Credential is exposed in version history and accessible to anyone with repo access. Cookie will expire and break collection silently.
- Fix approach: Move to environment variable (`process.env.ETASPOT_COOKIE`), remove from git history if ever pushed to a remote.

**Hardcoded S3 feed URLs in reference service:**
- Issue: `Code/etaspot_reference.ts` lines 90-91 hardcode the full S3 GTFS-RT URLs including bucket names. The `vehicles` Map in `ETASpotService` never evicts stale entries — only `getVehicles()` filters them, so memory grows unbounded if vehicles are removed from the feed without restarting.
- Files: `Code/etaspot_reference.ts`
- Impact: Map grows over a season as vehicles enter and leave service; minor memory leak for long-running processes.
- Fix approach: Periodically clear `this.vehicles` entries that are older than a reasonable threshold (e.g., 24 hours) in a scheduled cleanup.

**Duplicate data preparation codebases:**
- Issue: Two parallel, largely redundant data prep pipelines exist: `ETA-Model/src/data_prep.py` (1237 lines, PyTorch-focused) and `ETA-Model/src/data_prep_optimized.py` (1459 lines). The `scripts/` directory also has its own independent pipeline (`parse_telemetry.py`, `build_features.py`, etc.) for the XGBoost model. The PyTorch pipeline under `ETA-Model/src/` is described as an "existing system" that was never replaced or officially deprecated.
- Files: `ETA-Model/src/data_prep.py`, `ETA-Model/src/data_prep_optimized.py`, `scripts/parse_telemetry.py`
- Impact: Confusion about which pipeline produces training data for which model. `ETA-Model/src/data_prep.py` has a `# TODO: Extend to multiple stops` (line 669) left unresolved.
- Fix approach: Officially deprecate and remove `ETA-Model/src/data_prep.py` and the legacy PyTorch pipeline once the XGBoost model is deployed.

**`scripts/parse_telemetry.py` raw data path hardcoded to deleted directory:**
- Issue: The script hard-codes `RAW_DATA_DIR = PROJECT_ROOT / "mobile" / "src" / "ETA-Model" / "raw_data"` (line 16-17), but this entire `mobile/` directory has been deleted from the `rycode` branch (all files show `D` in git status). The script cannot run without editing this constant.
- Files: `scripts/parse_telemetry.py`
- Impact: Running the data pipeline from scratch on this branch will fail immediately.
- Fix approach: Update `RAW_DATA_DIR` to point to the actual `ETA-Model/raw_data/` directory at the project root.

**`scripts/build_baselines.py` uses relative paths requiring specific working directory:**
- Issue: `DATA_DIR = Path("data/processed")` (line 44) and `DIAG_DIR = Path("models/diagnostics")` (line 45) are relative paths. All scripts in `scripts/` use similar relative paths; they must be run from the project root. If run from within `scripts/`, they silently fail to find data.
- Files: `scripts/build_baselines.py`, `scripts/build_features.py`, `scripts/train_advanced.py`, `scripts/evaluate.py`
- Impact: Scripts fail with cryptic `FileNotFoundError` if CWD is wrong.
- Fix approach: Change all relative paths to `Path(__file__).resolve().parent.parent / "data/processed"` pattern (as `scripts/parse_telemetry.py` already does correctly).

**ETA-Model PyTorch API server has empty model registry:**
- Issue: `ETA-Model/config/routes.json` has an empty `"routes": []` array. The `ETA-Model/` directory has no `models/` directory. The FastAPI server at `ETA-Model/api/server.py` will start but respond to every `/api/eta/predict` call with a 404 because no models are loaded.
- Files: `ETA-Model/config/routes.json`, `ETA-Model/api/server.py`
- Impact: The PyTorch inference API is non-functional without trained model files.
- Fix approach: Either train per-route models and update `routes.json`, or document that this API is prototype-only and the XGBoost model is the production path.

**`lateness_now` feature has zero variance (known, accepted):**
- Issue: `STATE.md` documents that `lateness_now` was removed from `PHASE3_FEATURE_COLS` because `scheduled_eta == eta` in EtaSpot data, giving it zero variance. However, the v1.0 `build_features.py` still computes it as `FEAT-04` (line 147) and includes it in `FEATURE_COLS`.
- Files: `scripts/build_features.py`, `ETA-Model/data_prep/data_quality.py`
- Impact: 1 wasted feature column with no predictive value in the v1.0 pipeline.
- Fix approach: Remove `lateness_now` from `FEATURE_COLS` in `build_features.py` to match the v1.1 decision already documented in `STATE.md`.

---

## Known Bugs

**Feature count mismatch between `preprocess.py` (17 features) and API server:**
- Symptoms: `ETA-Model/src/preprocess.py` defines `NUM_FEATURES = 17` (len of `FEATURE_NAMES`), but `ETA-Model/api/server.py` calls `load_model(str(model_path), NUM_FEATURES)` importing this value. The actual trained models (if they exist) were trained on 44+ features (per `PROJECT.md` and `evaluate.py`). Loading a 44-feature model with `num_features=17` will either crash or silently produce wrong predictions.
- Files: `ETA-Model/src/preprocess.py`, `ETA-Model/api/server.py`
- Trigger: Starting the FastAPI server and sending a prediction request.
- Workaround: No model files exist, so this cannot be triggered at runtime currently.

**`ETA-Model/src/data_prep.py` builds training samples with only 1 label (not 3):**
- Symptoms: `_process_trajectory` in `ETA-Model/src/data_prep.py` has `# TODO: Extend to multiple stops` at line 669 and returns `labels = [actual_eta]` (single stop). The model architecture (`ETAPredictor`) expects 3-stop labels. Training with this file would produce shape errors at the loss function.
- Files: `ETA-Model/src/data_prep.py` lines 668-670
- Trigger: Running `python ETA-Model/src/train.py --generate-data`.
- Workaround: Use `ETA-Model/src/data_prep_optimized.py` which handles 3-stop labels.

**`build_baselines.py` Central Time offset is fixed at UTC-6, ignoring DST:**
- Symptoms: `add_ct_hour()` in `scripts/build_baselines.py` line 65 applies a fixed `-6 hour` offset for Central Time. Alabama observes CST (UTC-6) in winter and CDT (UTC-5) in summer. The training data spans November–December, which is CST, so this is correct for the training set. But re-running with spring/summer data will mislabel time-of-day buckets by 1 hour.
- Files: `scripts/build_baselines.py`
- Trigger: Re-running the pipeline with spring 2026 data collected after March DST transition.
- Workaround: Use `pd.Timestamp.tz_convert('America/Chicago')` instead of manual offset.

---

## Security Considerations

**Wildcard CORS on the prediction API:**
- Risk: `ETA-Model/api/server.py` lines 51-56 configures CORS with `allow_origins=["*"]`, `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`. Combining `allow_origins=["*"]` with `allow_credentials=True` is explicitly unsupported by the CORS standard (browsers block it) and misconfigured: credentials won't actually be forwarded, but the intent suggests the author expected them to be.
- Files: `ETA-Model/api/server.py`
- Current mitigation: Server is not deployed; only runs locally.
- Recommendations: For deployment, replace `allow_origins=["*"]` with explicit origin allowlist; set `allow_credentials=False` unless cookies/auth headers are actually needed.

**Supabase `anon` role granted `ALL` on `position_updates` tables:**
- Risk: Migration `20260319024944_create_schema.sql` grants `GRANT ALL ON TABLES TO anon` via `ALTER DEFAULT PRIVILEGES` in the `position_updates` schema. The `anon` role in Supabase is the unauthenticated public role. This gives unauthenticated users full read/write/delete access to all position update data.
- Files: `supabase/migrations/20260319024944_create_schema.sql`
- Current mitigation: Local development only; Row Level Security (RLS) not yet enabled.
- Recommendations: Before deploying to production: enable RLS on all tables, restrict `anon` to `SELECT` only (or nothing), require authenticated role for writes.

**No authentication on model reload endpoint:**
- Risk: `ETA-Model/api/server.py` `POST /api/models/reload` (line 255) has no authentication. Anyone who can reach the API can trigger a hot-reload of all models from disk. An attacker who can write model files to disk could load a malicious model.
- Files: `ETA-Model/api/server.py`
- Current mitigation: Server is not deployed.
- Recommendations: Add API key authentication or restrict endpoint to localhost before deployment.

**Session cookie in data collector committed to git:**
- Risk: `ETA-Model/batchCollector.js` line 11 contains an `express.sid` session cookie in plaintext. This was likely used for a personal account on `auburn.etaspot.com`. If this branch is ever pushed to a public remote, the credential is exposed.
- Files: `ETA-Model/batchCollector.js`
- Current mitigation: Branch `rycode` appears private; `.gitignore` does not exclude this file.
- Recommendations: Rotate the session cookie immediately, replace with `process.env.ETASPOT_COOKIE`, consider `git filter-branch` or `git-filter-repo` to scrub the credential from history.

---

## Performance Bottlenecks

**`compute_normalization_params` iterates row-by-row with `.iterrows()`:**
- Problem: `ETA-Model/src/preprocess.py` line 266 uses `for _, row in df.iterrows()` to compute distances for all training records. This is O(n) with high constant overhead — `iterrows()` is 10-100x slower than vectorized pandas operations.
- Files: `ETA-Model/src/preprocess.py`
- Cause: Scalar `haversine_distance` function is called once per row.
- Improvement path: Vectorize using the existing `haversine_meters` function from `scripts/build_differentiator_features.py` which accepts numpy arrays.

**`ETA-Model/src/data_prep.py` builds stop distance index with `iterrows()` on `stop_times.txt`:**
- Problem: `GTFSRouteData.__init__` (line 68) iterates `stop_times_df.iterrows()` to build the `stop_distances` dict. The GTFS `stop_times.txt` is large (tens of thousands of rows). This also builds a Python dict instead of an indexed DataFrame, making lookups O(1) but construction slow.
- Files: `ETA-Model/src/data_prep.py`
- Cause: Legacy implementation; `data_prep_optimized.py` exists to address this.
- Improvement path: Use `data_prep_optimized.py` exclusively; retire `data_prep.py`.

**`scripts/build_baselines.py` holds all split data in memory simultaneously:**
- Problem: The baselines script loads all three splits (train/val/test) and computes lookups in one session. The training parquet alone can be hundreds of MB. Combined peak memory may exceed 4GB on machines with limited RAM.
- Files: `scripts/build_baselines.py`
- Cause: Design choice for simplicity — lookups must be computed from train before applying to val/test.
- Improvement path: Stream processing is complex here; alternatively, document minimum RAM requirement (8GB+).

---

## Fragile Areas

**`scripts/train_advanced.py` deterministic round count depends on Optuna results file:**
- Files: `scripts/train_advanced.py`
- Why fragile: The final model is trained with a fixed `num_boost_round = best_iteration + 1` derived from Optuna. This value is stored in `models/v1_1_metrics.json`. If that file is deleted or Optuna is re-run, the deterministic round count is lost and retraining will not reproduce the exact model.
- Safe modification: Always re-run `--skip-tuning` variant after Optuna to regenerate the metrics file with round count.
- Test coverage: No tests; manually verified by developers.

**`ETA-Model/src/model.py` `load_model()` silently falls back to `ETAPredictor` for unknown `model_class`:**
- Files: `ETA-Model/src/model.py` lines 504-520
- Why fragile: If a checkpoint was saved with `ETAPredictorQuantile` (which exists in the same file), `load_model()` will silently instantiate the wrong architecture (`ETAPredictor`) rather than raising an error. The model will load without error but produce wrong output shapes.
- Safe modification: Add `ETAPredictorQuantile` to the `load_model` dispatch. Raise `ValueError` for truly unknown class names instead of silently defaulting.
- Test coverage: `if __name__ == '__main__'` block tests `ETAPredictor` save/load only.

**`ETA-Model/src/inference.py` smoothing state is unbounded:**
- Files: `ETA-Model/src/inference.py`
- Why fragile: `ETAInference._last_predictions` (line 53) stores state per `vehicle_id` string but never evicts entries. In a long-running deployment, every unique vehicle ID ever seen (including IDs from data quality issues or one-off test vehicles) accumulates in memory. `reset_vehicle_state()` must be called externally; there is no automatic eviction.
- Safe modification: Add an LRU cache or time-based eviction keyed on last-seen timestamp.
- Test coverage: None beyond the `if __name__ == '__main__'` smoke test.

**`supabase/migrations/` are incomplete — most GTFS tables missing:**
- Files: `supabase/migrations/`
- Why fragile: Only three migrations exist: the schema creation, the `position_updates` table, and `gtfs.calendar`. All other GTFS tables referenced in `PROJECT.md` (routes, stops, shapes, trips, stop_times, etc.) and the `trip_updates` schema have no migrations. The database cannot be reproduced from migrations alone.
- Safe modification: Only add new migrations; never edit existing ones.
- Test coverage: `supabase/seed.sql` is effectively empty (all INSERT statements are commented out).

**Feature column index 27 as magic number for route filtering:**
- Files: `ETA-Model/src/train.py` lines 361-363
- Why fragile: Route filtering uses `ROUTE_FEATURE_IDX = 27` with the comment "Route ID is stored in feature column 27, normalized as routeId/300". If the feature vector order in `data_prep_optimized.py` changes (features are added/removed at positions 0-26), this index silently filters on the wrong column with no error.
- Safe modification: Replace with a named lookup against `FEATURE_NAMES` array. Assert that `FEATURE_NAMES[27]` is `'route_id'` at startup.
- Test coverage: None.

---

## Scaling Limits

**XGBoost model trained on ~5 weeks of data from one semester:**
- Current capacity: 2.08M labeled rows from November 6 – December 12, 2025.
- Limit: Route 27 has only 96 test samples (documented in `STATE.md`). Sparse routes will show degraded accuracy as new routes or schedule changes occur.
- Scaling path: Re-run the full pipeline (`parse_telemetry.py` through `train_advanced.py`) on accumulated raw data from `ETA-Model/raw_data/`. Data collection scripts (`batchCollector.js`) are ready for this.

**`position_updates` table has no retention policy:**
- Current capacity: Local Supabase instance with no row limits configured.
- Limit: At 5-second poll intervals, a single active vehicle generates ~720 rows/hour. With ~20 simultaneous buses, this is ~14,400 rows/hour or ~345,000 rows/day. Without a retention policy, the table grows indefinitely.
- Scaling path: Add a Postgres `pg_cron` job or Supabase Edge Function to delete rows older than N days.

---

## Dependencies at Risk

**`ETA-Model/batchCollector.js` depends on undocumented EtaSpot IRM WebSocket API:**
- Risk: The data collection mechanism (`socket.io` events like `IRM_request_auburn.etaspot.com`, `IRM_rptPkt`) is a proprietary, undocumented internal API of the EtaSpot system. There is no SLA or versioning guarantee.
- Impact: If EtaSpot changes their WebSocket protocol or session authentication scheme, historical data collection breaks silently (collector connects but receives no packets).
- Migration plan: Archive the existing raw data in `ETA-Model/raw_data/`. The pipeline does not strictly need new data for the current model version.

**`ETA-Model/api/server.py` uses `@app.on_event("startup")` (deprecated in FastAPI):**
- Risk: `@app.on_event("startup")` was deprecated in FastAPI 0.93.0 in favor of `lifespan` context managers.
- Impact: Deprecation warning on startup; will be removed in a future FastAPI major version.
- Migration plan: Replace with `@asynccontextmanager` lifespan pattern.

---

## Missing Critical Features

**No Supabase ingestion pipeline for live GTFS-RT data:**
- Problem: The reference service in `Code/etaspot_reference.ts` parses live GTFS-RT feeds (position updates and trip updates) into `VehiclePosition` objects in memory. There is no code that writes these to Supabase. The `position_updates.position_updates` table schema exists but is never populated.
- Blocks: Any mobile app feature that reads real-time bus positions from the database.

**No connection between the XGBoost model and the mobile app or API:**
- Problem: The trained XGBoost model (`models/v1_1_residual.ubj`, excluded from git) has no serving layer. `PROJECT.md` explicitly marks deployment as "deferred to v2". The FastAPI server in `ETA-Model/api/server.py` serves only the PyTorch model (which has no trained weights).
- Blocks: End-to-end ETA prediction for riders.

**No Row Level Security on Supabase tables:**
- Problem: None of the three migrations enable RLS. The `position_updates` table grants `ALL` to `anon`. This is incompatible with a production deployment.
- Blocks: Deploying Supabase to production without creating a public data exposure risk.

---

## Test Coverage Gaps

**Zero automated tests anywhere in the codebase:**
- What's not tested: All Python scripts (data parsing, feature engineering, training, evaluation), the FastAPI prediction server, the GTFS-RT feed parser, database migrations.
- Files: Entire `scripts/`, `ETA-Model/src/`, `ETA-Model/api/`
- Risk: Silent regressions when modifying data pipeline scripts. Feature column reordering, filter changes, or schema changes can silently corrupt training data with no test to catch it.
- Priority: High — the `scripts/` pipeline has multiple fragile index-based assumptions that are high-risk without test coverage.

**Data pipeline has assertion-based validation but no regression test harness:**
- What's not tested: The assertions in `scripts/parse_telemetry.py` (lines 212-220) and `scripts/build_features.py` (line 188) verify correctness at runtime but are not run in any CI pipeline. Removing a filter or changing a threshold can silently pass.
- Files: `scripts/parse_telemetry.py`, `scripts/build_features.py`, `scripts/label_join.py`
- Risk: Data quality regressions go undetected until model accuracy degrades.
- Priority: Medium — assertions exist which is good, but they need a CI harness to run them automatically.

**`ETA-Model/src/model.py` `load_model` dispatch untested for non-standard architectures:**
- What's not tested: `ETAPredictorQuantile` is defined in `ETA-Model/src/model.py` but not in the save/load test block (lines 529-567). Loading a quantile model checkpoint would silently instantiate the wrong class.
- Files: `ETA-Model/src/model.py`
- Risk: Silent model class mismatch if quantile models are ever trained and loaded.
- Priority: Low — quantile model is not currently the active training target.

---

*Concerns audit: 2026-03-25*
