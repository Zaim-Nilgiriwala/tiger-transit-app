# Codebase Concerns

**Analysis Date:** 2026-02-11

## Tech Debt

**ETA Model: Limited Training Data**
- Issue: Only 5 weeks of telemetry data (Nov 8 - Dec 13, 2025) available for training
- Files: `scripts/temporal_split.py`, `data/processed/labeled.parquet`
- Impact: Weak generalization to seasonal patterns, special events, weather variations. Model cannot learn semester transitions, exam periods, or holiday traffic patterns.
- Fix approach: Collect 3+ months of continuous data across academic year. Retrain models quarterly to capture seasonal shifts. Currently mitigated with aggressive regularization (reg_alpha=0.97, reg_lambda=0.42).

**ETA Model: Quantile Model Monotonicity Violations**
- Issue: 32.3% of independently-trained quantile predictions violate P20 < P50 < P75 ordering constraint
- Files: `scripts/train_asymmetric_quantile.py` (lines 200-250), `models/quantile_metrics.json`
- Impact: Non-monotonic predictions undermine user trust in uncertainty intervals. Post-hoc sorting fixes ordering but distorts calibration.
- Fix approach: Replace independent quantile models with joint quantile regression (multi-output XGBoost with quantile loss). Alternatively, retrain on full dataset (currently using 25% subsample for speed).

**ETA Model: Route-Level Prediction Bias**
- Issue: 8 routes show systematic bias beyond 15s threshold. Overprediction on routes 5, 7, 24, 31, 33, 96. Underprediction on routes 1, 99.
- Files: `models/evaluation/eval_residuals.json`, `models/evaluation/eval_residuals_by_route.png`
- Impact: Route 24 (MAE=147.2s) consistently predicts ~30s late arrivals. Users may lose trust when predictions are reliably wrong for specific routes.
- Fix approach: Train route-specific calibration layers (post-processing bias correction per route). Alternative: Separate model per route group (high-bias vs low-bias).

**ETA Model: Time-of-Day Overprediction Bias**
- Issue: Midday period (11:00-14:00 CT) shows systematic overprediction bias (+24.93s mean residual)
- Files: `models/evaluation/eval_residuals.json`, `scripts/evaluate.py` (lines 102-110)
- Impact: Predictions during midday suggest later arrivals than reality. Buses arrive earlier than predicted, risking missed buses for waiting riders.
- Fix approach: Add temporal calibration factors per time-of-day bucket. Investigate midday-specific patterns (reduced traffic, faster speeds not captured by features).

**Data Pipeline: Distance Feature Resolution Limit**
- Issue: All distance_to_target values < 7 km due to short route segments. Original <1km, 1-3km, 3-5km, 5km+ buckets collapse into single "<1km" bucket with 100% of samples.
- Files: `scripts/build_differentiator_features.py` (lines 128-137), `scripts/evaluate.py` (lines 278-293)
- Impact: Distance bucketing for sliced metrics is meaningless. Had to switch to quantile-based bucketing (Q25/Q50/Q75) as workaround. Distance may have low discriminative power for ETA.
- Fix approach: Use percentile-based distance features instead of absolute distance. Consider ratio features (distance_to_target / total_route_distance) for normalization.

**Data Pipeline: High NaN Rate in Short-Window Rolling Features**
- Issue: speed_std_30s has 99.9% NaN rate due to 60s ping interval. Cannot compute 30s rolling window with only one ping per minute.
- Files: `scripts/build_differentiator_features.py` (lines 142-166), `.planning/STATE.md` (line 74)
- Impact: Short-window features provide no signal. Model relies on 60s, 120s, 180s windows only. Rapid acceleration/deceleration events are invisible.
- Fix approach: Remove 30s window (dead feature). If higher temporal resolution needed, advocate for 15-30s ping intervals in data collection contract.

