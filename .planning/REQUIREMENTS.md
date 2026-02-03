# Requirements: Tiger Transit XGBoost ETA Model

**Defined:** 2026-02-03
**Core Value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.

## v1 Requirements

### Data Pipeline

- [ ] **DATA-01**: Parse raw JSONL telemetry files into clean filtered DataFrames (exclude jAUnt, Shuttle, inactive vehicles)
- [ ] **DATA-02**: Parse arrivals CSV with stop name-to-GTFS stop ID mapping for ground truth labels
- [ ] **DATA-03**: Integrate GTFS data for route distances (shape_dist_traveled), stop sequences, and schedule lookup
- [ ] **DATA-04**: Parse timepoint Excel spreadsheet (23 routes) and map human-readable stop names to numeric stop IDs and route IDs
- [ ] **DATA-05**: Join weather data (temperature, precipitation) by hour from weather_data.csv
- [ ] **DATA-06**: Per-stop row explosion with chunked-by-day Parquet processing (each observation x remaining stops = N rows)
- [ ] **DATA-07**: Vectorized label creation via merge_asof joining telemetry with arrivals for time_to_arrival_seconds ground truth
- [ ] **DATA-08**: Temporal train/val/test split by calendar date with gap period (no random splitting)

### Core Features (Baseline Model)

- [ ] **FEAT-01**: distance_to_target — route distance along GTFS shape from current position to target stop (meters)
- [ ] **FEAT-02**: scheduled_time_to_target — seconds from now until scheduled arrival at target stop (from GTFS stop_times)
- [ ] **FEAT-03**: current_speed, route_progress (nextStopPercentProgress), stops_remaining, stop_index
- [ ] **FEAT-04**: lateness_now — current schedule deviation in seconds (lastStop.time - lastStop.sdTime)
- [ ] **FEAT-05**: minutes_since_midnight (raw, not cyclical), day_of_week (XGBoost native categorical)
- [ ] **FEAT-06**: patternID as XGBoost native categorical
- [ ] **FEAT-07**: precipitation (mm/hr), temperature (Celsius) from weather data
- [ ] **FEAT-08**: passenger_load, is_idle / idle_duration

### Differentiator Features (Post-Baseline)

- [ ] **FEAT-09**: Rolling average speed over 30s, 60s, 120s, 180s windows
- [ ] **FEAT-10**: Timepoint features — is_timepoint (boolean), timepoints_remaining (count), time_until_next_timepoint_departure (seconds)
- [ ] **FEAT-11**: Historical segment travel time mean/std aggregated by (segment, hour, day_type) from training data only
- [ ] **FEAT-12**: Historical dwell time mean aggregated by (stop_id, hour, day_type) from training data only
- [ ] **FEAT-13**: is_rush_hour (boolean), class_let_out_recently (boolean, approximate: classes end at :50/:00)
- [ ] **FEAT-14**: Additional engineered features beyond specified list where they demonstrably improve accuracy

### Model Training

- [ ] **TRAIN-01**: Baseline XGBoost model with reg:squarederror, conservative regularization (max_depth=3-4, min_child_weight=10-50), early stopping on validation MAE
- [ ] **TRAIN-02**: Asymmetric loss implementation — custom XGBoost objective or quantile regression to replicate 5x overestimation penalty from existing PyTorch model
- [ ] **TRAIN-03**: Optuna hyperparameter tuning (100-200 trials) with TimeSeriesSplit/GroupKFold cross-validation
- [ ] **TRAIN-04**: Multi-quantile predictions (P50, P80) via reg:quantileerror for confidence intervals

### Evaluation

- [ ] **EVAL-01**: Metrics (MAE, RMSE, MAPE) overall and sliced by route, stops_remaining bucket, time-of-day, distance bucket
- [ ] **EVAL-02**: SHAP feature importance analysis — global TreeExplainer and sample-level explanations
- [ ] **EVAL-03**: Comparison report vs schedule-based baseline (scheduled_time_to_target as naive predictor)
- [ ] **EVAL-04**: Residual analysis for systematic bias detection (over/under-prediction patterns by route, time, stop type)

## v2 Requirements

### Deployment

- **DEPLOY-01**: Production prediction API (FastAPI or Node.js backend integration)
- **DEPLOY-02**: Feature computation module matching training pipeline (< 500ms latency)
- **DEPLOY-03**: Model artifact packaging (UBJSON format, feature_columns.json, model_config.json)

### Advanced Features

- **FEAT-15**: Fleet-level lag features (how other buses on same route are currently performing)
- **FEAT-16**: Event features (game days, special events — insufficient data in current 5-week window)
- **FEAT-17**: Per-route models (if single global model underperforms on specific routes)
- **FEAT-18**: Speed trend derivative (180s avg - 30s avg for acceleration/deceleration pattern)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deploying model to production | Focus on model quality first; deployment deferred to v2 |
| Collecting new raw data | Using existing Nov 6 - Dec 12 dataset (~5 weeks) |
| Real-time inference pipeline | Deferred until model accuracy validated |
| Mobile app integration | Model-only scope for this milestone |
| Replacing existing PyTorch model | Parallel effort, not a replacement |
| Neural network approaches | XGBoost only per project decision |
| Feature normalization/z-scoring | Unnecessary for tree-based models |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DATA-01 | Phase 1 | Pending |
| DATA-02 | Phase 1 | Pending |
| DATA-03 | Phase 1 | Pending |
| DATA-04 | Phase 1 | Pending |
| DATA-05 | Phase 1 | Pending |
| DATA-06 | Phase 2 | Pending |
| DATA-07 | Phase 2 | Pending |
| DATA-08 | Phase 2 | Pending |
| FEAT-01 | Phase 3 | Pending |
| FEAT-02 | Phase 3 | Pending |
| FEAT-03 | Phase 3 | Pending |
| FEAT-04 | Phase 3 | Pending |
| FEAT-05 | Phase 3 | Pending |
| FEAT-06 | Phase 3 | Pending |
| FEAT-07 | Phase 3 | Pending |
| FEAT-08 | Phase 3 | Pending |
| FEAT-09 | Phase 4 | Pending |
| FEAT-10 | Phase 4 | Pending |
| FEAT-11 | Phase 4 | Pending |
| FEAT-12 | Phase 4 | Pending |
| FEAT-13 | Phase 4 | Pending |
| FEAT-14 | Phase 4 | Pending |
| TRAIN-01 | Phase 3 | Pending |
| TRAIN-02 | Phase 5 | Pending |
| TRAIN-03 | Phase 5 | Pending |
| TRAIN-04 | Phase 5 | Pending |
| EVAL-01 | Phase 6 | Pending |
| EVAL-02 | Phase 6 | Pending |
| EVAL-03 | Phase 6 | Pending |
| EVAL-04 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 30 total
- Mapped to phases: 30
- Unmapped: 0

---
*Requirements defined: 2026-02-03*
*Last updated: 2026-02-03 after roadmap creation*
