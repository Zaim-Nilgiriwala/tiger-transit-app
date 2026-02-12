# Tiger Transit XGBoost ETA Model

## What This Is

An XGBoost-based ETA prediction model for Auburn University's Tiger Transit bus system. The model predicts time-to-arrival (in seconds) from a vehicle's current position to every remaining stop on its route, achieving 123.1s MAE across all 23 routes (82.6% improvement over naive schedule). Built on 5 weeks of telemetry data with 43 engineered features including timepoint holds, rolling speed windows, and historical segment statistics.

## Core Value

Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions like weather and class schedules.

## Requirements

### Validated

- ✓ Raw telemetry data collection from ETA Spot IRM API -- existing (batchCollector.js)
- ✓ Arrivals ground truth data -- existing (CSV from ETA Spot)
- ✓ GTFS route/stop/shape data -- existing (gtfs_data/)
- ✓ Weather data -- existing (weather_data.csv)
- ✓ Timepoint schedule data -- existing (Spring 2026 Timepoint Update.xlsx)
- ✓ Data filtering (exclude jAUnt, Shuttle, inactive vehicles) -- existing pipeline
- ✓ Parse and map timepoint spreadsheet to stop IDs and route IDs -- v1.0
- ✓ Data pipeline producing per-stop rows (one row per observation x target_stop pair) -- v1.0
- ✓ 43-feature engineering (vehicle state, route context, temporal, weather, schedule, rolling speed, timepoints, historical stats) -- v1.0
- ✓ Single XGBoost model predicting time-to-target-stop (123.1s MAE) -- v1.0
- ✓ Asymmetric loss with 3:1 overestimation penalty -- v1.0
- ✓ Quantile confidence intervals (P20/P50/P75) -- v1.0
- ✓ Optuna hyperparameter tuning (50 trials, temporal CV) -- v1.0
- ✓ Comprehensive evaluation with sliced metrics, SHAP, residual bias detection -- v1.0

### Active

- [ ] Build blended baseline ETA calculator (average of segment-median sum and stop-to-stop historical average)
- [ ] Compute residual labels (actual_arrival - baseline_ETA) for training data
- [ ] Modify v1.0 training pipeline to predict residual instead of raw seconds
- [ ] Fresh Optuna hyperparameter tuning for residual target distribution
- [ ] Symmetric squared error loss (no asymmetric initially)
- [ ] Evaluation comparing v1.1 residual model vs v1.0 raw model (must beat 123.1s MAE)

### Out of Scope

- Deployment/integration into the backend or mobile app -- deferred to v2
- Real-time prediction API -- deferred until model is validated
- Per-route models -- single model approach sufficient (route encoded as feature)
- Replacing the existing PyTorch model in production -- parallel effort
- Collecting new raw data -- using existing Nov 6 - Dec 12 dataset
- Neural network approaches -- XGBoost only per project decision
- Feature normalization/z-scoring -- unnecessary for tree-based models

## Current Milestone: v1.1 Model Reapproach

**Goal:** Rearchitect the XGBoost model to predict residuals (actual - baseline_ETA) instead of raw seconds, where the baseline is a blended average of segment-median sums and stop-to-stop historical averages.

**Key changes from v1.0:**
- Target variable: residual (centered ~0) instead of raw time_to_arrival_seconds (0-2000+s)
- Baseline ETA: average of (sum of segment medians) and (direct stop-to-stop historical average)
- Same 43 features retained
- Modify v1.0 scripts in place (no forking)
- Symmetric loss first, fresh Optuna tuning
- Success: beat v1.0's 123.1s MAE

**At inference:** `predicted_arrival = baseline_ETA + predicted_residual`

## Context

### Current State (v1.0 shipped)
- XGBoost model: 123.1s MAE, 82.6% improvement over naive schedule
- 43 features across 6 categories, trained on 2.08M labeled rows
- Progressive improvement: Naive (708.9s) -> Baseline (394.7s) -> Differentiator (175.7s) -> Tuned (123.1s)
- 23/23 route wins vs naive; 6 routes show overprediction bias, 2 underprediction
- Top SHAP features: time_until_next_timepoint_departure, stop_index, pattern_id
- ~22,550 lines of Python across 13 scripts

### Existing System
- PyTorch neural network with 44 features, predicting next 3 stops
- Per-route models with vehicle embeddings and asymmetric loss (5x penalty for overestimation)
- Data pipeline: JSONL telemetry -> data_prep scripts -> .npy arrays -> PyTorch training
- FastAPI prediction endpoint (api/server.py)

### Data Sources
| Source | Location | Format |
|--------|----------|--------|
| Raw telemetry | raw_data/*.jsonl(.gz) | JSONL, Nov 6 - Dec 12 |
| Arrivals ground truth | raw_data/*.csv | CSV |
| Weather | weather_data.csv | CSV |
| GTFS | gtfs_data/ | Standard GTFS CSVs |
| Timepoints | raw_data/Spring 2026 Timepoint Update.xlsx | Excel, 23 sheets |

### Known Issues
- Quantile monotonicity violations (32.3%) -- trained on 25% subsample
- Route 27: only 96 test samples, 336.9s MAE (insufficient data)
- lateness_now has zero variance (EtaSpot scheduled_eta == eta)
- Midday overprediction bias (+24.93s mean residual)
- 6 routes overpredicting (5, 7, 24, 31, 33, 96), 2 underpredicting (1, 99)

## Constraints

- **Data:** Use existing raw data only (Nov 6 - Dec 12, ~5 weeks)
- **Tech stack:** Python, XGBoost, pandas/numpy for data prep, scikit-learn for evaluation
- **Model type:** XGBoost (gradient boosted trees), not neural network
- **Single model:** One model for all routes (route as a feature), not per-route models

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| XGBoost over PyTorch | Gradient boosted trees handle tabular data well, easier to interpret, faster training iteration | ✓ Good -- 123.1s MAE, trains in seconds |
| Single model, per-stop rows | Variable number of remaining stops per observation; one model learns time-to-any-stop | ✓ Good -- 23/23 routes beat naive |
| All remaining stops (not just next 3) | More useful predictions for riders planning ahead | ✓ Good -- works across all stop distances |
| Approximate class schedule | Classes assumed to end at :50/:00 during typical hours | ✓ Good -- class_let_out_recently contributes to predictions |
| Use existing data only | 5 weeks sufficient to build and validate; pipeline can ingest more later | ✓ Good -- sufficient for model development |
| Deployment deferred | Focus on model accuracy first, integration second | ✓ Good -- model quality validated before deployment work |
| pred_contribs over TreeExplainer | 2158-iteration model too slow for TreeExplainer | ✓ Good -- equivalent exact SHAP values, 5 min vs hours |
| 3:1 asymmetric loss (not 5:1) | 5:1 too aggressive; 3:1 with proximity scaling protects riders near buses | ✓ Good -- median residual -16.5s (conservative) |
| Optuna 50 trials on 10% subsample | Fast search with full-data verification | ✓ Good -- found optimal params efficiently |
| Quantile-based distance bucketing | All distances < 7 km; meter thresholds put 100% in one bucket | ✓ Good -- meaningful 4-bucket analysis |
| Residual target over raw seconds (v1.1) | Model learns deviation from historical baseline, tighter target distribution, focuses on explaining anomalies | -- Pending |
| Modify in place over forking (v1.1) | Simpler codebase, v1.0 preserved in git history | -- Pending |
| Symmetric loss first (v1.1) | Residual targets centered around 0; asymmetric penalty semantics change with residuals | -- Pending |

---
*Last updated: 2026-02-11 after v1.1 milestone start*
