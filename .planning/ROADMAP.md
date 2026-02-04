# Roadmap: Tiger Transit XGBoost ETA Model

## Overview

Build an XGBoost-based ETA prediction model for Auburn's Tiger Transit system, replacing the existing PyTorch neural network. The roadmap follows an incremental approach: establish reliable data pipelines first, train a baseline model on core features, layer on differentiator features (timepoints, rolling speeds, historical stats), optimize training with asymmetric loss and hyperparameter tuning, then validate thoroughly with sliced metrics and SHAP analysis. Every phase produces a verifiable artifact -- no phase ends without something you can run and check.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Data Foundation** - Parse all raw sources into clean, joined DataFrames ready for feature engineering
- [x] **Phase 2: Row Explosion & Labels** - Explode observations into per-stop rows, create ground truth labels, and split temporally
- [x] **Phase 3: Baseline Model** - Engineer core features and train first XGBoost model with conservative hyperparameters
- [ ] **Phase 4: Differentiator Features** - Add timepoint, rolling speed, historical, and Auburn-specific features
- [ ] **Phase 5: Advanced Training** - Implement asymmetric loss, hyperparameter tuning, and quantile predictions
- [ ] **Phase 6: Evaluation & Analysis** - Comprehensive sliced metrics, SHAP explainability, and bias detection

## Phase Details

### Phase 1: Data Foundation
**Goal**: All raw data sources are parsed, filtered, mapped, and joinable -- producing clean DataFrames that downstream feature engineering can consume without touching raw files
**Depends on**: Nothing (first phase)
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):
  1. Running the telemetry loader produces a filtered DataFrame excluding jAUnt, Shuttle, and inactive vehicles with no invalid GPS rows
  2. Running the arrivals parser produces a DataFrame with numeric GTFS stop IDs (not human-readable names) successfully joined to arrival records
  3. GTFS shape distances are computable between any two stops on a route (shape_dist_traveled lookup works)
  4. Timepoint Excel spreadsheet (all 23 sheets) is parsed into a mapping table of (route_id, stop_id, scheduled_departure_time) tuples
  5. Weather data joins by hour produce temperature and precipitation columns aligned to telemetry timestamps with no nulls in the join window
**Plans**: 3 plans

Plans:
- [x] 01-01-PLAN.md -- Parse telemetry JSONL and weather CSV into clean parquets
- [x] 01-02-PLAN.md -- Parse GTFS static files and arrivals CSVs with ID mappings
- [x] 01-03-PLAN.md -- Generate timepoint mapping (with user review) and parse timepoint Excel

### Phase 2: Row Explosion & Labels
**Goal**: Each telemetry observation is expanded into N rows (one per remaining stop), labeled with ground truth time_to_arrival_seconds, and split into train/val/test sets by calendar date
**Depends on**: Phase 1
**Requirements**: DATA-06, DATA-07, DATA-08
**Success Criteria** (what must be TRUE):
  1. Row explosion runs to completion without OOM using chunked-by-day Parquet processing (peak memory stays under available RAM)
  2. merge_asof label join achieves a success rate above 60% (rows with valid time_to_arrival_seconds / total rows), and label distribution shows no 3600s spikes (timezone bug indicator)
  3. Train/val/test splits are strictly temporal by calendar date with a gap period, and no trip_id appears in more than one split
  4. Final Parquet files exist on disk with correct schema and row counts logged
**Plans**: 2 plans

Plans:
- [x] 02-01-PLAN.md -- Build stop sequences and explode telemetry into per-stop rows
- [x] 02-02-PLAN.md -- Label join via merge_asof and temporal train/val/test split

### Phase 3: Baseline Model
**Goal**: A trained XGBoost model using only core features (distance, schedule, speed, temporal, weather) produces meaningful predictions that beat the naive schedule baseline
**Depends on**: Phase 2
**Requirements**: FEAT-01, FEAT-02, FEAT-03, FEAT-04, FEAT-05, FEAT-06, FEAT-07, FEAT-08, TRAIN-01
**Success Criteria** (what must be TRUE):
  1. All 8 core features (distance_to_target, scheduled_time_to_target, current_speed, route_progress, stops_remaining, stop_index, lateness_now, minutes_since_midnight, day_of_week, patternID, precipitation, temperature, passenger_load, is_idle/idle_duration) are computed and present in the training DMatrix
  2. XGBoost trains with reg:squarederror, early stopping on validation MAE, and converges (training loss decreases, validation loss stabilizes)
  3. Test set MAE is reported and is lower than the naive baseline (using scheduled_time_to_target as the prediction)
  4. SHAP summary plot shows distance_to_target and scheduled_time_to_target among the top 3 most important features (sanity check)
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md -- Engineer all 15 core features from Phase 2 splits into featured parquets
- [x] 03-02-PLAN.md -- Train XGBoost baseline, evaluate with sliced metrics, compute SHAP, save model

