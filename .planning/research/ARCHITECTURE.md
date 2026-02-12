# Architecture Research: Residual-Based ETA Prediction Pipeline

**Domain:** Modifying existing XGBoost ETA pipeline from raw-second prediction to residual prediction
**Researched:** 2026-02-11
**Confidence:** HIGH (based on direct codebase inspection + validated industry pattern)

## Executive Summary

The residual-based approach replaces the XGBoost target variable from raw `time_to_arrival_seconds` (range 10-7200s) with `residual = actual_arrival - baseline_ETA` (centered ~0). This is the same pattern Uber uses in DeepETA: a routing engine produces a baseline ETA, and the ML model predicts the residual (correction). The tighter target distribution should help XGBoost focus on explaining deviations from historical norms rather than learning the overall time-distance relationship from scratch.

The key architectural question is: **where does the baseline computation fit in the existing 9-script pipeline?** The answer is: between `temporal_split.py` (Step 6) and `build_features.py` / `build_differentiator_features.py` (Step 7), implemented as a new `compute_baseline.py` script that computes baseline ETA for every row in each split, using lookup tables built exclusively from training data.

## System Overview: Current vs Proposed

### Current Pipeline (v1.0)

```
[1] parse_telemetry.py     --> telemetry.parquet
[2] parse_arrivals.py      --> arrivals.parquet
[3] parse_gtfs.py          --> stop_sequences.parquet, shapes, etc.
[4] explode_rows.py        --> exploded.parquet  (telemetry x target_stops)
[5] label_join.py          --> labeled.parquet    (+ time_to_arrival_seconds)
[6] temporal_split.py      --> train/val/test.parquet
[7] build_features.py      --> train/val/test_featured.parquet  (15 features)
[7b] build_differentiator_features.py
                            --> historical_segments.parquet (from train only)
                            --> historical_dwells.parquet   (from train only)
                            --> train/val/test_featured_v2.parquet (43 features)
[8] train_*.py             --> models/*.ubj
[9] evaluate.py            --> models/evaluation/*
```

**Target variable:** `time_to_arrival_seconds` (raw seconds, range 10-7200s)

### Proposed Pipeline (v1.1)

```
[1-6] UNCHANGED            --> train/val/test.parquet  (same as v1.0)

[6.5] compute_baseline.py  --> historical_stop_to_stop.parquet  (from train only)
                            --> train/val/test.parquet  (+ baseline_eta, residual columns)
                                                         ^^^ MODIFIES IN PLACE

[7b] build_differentiator_features.py  (MODIFIED)
                            --> historical_segments.parquet (unchanged)
                            --> historical_dwells.parquet   (unchanged)
                            --> train/val/test_featured_v2.parquet
                                TARGET_COL now = "residual"
                                ALSO INCLUDES: baseline_eta column for reconstruction

[8] train_*.py             (MODIFIED: target="residual", symmetric loss)
                            --> models/*.ubj

[9] evaluate.py            (MODIFIED: reconstruct = baseline_eta + pred_residual,
                             then evaluate reconstructed vs actual)
```

**Target variable:** `residual = time_to_arrival_seconds - baseline_eta` (centered ~0)
**Inference formula:** `predicted_arrival = baseline_eta + predicted_residual`

## Component Responsibilities

| Component | Current Responsibility | v1.1 Change | Effort |
|-----------|----------------------|-------------|--------|
| `parse_*.py` (1-3) | Parse raw data | None | -- |
| `explode_rows.py` (4) | Create per-stop rows | None | -- |
| `label_join.py` (5) | Compute ground truth labels | None | -- |
| `temporal_split.py` (6) | Split by date | None | -- |
| **`compute_baseline.py` (6.5)** | **NEW: Build baseline ETA for every row** | **New script** | **High** |
| `build_differentiator_features.py` (7b) | Engineer 43 features + save parquets | Add `baseline_eta` and `residual` to output columns; change `TARGET_COL` | Medium |
| `train_*.py` (8) | Train XGBoost | Change target, use symmetric loss, re-tune | Medium |
| `evaluate.py` (9) | Evaluate on test set | Reconstruct actual from residual + baseline, compare | Medium |