**Data Pipeline: Timepoint Coverage Gaps**
- Issue: Routes 27 and 235 have no timepoint data. is_timepoint feature set to NaN for all observations on these routes.
- Files: `scripts/build_differentiator_features.py` (lines 400-450), `.planning/STATE.md` (line 78)
- Impact: Timepoint-related features (time_until_next_timepoint_departure is #2 SHAP feature) unavailable for 2 routes. Model may perform worse on these routes.
- Fix approach: Manual data collection from transit operations team for missing route schedules. Alternatively, exclude timepoint features from route 27/235 predictions.

**Feature Engineering: Zero Variance in lateness_now**
- Issue: scheduled_eta_seconds == eta_seconds in ETA SPOT telemetry data. lateness_now feature always zero.
- Files: `scripts/build_features.py` (line 150), `.planning/STATE.md` (lines 67, 72)
- Impact: Wasted feature column (confirmed zero SHAP importance). Indicates ETA SPOT scheduled field may not reflect real schedules, or schedule adherence not tracked.
- Fix approach: Remove lateness_now from feature set. Investigate scheduled_time_to_target validity as schedule proxy.

## Known Bugs

**Date Boundary Issue in temporal_split.py**
- Symptoms: temporal_split.py uses year 2025 for Nov/Dec dates (lines 27-34), but data is from 2024 according to git history
- Files: `scripts/temporal_split.py` (lines 27-34)
- Trigger: Running temporal split on newly collected 2026 data will fail due to hardcoded 2025 dates
- Workaround: Manually update TRAIN_START, VAL_START, TEST_START dates before each run
- Fix: Replace hardcoded dates with auto-detection from data min/max timestamps or command-line args

**Evaluation Script: All Distances Fall in Single Bucket**
- Symptoms: evaluate.py distance bucketing shows 100% of test samples in "<1km" bucket
- Files: `scripts/evaluate.py` (lines 278-293), `scripts/train_advanced.py` (lines 128-137)
- Trigger: Running sliced evaluation on per_distance metrics
- Workaround: Switched to quantile-based bucketing in evaluate.py (lines 281-313)
- Fix: Remove absolute distance buckets entirely. Use only quantile-based or ratio-based distance slicing.

## Security Considerations

**API Server: No Authentication**
- Risk: `api/server.py` prediction endpoint exposed without auth. Anyone with network access can query predictions.
- Files: `mobile/src/ETA-Model/api/server.py`
- Current mitigation: Server not deployed publicly (localhost only in development)
- Recommendations: Add API key authentication before production deployment. Use HTTPS with certificate pinning for mobile app.

**Optuna Database: SQLite File Permissions**
- Risk: `models/optuna_study.db` stores hyperparameter tuning trials. No encryption at rest.
- Files: `models/optuna_study.db`, `scripts/train_advanced.py` (line 156)
- Current mitigation: Database file in gitignored models/ directory
- Recommendations: Set restrictive file permissions (600) on SQLite database. Not a high-risk concern (no PII/credentials).

**Environment Variables: No .env File**
- Risk: No evidence of .env file for secrets management. API keys, database credentials may be hardcoded or missing.
- Files: N/A (missing .env file is the concern)
- Current mitigation: Project appears to use only local files, no external API keys detected
- Recommendations: Create .env.example template if any secrets added (weather API keys, database URLs, etc.).

## Performance Bottlenecks

**SHAP Computation: 100s per 1000 rows on 2158-iteration model**
- Problem: pred_contribs on tuned model (2158 iterations) takes ~100s per 1000 rows. Full test set (296K rows) would take 8+ hours.
- Files: `scripts/evaluate.py` (lines 341-403)
- Cause: Tree SHAP complexity is O(TLD^2) where T=trees, L=leaves, D=depth. Model has 2158 trees, max_depth=8.
- Improvement path: Subsample to 2000 rows for SHAP (current approach). Consider approximate SHAP methods (TreeExplainer with feature perturbation) or model distillation to fewer trees.

**Label Join: merge_asof on 2.34M rows**
- Problem: merge_asof with 2-hour tolerance on 2.34M telemetry rows takes ~90s
- Files: `scripts/label_join.py`, Phase 2 execution logs
- Cause: Temporal join requires sorting both DataFrames and scanning forward within tolerance window
- Improvement path: Pre-filter arrivals to ±3 hour window around telemetry date range. Index both DataFrames on timestamp before merge_asof. Consider Polars for faster temporal joins.

**Row Explosion: 2.34M output rows from 730K input**
- Problem: Exploding telemetry (avg 3.2 stops ahead per observation) produces 3.2x data expansion
- Files: `scripts/explode_rows.py`, `.planning/STATE.md` (line 62)
- Cause: Each observation generates one row per remaining stop on route
- Improvement path: Acceptable for current dataset size. If data grows 10x, consider chunked processing or sparse storage (only explode for training, not for inference).

## Fragile Areas

**Feature Engineering Pipeline: Implicit Dependency Chain**
- Files: `scripts/build_differentiator_features.py` (requires `data/processed/{train,val,test}.parquet`), `scripts/build_features.py` (Phase 3 baseline features)
- Why fragile: No dependency tracking. Running build_differentiator_features.py before label_join.py fails silently. Must run in specific order: parse → explode → label → split → features_v1 → features_v2 → train.
- Safe modification: Always check for required input files at script start. Add --force flag to allow reruns. Document execution order in README or Makefile.
- Test coverage: No unit tests for feature computation. Integration test would validate end-to-end pipeline.

**Categorical Dtype Handling in Parquet I/O**
- Files: `scripts/build_differentiator_features.py` (lines 58-62 CATEGORICAL_COLS_V2), `scripts/train_advanced.py` (load_featured_v2 function)
- Why fragile: Pandas 2.3.3 loses categorical dtype when saving/loading Parquet with PyArrow engine. Must manually restore dtype after read.
- Safe modification: Always use load_featured_v2() helper instead of raw pd.read_parquet(). If adding new categorical columns, update CATEGORICAL_COLS_V2 constant.
- Test coverage: None. Failure mode is silent (XGBoost interprets as string, creates many one-hot columns, OOMs).

**Optuna Study Resume Logic**
- Files: `scripts/train_advanced.py` (lines 156-293)
- Why fragile: SQLite storage for persistent study. If database file corrupted or deleted mid-run, study loses all trials. --batch mode assumes study exists for resume.
- Safe modification: Always check study.trials length before batch operations. Back up optuna_study.db before major reruns. Use --skip-tuning to bypass corrupted study.
- Test coverage: None. Manual validation only.

**Model File Format: UBJSON**
- Files: `models/tuned_v1.ubj`, `models/asymmetric_v1.ubj`, `models/quantile_p*.ubj`
- Why fragile: UBJSON format is binary, not human-readable. XGBoost version compatibility required for load. No schema validation.
- Safe modification: Always save model alongside metrics JSON (model_name_metrics.json). Store XGBoost version in metrics. Test load immediately after save.
- Test coverage: None. Failure mode is corrupted model file unusable for inference.

## Scaling Limits

**Current Data Size: 296K test samples, 43 features**
- Current capacity: Fits in memory (under 1GB). Training takes ~10 min for 2000 rounds.
- Limit: 10x data growth (3M rows) will exceed typical laptop RAM during DMatrix creation.
- Scaling path: Switch to XGBoost external memory mode (set max_bin, use DMatrix with cache). Use Dask-XGBoost for distributed training. Subsample training data (weighted by route priority).

**Optuna Trials: 150 trials, 41 complete, 109 pruned**
- Current capacity: 150 trials completes in ~90 minutes with 10% subsample
- Limit: Full-data tuning (100% of train) would take 15+ hours for 150 trials
- Scaling path: Increase subsample to 25% (4x slower but acceptable for final tuning). Use parallel Optuna with n_jobs=4 on multi-core machine. Reduce n_trials to 50 for faster iteration.

**SHAP Explainability: 2000-row subsample**
- Current capacity: 2000 rows for SHAP global importance completes in ~3 minutes
- Limit: Full test set (296K rows) would take 8+ hours
- Scaling path: Current subsample approach is sufficient. For per-prediction SHAP (inference time), use approximate TreeExplainer or precompute SHAP values for top-10 features only.

## Dependencies at Risk

**XGBoost 2.1.3: GPU Support Requirement**
- Risk: Project uses device="cuda" for GPU acceleration. If deployed on CPU-only server, training fails.
- Impact: train_advanced.py, train_asymmetric_quantile.py crash with "CUDA device not available"
- Migration plan: Add device detection (check torch.cuda.is_available() or xgboost GPU support). Fall back to device="cpu" with warning. Document GPU requirement in README.

**Optuna-Integration Package: Separate Install**
- Risk: optuna_integration.XGBoostPruningCallback used in train_advanced.py (line 219). Not in standard Optuna package.
- Impact: ImportError if optuna-integration not installed alongside optuna
- Migration plan: Add to requirements.txt explicitly. Graceful fallback to Optuna without pruning if import fails.

**Pandas 2.3.3: Categorical Dtype Limitations**
- Risk: Pandas loses categorical dtype on Parquet save/load (known issue in 2.x series)
- Impact: Silent failure (XGBoost creates many one-hot columns, potential OOM)
- Migration plan: Monitor Pandas 3.0 release for categorical dtype fixes. Use Polars as alternative (better categorical handling).

## Missing Critical Features

**No Real-Time Inference Pipeline**
- Problem: Trained models exist but no production inference endpoint consuming live telemetry
- Blocks: Cannot deploy model to mobile app or web dashboard
- Fix: Implement FastAPI endpoint in `api/server.py` that accepts telemetry ping and returns ETA predictions for all remaining stops. Add model versioning and A/B testing capability.

**No Model Monitoring/Drift Detection**
- Problem: Once deployed, no automated checks for prediction accuracy degradation over time
- Blocks: Cannot detect when model becomes stale due to route changes, construction, new traffic patterns
- Fix: Log predictions and actuals to timeseries database. Compute rolling 7-day MAE. Alert if MAE increases >20% from baseline. Retrigger automated retraining pipeline.

**No Confidence Intervals in Production**
- Problem: Quantile models trained (P20/P50/P75) but not integrated into inference API
- Blocks: Cannot show users "arrives between X and Y minutes" uncertainty ranges
- Fix: Update `api/server.py` to load quantile models alongside primary model. Return both point prediction (P50) and interval (P20, P75) in API response.

**No Explainability for User-Facing Predictions**
- Problem: SHAP analysis performed offline but not available per-prediction
- Blocks: Cannot explain to users why "Bus 5 is predicted late" (e.g., "heavy rain, rush hour traffic")
- Fix: Precompute SHAP values for top-5 features per route. Return feature contributions alongside predictions (e.g., "Rain: +30s, Traffic: +45s").

## Test Coverage Gaps

**No Unit Tests for Feature Engineering**
- What's not tested: Rolling speed computation, distance calculation, timepoint feature logic
- Files: `scripts/build_differentiator_features.py`, `scripts/build_features.py`
- Risk: Silent bugs in feature calculation propagate to model. Example: haversine_meters() returns NaN for invalid lat/lon, but no validation.
- Priority: High. Features are foundation of model quality.

**No Integration Tests for Pipeline**
- What's not tested: End-to-end run from raw data → trained model → predictions
- Files: All scripts in `scripts/`
- Risk: Breaking changes in intermediate outputs go undetected. Example: changing column names in explode_rows.py breaks label_join.py downstream.
- Priority: Medium. Manual smoke testing currently sufficient for research phase.

**No Validation Tests for Model Loading**
- What's not tested: XGBoost model load from .ubj file, DMatrix category dtype handling
- Files: `scripts/train_advanced.py`, `scripts/evaluate.py`
- Risk: Model corruption or version incompatibility causes silent failures at inference time
- Priority: Medium. Add test that loads each saved model, runs predict on sample data, validates output shape.

**No Tests for Data Quality Checks**
- What's not tested: verify_filters() in data_quality.py, missing value thresholds
- Files: `mobile/src/ETA-Model/data_prep/data_quality.py`
- Risk: Quality checks have bugs or are not enforced. Example: excluded vehicles (jAUnt) slip through filter.
- Priority: Low. Quality report generation confirms most checks, but no automated assertions.

---

*Concerns audit: 2026-02-11*
