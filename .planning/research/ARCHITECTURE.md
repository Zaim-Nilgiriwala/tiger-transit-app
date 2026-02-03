# Architecture Research: XGBoost Transit ETA Prediction Pipeline

**Domain:** ML training pipeline for transit bus ETA prediction
**Researched:** 2026-02-03
**Confidence:** HIGH

## System Overview

```
RAW DATA SOURCES                      DATA PREPARATION                         TRAINING & EVALUATION
=====================                 ======================                   =====================

live_data/*.jsonl (telemetry)  --->  [1. Loader]                              [7. Trainer]
raw_data/Arrivals*.csv         --->  [2. Filter]                                  |
raw_data/weather_data.csv      --->  [3. Feature Engineering]                 [8. Evaluator]
gtfs_data/ (shapes/stops/trips)--->      |                                        |
timepoints.xlsx                --->  [4. Row Exploder]                        [9. Artifact Exporter]
                                         |                                        |
                                     [5. Label Creator]                       Output:
                                         |                                      - model.json
                                     [6. Splitter]                              - metrics.json
                                         |                                      - feature_importance.json
                                     Output:                                    - evaluation_report.md
                                       - train.parquet
                                       - val.parquet
                                       - test.parquet
                                       - metadata.json
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| Loader | Parse JSONL telemetry, CSV arrivals, GTFS files, weather CSV, timepoints Excel into DataFrames | `loaders.py` -- one function per source format |
| Filter | Exclude jAUnt/Shuttle vehicles, inactive trips, invalid GPS, depot patterns | `filters.py` -- pure predicate functions |
| Feature Engineering | Compute rolling windows, distance features, temporal features, weather join, historical stats | `features/` subpackage with one module per feature group |
| Row Exploder | Expand each telemetry observation into N rows (one per remaining target stop on the trip) | `row_exploder.py` -- the critical memory-intensive step |
| Label Creator | Join exploded rows with arrivals CSV to get ground-truth `time_to_arrival_sec` | `labels.py` -- vectorized merge, not row-by-row iteration |
| Splitter | Temporal train/val/test split respecting time ordering | `split.py` -- date-based cutoffs |
| Trainer | XGBoost DMatrix creation, hyperparameter config, training with early stopping | `train.py` -- thin wrapper around xgb.train() |
| Evaluator | MAE/RMSE/MAPE by route, by stop count bucket, by time-of-day, residual analysis | `evaluate.py` -- metrics + visualization |
| Artifact Exporter | Save model JSON, normalization stats, feature lists, metadata for serving | `artifacts.py` -- everything needed to reproduce or serve |

## Recommended Project Structure

```
eta_pipeline/
|-- __init__.py
|-- config.py                    # All constants, paths, feature lists, thresholds
|-- cli.py                       # CLI entry point (argparse or click)
|
|-- data/
|   |-- __init__.py
|   |-- loaders.py               # Load JSONL, CSV arrivals, GTFS, weather, timepoints
|   |-- filters.py               # Vehicle/trip filtering predicates
|   |-- row_exploder.py          # Per-stop row expansion (the critical component)
|   |-- labels.py                # Join telemetry with arrivals for ground truth
|   |-- split.py                 # Temporal train/val/test splitting
|
|-- features/
|   |-- __init__.py
|   |-- core.py                  # Speed, heading sin/cos, passenger count, delay
|   |-- distance.py              # GTFS route distance, haversine, stops remaining
|   |-- temporal.py              # Hour, day, cyclical encoding, rush hour, class change
|   |-- rolling.py               # Rolling window speed/distance/heading stats
|   |-- weather.py               # Temperature, precipitation, is_raining
|   |-- historical.py            # Segment avg times, dwell times, vehicle speed factor
|   |-- schedule.py              # Scheduled baseline, timepoint hold times
|   |-- pipeline.py              # Orchestrates all feature groups in order
|
|-- model/
|   |-- __init__.py
|   |-- train.py                 # XGBoost training with early stopping
|   |-- evaluate.py              # Metrics computation and reporting
|   |-- artifacts.py             # Model saving/loading, metadata export
|   |-- hyperparams.py           # Default hyperparameter configs
|
|-- scripts/
|   |-- run_pipeline.py          # Full end-to-end: data prep -> train -> evaluate
|   |-- run_data_prep.py         # Data preparation only
|   |-- run_training.py          # Training only (from existing parquet)
|   |-- run_evaluation.py        # Evaluation only (from existing model + test set)
|
|-- output/                      # Git-ignored runtime outputs
    |-- data/
    |   |-- train.parquet
    |   |-- val.parquet
    |   |-- test.parquet
    |   |-- metadata.json
    |
    |-- models/
    |   |-- model.json            # XGBoost model artifact
    |   |-- model_config.json     # Hyperparameters used
    |   |-- feature_columns.json  # Ordered feature list
    |
    |-- reports/
        |-- quality_report.md
        |-- evaluation_report.md
        |-- feature_importance.png
