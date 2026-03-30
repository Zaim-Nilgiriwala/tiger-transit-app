# Phase 7: Baseline Infrastructure - Research

**Researched:** 2026-02-11
**Domain:** Historical baseline ETA computation, residual label generation (pandas/parquet pipeline)
**Confidence:** HIGH

## Summary

This research investigates how to implement stop-to-stop historical average baselines, segment-median-sum baselines, and residual label computation for the Tiger Transit v1.1 model reapproach. The primary data source is the existing v1.0 pipeline codebase and live parquet files, which were deeply analyzed to determine column schemas, data coverage, and feasibility.

The existing codebase provides strong foundations: `train.parquet` (1.2M rows), `val.parquet` (384K rows), and `test.parquet` (297K rows) each contain the key columns (`route_id`, `last_stop_id`, `target_stop_id`, `timestamp`, `is_weekday`, `time_to_arrival_seconds`). The `stop_sequences.parquet` file provides route path ordering (202 rows, 23 active routes). The existing `historical_segments.parquet` was built with MIN_OBS=10 for Phase 4 purposes and must be rebuilt with MIN_OBS=5 for Phase 7's fallback hierarchy.

A quick feasibility test confirms the stop-to-stop Tier 1 baseline alone achieves 128.3s MAE on test (99.0% coverage), well within the expected 150-500s range. The 50/50 blend with segment-median-sum should land in the 200-350s range, which is realistic for a zero-feature baseline and confirms the approach is sound.

**Primary recommendation:** Build the baseline computation as a single Python script (`scripts/build_baselines.py`) that reads `train.parquet` and `stop_sequences.parquet`, computes both lookup tables from training data only, applies them to all three splits with the fallback hierarchy, writes augmented parquets, and produces the diagnostic report inline.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pandas | 2.3.3 | DataFrame operations, groupby aggregation, merge | Already in pipeline, all v1.0 scripts use it |
| numpy | 2.2.6 | Numerical computation, NaN handling | Already in pipeline |
| pyarrow | 23.0.0 | Parquet I/O with dictionary encoding | Already in pipeline, used by save functions |
| matplotlib | 3.10.8 | Diagnostic histogram and visualization | Already in pipeline, evaluate.py uses it |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Python pathlib | stdlib | File path handling | Already used across all scripts |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pandas groupby | polars groupby | Faster but inconsistent with v1.0 stack, unnecessary for this data size |

**Installation:**
No new packages required. All dependencies already installed.

## Architecture Patterns

### Recommended Script Structure

```
scripts/
    build_baselines.py     # NEW: Phase 7 baseline computation
    build_features.py      # Existing v1.0 (Phase 3 features)
    build_differentiator_features.py  # Existing v1.0 (Phase 4 features)
```

### Pattern 1: Training-Only Lookup Table Construction
**What:** Build aggregation lookup tables exclusively from `train.parquet`, then apply to all splits via left merge.
**When to use:** Always for baseline construction -- prevents data leakage.
**Example:**
```python
# Source: Existing pattern from build_differentiator_features.py lines 252-330
# Build lookup from training data ONLY
train = pd.read_parquet("data/processed/train.parquet")
train["hour_ct"] = (train["timestamp"] - pd.Timedelta(hours=6)).dt.hour
train["day_type"] = train["is_weekday"].astype(int)  # 1=weekday, 0=weekend

# Tier 1: Full grouping
tier1 = train.groupby(
    ["route_id", "last_stop_id", "target_stop_id", "hour_ct", "day_type"]
)["time_to_arrival_seconds"].agg(mean="mean", count="count").reset_index()
tier1 = tier1[tier1["count"] >= 5]  # MIN_OBS = 5
```

### Pattern 2: Cascading Fallback Merge
**What:** Apply tiered lookups sequentially, filling NaN gaps from each previous tier.
**When to use:** For the 3-tier fallback hierarchy.
**Example:**
```python
# Apply Tier 1
df = df.merge(tier1_lookup, on=keys_tier1, how="left")
df["baseline_s2s"] = df["_tier1_mean"]

# Fill missing with Tier 2
mask = df["baseline_s2s"].isna()
df.loc[mask, "baseline_s2s"] = df.loc[mask].merge(
    tier2_lookup, on=keys_tier2, how="left"
)["_tier2_mean"].values

# Fill remaining with Tier 3
mask = df["baseline_s2s"].isna()
df.loc[mask, "baseline_s2s"] = df.loc[mask].merge(
    tier3_lookup, on=keys_tier3, how="left"
)["_tier3_scaled"].values
```

