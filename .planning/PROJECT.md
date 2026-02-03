# Tiger Transit XGBoost ETA Model

## What This Is

A new XGBoost-based ETA prediction model for Auburn University's Tiger Transit bus system, replacing the existing PyTorch neural network. The model predicts time-to-arrival (in seconds) from a vehicle's current position to every remaining stop on its route. Built on existing telemetry data (Nov 6 - Dec 12), GTFS schedule data, weather data, and timepoint schedules.

## Core Value

Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions like weather and class schedules.

## Requirements

### Validated

- ✓ Raw telemetry data collection from ETA Spot IRM API — existing (batchCollector.js)
- ✓ Arrivals ground truth data — existing (CSV from ETA Spot)
- ✓ GTFS route/stop/shape data — existing (gtfs_data/)
- ✓ Weather data — existing (weather_data.csv)
- ✓ Timepoint schedule data — existing (Spring 2026 Timepoint Update.xlsx)
- ✓ Data filtering (exclude jAUnt, Shuttle, inactive vehicles) — existing pipeline

### Active

- [ ] Parse and map timepoint spreadsheet to stop IDs and route IDs
- [ ] Build new data preparation pipeline producing per-stop rows (one row per vehicle_observation x target_stop pair)
- [ ] Engineer all specified features: vehicle state, route context, temporal, weather, schedule, rolling speed windows, lateness, historic averages
- [ ] Engineer timepoint-aware features: is_timepoint, scheduled_departure_at_timepoint, forced_dwell_time
- [ ] Engineer additional features beyond the specified list where they improve accuracy
- [ ] Train single XGBoost model that predicts time-to-target-stop
- [ ] Proper train/val/test evaluation with relevant metrics (MAE, RMSE, percentile errors)
- [ ] Feature importance analysis to understand what drives predictions

### Out of Scope

- Deployment/integration into the backend or mobile app — focus on model quality first
- Real-time prediction API — deferred until model is validated
- Per-route models — single model approach first (route encoded as feature)
- Replacing the existing PyTorch model in production — this is a parallel effort
- Collecting new raw data — using existing Nov 6 - Dec 12 dataset

## Context

### Existing System
- PyTorch neural network with 44 features, predicting next 3 stops
- Per-route models with vehicle embeddings and asymmetric loss (5x penalty for overestimation)
- Data pipeline: JSONL telemetry → data_prep scripts → .npy arrays → PyTorch training
- FastAPI prediction endpoint (api/server.py)

### New Model Design
- **Architecture:** Single XGBoost regressor, one model for all routes
- **Row structure:** Each training example = (vehicle_observation, target_stop) pair. A single vehicle observation at position P on a route with N remaining stops produces N rows.
- **Target variable:** time_to_arrival_seconds (actual arrival time at target stop minus observation timestamp)
- **Labels source:** Arrivals CSV data joined with telemetry on vehicle ID and timestamp proximity

### Timepoint System
- 23 routes with 1-4 buses each have mandatory hold points
- Buses cannot depart timepoint stops before scheduled time
- Timepoint data in "Spring 2026 Timepoint Update.xlsx" — needs mapping from human-readable stop names to numeric stop IDs
- Timepoints create a "floor" on ETAs for downstream stops when bus is ahead of schedule

### Feature List (specified + to be expanded)
**Vehicle state:** speed, heading, load, lat, lon, progress, isIdle, offroute, idle time
**Rolling averages:** average speed over 30s, 60s, 120s, 180s windows
**Route context:** patternID, tripID, trainID, dir, totalDistance, segment_id, stop_index, nextStopPercentProgress, lastStopStopID, lastStop.time, lastStop.sdTime, distance_to_target
**Schedule context:** eta.stopID, schedule.stops, scheduled_time_to_target, lateness_now, timepoint features
**Temporal:** time of day, day of week (is_monday...is_sunday), is_rush_hour, class_let_out_recently (approximate: classes end at :50/:00)
**Weather:** from weather_data.csv
**Historical averages:** segment travel times (mean/std by hour), boarding rates, dwell times, vehicle speed averages, and any other discoverable patterns
**Target stop context:** stops remaining, distance to target stop, number of timepoints between current position and target

### Data Sources
| Source | Location | Format |
|--------|----------|--------|
| Raw telemetry | raw_data/*.jsonl(.gz) | JSONL, Nov 6 - Dec 12 |
| Arrivals ground truth | raw_data/*.csv | CSV |
| Weather | weather_data.csv | CSV |
| GTFS | gtfs_data/ | Standard GTFS CSVs |
| Timepoints | raw_data/Spring 2026 Timepoint Update.xlsx | Excel, 23 sheets |

## Constraints

- **Data:** Use existing raw data only (Nov 6 - Dec 12, ~5 weeks)
- **Tech stack:** Python, XGBoost, pandas/numpy for data prep, scikit-learn for evaluation
- **Model type:** XGBoost (gradient boosted trees), not neural network
- **Single model:** One model for all routes (route as a feature), not per-route models
- **Timepoint mapping:** Must resolve human-readable stop names from spreadsheet to numeric stop IDs in GTFS/ETA Spot system

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| XGBoost over PyTorch | Gradient boosted trees handle tabular data well, easier to interpret, faster training iteration | -- Pending |
| Single model, per-stop rows | Variable number of remaining stops per observation; one model learns time-to-any-stop | -- Pending |
| All remaining stops (not just next 3) | More useful predictions for riders planning ahead | -- Pending |
| Approximate class schedule | Classes assumed to end at :50/:00 during typical hours; no actual Auburn schedule data needed | -- Pending |
| Use existing data only | 5 weeks sufficient to build and validate; pipeline can ingest more later | -- Pending |
| Deployment deferred | Focus on model accuracy first, integration second | -- Pending |

---
*Last updated: 2026-02-03 after initialization*