```

### Structure Rationale

- **`data/` vs `features/` separation:** Data loading/filtering/splitting is structural plumbing. Feature engineering is domain logic that changes frequently. Separating them means you can swap feature groups without touching the data pipeline.
- **`features/pipeline.py` orchestrator:** Runs all feature groups in dependency order. Adding a new feature group means adding one import and one function call here.
- **`model/` isolation:** Training, evaluation, and artifact management are independent of data preparation. You should be able to re-train from cached parquet without re-running data prep.
- **`scripts/` entry points:** Separate scripts for each phase so you can iterate on training without waiting for data prep, or vice versa.
- **`output/` git-ignored:** Parquet files, models, and reports are regenerated artifacts. Only code and config go in version control.

## Data Flow

### End-to-End Pipeline Flow

```
[1] LOAD RAW DATA
    |
    |  JSONL telemetry files --> pd.DataFrame (one row per GPS packet)
    |  Arrivals CSVs --> pd.DataFrame (one row per stop arrival event)
    |  GTFS files --> lookup structures (shapes, stop_times, trips)
    |  Weather CSV --> pd.DataFrame (one row per hour)
    |  Timepoints XLSX --> Dict[route_id -> List[stop_ids with hold times]]
    |
    v
[2] FILTER
    |
    |  Remove jAUnt/Shuttle vehicles
    |  Keep only active service states (status 7, 71)
    |  Remove NIS pattern (9998)
    |  Remove records outside Auburn geo-bounds
    |
    v
[3] FEATURE ENGINEERING (on telemetry-granularity DataFrame)
    |
    |  Core features: speed, heading_sin/cos, passenger_count, delay
    |  Rolling features: speed_avg_30s..300s, distance_traveled, heading_change
    |  Temporal features: hour, day, cyclical time, rush_hour, class_change
    |  Weather join: temperature, precipitation, is_raining
    |  Historical stats: segment_avg_time, dwell_time, vehicle_speed_factor
    |
    |  At this point: ~50 features per telemetry observation
    |  Row count = number of valid telemetry packets (unchanged)
    |
    v
[4] ROW EXPLOSION (per-stop expansion)  <--- CRITICAL MEMORY STEP
    |
    |  For each telemetry row:
    |    Look up trip's stop sequence from GTFS
    |    Identify remaining stops (after last_stop_id)
    |    Create one row per remaining target stop
    |    Add per-row features: route_distance_to_target, stops_remaining,
    |                          haversine_to_target, scheduled_time_to_target
    |
    |  Row count MULTIPLIED by avg ~8-12 remaining stops per observation
    |  Example: 500K telemetry rows -> 4-6M training rows
    |
    v
[5] LABEL CREATION (vectorized join)
    |
    |  For each exploded row (vid, timestamp, target_stop_id):
    |    Find next arrival of that vehicle at that stop in arrivals CSV
    |    Compute: time_to_arrival_sec = arrival_time - telemetry_time
    |    Drop rows with no matching arrival (no ground truth)
    |    Drop rows with label > 3600s or < 0s
    |
    |  Typical survival rate: 50-70% of exploded rows get labels
    |
    v
