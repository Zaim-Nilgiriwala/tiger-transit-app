# Phase 3: Baseline Model - Research

**Researched:** 2026-02-03
**Domain:** XGBoost feature engineering + training for transit ETA prediction
**Confidence:** HIGH

## Summary

This phase engineers 14+ features from the existing exploded/labeled data (train.parquet, val.parquet, test.parquet) and trains a baseline XGBoost regression model. The data schema from Phase 2 contains raw telemetry columns (speed, progress, load, lat/lon, timestamps, stop IDs) plus explosion columns (target_stop_id, target_stop_progress, stops_away) and labels (time_to_arrival_seconds). Feature engineering must compute distance_to_target from GTFS shape_dist_traveled, scheduled_time_to_target from GTFS stop_times, lateness_now from lastStop timing, and temporal/weather/idle features.

A critical finding is that SHAP's TreeExplainer library is NOT compatible with XGBoost models trained with `enable_categorical=True`. The workaround is to use XGBoost's built-in SHAP computation via `booster.predict(dmatrix, pred_contribs=True)` for SHAP values, then use matplotlib directly for visualization rather than the shap library's plotting functions. Alternatively, pre-encode categoricals with OrdinalEncoder to use full shap library compatibility -- but this sacrifices XGBoost's native categorical split optimization.

The recommended approach: use XGBoost native categoricals for training (better model quality), compute SHAP values via `pred_contribs=True`, and build simple matplotlib bar plots for the summary visualization. This avoids the shap library dependency entirely for the baseline phase.

**Primary recommendation:** Build features in a single script, train with xgb.train() native API using enable_categorical=True and eval_metric='mae', compute SHAP via pred_contribs=True, and produce a comprehensive metrics report.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | >=2.1 (latest 3.1.1) | Gradient boosted trees | Decision locked. Native categorical support stable since 1.6, fully production since 3.1 |
| pandas | 2.3.3 (installed) | DataFrame manipulation for feature engineering | Already in use from Phase 1-2 |
| numpy | 2.2.6 (installed) | Numerical operations | Already in use |
| pyarrow | 23.0.0 (installed) | Parquet I/O | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib | any | SHAP summary plot PNG, training curves | Required for SHAP visualization since shap library is incompatible with native categoricals |
| scikit-learn | any | MAE/RMSE metric computation helpers | Optional -- can compute manually with numpy |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| XGBoost native `pred_contribs` | shap.TreeExplainer | shap library incompatible with enable_categorical=True models; would need OrdinalEncoder workaround |
| xgb.train() native API | XGBRegressor sklearn API | Native API gives more control over DMatrix, eval logging, iteration_range for predictions |

**Installation:**
```bash
pip install xgboost matplotlib
```

## Architecture Patterns

### Recommended Project Structure
```
scripts/
    build_features.py      # FEAT-01 through FEAT-08: feature engineering
    train_baseline.py      # TRAIN-01: XGBoost training + evaluation + SHAP
models/
    baseline_v1.ubj        # Saved model artifact (UBJSON format for categorical support)
    baseline_metrics.json   # Metrics report
    shap_summary.png       # SHAP summary plot
    training_log.txt       # Training curve log
```

### Pattern 1: Feature Engineering Pipeline
**What:** Load train/val/test parquets, compute all features by joining with GTFS data, write feature-enriched parquets or go directly to DMatrix.
**When to use:** Always -- separating feature engineering from training allows reuse in Phase 4.

Key design: Features are computed identically for train/val/test. The feature script loads supplementary data (stop_sequences.parquet, gtfs_stop_times.parquet, weather.parquet) and merges/computes features on each split independently.

```python
# Feature engineering pattern
def build_features(df: pd.DataFrame, stop_seqs: pd.DataFrame,
                   stop_times: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """Add all FEAT-01 through FEAT-08 columns to df."""
    df = compute_distance_to_target(df, stop_seqs)
    df = compute_scheduled_time_to_target(df, stop_times)
    df = compute_speed_features(df)
    df = compute_lateness(df)
    df = compute_temporal_features(df)
    df = compute_weather_features(df, weather)
    df = compute_idle_features(df)
    return df
```