## Detailed Architecture: compute_baseline.py

This is the critical new component. It must:

1. Build two lookup tables from **training data only** (no leakage)
2. Compute a blended baseline ETA for every row in train/val/test
3. Compute the residual label for training

### Baseline Definition

```
baseline_eta = average(
    segment_sum_eta,       # Sum of historical segment median travel times
    stop_to_stop_eta       # Direct historical average from current stop to target stop
)
```

### Component 1: Segment-Sum ETA

For each row (observation at current_stop heading to target_stop):
- Identify all segments between current_stop and target_stop on the route
- Look up each segment's median travel time from `historical_segments.parquet`
- Sum them: `segment_sum_eta = SUM(segment_median[seg_i])` for all segments from current to target

**Already exists:** `historical_segments.parquet` is computed in `build_differentiator_features.py` from training pings. It contains `(route_id, last_stop_id, hour_ct, day_type) -> segment_travel_median`. However, the current aggregation is per-segment (between consecutive stop transitions), not per-stop-pair cumulative. The baseline needs to **sum consecutive segment medians** from `last_stop_id` to `target_stop_id`.

**Key consideration:** The segment medians are keyed by `(route_id, last_stop_id, hour_ct, day_type)`. For baseline computation, we need to traverse the stop sequence for the route and sum up medians for each intermediate segment. Segments missing from the lookup (sparse data) need a fallback strategy.

### Component 2: Stop-to-Stop Historical Average

For each row (observation at current_stop heading to target_stop):
- Look up the historical average `time_to_arrival_seconds` for this `(route_id, current_stop, target_stop, hour, day_type)` combination from training data

**Does NOT exist yet.** Must be computed from the training split of `labeled.parquet` (or `train.parquet`). This is a direct aggregation:

```python
stop_to_stop_agg = train_df.groupby(
    ["route_id", "last_stop_id", "target_stop_id", "hour_ct", "day_type"]
)["time_to_arrival_seconds"].agg(["median", "mean", "count"])
```

**Use median** (robust to outliers, consistent with segment approach).

### Blending Strategy

```python
if both available:
    baseline_eta = (segment_sum_eta + stop_to_stop_eta) / 2
elif only segment_sum available:
    baseline_eta = segment_sum_eta
elif only stop_to_stop available:
    baseline_eta = stop_to_stop_eta
else:
    baseline_eta = scheduled_time_to_target  # ultimate fallback
```

### Residual Computation

```python
residual = time_to_arrival_seconds - baseline_eta
```

This residual becomes the new training target. Positive residual = bus took longer than baseline predicted. Negative = bus was faster than baseline.

## Data Flow: Training vs Inference

### Training Time

```
                    TRAINING DATA ONLY
                    (no val/test leakage)
                           |
                           v
            +------------------------------+
            |  Build Historical Lookups    |
            |                              |
            |  1. historical_segments      |  <-- already exists in v1.0
            |     (route, stop, hour, day) |
            |     -> segment_travel_median |
            |                              |
            |  2. historical_stop_to_stop  |  <-- NEW
            |     (route, from, to, hr, d) |
            |     -> median travel time    |
            +------------------------------+
                           |
           applies to ALL splits (train + val + test)
                           |
                           v
            +------------------------------+
            |  For each row in split:      |
            |                              |
            |  1. Traverse stop sequence   |
            |     from last_stop_id to     |
            |     target_stop_id           |
            |                              |
            |  2. Sum segment medians      |
            |     along the path           |
            |     = segment_sum_eta        |
            |                              |
            |  3. Look up stop-to-stop     |
            |     historical average       |
            |     = stop_to_stop_eta       |
            |                              |
            |  4. Blend:                   |
            |     baseline_eta = avg(      |
            |       segment_sum_eta,       |
            |       stop_to_stop_eta       |
            |     )                        |
            |                              |
            |  5. residual =               |
            |     actual - baseline_eta    |
            +------------------------------+
                           |
                           v
              XGBoost trains on residual
              using 43 features (same as v1.0)
```