[6] TEMPORAL SPLIT
    |
    |  Sort by timestamp_ms
    |  Train: first 70% of time range (e.g., weeks 1-3.5)
    |  Val: next 15% (e.g., week 3.5-4.25)
    |  Test: final 15% (e.g., week 4.25-5)
    |  Save as Parquet with float32 dtypes
    |
    v
[7] XGBOOST TRAINING
    |
    |  Load train.parquet and val.parquet
    |  Create DMatrix objects (features + label)
    |  Set categorical feature types for route_id, hour, day_of_week
    |  Train with early stopping on validation MAE
    |  Log training curves
    |
    v
[8] EVALUATION
    |
    |  Load test.parquet + trained model
    |  Predict on test set
    |  Compute: MAE, RMSE, MAPE, R-squared
    |  Slice by: route, stops_remaining bucket, time_of_day, distance bucket
    |  Feature importance (gain, cover, weight)
    |  Residual distribution analysis
    |
    v
[9] ARTIFACT EXPORT
    |
    |  model.json (XGBoost native format)
    |  feature_columns.json (ordered list for inference)
    |  model_config.json (hyperparams, training metadata)
    |  evaluation_report.md (human-readable summary)
    |  feature_importance.json (for analysis)
```

### Key Data Flows

1. **Telemetry-to-features flow:** JSONL -> flat DataFrame -> rolling window enrichment -> temporal enrichment -> weather join. Each step adds columns but does not change row count. This is the "safe" part of the pipeline.

2. **Row explosion flow:** One telemetry row with `last_stop_id` and `trip_id` expands into N rows (one per remaining stop). This is where the data multiplies. The per-target-stop features (distance, stops_remaining, scheduled_time) are computed during explosion, not before.

3. **Label join flow:** Exploded rows are matched to arrivals CSV. This is a left join on (vid, target_stop_id) where arrival_time > telemetry_time. Unmatched rows (no ground truth) are dropped.

## Architectural Patterns

### Pattern 1: Two-Phase Data Prep (Pre-Explosion + Post-Explosion Features)

**What:** Split feature engineering into features computed once per telemetry observation (rolling stats, temporal, weather) and features computed per target stop (distance, stops_remaining, scheduled_time). Compute the first set before row explosion, the second set during/after.

**When to use:** Always, for this pipeline. Computing rolling window features after explosion would wastefully recompute identical values for every exploded copy of the same observation.

**Trade-offs:** Slightly more complex pipeline orchestration, but dramatic memory and compute savings.

**Example:**
```python
# Phase 1: Features on telemetry-level rows (cheap)
df = compute_rolling_features(df)        # ~50 features, N rows
df = compute_temporal_features(df)
df = join_weather_data(df)

# Phase 2: Explode (expensive -- row count multiplies)
df_exploded = explode_per_stop(df, gtfs_stop_sequences)

# Phase 3: Per-target features (on exploded rows)
df_exploded = compute_distance_to_target(df_exploded, gtfs_calculator)
df_exploded = compute_scheduled_time_to_target(df_exploded, stop_times)
```

### Pattern 2: Chunked Explosion with Parquet Append

**What:** Process telemetry data in day-sized chunks. For each chunk: compute features, explode, create labels, append to a growing Parquet file. Never hold the full exploded dataset in memory at once.

**When to use:** When total exploded dataset exceeds available RAM (likely: 5 weeks of data at ~10 stops per observation could produce 5-10M rows with 50+ features).

**Trade-offs:** Slightly slower due to I/O overhead, but prevents OOM crashes. Parquet append via PyArrow is efficient.

**Example:**
```python
writer = None
for day_file in sorted(telemetry_files):
    chunk = load_and_filter(day_file)
    chunk = compute_telemetry_features(chunk)
    exploded = explode_per_stop(chunk, gtfs)
    labeled = create_labels(exploded, arrivals)

    table = pa.Table.from_pandas(labeled)
    if writer is None:
        writer = pq.ParquetWriter(output_path, table.schema)
    writer.write_table(table)

