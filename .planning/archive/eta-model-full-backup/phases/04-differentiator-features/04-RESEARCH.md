# Phase 4: Differentiator Features - Research

**Researched:** 2026-02-04
**Domain:** Feature engineering for transit ETA prediction (pandas + XGBoost)
**Confidence:** HIGH

## Summary

Phase 4 adds four categories of advanced features to the existing 15-feature baseline: GPS-derived rolling speed windows (with acceleration, variance, idle detection), timepoint schedule features, historical segment/dwell time aggregates, and a normalized speed ratio. The data is already downsampled to ~60-second intervals (median ping delta = 60s), which constrains rolling window design -- a 30s window will typically contain only 1 observation and a 180s window about 3. Features are computed from the existing `train.parquet` / `val.parquet` / `test.parquet` splits (which contain raw columns `lat`, `lon`, `vehicle_id`, `timestamp`, `last_stop_id`, `route_id`, `is_weekday`, etc.) and historical aggregates must use training data only to prevent leakage.

The timepoints.parquet file contains 1,958 schedule entries across 22 routes (2 timepoint stops per route typically), and 21 of 23 data routes have timepoint coverage. Routes 27 and 235 lack timepoints (set features to NaN). The stop_sequences.parquet defines 163 segments across all routes, with a median of 228 observations per route-segment-hour-daytype combo (6% have fewer than 10 observations). Timestamps are UTC; Auburn Central Time = UTC - 6 hours, with service running roughly 6am-8pm CT (hours 12-02 UTC).

The existing codebase pattern (`build_features.py`) computes features in a single `compute_features()` function, modifying the DataFrame in-place. Phase 4 should extend this pattern with a new `build_differentiator_features.py` script that loads the Phase 2 splits, computes Phase 3 features plus all new differentiator features, and outputs `train_featured_v2.parquet` etc.

**Primary recommendation:** Build a single new feature engineering script that computes all differentiator features per-vehicle-trajectory (rolling speeds require sorted vehicle timelines), merges timepoint and historical aggregate lookups, and outputs v2 featured files alongside a v2 training script.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | DataFrame operations, groupby rolling, merge | Already in project, `groupby().rolling()` supports time-based windows |
| numpy | latest | Haversine vectorized computation, array math | Already in project, faster than pure pandas for trig ops |
| xgboost | latest | Model retraining with expanded features | Already in project, native NaN handling for sparse features |
| pyarrow | latest | Parquet I/O with dictionary encoding | Already in project, preserves categorical dtypes |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| matplotlib | latest | SHAP plots, feature importance comparison | Retrain evaluation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas groupby rolling | polars | Faster but adds dependency; pandas sufficient at 1.2M rows |
| numpy haversine | scikit-learn haversine_distances | sklearn adds import overhead for one function |

**Installation:** No new packages needed. All dependencies already installed.

## Architecture Patterns

### Recommended Script Structure
```
scripts/
  build_features.py          # Phase 3 (keep unchanged for reproducibility)
  build_differentiator_features.py  # Phase 4: all features including Phase 3
  train_differentiator.py    # Phase 4: retrain with v2 features
data/processed/
  train_featured_v2.parquet  # Phase 4 output
  val_featured_v2.parquet
  test_featured_v2.parquet
  historical_segments.parquet  # Precomputed from training data only
  historical_dwells.parquet    # Precomputed from training data only
models/
  differentiator_v1.ubj       # Phase 4 model
  differentiator_metrics.json
```

### Pattern 1: Vehicle-Trajectory Sorting for Rolling Features
**What:** Sort by (vehicle_id, route_id, timestamp) before computing rolling features, then merge back to exploded rows.
**When to use:** Rolling speed, acceleration, idle detection -- all require temporal ordering per vehicle.
**Why critical:** The exploded data has ~4.4x duplication (each ping appears for multiple target stops). Rolling features must be computed on unique pings first, then merged back.

```python
# Step 1: Extract unique pings
pings = df.drop_duplicates(subset=['vehicle_id', 'timestamp']).copy()
pings = pings.sort_values(['vehicle_id', 'route_id', 'timestamp'])

# Step 2: Compute GPS speed on pings
pings['gps_speed_mps'] = compute_gps_speed(pings)  # haversine-based

# Step 3: Compute rolling features on pings
pings = compute_rolling_features(pings)

# Step 4: Merge rolling features back to full exploded DataFrame
rolling_cols = ['gps_speed_30s', 'gps_speed_60s', ...]
df = df.merge(
    pings[['vehicle_id', 'timestamp'] + rolling_cols],
    on=['vehicle_id', 'timestamp'],
    how='left'
)
```

