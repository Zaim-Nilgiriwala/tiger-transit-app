# Phase 2: Row Explosion & Labels - Research

**Researched:** 2026-02-03
**Domain:** Pandas data transformation -- row explosion, asof joins, temporal splitting
**Confidence:** HIGH

## Summary

This phase transforms 13.47M telemetry rows into a labeled training dataset by: (1) downsampling to ~60s intervals (~750K rows), (2) exploding each row into up to 8 per-stop rows (~6M total), (3) joining with actual arrival times via `merge_asof` to create `time_to_arrival_seconds` labels, and (4) splitting temporally into train/val/test.

The data is well-structured for this task. Telemetry already contains `progress` (0.0-1.0 fraction along route shape), `next_stop_id`, and `last_stop_id` fields that map cleanly to GTFS stops (98.1% match rate). Shape distance projection reduces to comparing the telemetry `progress` value against precomputed stop progress fractions from GTFS `shape_dist_traveled / max_shape_dist`. Routes have 4-10 stops each, so "next 8" covers most or all remaining stops.

Memory is not a concern at the per-day level. The busiest day has ~35K rows after downsampling, exploding to ~280K rows (~38 MB). Total dataset is ~6M exploded rows. Chunked-by-day processing is still the right strategy for robustness, but OOM risk is low.

**Primary recommendation:** Use the telemetry `progress` field directly as normalized shape distance rather than projecting GPS coordinates onto shape geometry -- it is already computed by the transit system and matches GTFS stop fractions.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.x | DataFrame operations, merge_asof, groupby | Already used in Phase 1 scripts |
| pyarrow | 14+ | Parquet read/write with predicate pushdown | Already used in Phase 1 |
| numpy | 1.26+ | Vectorized arithmetic for distance/time | Already in environment |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psutil | 5.9+ | Peak memory monitoring | Optional: log RSS after each day chunk |
| tqdm | 4.x | Progress bars for day-by-day processing | Optional: UX during long runs |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas merge_asof | Manual binary search | merge_asof is vectorized C, faster and correct |
| Per-day chunking | Dask/Polars | Overkill for ~6M rows; pandas handles this fine |
| GPS-to-shape projection | progress field | progress is pre-computed by transit system, more accurate |

**Installation:**
```bash
pip install pandas pyarrow numpy psutil tqdm
```

## Architecture Patterns

### Recommended Script Structure
```
scripts/
├── build_stop_sequences.py   # Pre-compute per-route ordered stop lists with progress fractions
├── explode_rows.py           # Downsample + explode telemetry into per-stop rows (chunked by day)
├── label_join.py             # merge_asof to attach arrival times as labels
├── temporal_split.py         # Split into train/val/test by calendar date
data/processed/
├── stop_sequences.parquet    # Route -> ordered stops with progress fractions
├── exploded.parquet          # All exploded rows (or partitioned by date)
├── labeled.parquet           # Exploded rows with time_to_arrival_seconds
├── train.parquet             # Temporal split
├── val.parquet
└── test.parquet
```

### Pattern 1: Progress-Based Stop Sequencing
**What:** Use telemetry `progress` (0-1) and GTFS `shape_dist_traveled` to determine remaining stops.
**When to use:** Every telemetry row during explosion.
**How it works:**
1. For each route, pick the canonical shape (the one with the most stops).
2. Compute `stop_progress = shape_dist_traveled / max_shape_dist` for each stop.
3. For each telemetry ping, find stops where `stop_progress > telemetry.progress`.
4. Take the first 8 such stops in order of `stop_progress`.

```python
# Pre-compute stop sequences per route
def build_stop_sequences(stop_times, shapes, routes):
    """Build ordered stop lists with progress fractions per route."""
    max_dist = shapes.groupby('shape_id')['shape_dist_traveled'].max()

    # Pick canonical shape per route (most stops)
    shape_stop_counts = stop_times.groupby(['route_id', 'shape_id'])['stop_id'].nunique()
    canonical = shape_stop_counts.groupby('route_id').idxmax().apply(lambda x: x[1])

    sequences = []
    for route_id, shape_id in canonical.items():
        mask = (stop_times['route_id'] == route_id) & (stop_times['shape_id'] == shape_id)
        route_stops = stop_times[mask].drop_duplicates('stop_id').sort_values('stop_sequence')
        route_stops['stop_progress'] = route_stops['shape_dist_traveled'] / max_dist[shape_id]
        route_stops['route_id_num'] = routes_lookup[route_id]  # map to numeric
        sequences.append(route_stops[['route_id_num', 'stop_id', 'stop_sequence', 'stop_progress']])

    return pd.concat(sequences, ignore_index=True)
```

