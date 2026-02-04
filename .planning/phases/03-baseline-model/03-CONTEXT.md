# Phase 3: Baseline Model - Context

**Gathered:** 2026-02-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Engineer core features from the exploded/labeled data (distance, schedule, speed, temporal, weather, passenger load, idle detection) and train a first XGBoost model with conservative hyperparameters that beats the naive schedule baseline. Feature list is defined in the roadmap requirements (FEAT-01 through FEAT-08, TRAIN-01). Differentiator features (timepoints, rolling speeds, historical stats) belong to Phase 4.

</domain>

<decisions>
## Implementation Decisions

### Feature Computation
- **current_speed**: Use the GPS-reported speed field directly from telemetry data (do not compute from consecutive positions)
- **is_idle / idle_duration**: Claude's discretion on thresholds -- analyze speed distribution in the data and pick sensible cutoffs
- **passenger_load**: Use raw integer passenger count as-is (no normalization by capacity)
- **lateness_now**: Compute as elapsed difference (actual_elapsed_since_trip_start - scheduled_elapsed_since_trip_start), not timepoint-relative

### Training Configuration
- **Priority**: Avoid overfitting -- shallow trees (max_depth ~4-6), high regularization, low learning rate. Conservative given only 5 weeks of data
- **Early stopping**: 100 rounds patience on validation MAE
- **Device**: Claude's discretion based on environment availability (CPU or GPU)
- **Categorical features**: Use XGBoost native categorical support (enable_categorical=True) for route_id and patternID

### Evaluation & Reporting
- **Primary metrics**: MAE (seconds) + RMSE (seconds)
- **Asymmetric preference**: Underprediction preferred over overprediction -- better for a rider to arrive early than miss the bus. (Formal asymmetric loss is Phase 5, but interpret baseline results with this lens)
- **Metric slices**: Report overall + per-route + by stops_remaining buckets
- **Success target**: Under 60 seconds MAE on test set
- **SHAP output**: Both saved SHAP summary plot (PNG) AND logged feature importance rankings
- **Baseline comparison**: Compare XGBoost predictions vs naive schedule baseline (scheduled_time_to_target as prediction)

### Claude's Discretion
- Idle detection thresholds (speed and duration cutoffs)
- CPU vs GPU training device selection
- Exact learning rate, max_depth, and regularization values (within "conservative" constraint)
- Loading skeleton / intermediate logging verbosity
- Exact SHAP sample size for summary plot

</decisions>

<specifics>
## Specific Ideas

- Asymmetric error preference: "someone arriving to a stop earlier is better than someone missing a bus" -- this should inform how we interpret results even before Phase 5 implements formal asymmetric loss
- Full metric breakdown (overall + route + stops_remaining) even at baseline stage to establish a rich comparison baseline for later phases

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 03-baseline-model*
*Context gathered: 2026-02-03*