writer.close()
```

### Pattern 3: Temporal Split by Calendar Date, Not by Row Index

**What:** Split train/val/test by calendar date boundaries, not by row-count percentages. This ensures no temporal leakage even after row explosion (where one observation time generates many rows).

**When to use:** Always, for time-series transit data.

**Trade-offs:** Split sizes are not perfectly balanced (some days have more data), but temporal integrity is preserved.

**Example:**
```python
# With ~5 weeks of data (Nov 6 - Dec 14):
# Train: Nov 6 - Dec 1   (~25 days, ~71%)
# Val:   Dec 2 - Dec 8   (~7 days, ~15%)
# Test:  Dec 9 - Dec 14  (~6 days, ~14%)
train_mask = df['date'] <= '2025-12-01'
val_mask   = (df['date'] > '2025-12-01') & (df['date'] <= '2025-12-08')
test_mask  = df['date'] > '2025-12-08'
```

### Pattern 4: XGBoost Native API with DMatrix

**What:** Use XGBoost's native `xgb.train()` API with DMatrix objects rather than the sklearn wrapper. This gives access to early stopping callbacks, custom evaluation metrics, and efficient categorical feature handling.

**When to use:** When you need fine-grained control over training (which this pipeline does -- early stopping, categorical features, custom eval).

**Trade-offs:** Slightly more boilerplate than sklearn's `fit()`, but more flexible and performant.

**Example:**
```python
dtrain = xgb.DMatrix(
    X_train, label=y_train,
    feature_names=feature_columns,
    enable_categorical=True
)
dval = xgb.DMatrix(X_val, label=y_val, feature_names=feature_columns, enable_categorical=True)

params = {
    'objective': 'reg:squarederror',
    'eval_metric': 'mae',
    'max_depth': 8,
    'learning_rate': 0.05,
    'subsample': 0.8,
    'colsample_bytree': 0.8,
    'min_child_weight': 50,
    'tree_method': 'hist',
}

model = xgb.train(
    params, dtrain,
    num_boost_round=2000,
    evals=[(dtrain, 'train'), (dval, 'val')],
    early_stopping_rounds=50,
    verbose_eval=25,
)
```

## Scaling Considerations

### Memory Budget for Row Explosion

| Metric | Estimate | Notes |
|--------|----------|-------|
| Raw telemetry rows | ~500K-1M | 5 weeks, ~15-20K packets/day after filtering |
| Avg remaining stops per observation | ~8-12 | Depends on where bus is on route |
| Exploded rows | ~4-10M | This is the critical number |
| Features per row | ~55 (float32) | 220 bytes/row |
| Total memory (exploded) | ~1-2 GB | Fits in RAM but leaves little headroom |
| After label join (50-70% survive) | ~2.5-7M rows | ~0.5-1.5 GB |

**Recommendation:** With ~5 weeks of data and ~55 features, the exploded dataset is likely 1-2 GB. This fits in 16 GB RAM but is uncomfortable. Use the **chunked explosion pattern** (Pattern 2) for safety, processing one day at a time and writing to Parquet incrementally.

### Scale Priorities

| Scale | Architecture Adjustments |
|-------|--------------------------|
| Current (5 weeks, 23 routes) | Single-machine Python, Pandas, chunked by day. Train in <5 minutes on CPU. |
| 3 months of data | Same architecture. Exploded dataset ~3-4 GB. Still fits in RAM with chunked processing. |
| 6+ months of data | Consider downsampling telemetry (keep every 3rd observation), or use XGBoost external memory / Dask. |

### Training Time Estimates

| Dataset Size | tree_method | Estimated Training Time | Notes |
|-------------|-------------|------------------------|-------|
| 3M rows, 55 features | `hist` (CPU) | 2-5 minutes | Default recommendation |
| 3M rows, 55 features | `gpu_hist` | 30-60 seconds | If CUDA GPU available |
| 10M rows, 55 features | `hist` (CPU) | 10-20 minutes | Still feasible |

## Anti-Patterns

### Anti-Pattern 1: Computing Per-Target Features Before Explosion

**What people do:** Try to compute `route_distance_to_stop` and `stops_remaining` on the original telemetry DataFrame by iterating over all possible target stops.
**Why it's wrong:** You end up with nested loops (for each row, for each possible target stop) which is extremely slow and creates confusing multi-column DataFrames (distance_to_stop_1, distance_to_stop_2, ... distance_to_stop_N).
**Do this instead:** First explode the rows (one row per target stop), then compute distance/stops_remaining as simple single-value columns. The explosion makes the computation trivially vectorizable.

### Anti-Pattern 2: Random Train/Test Split

**What people do:** Use `sklearn.model_selection.train_test_split(df, test_size=0.2, random_state=42)`.
**Why it's wrong:** For time-series data, random splitting causes temporal leakage. The model sees future data during training (e.g., December afternoon data in train, December morning data in test). This produces optimistic evaluation metrics that do not reflect real-world performance.
**Do this instead:** Always split by calendar date. Train on earlier dates, validate and test on later dates. This mimics real deployment where the model only has access to past data.

### Anti-Pattern 3: Row-by-Row Label Matching

**What people do:** Loop through each telemetry row, filter arrivals DataFrame for that vehicle and stop, find the next arrival. This is O(N * M) where N = telemetry rows and M = arrivals rows.
**Why it's wrong:** With millions of exploded rows, row-by-row matching takes hours. The existing `label_creator.py` does this and it is the main bottleneck.
**Do this instead:** Use a vectorized merge-asof approach. Sort both DataFrames by timestamp, then use `pd.merge_asof()` to find the next arrival for each telemetry record in O(N log N) time.

```python
# Vectorized label creation (fast)
df_sorted = df.sort_values('timestamp_ms')
arrivals_sorted = arrivals.sort_values('arrival_timestamp_ms')