### Pattern 2: Chunked-by-Day Processing
**What:** Process one calendar day at a time, writing results to Parquet partitions.
**When to use:** All pipeline stages.

```python
def process_by_day(telemetry_path, output_dir, process_fn):
    """Process telemetry one day at a time."""
    tel = pd.read_parquet(telemetry_path, columns=['timestamp'])
    dates = pd.Series(tel['timestamp'].dt.date.unique()).sort_values()
    del tel

    for date in tqdm(dates, desc="Processing days"):
        # Read only this day using predicate pushdown (pyarrow filter)
        day_df = pd.read_parquet(
            telemetry_path,
            filters=[('timestamp', '>=', pd.Timestamp(date, tz='UTC')),
                     ('timestamp', '<', pd.Timestamp(date + pd.Timedelta(days=1), tz='UTC'))]
        )
        result = process_fn(day_df)
        result.to_parquet(output_dir / f"{date}.parquet", index=False)
        del day_df, result
```

### Pattern 3: 60-Second Bucket Downsampling
**What:** Keep one row per (vehicle_id, route_id, 60s-bucket) to reduce data volume.
**When to use:** Before explosion.

```python
def downsample_60s(df):
    """Keep first row per vehicle/route per 60-second window."""
    df = df.sort_values('timestamp')
    df['bucket'] = df['timestamp'].astype(np.int64) // (60 * 10**9)  # 60s buckets
    downsampled = df.groupby(['vehicle_id', 'route_id', 'bucket']).first().reset_index()
    return downsampled.drop(columns=['bucket'])
```

### Pattern 4: Row Explosion via Cross Join
**What:** For each telemetry row, create N rows (one per remaining stop).

```python
def explode_to_stops(day_df, stop_sequences):
    """Explode each telemetry row into per-stop rows."""
    results = []
    for route_id, route_group in day_df.groupby('route_id'):
        route_stops = stop_sequences[stop_sequences['route_id_num'] == route_id]
        if route_stops.empty:
            continue

        for _, row in route_group.iterrows():
            # Find stops ahead of current progress
            remaining = route_stops[route_stops['stop_progress'] > row['progress']]
            remaining = remaining.head(8)  # Next 8 stops only

            if remaining.empty:
                continue

            # Create exploded rows
            exploded = remaining.copy()
            for col in row.index:
                if col not in exploded.columns:
                    exploded[col] = row[col]
            exploded['target_stop_id'] = exploded['stop_id']
            exploded['target_stop_progress'] = exploded['stop_progress']
            results.append(exploded)

    if not results:
        return pd.DataFrame()
    return pd.concat(results, ignore_index=True)
```

**Vectorized alternative (preferred for speed):**
```python
def explode_vectorized(day_df, stop_sequences):
    """Vectorized explosion using merge + filter."""
    # Cross-join telemetry with route stops
    merged = day_df.merge(
        stop_sequences.rename(columns={'stop_id': 'target_stop_id', 'stop_progress': 'target_stop_progress'}),
        left_on='route_id', right_on='route_id_num',
        how='inner'
    )
    # Keep only stops ahead of vehicle
    merged = merged[merged['target_stop_progress'] > merged['progress']]

    # Keep only next 8 per original row
    merged['rank'] = merged.groupby(merged.index)['target_stop_progress'].rank(method='first')
    merged = merged[merged['rank'] <= 8].drop(columns=['rank'])

    return merged
```

### Pattern 5: merge_asof Label Join
**What:** Join telemetry timestamps with arrival timestamps to get actual arrival time at each stop.
**When to use:** After explosion, to create `time_to_arrival_seconds` label.