### Inference Time

```
            +------------------------------+
            |  Live vehicle observation    |
            |  (lat, lon, route, speed,    |
            |   last_stop, target_stop)    |
            +------------------------------+
                           |
              +------------+------------+
              |                         |
              v                         v
    +-----------------+      +------------------+
    | Baseline ETA    |      | Feature Eng.     |
    | Calculator      |      | (same 43 feats)  |
    |                 |      |                  |
    | Uses same       |      | XGBoost model    |
    | historical      |      | predicts         |
    | lookup tables   |      | RESIDUAL         |
    +-----------------+      +------------------+
              |                         |
              v                         v
           baseline_eta         predicted_residual
              |                         |
              +------------+------------+
                           |
                           v
              predicted_arrival_time =
                baseline_eta + predicted_residual
```

**Critical inference requirement:** The historical lookup tables (`historical_segments.parquet`, `historical_stop_to_stop.parquet`) must be shipped alongside the model artifact. They are needed at inference time to compute baseline_eta.

## Script Modification Map

### NEW: `scripts/compute_baseline.py`

**Purpose:** Compute baseline ETA and residual for every row in train/val/test splits.

**Inputs:**
- `data/processed/train.parquet` (source for building lookups)
- `data/processed/val.parquet`
- `data/processed/test.parquet`
- `data/processed/stop_sequences.parquet` (for route stop ordering)
- `data/processed/historical_segments.parquet` (from `build_differentiator_features.py`)

**Outputs:**
- `data/processed/historical_stop_to_stop.parquet` (new lookup)
- `data/processed/train.parquet` (augmented with `baseline_eta`, `residual`)
- `data/processed/val.parquet` (augmented)
- `data/processed/test.parquet` (augmented)

**Dependency:** Must run AFTER `temporal_split.py` and AFTER `build_differentiator_features.py` has produced `historical_segments.parquet`. Alternatively, could compute segment medians internally.

**Key implementation detail:** The stop-to-stop lookup is built from `train.parquet` rows that already have `time_to_arrival_seconds`. This uses the actual arrival labels, not model predictions. The segment-sum approach uses `historical_segments.parquet` which is already computed from training pings only.

### MODIFY: `scripts/build_differentiator_features.py`

**Changes needed:**
1. Add `baseline_eta` to `KEEP_EXTRA` list so it survives the column selection in `save_v2_parquet()`
2. Change `TARGET_COL` from `"time_to_arrival_seconds"` to `"residual"` (or add a `RESIDUAL_COL` constant)
3. Ensure `baseline_eta` column is passed through the feature pipeline without being dropped
4. The `load_featured_v2()` function should return both residual (for training) and baseline_eta (for reconstruction)

**Lines affected:**
- Line 750: `TARGET_COL = "time_to_arrival_seconds"` --> needs dual-target support
- Line 752: `KEEP_EXTRA = ["stops_away", "route_id"]` --> add `"baseline_eta"`, `"time_to_arrival_seconds"`
- Line 861: `out_cols = list(FEATURE_COLS_V2) + [TARGET_COL]` --> include both targets

### MODIFY: `scripts/train_baseline.py`, `train_asymmetric_quantile.py`, `run_optuna_batches.py`

**Changes needed:**
1. Replace `TARGET_COL = "time_to_arrival_seconds"` with residual target
2. For `train_baseline.py`: remove asymmetric loss, use `reg:squarederror` (already is)
3. For `train_asymmetric_quantile.py`: remove asymmetric section initially (symmetric loss for v1.1)
4. Optuna tuning: re-tune for residual target distribution (may need different hyperparams since distribution is centered ~0 instead of right-skewed ~10-7200)