# For each (vid, target_stop_id) group, merge_asof to find next arrival
labeled = pd.merge_asof(
    df_sorted,
    arrivals_sorted,
    left_on='timestamp_ms',
    right_on='arrival_timestamp_ms',
    by=['vid', 'target_stop_id'],
    direction='forward',
    tolerance=3600000  # 1 hour max lookahead
)
labeled['time_to_arrival_sec'] = (
    labeled['arrival_timestamp_ms'] - labeled['timestamp_ms']
) / 1000.0
```

### Anti-Pattern 4: Normalizing Features for XGBoost

**What people do:** Apply StandardScaler or MinMaxScaler to features before XGBoost training.
**Why it's wrong:** XGBoost splits on threshold values (e.g., "if speed > 15 mph, go left"). Normalization does not change split ordering and provides zero benefit. It adds complexity (need to save/load scaler) and makes feature importance harder to interpret.
**Do this instead:** Feed raw feature values directly. The existing `data_prep` pipeline correctly notes this: "No normalization -- GBDT splits on raw values; normalization adds no benefit."

### Anti-Pattern 5: One Model Per Route

**What people do:** Train separate XGBoost models for each of the 23 routes.
**Why it's wrong:** With only ~5 weeks of data, splitting by route means each model sees 1/23rd of the data. Short routes with few trips will have tiny training sets. Also creates 23x maintenance burden.
**Do this instead:** Train a single model with `route_id` as a categorical feature. XGBoost can learn route-specific patterns through tree splits on route_id. If a route truly behaves differently, the tree will branch on it. One model is simpler to train, evaluate, deploy, and maintain.

## Integration Points

### External Data Sources

| Source | Integration Pattern | Notes |
|--------|---------------------|-------|
| JSONL telemetry (live_data/) | Batch file loading, one file per day | Already collected, ~5 weeks of data |
| Arrivals CSV (raw_data/) | Pandas read_csv, column name mapping needed | Station names need mapping to stop IDs |
| GTFS (gtfs_data/) | Load shapes.txt, trips.txt, stop_times.txt into lookup dicts | Shapes for route distance, stop_times for sequences |
| Weather CSV (raw_data/) | Pandas read_csv, join on truncated hour | Hourly granularity |
| Timepoints XLSX | openpyxl/pandas read_excel, parse route-stop hold times | 23 routes with mandatory hold times at certain stops |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| data/ -> features/ | DataFrame in, DataFrame out | Features module adds columns to existing DataFrame |
| features/ -> data/row_exploder | DataFrame in, DataFrame out (larger) | Row count multiplies here |
| data/ -> model/ | Parquet files on disk | Clean boundary: data prep writes Parquet, training reads Parquet |
| model/train -> model/evaluate | Model object + test DMatrix | Evaluator receives trained model and test data |
| model/ -> output/ | JSON/Parquet/Markdown files | All artifacts written to output directory |

## Build Order (Dependency Chain)

The pipeline components have strict build-order dependencies. This is the recommended implementation sequence:

```
Phase 1: Data Foundation
  [1] config.py (constants, paths, feature lists)
  [2] data/loaders.py (JSONL, CSV, GTFS, weather parsers)
  [3] data/filters.py (vehicle/trip filtering)