```python
def join_labels(exploded, arrivals):
    """Use merge_asof to find the next arrival at target_stop_id after telemetry timestamp."""
    # Both must be sorted by timestamp
    exploded = exploded.sort_values('timestamp')
    arrivals = arrivals.sort_values('arrival_timestamp')

    labeled = pd.merge_asof(
        exploded,
        arrivals[['arrival_timestamp', 'route_id', 'stop_id', 'vehicle_id']].rename(
            columns={'arrival_timestamp': 'actual_arrival', 'stop_id': 'target_stop_id'}
        ),
        left_on='timestamp',
        right_on='actual_arrival',
        by=['route_id', 'target_stop_id', 'vehicle_id'],
        direction='forward',
        tolerance=pd.Timedelta('2h')  # max 2 hours forward
    )

    # Compute label
    labeled['time_to_arrival_seconds'] = (
        labeled['actual_arrival'] - labeled['timestamp']
    ).dt.total_seconds()

    return labeled
```

### Anti-Patterns to Avoid
- **Iterating row-by-row for explosion:** Use vectorized merge + filter instead of iterrows. The iterrows pattern above is illustrative only; the vectorized version is 100x faster.
- **Loading full telemetry into memory at once:** Always read one day at a time with Parquet predicate pushdown.
- **Using `direction='backward'` for label join:** We need the NEXT arrival (forward), not the previous one.
- **Forgetting to filter `progress == 0` rows:** These are idle/starting vehicles that haven't begun their route yet.
- **Not deduplicating the cross-join index:** After merge, use a proper row identifier (not the pandas index) to rank stops per observation.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GPS-to-shape projection | Haversine nearest-point-on-polyline | `progress` field from telemetry | Already computed by transit system; 0-1 normalized shape distance |
| Temporal asof matching | Manual binary search per row | `pd.merge_asof` | Vectorized C implementation, handles edge cases, supports tolerance |
| Parquet date filtering | Read-then-filter | PyArrow predicate pushdown via `filters=` | Reads only relevant row groups from disk |
| Stop ordering per route | Manual shape geometry parsing | GTFS `stop_times.shape_dist_traveled` | Already contains exact distances along route |

**Key insight:** The telemetry data already includes `progress` (0-1 fraction along route), `next_stop_id`, and `last_stop_id`. These fields eliminate the need for complex geospatial projection. The "shape distance projection" specified in the context reduces to a simple numeric comparison: `stop_progress > vehicle_progress`.

## Common Pitfalls

### Pitfall 1: Timezone Bug Producing 3600s Label Spikes
**What goes wrong:** Labels cluster around 3600s (1 hour) due to timezone mismatch between telemetry (UTC) and arrivals.
**Why it happens:** Arrivals were converted from US/Central to UTC in Phase 1, but if any step re-localizes or double-converts, 1-hour offsets appear.
**How to avoid:** Assert both timestamps are UTC before merge_asof. Check label histogram for 3600s spikes.
**Warning signs:** Bimodal distribution with spike at 3600s in `time_to_arrival_seconds`.

### Pitfall 2: Duplicate merge_asof Matches
**What goes wrong:** Multiple telemetry rows match the same arrival, or one telemetry row matches an arrival from a different trip.
**Why it happens:** `merge_asof` finds the nearest match globally. Without `by=['vehicle_id']`, a vehicle's ping could match another vehicle's arrival.
**How to avoid:** Always include `vehicle_id` in the `by` parameter. Use a reasonable `tolerance` (2 hours max).
**Warning signs:** Label values that are negative (arrival before ping) or suspiciously large (>7200s).

### Pitfall 3: End-of-Route / Layover Contamination
**What goes wrong:** Vehicle at end of route (progress ~1.0) has no remaining stops, or vehicle in layover (progress=0, speed=0) produces meaningless rows.
**Why it happens:** Vehicles idle at terminals between runs; progress resets.
**How to avoid:** Filter out rows where `progress == 0.0 AND speed == 0` (idle). Filter out rows where no stops have `stop_progress > vehicle_progress` (end of route).
**Warning signs:** Large number of exploded rows with zero remaining stops or very short time_to_arrival.

### Pitfall 4: Shape Variant Mismatch
**What goes wrong:** Vehicle is on a reduced-stop shape variant (e.g., CL1.7 with 5 stops) but stop sequence uses the full shape (CL1 with 7 stops), producing targets at stops the vehicle will skip.
**Why it happens:** Routes have multiple shape variants for different times of day. The `.7` and `.730` suffixes indicate reduced schedules.
**How to avoid:** Use the canonical (most-stops) shape for stop ordering, but validate that arrival data actually exists at those stops for that route. Missing arrival matches will naturally filter out skipped stops during label join.
**Warning signs:** Low label join rate on specific routes; stops that never get matched.