**Specific code change pattern:**
```python
# Old: load target as raw seconds
y_train = df_train[TARGET_COL].values  # TARGET_COL = "time_to_arrival_seconds"

# New: load target as residual, keep baseline for reconstruction
y_train = df_train["residual"].values
baseline_train = df_train["baseline_eta"].values  # for analysis only

# At evaluation time:
y_pred_residual = bst.predict(dtest)
y_pred_actual = baseline_test + y_pred_residual  # reconstruct
final_mae = mae(y_test_actual, y_pred_actual)    # evaluate on actual seconds
```

### MODIFY: `scripts/evaluate.py`

**Changes needed:**
1. Load `baseline_eta` from test data alongside features
2. After predicting residual, reconstruct: `predicted_arrival = baseline_eta + predicted_residual`
3. Evaluate on reconstructed predictions vs actual `time_to_arrival_seconds`
4. Add new analysis: baseline_eta quality assessment (MAE of baseline alone vs naive schedule)
5. Add residual distribution analysis (should be approximately centered at 0 if baseline is good)

**Critical:** All existing evaluation slicing (per-route, per-stops, per-TOD) should evaluate the **reconstructed** prediction, not the raw residual.

### MODIFY: `scripts/build_features.py`

**Changes needed:** Same pattern as `build_differentiator_features.py` -- propagate `baseline_eta` and `residual` through. However, since v1.1 uses the v2 feature pipeline, this script may not need modification if we only use `build_differentiator_features.py`.

**Recommendation:** Modify only `build_differentiator_features.py` (the v2 pipeline) since all v1.1 training uses v2 features (43 features).

## Data Leakage Prevention

This is the most critical architectural concern. The baseline must be computed from training data only.

### Leakage Points and Prevention

| Leakage Risk | Where | Prevention |
|---|---|---|
| Stop-to-stop lookup uses val/test data | `compute_baseline.py` | Build lookup from `train.parquet` ONLY, then apply to all splits |
| Segment medians use val/test data | `build_differentiator_features.py` | Already handled: `historical_segments.parquet` computed from train pings only (line 1016) |
| Dwell medians use val/test data | `build_differentiator_features.py` | Already handled: `historical_dwells.parquet` computed from train pings only (line 1030) |
| Baseline uses row's own actual label | `compute_baseline.py` | The stop-to-stop lookup is an AGGREGATE (median over many observations). Individual row's own contribution to the median is negligible with 1.5M+ training rows. Not a practical leakage concern. |
| Historical lookup populated with future timestamps | `compute_baseline.py` | All training data is temporally before val/test data (temporal split enforced by `temporal_split.py`). No future leakage. |

### Validation Strategy

After computing baseline:
1. Check that baseline_eta is non-negative for all rows
2. Check that residual distribution is approximately centered (mean close to 0 for training data)
3. Check that baseline MAE on test set is between naive schedule MAE (708.9s) and current model MAE (123.1s) -- a reasonable baseline should be somewhere in this range
4. Check coverage: what fraction of rows get a valid segment_sum_eta? valid stop_to_stop_eta?

### Expected Baseline Quality

The baseline should be a strong predictor already:
- `historical_segments.parquet` captures route/stop/hour/day_type patterns
- Stop-to-stop historical averages directly capture the distribution of the target variable

**Expected baseline MAE:** Likely in the 200-400s range (between naive schedule at 708.9s and XGBoost at 123.1s). The XGBoost model's job then becomes explaining the remaining variance.

## Fallback Strategy for Sparse Lookups

Not all `(route, from_stop, to_stop, hour, day_type)` combinations will have sufficient observations in training data. The fallback chain:

```
Level 1: Full key match (route, from_stop, to_stop, hour, day_type)
    |
    v (if no match or count < 10)
Level 2: Relaxed key (route, from_stop, to_stop, hour)  -- ignore day_type
    |
    v (if no match)
Level 3: Further relaxed (route, from_stop, to_stop)    -- ignore hour
    |
    v (if no match)
Level 4: Use scheduled_time_to_target as baseline        -- ultimate fallback
```