### Pattern 2: Historical Aggregates from Training Data Only
**What:** Compute segment/dwell medians from training split, then merge to all splits.
**When to use:** Historical segment travel time and dwell time features.
**Why critical:** Using val/test data in aggregates causes data leakage.

```python
# Compute from training data only
hist_segments = compute_historical_segments(train_df)  # returns DataFrame
hist_segments.to_parquet('data/processed/historical_segments.parquet')

# Merge to ALL splits (train, val, test)
for split_df in [train_df, val_df, test_df]:
    split_df = split_df.merge(hist_segments, on=['route_id', 'segment_id', 'hour', 'day_type'], how='left')
```

### Pattern 3: Timepoint Lookup with Nearest Schedule Match
**What:** For each observation, find the nearest scheduled departure at each timepoint stop on the route.
**When to use:** Computing `time_until_next_timepoint_departure` and `scheduled_departure_seconds`.

```python
# Convert timepoint scheduled_time to seconds since midnight
tp['sched_secs'] = pd.to_timedelta(tp['scheduled_time']).dt.total_seconds()

# For each observation's time-of-day, find next scheduled departure
# Use merge_asof with direction='forward' per route+stop
```

### Anti-Patterns to Avoid
- **Computing rolling features on exploded data:** Each ping is duplicated ~4.4x for different target stops. Rolling windows on exploded data would be 4.4x slower and potentially produce wrong results if not grouped correctly. Always compute on unique pings first.
- **Using val/test dates for historical aggregates:** This is data leakage. Aggregates must come from training dates only.
- **Forward-filling across vehicle trips:** When a vehicle changes route or has a multi-hour gap, rolling windows should NOT carry over. Use vehicle_id + route_id grouping and reset on large gaps.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Haversine distance | Manual trig formula from scratch | Vectorized numpy implementation (see Code Examples) | Off-by-one in radians conversion, need vectorized for 272K pings |
| Time-based rolling windows | Manual loop over timestamps | `pandas.groupby().rolling(window='60s')` with DatetimeIndex | pandas handles irregular spacing, min_periods, edge cases |
| NaN for sparse combos | Custom if/else fill logic | Let XGBoost handle NaN natively | XGBoost's sparsity-aware split finding learns optimal direction for missing values |
| Segment identification | Complex route-progress binning | Assign segment as `last_stop_id` (current segment = stop bus just passed) | `last_stop_id` is already in the data and naturally defines which segment the bus is on |

**Key insight:** The `last_stop_id` column already present in the data is the natural segment identifier. The bus is "on the segment from last_stop_id to the next stop." No need to compute segment IDs from route progress.

## Common Pitfalls

### Pitfall 1: GPS Speed Blow-Up from Jitter
**What goes wrong:** GPS positions can jump by 10-50 meters even when stationary, producing enormous computed speeds (100+ mph) over short time intervals.
**Why it happens:** Consumer GPS accuracy is ~5-15m. Over a 2-second delta, 15m jitter = 17 mph phantom speed.
**How to avoid:** (1) Enforce minimum 5-second time delta between pings. (2) Cap GPS speed at 65 mph (29 m/s). (3) The data is already downsampled to ~60s intervals, which naturally smooths jitter.
**Warning signs:** Max GPS speed values > 65 mph, or mean GPS speed much higher than device `speed` field.

### Pitfall 2: Rolling Window Sparsity at 60s Ping Rate
**What goes wrong:** With ~60s ping intervals, a 30s rolling window contains 0-1 points, and a 60s window contains 1-2 points. Rolling mean/std are undefined or noisy.
**Why it happens:** Data was downsampled to 60s buckets in Phase 2 (explode_rows.py).
**How to avoid:** Use `min_periods=1` for rolling computations. Accept that smaller windows (30s, 60s) will be noisy -- the model will learn their reliability via SHAP importance. The 120s and 180s windows will be more stable (2-3 points).
**Warning signs:** >50% NaN in 30s rolling speed feature.