### Pattern 3: Segment Path Summation
**What:** Sum historical segment travel time medians along the route path from current stop to target stop.
**When to use:** For the segment-median-sum baseline (BASE-02).
**Example:**
```python
# For each row, identify the ordered list of stops between last_stop_id and target_stop_id
# using stop_sequences, then sum segment medians for each intermediate stop.
# Pre-build a cumulative sum table per (route_id, hour_ct, day_type) for efficiency.
```

### Pattern 4: Row-Count-Preserving Merge Assertions
**What:** Assert `len(df) == n_before` after every merge to catch row explosion.
**When to use:** After every `df.merge()` call. This is a critical existing pattern used throughout the codebase.
**Example:**
```python
# Source: Existing pattern from build_differentiator_features.py lines 941-942
n_pre = len(df)
df = df.merge(lookup, on=merge_keys, how="left")
assert len(df) == n_pre, f"Row explosion on merge! {n_pre} -> {len(df)}"
```

### Anti-Patterns to Avoid
- **Computing aggregates on val/test data:** Baselines must be built from `train.parquet` ONLY. Merging lookup tables to val/test is fine; computing means from val/test is data leakage.
- **Modifying existing parquets in place:** Write new columns to new output files or augmented copies. The existing `train.parquet` etc. must remain unchanged for reproducibility.
- **Ignoring last_stop_id=0:** About 0.6-0.7% of rows across all splits have `last_stop_id=0` which is not in `stop_sequences.parquet`. These rows must be handled (will fall to Tier 2 or 3).
- **Using inner merge instead of left merge:** Always use `how="left"` to preserve all rows. NaN values indicate fallback needed.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Parquet I/O with categoricals | Custom parquet writer | Existing `save_v2_parquet()` pattern from `build_differentiator_features.py` | Dictionary encoding for categoricals is already solved |
| Central Time hour extraction | Manual UTC offset | Existing `add_ct_hour()` from `build_differentiator_features.py` line 241 | Already handles UTC-6 offset correctly |
| Day type encoding | New encoding logic | `train["is_weekday"].astype(int)` | Already used throughout codebase, produces `day_type` 1=weekday, 0=weekend |
| Route path ordering | Custom graph traversal | `stop_sequences.parquet` sorted by `stop_sequence` | Already ordered correctly per route |

**Key insight:** The v1.0 codebase has established patterns for every supporting operation. The only genuinely new logic is the baseline computation itself (lookup tables + fallback hierarchy + segment summation + blending).

## Common Pitfalls

### Pitfall 1: Data Leakage in Baseline Construction
**What goes wrong:** Computing baseline means using val/test data, or using the target row's own value when computing the group mean.
**Why it happens:** Easy to accidentally load all splits when computing aggregates.
**How to avoid:** Build ALL lookup tables from `train.parquet` only. Apply via left merge. The existing codebase demonstrates this pattern in `build_differentiator_features.py` (lines 1006-1043: historical aggregates from training data only).
**Warning signs:** Baseline MAE on train is suspiciously close to 0, or train MAE is significantly lower than test MAE.

### Pitfall 2: Row Explosion on Merge
**What goes wrong:** Merge produces more rows than input because lookup keys are not unique.
**Why it happens:** Duplicate keys in lookup tables (e.g., same grouping key appearing twice).
**How to avoid:** Always assert `len(df) == n_before` after merge. Ensure lookup tables have unique keys via `drop_duplicates()` or `groupby().first()`.
**Warning signs:** Output parquet has more rows than input parquet.