### Pattern 2: XGBoost Native Training with Early Stopping
**What:** Use xgb.train() with DMatrix, evals list, early_stopping_rounds, and eval_metric='mae'.
**When to use:** Always for this project -- native API provides full control.

```python
# Source: https://xgboost.readthedocs.io/en/stable/python/python_intro.html
params = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "tree_method": "hist",
    "max_depth": 5,
    "learning_rate": 0.05,
    "min_child_weight": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "enable_categorical": True,
    "max_cat_to_onehot": 10,
}

dtrain = xgb.DMatrix(X_train, label=y_train, enable_categorical=True)
dval = xgb.DMatrix(X_val, label=y_val, enable_categorical=True)

bst = xgb.train(
    params,
    dtrain,
    num_boost_round=2000,
    evals=[(dtrain, "train"), (dval, "val")],
    early_stopping_rounds=100,
    verbose_eval=50,
)

# Predict using best iteration (NOT last iteration)
y_pred = bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))
```

### Pattern 3: SHAP via XGBoost Native pred_contribs
**What:** Compute SHAP values using XGBoost's built-in Tree SHAP rather than the shap Python library.
**When to use:** Always when using enable_categorical=True (shap library is incompatible).

```python
# Source: https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html
# Compute SHAP contributions
shap_values = bst.predict(dmatrix, pred_contribs=True)
# Shape: (n_samples, n_features + 1) -- last column is bias
# Column order matches feature names from DMatrix
feature_names = dmatrix.feature_names
shap_no_bias = shap_values[:, :-1]  # drop bias column

# Global feature importance: mean |SHAP|
mean_abs_shap = np.abs(shap_no_bias).mean(axis=0)
importance_order = np.argsort(mean_abs_shap)[::-1]

# Plot with matplotlib
import matplotlib.pyplot as plt
fig, ax = plt.subplots(figsize=(10, 8))
ax.barh(range(len(feature_names)),
        mean_abs_shap[importance_order],
        tick_label=[feature_names[i] for i in importance_order])
ax.set_xlabel("Mean |SHAP value|")
ax.set_title("Feature Importance (SHAP)")
fig.tight_layout()
fig.savefig("models/shap_summary.png", dpi=150)
```

### Anti-Patterns to Avoid
- **Using shap.TreeExplainer with enable_categorical models:** Will crash with `XGBoostError: Check failed: !HasCategoricalSplit()`. Use `pred_contribs=True` instead.
- **Using bst.predict() without iteration_range after early stopping:** Returns predictions from LAST iteration, not best. Always use `iteration_range=(0, bst.best_iteration + 1)`.
- **Saving model as .bin (binary format):** Binary format does NOT preserve categorical split information. Always save as `.ubj` (UBJSON) or `.json`.
- **Forgetting to set enable_categorical on DMatrix for prediction:** If the model was trained with categoricals, the prediction DMatrix also needs `enable_categorical=True`.
- **Computing features differently on train vs test:** All feature engineering must be identical. Use the same function for all splits.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHAP values | Custom permutation importance | `bst.predict(dm, pred_contribs=True)` | XGBoost's Tree SHAP is exact and O(TLD) where T=trees, L=leaves, D=depth |
| Distance along route | Haversine between GPS points | GTFS shape_dist_traveled difference | Route distance follows road geometry, not straight lines |
| MAE/RMSE computation | Manual loops | `np.mean(np.abs(y_true - y_pred))` and `np.sqrt(np.mean((y_true - y_pred)**2))` | One-liners, no need for sklearn |
| Categorical encoding | OrdinalEncoder or LabelEncoder | Pandas `.astype("category")` + XGBoost native | Native splits are optimal partitioning, not ordinal comparison |
| Early stopping logic | Manual training loop with patience | `xgb.train(early_stopping_rounds=100)` | Built-in, tracks best_iteration automatically |

**Key insight:** XGBoost's native API handles categoricals, SHAP, and early stopping internally. The less custom code, the fewer bugs.

## Common Pitfalls

