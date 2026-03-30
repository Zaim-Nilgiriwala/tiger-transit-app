---
phase: 04-differentiator-features
plan: 01
subsystem: feature-engineering
tags: [gps, haversine, rolling-speed, acceleration, idle-detection, historical-aggregates, parquet]

# Dependency graph
requires:
  - phase: 02-row-explosion-labels
    provides: train.parquet with exploded rows, last_stop_id, vehicle trajectories
provides:
  - GPS-derived rolling speed features (13 columns) computed on unique pings
  - Historical segment travel time medians (historical_segments.parquet)
  - Historical dwell time medians (historical_dwells.parquet)
  - merge_rolling_to_exploded() helper for Plan 02 integration
affects: [04-02 feature integration, 05-advanced-training]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Unique ping extraction before rolling computation (avoid 4.4x duplication)"
    - "Haversine GPS speed with jitter filter and gap reset"
    - "Time-based rolling windows with min_periods=1 for sparse pings"
    - "Historical aggregates from training data only (no leakage)"

key-files:
  created:
    - scripts/build_differentiator_features.py
    - data/processed/historical_segments.parquet (gitignored, reproducible)
    - data/processed/historical_dwells.parquet (gitignored, reproducible)
  modified: []

key-decisions:
  - "speed_std_30s has 99.9% NaN due to 60s ping intervals -- expected, larger windows compensate"
  - "1,212 valid segment combos (vs 2,550 research estimate) because training split is 58% of full data"
  - "Dwell time resolution limited to ~60s minimum by ping interval"

patterns-established:
  - "extract_unique_pings(): always deduplicate before per-ping feature computation"
  - "add_ct_hour(): UTC-6 shift for Central Time hour-based aggregation"
  - "MIN_OBS=10 threshold: sparse combos set to NaN, not dropped"

# Metrics
duration: 6min
completed: 2026-02-04
---

# Phase 4 Plan 01: Differentiator Features - Rolling Speed and Historical Aggregates Summary

**GPS-derived rolling speed features (13 cols) via haversine on unique pings, plus historical segment/dwell medians from training data**

## Performance

- **Duration:** ~6 min
- **Started:** 2026-02-04T20:45:52Z
- **Completed:** 2026-02-04T20:51:27Z
- **Tasks:** 2
- **Files created:** 3 (1 script + 2 parquets)

## Accomplishments
- 13 rolling/speed features computed on 272K unique pings: gps_speed_mps, 4 rolling means, 4 rolling stds, acceleration, is_idle_gps, seconds_idle
- Historical segment travel time medians saved (1,953 combos, 1,212 valid with count >= 10)
- Historical dwell time medians saved (588 combos, 284 valid)
- All historical aggregates computed from training split only (no data leakage)

## Task Commits

Each task was committed atomically:

1. **Task 1: GPS-derived rolling speed, acceleration, and idle features** - `0cc7114` (feat)
2. **Task 2: Historical segment and dwell aggregates** - included in `0cc7114` (same script file; parquet outputs are gitignored)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `scripts/build_differentiator_features.py` - Full differentiator feature pipeline: haversine GPS speed, rolling windows, acceleration, idle detection, historical segment/dwell aggregates
- `data/processed/historical_segments.parquet` - 1,953 rows: median/p25/p75 segment travel times by (route_id, last_stop_id, hour_ct, day_type)
- `data/processed/historical_dwells.parquet` - 588 rows: median/p25/p75 dwell times by (route_id, stop_id, hour_ct, day_type)

## Decisions Made
- **speed_std_30s nearly all NaN:** With median 60s ping intervals, a 30s rolling window rarely contains 2+ points needed for std. This is expected; 60s/120s/180s windows provide std coverage (70.5%/86.4%/90.2% valid).
- **Segment valid combos (1,212) below research estimate (2,550):** Research counted full labeled dataset; we correctly use only training split (~58% of data). More combos fall below MIN_OBS=10 threshold as a result.
- **Dwell resolution ~60s minimum:** Ping interval of ~60s means dwell measurements have ~60s granularity. Median dwell is 61s which reflects this resolution floor.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Rolling feature functions ready for merge-back to exploded data via `merge_rolling_to_exploded()`
- Historical parquets ready for lookup-merge in Plan 02
- Plan 02 will integrate these features into train/val/test featured parquets

---
*Phase: 04-differentiator-features*
*Completed: 2026-02-04*