### Pitfall 3: Timezone Confusion for Hour-Based Features
**What goes wrong:** Timestamps are UTC. Auburn is Central Time (UTC-6). Computing `hour` directly gives UTC hours, making "rush hour" and "time of day" features meaningless.
**Why it happens:** All timestamps stored as UTC in telemetry.
**How to avoid:** Convert to Central Time before extracting hour for historical aggregates and timepoint matching: `(timestamp - pd.Timedelta(hours=6)).dt.hour`. Service hours are ~6am-8pm CT (UTC hours 12-02).
**Warning signs:** Peak activity appearing at hours 13-23 instead of 7-17.

### Pitfall 4: Data Leakage in Historical Aggregates
**What goes wrong:** If you compute historical medians across all data (including val/test dates), the model sees future information.
**Why it happens:** Easy to accidentally compute aggregates on the full dataset before splitting.
**How to avoid:** Compute historical aggregates exclusively from `train.parquet`. Save as separate artifact. Merge into all splits as a lookup.
**Warning signs:** Suspiciously good val/test performance that doesn't generalize.

### Pitfall 5: Timepoint Features for Routes Without Timepoints
**What goes wrong:** Routes 27 and 235 have no timepoint data. Attempting to merge produces NaN, which is correct, but failing to handle this explicitly could cause confusion.
**Why it happens:** 2 of 23 data routes lack timepoint schedules.
**How to avoid:** Set all timepoint features to NaN for routes without timepoints. XGBoost handles NaN natively. Document which routes are affected.
**Warning signs:** Assertion errors on non-null checks.

### Pitfall 6: Vehicle Trip Boundary in Rolling Windows
**What goes wrong:** A vehicle finishes one route and starts another. Rolling speed window spans the trip boundary, mixing speeds from different routes/locations.
**Why it happens:** Same vehicle_id, different trips, treated as continuous series.
**How to avoid:** Group rolling windows by (vehicle_id, route_id). Additionally, reset rolling context when time gap > 5 minutes (the p90 delta is 119s, so a 5-minute gap indicates a trip boundary).
**Warning signs:** Unrealistic speed transitions, especially when route_id changes.

## Code Examples

### Vectorized Haversine for GPS Speed
```python
# Source: Standard haversine formula, vectorized with numpy
def haversine_meters(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in meters."""
    R = 6_371_000  # Earth radius in meters
    lat1, lon1, lat2, lon2 = map(np.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * R * np.arcsin(np.sqrt(a))

def compute_gps_speed(pings: pd.DataFrame) -> pd.Series:
    """Compute GPS-derived speed in m/s per ping.

    Requires pings sorted by (vehicle_id, route_id, timestamp).
    Returns NaN for first ping per vehicle-route and for delta < 5s.
    Caps at 29.06 m/s (65 mph).
    """
    # Shift within group
    g = pings.groupby(['vehicle_id', 'route_id'])
    lat_prev = g['lat'].shift(1)
    lon_prev = g['lon'].shift(1)
    ts_prev = g['timestamp'].shift(1)

    dist_m = haversine_meters(lat_prev.values, lon_prev.values,
                              pings['lat'].values, pings['lon'].values)
    delta_s = (pings['timestamp'] - ts_prev).dt.total_seconds()

    speed = dist_m / delta_s
    # Filter: min 5s delta, max 65 mph (29.06 m/s)
    speed = speed.where(delta_s >= 5, np.nan)
    speed = speed.clip(upper=29.06)
    return speed
```

### Time-Based Rolling Speed Windows
```python
# Source: pandas 2.3.3 groupby().rolling() with time offset
def compute_rolling_speed_features(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling speed statistics over 30s, 60s, 120s, 180s windows.

    pings must be sorted by (vehicle_id, route_id, timestamp) and have
    'gps_speed_mps' column. timestamp must be the index or used as on= param.
    """
    pings = pings.set_index('timestamp')
    group = pings.groupby(['vehicle_id', 'route_id'])

    for window in ['30s', '60s', '120s', '180s']:
        label = window.replace('s', '')  # '30', '60', etc.
        rolling = group['gps_speed_mps'].rolling(window=window, min_periods=1)
        pings[f'speed_mean_{label}s'] = rolling.mean().droplevel([0, 1])
        pings[f'speed_std_{label}s'] = rolling.std().droplevel([0, 1])

    pings = pings.reset_index()
    return pings
```