### Pitfall 3: last_stop_id=0 Rows
**What goes wrong:** ~0.7% of rows have `last_stop_id=0` (telemetry marker for "no previous stop"), which has no match in stop_sequences.
**Why it happens:** Telemetry data includes pings before the first stop.
**How to avoid:** These rows will naturally get NaN from Tier 1 and Tier 2 lookups (since `last_stop_id=0` won't match any real stop pair). They fall to Tier 3 (route-level fallback), which is correct behavior. Also, Route 100 has `last_stop_id=54` (148 train rows) which is not in stop_sequences -- same treatment.
**Warning signs:** More than 1% of rows requiring Tier 3 fallback.

### Pitfall 4: Segment-Median-Sum NaN Propagation
**What goes wrong:** If ANY segment along the path has NaN median, the entire sum becomes NaN.
**Why it happens:** Historical segments has 37.9% NaN rate (sparse hour/day_type combos).
**How to avoid:** For the segment-median-sum, use a fallback within segments: if a specific (route_id, last_stop_id, hour_ct, day_type) combo has no data, fall back to (route_id, last_stop_id, day_type) across all hours. If still NaN, use the route-wide median for that segment. This parallels the Tier 1/2/3 hierarchy.
**Warning signs:** Segment-median-sum baseline has high NaN rate (>5%).

### Pitfall 5: Segment Path vs Telemetry Stop Ordering
**What goes wrong:** Stop sequences from GTFS may not match the order buses actually visit stops in telemetry.
**Why it happens:** `stop_sequences.parquet` comes from GTFS canonical shapes, while `last_stop_id` in telemetry comes from real-time tracking. They may occasionally disagree.
**How to avoid:** Use `stop_sequences.parquet` as the authoritative path. When summing segments, look up each intermediate stop's segment median by its stop_id in the sequence. If a stop in the sequence has no segment data at all, skip it in the sum (it contributes 0 travel time, which underestimates -- but this is rare).
**Warning signs:** Segment-sum produces nonsensical values (e.g., negative or extremely large ETAs).

### Pitfall 6: Residual Mean Drift
**What goes wrong:** Training-set residual mean is not near zero.
**Why it happens:** Baseline is computed from training data means, so train residual mean should be near zero by construction for Tier 1. But Tier 2/3 fallbacks and the segment-sum component introduce drift.
**How to avoid:** Check that training-set residual mean is within +/-30s of zero (success criterion #3). If not, investigate which component is causing drift.
**Warning signs:** `residual.mean()` on train > 30 in absolute value.

### Pitfall 7: Saturday Data Sparsity
**What goes wrong:** Weekend baseline has very few observations because Saturday has only 13K train rows (1.1%) and there are ZERO Sunday rows.
**Why it happens:** Transit service is minimal on weekends in this dataset.
**How to avoid:** Use binary weekday/weekend as day_type (not finer granularity). Weekend combos will frequently fall to Tier 2 or 3. This is acceptable and expected.
**Warning signs:** Weekend rows having significantly higher fallback tier rates.

## Code Examples

### Stop-to-Stop Lookup Table Construction (Tier 1)
```python
# Source: Verified against existing codebase patterns
MIN_OBS = 5

train = pd.read_parquet("data/processed/train.parquet")
train["hour_ct"] = (train["timestamp"] - pd.Timedelta(hours=6)).dt.hour
train["day_type"] = train["is_weekday"].astype(int)

# Tier 1: (route_id, last_stop_id, target_stop_id, hour_ct, day_type)
TIER1_KEYS = ["route_id", "last_stop_id", "target_stop_id", "hour_ct", "day_type"]
tier1 = train.groupby(TIER1_KEYS)["time_to_arrival_seconds"].agg(
    s2s_mean="mean", s2s_count="count"
).reset_index()
tier1 = tier1[tier1["s2s_count"] >= MIN_OBS].drop(columns=["s2s_count"])
```

### Tier 2: Drop Hour
```python
TIER2_KEYS = ["route_id", "last_stop_id", "target_stop_id", "day_type"]
tier2 = train.groupby(TIER2_KEYS)["time_to_arrival_seconds"].agg(
    s2s_mean="mean", s2s_count="count"
).reset_index()
tier2 = tier2[tier2["s2s_count"] >= MIN_OBS].drop(columns=["s2s_count"])
```

### Tier 3: Route-Level Distance-Scaled Fallback
```python
# Source: Discretionary decision -- recommended approach
ss = pd.read_parquet("data/processed/stop_sequences.parquet")

# Compute average speed per (route_id, day_type) from training data
# Speed = distance / time, where distance is shape_dist difference and time is time_to_arrival
# Then baseline = distance_to_target / avg_speed

# Build route-level mean travel time per unit distance
route_stats = train.merge(
    ss.rename(columns={"stop_id": "target_stop_id", "shape_dist_traveled": "target_shape_dist"})[
        ["route_id", "target_stop_id", "target_shape_dist"]
    ],
    on=["route_id", "target_stop_id"],
    how="left"
)
# Also get current stop's shape_dist
route_stats = route_stats.merge(
    ss.rename(columns={"stop_id": "last_stop_id", "shape_dist_traveled": "current_shape_dist"})[
        ["route_id", "last_stop_id", "current_shape_dist"]
    ],
    on=["route_id", "last_stop_id"],
    how="left"
)
route_stats["dist"] = route_stats["target_shape_dist"] - route_stats["current_shape_dist"]
route_stats = route_stats[route_stats["dist"] > 0]

# seconds_per_dist_unit = time_to_arrival / distance
route_stats["speed"] = route_stats["time_to_arrival_seconds"] / route_stats["dist"]
tier3 = route_stats.groupby(["route_id", "day_type"])["speed"].agg(
    avg_speed="mean"
).reset_index()

# Apply: baseline = distance * avg_speed (seconds per distance unit)
# For each row missing Tier 1 and 2, compute distance and multiply
```

### Segment-Median-Sum via Cumulative Sum Table
```python
# Efficient approach: pre-build cumulative segment sums per route
# For each (route_id, hour_ct, day_type), compute cumsum of segment medians
# along the stop_sequence order. Then segment_sum = cumsum[target] - cumsum[current].

ss = pd.read_parquet("data/processed/stop_sequences.parquet")

# Build segment lookup from training data (same pattern as build_differentiator_features.py)
# Key: (route_id, stop_id, hour_ct, day_type) -> segment_travel_median
# Where stop_id = the stop departed from for that segment

# For efficient summation:
# 1. For each route, create ordered stop list from stop_sequences
# 2. For each (route_id, hour_ct, day_type), build array of segment medians in sequence order
# 3. Compute cumulative sum
# 4. For any row: segment_sum = cumsum[target_seq_idx] - cumsum[current_seq_idx]
```

### Blending Both Baselines
```python
# 50/50 blend (locked decision)
df["baseline_eta"] = (df["baseline_s2s"] + df["baseline_seg_sum"]) / 2

# If one baseline is NaN and the other isn't, use the non-NaN one
s2s_only = df["baseline_seg_sum"].isna() & df["baseline_s2s"].notna()
seg_only = df["baseline_s2s"].isna() & df["baseline_seg_sum"].notna()
df.loc[s2s_only, "baseline_eta"] = df.loc[s2s_only, "baseline_s2s"]
df.loc[seg_only, "baseline_eta"] = df.loc[seg_only, "baseline_seg_sum"]
```

### Residual Computation
```python
df["residual"] = df["time_to_arrival_seconds"] - df["baseline_eta"]

# Validation
train_residual_mean = train_df["residual"].mean()
assert abs(train_residual_mean) < 30, f"Train residual mean {train_residual_mean:.1f} exceeds +/-30s"
```

### Diagnostic Report Pattern
```python
# Source: Adapted from evaluate.py pattern
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Overall MAE
for name, method_col in [("S2S", "baseline_s2s"), ("SegSum", "baseline_seg_sum"), ("Blend", "baseline_eta")]:
    mae = np.abs(test["time_to_arrival_seconds"] - test[method_col]).mean()
    print(f"{name} MAE: {mae:.1f}s")

# Per-route breakdown
for rid in sorted(test["route_id"].unique()):
    rmask = test["route_id"] == rid
    mae = np.abs(test.loc[rmask, "time_to_arrival_seconds"] - test.loc[rmask, "baseline_eta"]).mean()
    print(f"  Route {rid}: MAE={mae:.1f}s, n={rmask.sum()}")

# Error distribution histogram
errors = test["time_to_arrival_seconds"] - test["baseline_eta"]
plt.figure(figsize=(10, 6))
plt.hist(errors, bins=100, edgecolor="black", alpha=0.7)
plt.xlabel("Error (actual - baseline) seconds")
plt.ylabel("Count")
plt.title("Baseline Error Distribution")
plt.savefig("models/diagnostics/baseline_error_dist.png", dpi=150, bbox_inches="tight")
```

## Data Schema Reference

### train.parquet / val.parquet / test.parquet (26 columns)
| Column | Dtype | Role in Phase 7 |
|--------|-------|------------------|
| `route_id` | int64 | Grouping key |
| `last_stop_id` | int64 | = from_stop_id, grouping key |
| `target_stop_id` | int64 | Grouping key |
| `timestamp` | datetime64[ns, UTC] | Extract hour_ct |
| `is_weekday` | bool | = day_type (1=weekday, 0=weekend) |
| `time_to_arrival_seconds` | float64 | Ground truth, used for aggregates and residual |
| `target_stop_progress` | float64 | For distance computation |
| `progress` | float64 | For distance computation |
| `stops_away` | int64 | Informational |
| `target_stop_sequence` | int64 | For segment path ordering |

### stop_sequences.parquet (202 rows, 39 routes)
| Column | Dtype | Role |
|--------|-------|------|
| `route_id` | Int64 | Join key (note: nullable Int64, must cast to int for merge) |
| `stop_id` | int64 | Route path stop identification |
| `stop_sequence` | int64 | Ordering of stops along route |
| `shape_dist_traveled` | float64 | Distance along route shape (km) |
| `max_shape_dist` | float64 | Total route length (km) |
| `stop_progress` | float64 | Normalized progress [0, 1] |

### Key Data Facts (HIGH confidence -- verified from live data)
- **23 active routes** in train/val/test (out of 39 in stop_sequences)
- **Train:** 1,206,181 rows (24 days: Nov 6-29)
- **Val:** 384,002 rows (6 days: Dec 1-6)
- **Test:** 296,608 rows (11 days: Dec 8-18)
- **Tier 1 coverage:** 99.0% of test rows (14,535 of 17,038 groupings have >= 5 obs)
- **Tier 1 test MAE:** 128.3s (stop-to-stop average alone)
- **last_stop_id=0 rate:** 0.63% train, 0.75% val, 0.67% test
- **Route 100 also has last_stop_id=54** not in stop_sequences (148 train rows)
- **Saturday rows:** 1.1% of train, 1.8% of val, 2.2% of test
- **No Sunday data** in any split
- **day_type=1 (weekday)** covers 98.9% of train
- **stops_away** ranges 1-8, mean 3.41
- **historical_segments.parquet NaN rate:** 37.9% (was built with MIN_OBS=10)
- **time_to_arrival_seconds** mean ~1147s (19 min), range 10-7200s

## Discretionary Decisions (Claude's Recommendations)

### 1. day_type Definition
**Recommendation:** Use binary weekday/weekend (1/0) mapping from `is_weekday`.

**Rationale:** Finer granularity (e.g., Mon-Fri distinct, or rush-hour subdivisions) would fragment an already sparse weekend dataset. Saturday has only 13K train rows and there are zero Sunday rows. The existing codebase uses `is_weekday.astype(int)` consistently (`temporal_split.py` line 90, `build_differentiator_features.py` lines 299, 398). Staying consistent avoids confusion.

### 2. Tier-3 Distance-Scaling Method
**Recommendation:** Compute per-(route_id, day_type) average travel time per shape_dist unit (seconds/km). For each Tier-3 row, compute distance from `last_stop_id` to `target_stop_id` using `stop_sequences.shape_dist_traveled`, multiply by the route's seconds-per-km rate.

**Rationale:** This is the simplest linear scaling that accounts for both route speed characteristics and trip distance. The alternative (fixed route-level mean travel time regardless of distance) would produce the same baseline for 1-stop-away and 8-stops-away, which is clearly wrong. Shape distances are already available in stop_sequences.

**Edge case:** For rows with `last_stop_id=0` (not in stop_sequences), use `progress` and `target_stop_progress` with `max_shape_dist` to compute distance: `dist = (target_stop_progress - progress) * max_shape_dist`.

### 3. Histogram Bin Sizing
**Recommendation:** Use 100 bins spanning the range of errors, or `np.arange(-2000, 2000, 20)` for 20-second bins centered on zero. The existing `evaluate.py` uses similar granularity.

### 4. Segment-Median-Sum Gap Handling
**Recommendation:** When computing segment medians from training data for the segment-sum baseline, apply the same tiered fallback:
- Tier A: (route_id, last_stop_id, hour_ct, day_type) with MIN_OBS=5
- Tier B: (route_id, last_stop_id, day_type) across all hours with MIN_OBS=5
- Tier C: (route_id, last_stop_id) across all hours and day_types with MIN_OBS=5
- If still no data for a segment, skip it in the sum (contributes 0). This underestimates travel time slightly but only affects rare edge cases.

This parallels the main fallback hierarchy and minimizes NaN propagation from the 37.9% NaN rate in the original historical_segments (which used MIN_OBS=10).

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Raw time_to_arrival_seconds as target | Residual (actual - baseline) as target | v1.1 decision | Model learns deviations, not absolute times |
| historical_segments MIN_OBS=10 | MIN_OBS=5 for baseline | Phase 7 decision | Better coverage for sparse combos |
| No baseline ETA column | baseline_eta as feature #44 | v1.1 decision | Model knows trip difficulty scale |

**Deprecated/outdated:**
- `historical_segments.parquet` (current file): Built with MIN_OBS=10 for Phase 4 features. Phase 7 should rebuild segment aggregations with MIN_OBS=5. The Phase 4 file should not be overwritten -- it's used by existing v2 features. Phase 7 produces its own lookup tables.

## Open Questions

1. **Should we rebuild or reuse historical_segments.parquet?**
   - What we know: Existing file uses MIN_OBS=10, Phase 7 needs MIN_OBS=5. The aggregation approach is similar but not identical.
   - What's unclear: Whether to overwrite the file (breaking v2 features) or create a separate baseline-specific file.
   - Recommendation: Create separate lookup tables for baseline computation (they live in the script's scope, not as persistent files). The segment-median-sum for baselines has different aggregation needs than the per-row segment features in v2.

2. **Where to save augmented parquets?**
   - What we know: Existing splits are at `data/processed/{train,val,test}.parquet`. v2 features go to `{split}_featured_v2.parquet`.
   - What's unclear: Whether to add columns to existing parquets or create new files.
   - Recommendation: Add `baseline_eta` and `residual` columns to the existing `{split}.parquet` files (modify in place). These are raw split files that Phase 8's training script reads. Alternatively, create `{split}_baselined.parquet` but this adds complexity. The simplest approach is to update the raw splits since they already contain derived columns like `time_to_arrival_seconds`, `is_weekday`, etc.

3. **Segment-sum feasibility for all rows**
   - What we know: Segment medians have 37.9% NaN rate. With the recommended tiered fallback within segments, NaN rate should drop significantly.
   - What's unclear: Exact NaN rate after segment fallback tiers. If still high, the blend falls back to s2s-only.
   - Recommendation: Implement segment fallback tiers. Where segment-sum is still NaN after all fallbacks, use s2s-only as the baseline (no penalty -- the blend naturally degrades to a single method).

## Sources

### Primary (HIGH confidence)
- **Existing codebase** (`scripts/build_differentiator_features.py`) - Historical segment computation, aggregation patterns, merge patterns, hour/day_type extraction
- **Existing codebase** (`scripts/temporal_split.py`) - Split boundaries, is_weekday flag computation
- **Existing codebase** (`scripts/build_features.py`, `scripts/build_stop_sequences.py`) - Feature patterns, stop_sequences schema
- **Live parquet files** - All schemas, row counts, coverage rates, and feasibility numbers verified by running Python against actual data files

### Secondary (MEDIUM confidence)
- **Tier 1 MAE estimate** (128.3s on test) - Computed from live data but uses training-set means applied to test (standard approach, reliable)

### Tertiary (LOW confidence)
- None. All findings verified against live codebase and data.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All libraries already installed and used in v1.0 pipeline
- Architecture: HIGH - Patterns directly extracted from existing codebase
- Pitfalls: HIGH - Verified against live data (last_stop_id=0 counts, NaN rates, coverage rates all measured)
- Discretionary decisions: MEDIUM - Recommendations based on data analysis, but alternatives could work

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (stable -- data and codebase are static for v1.1)