For segment_sum_eta, missing individual segments should use the mean segment time for that route as a fallback, not zero.

## Recommended Project Structure Changes

```
scripts/
|-- compute_baseline.py          # NEW: baseline ETA computation
|-- build_differentiator_features.py  # MODIFIED: include baseline_eta/residual
|-- train_baseline.py            # MODIFIED: predict residual
|-- run_optuna_batches.py        # MODIFIED: tune for residual target
|-- train_asymmetric_quantile.py # MODIFIED: symmetric loss initially
|-- evaluate.py                  # MODIFIED: reconstruct and evaluate

data/processed/
|-- historical_stop_to_stop.parquet  # NEW: stop-to-stop lookup table
|-- train.parquet                    # AUGMENTED: + baseline_eta, residual
|-- val.parquet                      # AUGMENTED: + baseline_eta, residual
|-- test.parquet                     # AUGMENTED: + baseline_eta, residual
```

## Suggested Build Order

The dependency chain dictates this build order:

```
Phase 1: Baseline Infrastructure
  [1] compute_baseline.py
      - Build historical_stop_to_stop lookup from train.parquet
      - Compute segment_sum_eta using historical_segments + stop_sequences
      - Compute blended baseline_eta for all splits
      - Compute residual = actual - baseline_eta
      - Augment train/val/test.parquet with new columns
      - Validate: baseline MAE, coverage %, residual distribution

Phase 2: Feature Pipeline Adaptation
  [2] Modify build_differentiator_features.py
      - Propagate baseline_eta and residual through feature pipeline
      - Add both to KEEP_EXTRA for output parquets
      - Dual target support (residual for training, baseline_eta for reconstruction)
      - Re-run to produce updated train/val/test_featured_v2.parquet

Phase 3: Training Pipeline Adaptation
  [3] Modify train_baseline.py
      - Change target to residual
      - Keep reg:squarederror (symmetric)
      - At evaluation: reconstruct predicted_actual = baseline + pred_residual
      - Compare reconstructed MAE vs v1.0 baseline

  [4] Modify run_optuna_batches.py
      - Retune hyperparameters for residual distribution
      - Residual is centered ~0 with potentially different variance structure
      - May need different max_depth, learning_rate

  [5] Modify train_asymmetric_quantile.py
      - Initially: symmetric loss only (remove asymmetric section)
      - Quantile models predict residual quantiles
      - Reconstruct: actual_quantile = baseline + residual_quantile

Phase 4: Evaluation Adaptation
  [6] Modify evaluate.py
      - Load baseline_eta alongside features
      - Reconstruct predictions before all metric computation
      - Add baseline quality analysis section
      - Add residual distribution analysis
      - Full comparison: v1.0 raw vs v1.1 residual
```

**Phase ordering rationale:**
- Phase 1 first because all downstream scripts depend on baseline_eta/residual columns existing
- Phase 2 before Phase 3 because training scripts import from the feature pipeline module
- Phase 3 before Phase 4 because evaluation needs a trained model
- Within Phase 3, baseline training (3) before Optuna (4) to verify the approach works before investing in tuning

## Anti-Patterns to Avoid

### Anti-Pattern 1: Computing Baseline After Feature Engineering

**What people do:** Try to compute baseline_eta inside `build_differentiator_features.py` alongside other features.
**Why it's wrong:** The baseline computation depends on the stop-to-stop historical lookup, which must be built from training data with actual labels. The feature pipeline should not be responsible for building new lookup tables AND computing residuals. Mixing concerns makes the code harder to test and debug.
**Do this instead:** Compute baseline_eta in a separate script (`compute_baseline.py`) that runs between temporal_split and feature engineering. This keeps each script's responsibility clear.

### Anti-Pattern 2: Using Val/Test Data in Lookup Tables