Phase 2: Feature Engineering
  [4] features/core.py (heading sin/cos, basic transforms)
  [5] features/temporal.py (hour, day, cyclical, rush hour)
  [6] features/distance.py (GTFS route distance, haversine)
  [7] features/rolling.py (rolling window stats)
  [8] features/weather.py (weather join)
  [9] features/historical.py (segment times from arrivals)
  [10] features/schedule.py (timepoint hold times, scheduled baseline)
  [11] features/pipeline.py (orchestrate all feature groups)

Phase 3: Row Explosion + Labels
  [12] data/row_exploder.py (per-stop expansion)
  [13] data/labels.py (vectorized arrival matching)
  [14] data/split.py (temporal train/val/test)

Phase 4: Training + Evaluation
  [15] model/hyperparams.py (default XGBoost config)
  [16] model/train.py (DMatrix creation, xgb.train wrapper)
  [17] model/evaluate.py (metrics, sliced analysis, reporting)
  [18] model/artifacts.py (save/load model + metadata)

Phase 5: Integration + CLI
  [19] scripts/run_pipeline.py (end-to-end orchestration)
  [20] scripts/run_data_prep.py (data-only mode)
  [21] scripts/run_training.py (training-only mode)
```

**Critical dependency:** Row explosion (12) depends on GTFS distance calculator (6) and feature pipeline (11). Labels (13) depend on row explosion (12) and arrivals loader (2). Training (16) depends on split (14) producing Parquet files.

**Parallelizable:** Feature modules (4-10) are mostly independent of each other and can be developed in parallel, as long as `features/pipeline.py` (11) integrates them in the correct order.

## Sources

- [XGBoost 3.1.1 Official Documentation - Python Introduction](https://xgboost.readthedocs.io/en/stable/python/python_intro.html) -- HIGH confidence, verified current API patterns
- [XGBoost External Memory Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/external_memory.html) -- HIGH confidence, chunked processing patterns
- [Train-Test Split Strategies for Time Series Data](https://apxml.com/courses/time-series-analysis-forecasting/chapter-6-model-evaluation-selection/train-test-split-time-series) -- MEDIUM confidence, temporal split best practices
- [scikit-learn TimeSeriesSplit](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html) -- HIGH confidence, walk-forward validation reference
- [Part-2: How to Design an ML System for ETA Prediction](https://mlsavvy.substack.com/p/part-2-how-to-design-an-ml-system) -- MEDIUM confidence, transit ETA architecture patterns
- [MDPI: ETA Prediction Stacked Ensemble Approach](https://www.mdpi.com/2077-1312/14/2/177) -- MEDIUM confidence, feature engineering categories for ETA
- Existing codebase: `mobile/src/ETA-Model/data_prep/` -- HIGH confidence, direct inspection of current pipeline architecture

---
*Architecture research for: XGBoost Transit ETA Prediction Pipeline*
*Researched: 2026-02-03*
