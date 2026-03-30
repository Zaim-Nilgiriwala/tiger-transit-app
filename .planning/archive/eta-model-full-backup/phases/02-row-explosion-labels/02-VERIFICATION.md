---
phase: 02-row-explosion-labels
verified: 2026-02-03T21:40:00Z
status: passed
score: 6/6 must-haves verified
---

# Phase 2: Row Explosion & Labels Verification Report

**Phase Goal:** Each telemetry observation is expanded into N rows (one per remaining stop), labeled with ground truth time_to_arrival_seconds, and split into train/val/test sets by calendar date

**Verified:** 2026-02-03T21:40:00Z
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Each route has an ordered list of stops with progress fractions derived from GTFS shape_dist_traveled | VERIFIED | stop_sequences.parquet exists with 202 rows (39 routes), contains shape_dist_traveled, max_shape_dist, stop_progress columns. Progress values range 0.0-1.0 per route. |
| 2 | Telemetry is downsampled to ~60s intervals before explosion (~750K rows from 13.47M) | VERIFIED | explode_rows.py implements 60s time bucketing via df.groupby(['vehicle_id', 'route_id', 'time_bucket']).last(). SUMMARY reports 732,436 downsampled rows (within target range). |
| 3 | Each downsampled telemetry row is exploded into up to 8 per-stop rows for remaining stops ahead on the route | VERIFIED | exploded.parquet contains 2,343,861 rows with stops_away column ranging 1-8. Expansion factor 3.2x (realistic for vehicles mid-route). target_stop_progress > progress verified in assertions. |
| 4 | Explosion runs chunked-by-day without OOM | VERIFIED | explode_rows.py uses PyArrow predicate pushdown (pq.read_table with filters) to process 31 days individually. Files exist and are loadable. Processing completed successfully per SUMMARY. |
| 5 | Each exploded row has a time_to_arrival_seconds label from merge_asof joining with actual arrivals | VERIFIED | labeled.parquet exists with time_to_arrival_seconds column. Label range 11s-5496s. 88.8% join success rate (exceeds 60% target). merge_asof(direction=forward, tolerance=2h) implemented correctly. |
| 6 | Label distribution has no 3600s spike (timezone bug indicator) | VERIFIED | Timezone spike check: 0.00% of labels in 3540-3660s range (target <5%). No timezone bug detected. Both telemetry and arrivals properly converted to UTC in Phase 1. |
| 7 | Train/val/test splits are strictly temporal by calendar date with a 1-day gap | VERIFIED | Temporal boundaries verified: Train (2025-11-06 to 2025-12-01), Val (2025-12-03 to 2025-12-08), Test (2025-12-10 to 2025-12-13). Gap periods: 2 days between each split. Zero date overlap. |
| 8 | No trip leaks across splits | VERIFIED | Date-based splitting with 2-day gaps prevents trip leakage by design (transit trips are at most few hours). No explicit trip_id column exists, but temporal gap ensures no overlap. Zero date overlap verified. |
| 9 | Final parquet files exist on disk with correct schema and row counts logged | VERIFIED | All 6 required parquets exist: stop_sequences (202 rows), exploded (2.34M rows), labeled (2.08M rows), train (1.21M rows), val (384K rows), test (297K rows). Schemas correct with expected columns. |

**Score:** 9/9 truths verified

### Required Artifacts

All required artifacts verified as SUBSTANTIVE and WIRED.

### Key Link Verification

All key links verified as WIRED with correct implementation patterns.

### Requirements Coverage

| Requirement | Status |
|-------------|--------|
| DATA-06 | SATISFIED |
| DATA-07 | SATISFIED |
| DATA-08 | SATISFIED |

### Anti-Patterns Found

None detected. All scripts are substantive implementations.

### Human Verification Required

None.

---

## Verification Summary

**Phase 2 goal achieved.** All 4 success criteria met:

1. Row explosion runs to completion without OOM - PASS
2. Label join success rate 88.8% (target >60%), no timezone spike - PASS
3. Temporal splits with gaps, zero overlap - PASS
4. All Parquet files exist with correct schemas - PASS

**Requirements coverage:** DATA-06, DATA-07, DATA-08 all satisfied.

**Ready for Phase 3.**

---

_Verified: 2026-02-03T21:40:00Z_
_Verifier: Claude (gsd-verifier)_