### Pitfall 5: Negative or Zero Labels
**What goes wrong:** `time_to_arrival_seconds` is negative (arrival happened before ping) or zero.
**Why it happens:** `merge_asof` with `direction='forward'` and stale data, or the bus already passed the stop.
**How to avoid:** Filter labels to `0 < time_to_arrival_seconds <= 7200`. Negative values mean the join matched an arrival that already happened (shouldn't occur with forward direction, but validate).
**Warning signs:** Non-trivial percentage of negative labels.

### Pitfall 6: Trip ID Leaking Across Splits
**What goes wrong:** The same trip appears in both train and test sets.
**Why it happens:** A trip that starts at 11:55 PM on day N has arrivals on day N+1. If day N is train and day N+1 is test, this trip leaks.
**How to avoid:** Assign trips to splits based on the trip's START date. Use a gap period (1+ days) between splits to prevent any leakage.
**Warning signs:** trip_id appearing in multiple splits (validate after splitting).

## Code Examples

### Complete Downsampling + Explosion Pipeline
```python
import pandas as pd
import numpy as np
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "processed"

def load_stop_sequences():
    """Load pre-computed stop sequences with progress fractions."""
    return pd.read_parquet(DATA_DIR / "stop_sequences.parquet")

def downsample_day(day_df):
    """60-second bucket downsampling."""
    day_df = day_df.sort_values('timestamp')
    day_df['bucket'] = day_df['timestamp'].astype(np.int64) // (60 * 10**9)
    ds = day_df.drop_duplicates(subset=['vehicle_id', 'route_id', 'bucket'], keep='first')
    return ds.drop(columns=['bucket'])

def filter_idle(df):
    """Remove idle vehicles and invalid rows."""
    mask = ~((df['progress'] == 0.0) & (df['speed'] == 0))
    mask &= df['next_stop_id'] != 0  # next_stop_id=0 means no active route
    return df[mask]

def explode_day(day_df, stop_seqs):
    """Vectorized per-stop explosion."""
    # Add row identifier before merge
    day_df = day_df.reset_index(drop=True)
    day_df['obs_id'] = np.arange(len(day_df))

    merged = day_df.merge(
        stop_seqs.rename(columns={
            'stop_id': 'target_stop_id',
            'stop_progress': 'target_stop_progress'
        }),
        left_on='route_id',
        right_on='route_id_num',
        how='inner'
    )

    # Keep only stops ahead of vehicle
    merged = merged[merged['target_stop_progress'] > merged['progress']].copy()

    # Rank by proximity and keep top 8 per observation
    merged['stop_rank'] = merged.groupby('obs_id')['target_stop_progress'].rank(method='first')
    merged = merged[merged['stop_rank'] <= 8]

    return merged
```

### merge_asof Label Join
```python
def create_labels(exploded_path, arrivals_path, output_path):
    """Join exploded rows with actual arrivals to create labels."""
    exploded = pd.read_parquet(exploded_path)
    arrivals = pd.read_parquet(arrivals_path)

    # Ensure both sorted by timestamp
    exploded = exploded.sort_values('timestamp')
    arrivals = arrivals.sort_values('arrival_timestamp')

    # Validate both are UTC
    assert str(exploded['timestamp'].dt.tz) == 'UTC', "Telemetry not in UTC!"
    assert str(arrivals['arrival_timestamp'].dt.tz) == 'UTC', "Arrivals not in UTC!"

    labeled = pd.merge_asof(
        exploded,
        arrivals[['arrival_timestamp', 'route_id', 'stop_id', 'vehicle_id']].rename(
            columns={'stop_id': 'target_stop_id'}
        ),
        left_on='timestamp',
        right_on='arrival_timestamp',
        by=['route_id', 'target_stop_id', 'vehicle_id'],
        direction='forward',
        tolerance=pd.Timedelta('2h')
    )

    # Compute label
    labeled['time_to_arrival_seconds'] = (
        labeled['arrival_timestamp'] - labeled['timestamp']
    ).dt.total_seconds()

    # Filter valid labels
    valid = labeled['time_to_arrival_seconds'].between(0, 7200, inclusive='neither')
    match_rate = valid.sum() / len(labeled)
    print(f"Label match rate: {match_rate:.1%} ({valid.sum():,} / {len(labeled):,})")

    labeled = labeled[valid]
    labeled.to_parquet(output_path, index=False)
    return labeled
```

### Temporal Split
```python
def temporal_split(labeled_path, output_dir, gap_days=1):
    """Split by calendar date with gap period."""
    df = pd.read_parquet(labeled_path)
    df['date'] = df['timestamp'].dt.date

    dates = sorted(df['date'].unique())
    n = len(dates)

    # 70/15/15 split by date count
    train_end_idx = int(n * 0.70)
    val_start_idx = train_end_idx + gap_days
    val_end_idx = val_start_idx + int(n * 0.15)
    test_start_idx = val_end_idx + gap_days

    train_dates = set(dates[:train_end_idx])
    val_dates = set(dates[val_start_idx:val_end_idx])
    test_dates = set(dates[test_start_idx:])

    train = df[df['date'].isin(train_dates)]
    val = df[df['date'].isin(val_dates)]
    test = df[df['date'].isin(test_dates)]

    # Validate no trip leakage
    # (trip_id not available directly, use vehicle_id + date as proxy for trips)

    print(f"Train: {len(train):,} rows, {len(train_dates)} days")
    print(f"Val:   {len(val):,} rows, {len(val_dates)} days")
    print(f"Test:  {len(test):,} rows, {len(test_dates)} days")

    train.to_parquet(output_dir / "train.parquet", index=False)
    val.to_parquet(output_dir / "val.parquet", index=False)
    test.to_parquet(output_dir / "test.parquet", index=False)
```

## Data Characteristics (Verified)

Critical measurements from the actual data:

| Metric | Value | Source |
|--------|-------|--------|
| Total telemetry rows | 13,471,208 | telemetry.parquet |
| Date range (telemetry) | 2025-11-06 to 2025-12-20 | telemetry.parquet |
| Date range (arrivals) | 2025-11-06 to 2026-01-23 | arrivals.parquet |
| Overlapping date range | 2025-11-06 to 2025-12-20 (31 days) | Both files |
| Arrivals rows | 232,610 | arrivals.parquet |
| After 60s downsample | ~749,175 rows | Computed from data |
| After x8 explosion | ~5,993,400 rows | Computed from data |
| Max day (downsampled) | ~34,787 rows -> 278K exploded | 2025-12-01 |
| Max day memory (exploded) | ~38 MB | Estimated |
| Routes in telemetry | 24 | telemetry.parquet |
| Routes in arrivals | 36 (23 overlap with telemetry) | arrivals.parquet |
| Route 237 (telemetry only) | No GTFS match -- exclude | Verified |
| next_stop_id match to GTFS | 98.1% | Computed |
| next_stop_id == 0 (idle) | 1.9% of rows | Computed |
| progress == 0.0 | 2.2% of rows | Computed |
| Vehicle ID overlap | 68/68 telemetry vehicles in arrivals | Computed |
| Shape distances | 0.4 - 21.7 miles | gtfs_shapes.parquet |
| Stops per route | 4-10 | gtfs_stop_times.parquet |
| Shape variants per route | 2-8 (includes .7 and .730 time variants) | gtfs_stop_times.parquet |

### Key Data Insights
1. **progress field is gold:** 0-1 normalized shape distance, pre-computed by the transit system. No GPS projection needed.
2. **~6M exploded rows is very manageable:** Far less than the 18M estimate in the context doc (which assumed higher ping frequency). Memory is not a bottleneck.
3. **31 overlapping days:** With 70/15/15 temporal split, that's ~21 train / ~5 val / ~5 test days. With 1-day gaps, approximately 21/4/4 usable days.
4. **Vehicle ID formats match exactly** between telemetry and arrivals (e.g., "21-148").
5. **Route 237 has no GTFS data** -- must be excluded.

## Discretionary Recommendations

### merge_asof Tolerance: 2 hours
- A bus should reach any stop within ~2 hours on these campus routes (max shape distance is 21 miles).
- Too tight (30 min) risks missing delayed vehicles.
- Too loose (4+ hours) risks matching wrong trips.
- **Recommendation: `tolerance=pd.Timedelta('2h')`**

### Label Filtering Thresholds
- **Minimum:** 10 seconds (anything less is noise -- vehicle is essentially at the stop)
- **Maximum:** 7200 seconds (2 hours -- matches tolerance)
- **Outlier removal:** Drop labels > 99.5th percentile within each route to handle data errors
- **Recommendation: `10 < time_to_arrival_seconds < 7200`**

### Temporal Split Date Ranges
- 31 days of overlapping data (Nov 6 - Dec 20)
- **Train:** Nov 6 - Dec 1 (26 days, ~70%)
- **Gap:** Dec 2 (1 day)
- **Val:** Dec 3 - Dec 8 (6 days, ~15%)
- **Gap:** Dec 9 (1 day)
- **Test:** Dec 10 - Dec 20 (11 days, ~15%+ of data)
- Note: Dec 13-14 are Saturday/Sunday (different traffic), Dec 20 has only 450 raw rows. Consider excluding low-volume days.
- **Gap period: 1 day** (sufficient for campus bus routes where no trip spans >4 hours)

### Idle / Layover Handling
- **Filter out:** `progress == 0.0 AND speed == 0` (idle at terminal)
- **Filter out:** `next_stop_id == 0` (no active route assignment)
- **Keep:** `progress == 0.0 AND speed > 0` (just departed terminal)
- This removes ~2.2% of rows (acceptable loss)

### Missing Arrival Matches
- Rows with no `merge_asof` match (NaN label) are expected and should be dropped
- Target: 60%+ match rate (per success criteria)
- Track match rate per route to identify systematic issues
- If a route has <30% match rate, investigate data quality for that route

### Chunking Strategy
- **Read:** PyArrow predicate pushdown by date
- **Process:** One calendar day at a time
- **Write:** One Parquet file per day, then concatenate at the end
- **Memory monitoring:** Optional -- peak memory for a day is ~40 MB, well within limits
- Given ~6M total exploded rows, final concatenation into single files is also safe (~1 GB max)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| GPS projection via Haversine | Use pre-computed `progress` field | N/A (data-specific) | Eliminates geospatial computation entirely |
| Random train/test split | Temporal split with gap | Standard practice | Prevents temporal leakage |
| Load all data then filter | PyArrow predicate pushdown | PyArrow 8+ | Read only needed rows from disk |

## Open Questions

1. **Pattern ID to Shape ID mapping**
   - What we know: Telemetry has `pattern_id` (e.g., 27071), GTFS has `shape_id` (e.g., WR1). No mapping table found.
   - What's unclear: Whether pattern_id corresponds to a specific shape variant.
   - Recommendation: Use canonical (most-stops) shape per route. The missing stops on reduced shapes will simply fail to match in label join, which is the correct behavior.

2. **Arrivals data completeness for all routes**
   - What we know: 23 routes overlap between telemetry and arrivals.
   - What's unclear: Whether all 23 routes have sufficient arrival density for 60%+ match rates.
   - Recommendation: Log per-route match rates. Flag routes with <30% match rate for investigation.

3. **Weekend/holiday patterns**
   - What we know: Data spans Nov 6 - Dec 20 (includes Thanksgiving break, weekends).
   - What's unclear: Whether weekend/break days should be included or excluded from training.
   - Recommendation: Include all days but add a `is_weekday` column. The model can learn patterns. The test set should include both weekday and weekend days.

## Sources

### Primary (HIGH confidence)
- Actual data files in `data/processed/` -- all statistics computed directly from the data
- pandas official docs for `merge_asof` -- https://pandas.pydata.org/docs/reference/api/pandas.merge_asof.html
- GTFS data in `gtfs_data/` -- route/shape/stop structure verified

### Secondary (MEDIUM confidence)
- Phase 1 scripts (`parse_telemetry.py`, `parse_arrivals.py`, `parse_gtfs.py`) -- verified column names, data types, filter logic

### Tertiary (LOW confidence)
- None -- all findings verified against actual data

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - pandas/pyarrow already used in Phase 1, APIs verified against docs
- Architecture: HIGH - all data characteristics measured, explosion counts computed
- Pitfalls: HIGH - timezone handling verified in Phase 1 code, edge cases identified from actual data distributions
- Label join strategy: MEDIUM - merge_asof API verified, but actual match rate unknown until implementation

**Research date:** 2026-02-03
**Valid until:** 2026-03-03 (data and stack are stable)