### Phase 4: Differentiator Features
**Goal**: Auburn-specific and advanced features (timepoint holds, rolling speeds, historical segment/dwell times, class schedules) are engineered and demonstrably improve model accuracy over baseline
**Depends on**: Phase 3
**Requirements**: FEAT-09, FEAT-10, FEAT-11, FEAT-12, FEAT-13, FEAT-14
**Success Criteria** (what must be TRUE):
  1. Rolling average speed features (30s, 60s, 120s, 180s) are computed per vehicle trajectory and present in the feature matrix
  2. Timepoint features (is_timepoint, timepoints_remaining, time_until_next_timepoint_departure) are computed using the Phase 1 timepoint mapping and present in the feature matrix
  3. Historical segment travel time and dwell time aggregates are computed from training data only (no leakage from val/test dates)
  4. Retraining with differentiator features produces a lower test MAE than the Phase 3 baseline model (improvement logged with exact numbers)
**Plans**: TBD

Plans:
- [ ] 04-01: TBD
- [ ] 04-02: TBD

### Phase 5: Advanced Training
**Goal**: The model uses asymmetric loss matching the existing PyTorch penalty structure, hyperparameters are tuned via Optuna, and quantile predictions provide confidence intervals
**Depends on**: Phase 4
**Requirements**: TRAIN-02, TRAIN-03, TRAIN-04
**Success Criteria** (what must be TRUE):
  1. Asymmetric loss (custom objective or quantile regression) is implemented and residual distribution shows the model penalizes overestimation more heavily than underestimation (median residual is slightly positive, indicating conservative predictions)
  2. Optuna study completes 100+ trials with GroupKFold or TimeSeriesSplit CV, and best trial MAE improves over the default-hyperparameter model from Phase 4
  3. Multi-quantile model produces P50 and P80 predictions, and P80 > P50 for all test samples (monotonicity check)
  4. Final tuned model test MAE is reported alongside all prior checkpoints (Phase 3 baseline, Phase 4 with features, Phase 5 tuned) showing progressive improvement
**Plans**: TBD

Plans:
- [ ] 05-01: TBD
- [ ] 05-02: TBD

### Phase 6: Evaluation & Analysis
**Goal**: The final model is comprehensively evaluated with sliced metrics, explainability analysis, and bias detection to confirm it is ready for production consideration
**Depends on**: Phase 5
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04
**Success Criteria** (what must be TRUE):
  1. Metrics report includes MAE, RMSE, and MAPE sliced by route, stops_remaining bucket (1, 2-3, 4-6, 7+), time-of-day (morning/midday/afternoon/evening), and distance bucket
  2. SHAP TreeExplainer produces global feature importance plot and at least 3 sample-level waterfall explanations showing sensible feature contributions
  3. Comparison table shows XGBoost model MAE vs. naive schedule baseline MAE, overall and per-route, with clear wins/losses identified
  4. Residual analysis identifies any systematic bias patterns (routes where model consistently over/under-predicts, time periods with degraded accuracy) and documents them
**Plans**: TBD

Plans:
- [ ] 06-01: TBD
- [ ] 06-02: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 > 2 > 3 > 4 > 5 > 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Data Foundation | 3/3 | ✓ Complete | 2026-02-03 |
| 2. Row Explosion & Labels | 2/2 | ✓ Complete | 2026-02-04 |
| 3. Baseline Model | 2/2 | ✓ Complete | 2026-02-04 |
| 4. Differentiator Features | 0/TBD | Not started | - |
| 5. Advanced Training | 0/TBD | Not started | - |
| 6. Evaluation & Analysis | 0/TBD | Not started | - |