### Pitfall 1: SHAP Library Incompatibility with Native Categoricals
**What goes wrong:** `shap.TreeExplainer(model)` raises `XGBoostError` when model has categorical splits.
**Why it happens:** The shap library loads trees via `save_raw()` binary format which cannot represent categorical splits. This is a known open issue (shap #2662).
**How to avoid:** Use `bst.predict(dmatrix, pred_contribs=True)` for SHAP values. Build matplotlib plots manually.
**Warning signs:** ImportError or XGBoostError mentioning "categorical" when calling TreeExplainer.

### Pitfall 2: distance_to_target Computed Incorrectly
**What goes wrong:** Using Euclidean or Haversine distance instead of route distance, or computing from raw lat/lon instead of GTFS shape_dist_traveled.
**Why it happens:** The exploded data has `progress` (normalized 0-1) and `target_stop_progress` (normalized 0-1), plus stop_sequences has `shape_dist_traveled` and `max_shape_dist`. Distance = `(target_stop_progress - progress) * max_shape_dist` gives route distance in the GTFS distance units (likely km based on max ~8.8 for Route 1).
**How to avoid:** Use the formula `(target_stop_progress - progress) * max_shape_dist_for_route`. This requires joining with stop_sequences to get `max_shape_dist` per route.
**Warning signs:** distance_to_target values that seem too small (straight-line) or negative.

### Pitfall 3: scheduled_time_to_target Requires GTFS Trip Matching
**What goes wrong:** Cannot compute scheduled_time_to_target without knowing which GTFS trip the vehicle is on.
**Why it happens:** GTFS stop_times has (trip_id, stop_id, arrival_time). Telemetry has route_id, timestamp, and current position but no trip_id. Need to match the vehicle to a specific GTFS trip to look up scheduled times.
**How to avoid:** Match by: (1) route_id to filter trips, (2) time-of-day proximity to find the closest scheduled trip, (3) compute scheduled arrival at target stop minus current time. This is the most complex feature to compute correctly.
**Warning signs:** Many NaN values in scheduled_time_to_target, or values that are negative (trip already passed).

### Pitfall 4: lateness_now Computation
**What goes wrong:** Misinterpreting the telemetry fields for schedule deviation.
**Why it happens:** The context says to compute as `actual_elapsed_since_trip_start - scheduled_elapsed_since_trip_start`. Telemetry has `last_stop_time_ms` (actual time at last stop) and `last_stop_on_time` (scheduled? flag?), plus `eta_seconds` and `scheduled_eta_seconds`.
**How to avoid:** The simplest proxy: `scheduled_eta_seconds - eta_seconds` gives current schedule deviation in seconds (positive = running late). Or use `last_stop_time_ms` vs scheduled departure at last stop from GTFS. Need to verify field semantics.
**Warning signs:** lateness values that are unrealistically large (>1 hour) or all zero.

### Pitfall 5: Forgetting iteration_range on Prediction
**What goes wrong:** Model predictions use all 2000 rounds instead of best_iteration, producing overfit predictions.
**Why it happens:** `xgb.train()` returns the model from the LAST iteration, not the best one.
**How to avoid:** Always use `bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))`.
**Warning signs:** Test MAE is worse than validation MAE despite early stopping being active.

### Pitfall 6: Category Dtype Not Set Before DMatrix Creation
**What goes wrong:** XGBoost treats route_id and pattern_id as numeric (continuous) features rather than categorical.
**Why it happens:** Parquet files store them as int64. Must explicitly cast to pandas category dtype before creating DMatrix.
**How to avoid:** `df["route_id"] = df["route_id"].astype("category")` and same for `pattern_id` BEFORE creating DMatrix.
**Warning signs:** Model treats route 228 as "greater than" route 5, or SHAP shows ordinal-looking patterns for route features.

### Pitfall 7: Data Leakage from weather.parquet Timezone
**What goes wrong:** Weather data joined by wrong hour if timezone not aligned.
**Why it happens:** Weather has UTC timestamps, telemetry has UTC timestamps. Should be fine, but verify the floor-to-hour matches.
**How to avoid:** Both should be UTC. Floor telemetry timestamp to nearest hour, merge with weather on hour.
**Warning signs:** Weather features show no predictive power, or precip values misaligned with actual rain periods.

## Code Examples

### Feature: distance_to_target (FEAT-01)
```python
# Distance along route from current position to target stop
# progress and target_stop_progress are both normalized [0, 1]
# max_shape_dist is the total route length in GTFS distance units
def compute_distance_to_target(df: pd.DataFrame, stop_seqs: pd.DataFrame) -> pd.DataFrame:
    # Get max_shape_dist per route from stop_sequences
    route_max_dist = stop_seqs.groupby("route_id")["max_shape_dist"].first()
    df = df.merge(route_max_dist.rename("_max_dist"), left_on="route_id", right_index=True, how="left")
    df["distance_to_target"] = (df["target_stop_progress"] - df["progress"]) * df["_max_dist"]
    df = df.drop(columns=["_max_dist"])
    # Clamp negative to 0 (shouldn't happen given explosion logic, but safety)
    df["distance_to_target"] = df["distance_to_target"].clip(lower=0)
    return df
```

### Feature: Temporal Features (FEAT-05)
```python
def compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    # minutes_since_midnight (raw, not cyclical -- XGBoost handles non-linearity)
    df["minutes_since_midnight"] = (
        df["timestamp"].dt.hour * 60 + df["timestamp"].dt.minute
    )
    # day_of_week as categorical (0=Monday, 6=Sunday)
    df["day_of_week"] = df["timestamp"].dt.dayofweek.astype("category")
    return df
```

### Feature: Idle Detection (FEAT-08)
```python
def compute_idle_features(df: pd.DataFrame) -> pd.DataFrame:
    # Recommended thresholds (Claude's discretion):
    # is_idle: speed <= 2 (accounts for GPS drift at stops)
    # idle_duration: requires sorting by (vehicle_id, timestamp) and
    # computing consecutive idle time -- but with downsampled 60s data,
    # a simpler proxy works:
    df["is_idle"] = (df["speed"] <= 2).astype(int)
    # idle_duration would require trip-level groupby -- for baseline,
    # is_idle binary flag may suffice. Can add duration in Phase 4.
    return df
```

### Creating DMatrix with Categoricals
```python
# Source: https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html
FEATURE_COLS = [
    "distance_to_target", "scheduled_time_to_target", "current_speed",
    "route_progress", "stops_remaining", "stop_index",
    "lateness_now", "minutes_since_midnight", "day_of_week",
    "pattern_id", "precipitation_mm", "temperature_c",
    "passenger_load", "is_idle",
]
CATEGORICAL_COLS = ["route_id", "day_of_week", "pattern_id"]

def make_dmatrix(df: pd.DataFrame, label_col: str = "time_to_arrival_seconds") -> xgb.DMatrix:
    # Cast categoricals BEFORE creating DMatrix
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")

    features = [c for c in FEATURE_COLS if c in df.columns]
    dm = xgb.DMatrix(
        df[features],
        label=df[label_col] if label_col in df.columns else None,
        enable_categorical=True,
    )
    return dm
```

### Evaluation with Sliced Metrics
```python
def evaluate_model(y_true, y_pred, df, label="test"):
    """Compute overall + sliced metrics."""
    mae = np.mean(np.abs(y_true - y_pred))
    rmse = np.sqrt(np.mean((y_true - y_pred) ** 2))
    print(f"\n{label} Overall: MAE={mae:.1f}s, RMSE={rmse:.1f}s")

    # Per-route
    for route_id in sorted(df["route_id"].unique()):
        mask = df["route_id"] == route_id
        if mask.sum() > 0:
            r_mae = np.mean(np.abs(y_true[mask] - y_pred[mask]))
            print(f"  Route {route_id}: MAE={r_mae:.1f}s (n={mask.sum():,})")

    # By stops_remaining buckets
    for bucket_name, low, high in [("1", 1, 1), ("2-3", 2, 3), ("4-6", 4, 6), ("7+", 7, 99)]:
        mask = (df["stops_away"] >= low) & (df["stops_away"] <= high)
        if mask.sum() > 0:
            b_mae = np.mean(np.abs(y_true[mask] - y_pred[mask]))
            print(f"  stops_remaining={bucket_name}: MAE={b_mae:.1f}s (n={mask.sum():,})")

    return {"mae": mae, "rmse": rmse}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| OrdinalEncoder for categoricals | XGBoost native `enable_categorical=True` | XGBoost 1.6+ (2022), experimental tag removed in 3.1 (2025) | Optimal partition splits vs ordinal comparisons |
| shap.TreeExplainer for SHAP | `bst.predict(dm, pred_contribs=True)` | Needed when using native categoricals | Same exact SHAP values, just different API |
| `.bin` model format | `.ubj` (UBJSON) or `.json` | Required for categorical models | Binary format cannot store categorical split info |
| Manual eval loop | Built-in `eval_metric='mae'` | Available since XGBoost 1.x | Cleaner, integrated with early stopping |

**Deprecated/outdated:**
- `save_raw()` / `.bin` model format: Cannot represent categorical splits. Use `.ubj` or `.json`.
- `shap` library with XGBoost categoricals: Known incompatibility (shap issue #2662). Use XGBoost native SHAP instead.

## Data Schema Reference

### Available Columns in train/val/test.parquet
| Column | Type | Source | Notes |
|--------|------|--------|-------|
| vehicle_id | string | telemetry | Vehicle identifier |
| route_id | int64 | telemetry | Numeric route ID (matches stop_sequences) |
| timestamp_ms | int64 | telemetry | Unix ms |
| lat, lon | double | telemetry | GPS position |
| heading | int64 | telemetry | Compass heading |
| speed | int64 | telemetry | GPS-reported speed (use directly as current_speed per decision) |
| load | int64 | telemetry | Passenger count (use directly as passenger_load per decision) |
| pattern_id | int64 | telemetry | Pattern identifier (use as categorical) |
| progress | double | telemetry | Normalized route progress [0, 1] |
| last_stop_id | int64 | telemetry | ID of last visited stop |
| last_stop_time_ms | double | telemetry | Timestamp (ms) vehicle was at last stop |
| last_stop_on_time | int64 | telemetry | Schedule adherence flag at last stop |
| next_stop_id | int64 | telemetry | ID of next stop |
| eta_seconds | int64 | telemetry | ETA system's current ETA estimate |
| scheduled_eta_seconds | int64 | telemetry | Scheduled ETA for comparison |
| is_delayed | bool | telemetry | Delay flag |
| timestamp | timestamp[ns, UTC] | derived | Parsed from timestamp_ms |
| target_stop_id | int64 | explosion | The stop we're predicting arrival at |
| target_stop_sequence | int64 | explosion | GTFS stop_sequence of target |
| target_stop_progress | double | explosion | Normalized progress of target stop |
| stops_away | int64 | explosion | Number of stops to target (1-8) |
| actual_arrival | timestamp[ns, UTC] | label join | Ground truth arrival time |
| time_to_arrival_seconds | double | label join | TARGET VARIABLE |
| date | date32 | split | Calendar date |
| is_weekday | bool | split | Weekday flag |

### Feature Mapping (Requirements to Data Columns)
| Requirement | Feature Name | Source Column(s) | Computation |
|-------------|-------------|-----------------|-------------|
| FEAT-01 | distance_to_target | progress, target_stop_progress, max_shape_dist | (target_stop_progress - progress) * max_shape_dist |
| FEAT-02 | scheduled_time_to_target | scheduled_eta_seconds OR GTFS stop_times | See Pitfall 3 -- may use scheduled_eta_seconds as proxy |
| FEAT-03 | current_speed | speed | Direct (per decision) |
| FEAT-03 | route_progress | progress | Direct (already normalized) |
| FEAT-03 | stops_remaining | stops_away | Direct rename |
| FEAT-03 | stop_index | target_stop_sequence | Direct rename |
| FEAT-04 | lateness_now | scheduled_eta_seconds, eta_seconds | scheduled_eta_seconds - eta_seconds (positive = late) |
| FEAT-05 | minutes_since_midnight | timestamp | hour * 60 + minute |
| FEAT-05 | day_of_week | timestamp | dayofweek as category |
| FEAT-06 | pattern_id | pattern_id | Cast to category |
| FEAT-07 | precipitation_mm | weather.parquet | Join by hour |
| FEAT-07 | temperature_c | weather.parquet | Join by hour |
| FEAT-08 | passenger_load | load | Direct (per decision) |
| FEAT-08 | is_idle | speed | speed <= 2 |

## Open Questions

1. **scheduled_time_to_target exact computation**
   - What we know: Telemetry has `scheduled_eta_seconds` which appears to be the system's scheduled ETA. GTFS stop_times has per-trip scheduled arrival times. The requirement says "seconds from now until scheduled arrival at target stop (from GTFS stop_times)."
   - What's unclear: Whether `scheduled_eta_seconds` in telemetry is already the scheduled time to the NEXT stop (not the target stop), or if it's to the target stop. If it's to next_stop only, we need GTFS trip matching to get scheduled time to arbitrary target stops.
   - Recommendation: First check what `scheduled_eta_seconds` represents by comparing it to the label. If it correlates well, it may be usable as scheduled_time_to_target. If not, compute from GTFS stop_times using trip matching (route_id + time-of-day to find trip, then look up scheduled arrival at target stop). A simpler fallback: interpolate using `(target_stop_progress - progress) / avg_route_speed * 3600` as a schedule proxy.

2. **lateness_now exact computation**
   - What we know: Context says "actual_elapsed_since_trip_start - scheduled_elapsed_since_trip_start". Telemetry has `last_stop_time_ms` (when vehicle was at last stop), `last_stop_on_time` (flag), `eta_seconds`, `scheduled_eta_seconds`.
   - What's unclear: Whether `last_stop_on_time` is 1/0 or a timestamp. What `last_stop_time_ms` precisely means (actual arrival or departure at last stop).
   - Recommendation: Use `scheduled_eta_seconds - eta_seconds` as a proxy for current schedule deviation. If both fields are ETAs to the next stop, their difference captures lateness. Validate by checking distribution -- should be centered near 0 with spread of a few minutes.

3. **GTFS distance units**
   - What we know: stop_sequences max_shape_dist for Route 1 is ~8.8. This is likely kilometers (reasonable for a campus bus route of ~5.5 miles).
   - What's unclear: GTFS spec allows arbitrary units. Could be km, meters, or miles.
   - Recommendation: Does not matter for model training (XGBoost is scale-invariant for splits). Just document the unit assumption. For interpretability, note that values are likely in km.

4. **idle_duration computation**
   - What we know: Data is downsampled to 60s intervals per vehicle. Computing consecutive idle duration requires sorting by (vehicle_id, timestamp) within a trip.
   - What's unclear: Whether 60s granularity is sufficient for meaningful idle duration.
   - Recommendation: For baseline, use binary `is_idle` (speed <= 2) only. Add `idle_duration` as enhancement if time permits. The binary flag captures "is the bus currently stopped" which is the main signal.

## Sources

### Primary (HIGH confidence)
- [XGBoost Categorical Tutorial](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html) - Native categorical support API, requirements, caveats
- [XGBoost Python Intro](https://xgboost.readthedocs.io/en/stable/python/python_intro.html) - xgb.train() with evals, early_stopping, DMatrix, model saving
- [XGBoost Parameters](https://xgboost.readthedocs.io/en/stable/parameter.html) - Confirmed mae as built-in eval_metric
- [SHAP/XGBoost incompatibility issue #2662](https://github.com/shap/shap/issues/2662) - Confirmed SHAP TreeExplainer does not work with categorical splits

### Secondary (MEDIUM confidence)
- [XGBoosting.com SHAP guide](https://xgboosting.com/explain-xgboost-predictions-with-shap/) - pred_contribs workaround verified against official docs
- [SHAP official docs](https://shap.readthedocs.io/en/latest/) - Latest version 0.50.0

### Tertiary (LOW confidence)
- idle detection threshold of speed <= 2: Based on general transit domain knowledge. Should be validated against data distribution.
- GTFS distance units assumption (km): Based on max_shape_dist ~8.8 for a campus route. Not verified.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - XGBoost and pandas are locked decisions, versions verified
- Architecture: HIGH - Pattern is straightforward feature engineering + xgb.train()
- SHAP workaround: HIGH - Incompatibility confirmed via official GitHub issue, workaround verified in XGBoost docs
- Feature computation: MEDIUM - distance_to_target is clear; scheduled_time_to_target and lateness_now need field-level validation during implementation
- Pitfalls: HIGH - All pitfalls verified against official documentation or known issues

**Research date:** 2026-02-03
**Valid until:** 2026-03-03 (30 days -- XGBoost API is stable)