### Acceleration Feature
```python
def compute_acceleration(pings: pd.DataFrame) -> pd.Series:
    """Compute acceleration (speed change rate) in m/s^2."""
    g = pings.groupby(['vehicle_id', 'route_id'])
    speed_prev = g['gps_speed_mps'].shift(1)
    ts_prev = g['timestamp'].shift(1)
    delta_s = (pings['timestamp'] - ts_prev).dt.total_seconds()
    accel = (pings['gps_speed_mps'] - speed_prev) / delta_s
    return accel.where(delta_s >= 5, np.nan)  # Same 5s min delta
```

### Idle Detection
```python
# Idle threshold: < 2 mph = 0.894 m/s
IDLE_SPEED_THRESHOLD = 0.894  # m/s (approximately 2 mph)

def compute_idle_features(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute is_idle_gps flag and seconds_idle duration."""
    pings['is_idle_gps'] = (pings['gps_speed_mps'] < IDLE_SPEED_THRESHOLD).astype(int)

    # Compute consecutive idle duration
    g = pings.groupby(['vehicle_id', 'route_id'])
    ts_prev = g['timestamp'].shift(1)
    delta_s = (pings['timestamp'] - ts_prev).dt.total_seconds().fillna(0)

    # Cumulative idle time (resets when not idle)
    idle_groups = (pings['is_idle_gps'] != pings.groupby(['vehicle_id', 'route_id'])['is_idle_gps'].shift(1)).cumsum()
    pings['seconds_idle'] = (
        pings[pings['is_idle_gps'] == 1]
        .groupby(['vehicle_id', 'route_id', idle_groups])['timestamp']
        .transform(lambda x: (x - x.iloc[0]).dt.total_seconds())
    )
    pings['seconds_idle'] = pings['seconds_idle'].fillna(0)
    return pings
```

### Historical Segment Medians (Training Data Only)
```python
def compute_historical_segments(train_pings: pd.DataFrame) -> pd.DataFrame:
    """Compute median segment travel time from training data.

    Segment = (route_id, last_stop_id).
    Aggregation key = (route_id, last_stop_id, hour_ct, day_type).
    """
    MIN_OBS = 10  # Minimum observations for reliable median

    # Compute per-vehicle-segment traversal times
    # ... (see Architecture Patterns)

    agg = (train_pings
           .groupby(['route_id', 'last_stop_id', 'hour_ct', 'day_type'])
           .agg(
               segment_travel_median=('segment_travel_s', 'median'),
               segment_travel_count=('segment_travel_s', 'count'),
           )
           .reset_index())

    # NaN out sparse combos
    agg.loc[agg['segment_travel_count'] < MIN_OBS, 'segment_travel_median'] = np.nan

    return agg[['route_id', 'last_stop_id', 'hour_ct', 'day_type', 'segment_travel_median']]
```