**What people do:** Build the stop-to-stop historical average from the entire labeled dataset (train + val + test).
**Why it's wrong:** This is data leakage. The baseline would incorporate future information, making residuals artificially small on val/test. Evaluation metrics would be optimistic and not reflect real-world performance.
**Do this instead:** Build ALL lookup tables from `train.parquet` exclusively. Apply them to val/test for baseline computation.

### Anti-Pattern 3: Not Carrying baseline_eta Through to Evaluation

**What people do:** Compute residual as the target, train the model, then try to evaluate the residual directly (e.g., "residual MAE = 50s").
**Why it's wrong:** A residual MAE of 50s is meaningless without reconstruction. The user cares about actual arrival time accuracy, not residual accuracy. You must reconstruct: `predicted_actual = baseline_eta + predicted_residual`, then compute MAE against actual arrival.
**Do this instead:** Always carry `baseline_eta` through the entire pipeline. Every evaluation metric must be computed on reconstructed predictions.

### Anti-Pattern 4: Overwriting Original Labels

**What people do:** Replace `time_to_arrival_seconds` with `residual` in the parquet files, losing the original label.
**Why it's wrong:** You need the original label for evaluation (to verify reconstructed predictions), for baseline quality assessment, and for debugging.
**Do this instead:** ADD columns (`baseline_eta`, `residual`) alongside the existing `time_to_arrival_seconds`. Never delete the original label.

### Anti-Pattern 5: Different Baseline Computation at Train vs Inference

**What people do:** Use a slightly different formula or fallback strategy for computing baseline_eta at inference time vs training time.
**Why it's wrong:** If the baseline is systematically different between training and inference, the residual model will produce biased predictions. The model learned to correct training-time baselines, not inference-time baselines.
**Do this instead:** Extract the baseline computation into a reusable function/class that is identical between training-time `compute_baseline.py` and inference-time code. Ship the same lookup tables with the model.

## Scaling Considerations

| Concern | Current Scale | Impact |
|---------|--------------|--------|
| Segment-sum computation | 2.08M rows x ~8 stops avg traversal | O(N * S) where S = avg segments. With ~23 routes, max ~30 stops per route. Vectorizable with stop_sequences.parquet merge. Expect 1-5 minutes. |
| Stop-to-stop lookup size | ~23 routes x ~30 stops x ~30 targets x 24 hours x 2 day_types | ~950K potential keys, but most are sparse. Realistic: 50-200K valid entries. Fits in memory easily. |
| Augmented parquet size | Adding 2 float columns to 2.08M rows | ~16MB additional. Negligible. |

## Sources

- **Uber DeepETA architecture:** [DeepETA: How Uber Predicts Arrival Times Using Deep Learning](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/) -- MEDIUM confidence, establishes industry precedent for residual prediction approach. Uber uses routing engine baseline + ML residual correction. Same pattern we're implementing with historical baseline + XGBoost residual.
- **Existing codebase:** Direct inspection of all 13 scripts in `scripts/` directory -- HIGH confidence. Pipeline structure, column names, data flow verified by reading actual code.
- **historical_segments.parquet:** Built from training data only in `build_differentiator_features.py` lines 1016-1026 -- HIGH confidence, verified no leakage.
- **Hybrid LSTM-XGBoost Residual Correction:** [Springer article on SSA-LSTM-XGBoost](https://link.springer.com/article/10.1007/s11869-025-01867-5) -- LOW confidence (different domain: air quality), but validates the residual-correction pattern where an initial model's residuals are modeled by a second learner.
- **Residual Error Modeling for Forecasts:** [MachineLearningMastery: Model Residual Errors](https://machinelearningmastery.com/model-residual-errors-correct-time-series-forecasts-python/) -- MEDIUM confidence, general technique for correcting forecasts using residual modeling.

---
*Architecture research for: Residual-Based ETA Prediction Pipeline (v1.1)*
*Researched: 2026-02-11*