### Timepoint Features
```python
def compute_timepoint_features(df: pd.DataFrame, tp: pd.DataFrame,
                                ss: pd.DataFrame) -> pd.DataFrame:
    """Add timepoint features to observation DataFrame.

    Features:
    - is_timepoint: target_stop_id is a timepoint stop
    - timepoints_remaining: count of timepoint stops between current and target
    - time_until_next_timepoint_departure: seconds to next scheduled departure
    - timepoint_adherence: seconds early/late at most recent passed timepoint
    """
    # Build set of (route_id, stop_id) that are timepoints
    tp_stops = set(zip(tp['route_id'], tp['stop_id']))

    # is_timepoint
    df['is_timepoint'] = df.apply(
        lambda r: int((r['route_id'], r['target_stop_id']) in tp_stops), axis=1
    )
    # ... (vectorized version preferred for 1.2M rows)
    return df
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Device-reported speed | GPS-derived speed (haversine) | Phase 4 decision | Device speed had moderate SHAP (rank 7); GPS-derived + rolling windows expected to capture more signal |
| Single point speed | Rolling window aggregates (30-180s) | Phase 4 decision | Smooths GPS noise, captures acceleration/deceleration trends |
| Global averages | Segment-hour-daytype medians | Phase 4 decision | Captures time-of-day and weekday/weekend travel patterns per segment |
| No schedule awareness | Timepoint adherence features | Phase 4 decision | Fills the gap left by zero-variance lateness_now from Phase 3 |

**Deprecated/outdated:**
- `lateness_now`: Confirmed zero SHAP importance (zero variance). Remains in feature set but contributes nothing. Timepoint adherence replaces its intended signal.
- `is_idle` (Phase 3): Based on device speed <= 2 mph. Phase 4 adds GPS-derived `is_idle_gps` and `seconds_idle` for richer idle signal.

## Open Questions

1. **Segment travel time computation method**
   - What we know: `last_stop_id` defines current segment. Need to compute how long the bus took to traverse from one stop to the next.
   - What's unclear: Whether to compute from consecutive pings at the same last_stop_id (time from first to last ping in a segment) or from stop-to-stop actual arrival differences.
   - Recommendation: Use the time between when `last_stop_id` changes for a vehicle (first ping with new `last_stop_id` minus last ping with previous `last_stop_id`). This naturally measures segment traversal time.

2. **Dwell time computation**
   - What we know: Dwell time = time bus spends at a stop (between arriving and departing).
   - What's unclear: The data has no explicit "door open/close" event. Must infer from consecutive pings where progress barely changes and speed is near zero at a stop location.
   - Recommendation: Define dwell as consecutive low-speed pings (< 2 mph) where `last_stop_id` just changed to a new value. The duration from the last_stop_id change to when speed exceeds threshold approximates dwell.

3. **Gap handling for rolling speed windows**
   - What we know: 4% of ping deltas > 5 minutes (trip boundaries).
   - What's unclear: Whether to NaN the first few pings after a gap or let the rolling window naturally handle it with min_periods=1.
   - Recommendation: Use NaN for the first ping after a gap > 300s (5 minutes). The rolling window with min_periods=1 will produce values from subsequent pings. This is simpler than forward-fill and avoids stale speed data.

4. **Percentile features for historical aggregates**
   - What we know: User left this to Claude's discretion. Median is locked as primary statistic.
   - What's unclear: Whether p25/p75 add signal beyond median.
   - Recommendation: Add p25 and p75 alongside median. Three features per aggregate (segment travel time p25/median/p75 and dwell time p25/median/p75) capture the spread of travel conditions. The added feature count is modest and XGBoost will ignore uninformative ones.

5. **Minimum observation threshold for historical NaN cutoff**
   - What we know: 6% of route-segment-hour-daytype combos have < 10 observations, 13% have < 30.
   - Recommendation: Use 10 as the minimum threshold. This balances data coverage (94% of combos retained) against statistical reliability. At 30, we lose 13% of combos.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `build_features.py`, `train_baseline.py`, `explode_rows.py`, `temporal_split.py`, `parse_timepoints.py` -- verified column names, data shapes, existing patterns
- Data inspection: `train.parquet` (1.21M rows, 26 columns), `timepoints.parquet` (1,958 entries, 22 routes), `stop_sequences.parquet` (202 stops, 163 segments)
- `baseline_metrics.json` -- Phase 3 baseline MAE 394.7s, SHAP rankings, per-route and per-bucket metrics
- [pandas 2.3.3 DataFrame.rolling()](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.rolling.html) -- time-based rolling window API
- [pandas 2.3.3 GroupBy.rolling()](https://pandas.pydata.org/docs/reference/api/pandas.core.groupby.DataFrameGroupBy.rolling.html) -- grouped rolling windows
- [XGBoost FAQ - Missing Values](https://xgboost.readthedocs.io/en/stable/faq.html) -- native NaN handling via sparsity-aware split finding

### Secondary (MEDIUM confidence)
- Ping density analysis: median 60s interval, p90 = 119s, 4% gaps > 5 min -- computed directly from training data
- Segment combo density: 2,550 unique (route, last_stop, hour, day_type) combos, median 228 observations per combo
- Route-timepoint overlap: 21 of 23 data routes have timepoint data, routes 27 and 235 lack coverage

### Tertiary (LOW confidence)
- Idle speed threshold of 2 mph -- common heuristic in transit literature, not verified against this specific dataset's speed distribution. May need tuning based on GPS-derived speed histogram.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - same libraries already in project, verified via codebase inspection
- Architecture: HIGH - patterns derived from actual codebase analysis and data structure verification
- Pitfalls: HIGH - identified from actual data analysis (ping density, timezone, segment density)
- Code examples: MEDIUM - pandas rolling API verified via official docs, haversine is standard formula, but exact groupby().rolling() droplevel behavior should be validated during implementation

**Research date:** 2026-02-04
**Valid until:** 2026-03-04 (stable domain, no rapidly changing dependencies)
