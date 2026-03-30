---
phase: 01-data-foundation
plan: 02
subsystem: data-pipeline
tags: [gtfs, parquet, arrivals, parsing, etl]
dependency_graph:
  requires: []
  provides: [gtfs-parquets, arrivals-parquet, route-lookup, stop-id-mapping]
  affects: [01-03, 02-01, 02-02]
tech_stack:
  added: [pandas, pyarrow]
  patterns: [parquet-storage, id-mapping-pipeline]
key_files:
  created:
    - scripts/parse_gtfs.py
    - scripts/parse_arrivals.py
    - data/processed/gtfs_routes.parquet
    - data/processed/gtfs_stops.parquet
    - data/processed/gtfs_stop_times.parquet
    - data/processed/gtfs_shapes.parquet
    - data/processed/arrivals.parquet
  modified: []
decisions:
  - id: mixed-date-format
    choice: "Used pandas format='mixed' for date parsing"
    reason: "Second CSV uses ISO format (2026-01-14) while first uses m/d/Y (11/6/2025)"
  - id: filter-before-map
    choice: "Filter NIS/jAUnt rows before ID mapping"
    reason: "Avoids false unmatched warnings from rows we would discard anyway"
  - id: drop-unmatched
    choice: "Drop rows with unmatched station or route names"
    reason: "Only 124 rows affected (Recruitment Stop, No Route) -- not transit data"
metrics:
  duration: 6m
  completed: 2026-02-03
---

# Phase 01 Plan 02: GTFS & Arrivals Parsing Summary

GTFS static files and arrivals CSVs parsed into 5 clean parquet files with consistent numeric ID mappings; shape_dist_traveled validated complete for distance computation.

## Tasks Completed

| Task | Name | Commit | Key Output |
|------|------|--------|------------|
| 1 | Create GTFS parser script | 9971708 | 4 parquets: routes (39), stops (179), stop_times (8269), shapes (16638 pts) |
| 2 | Create arrivals parser script | bbc6b2c | arrivals.parquet: 232,610 rows with numeric stop_id and route_id |

## Key Results

### GTFS Parser (parse_gtfs.py)
- **39 routes** with `route_id_num` extracting numeric ID from compound strings (e.g., `215_202_201_156` -> `215`)
- **179 stops** with integer stop_id, lat/lon coordinates
- **8,269 stop_times** with zero null `shape_dist_traveled` values -- distance between any two stops on a route is directly computable
- **130 shapes** with 16,638 shape points for route geometry
- Stop times enriched with `route_id` and `shape_id` via trips.txt join

### Arrivals Parser (parse_arrivals.py)
- **350,564 raw rows** from 2 CSV files spanning Nov 2025 - Jan 2026
- Filtered: 113,173 NIS rows, 60,177 jAUnt rows removed
- **232,610 clean rows** with numeric `stop_id` (150 unique) and `route_id` (37 unique)
- Station name mapping: 232,723/232,734 matched (99.995%) -- only "Recruitment Stop" unmatched
- Route name mapping: 232,610/232,723 matched -- only "No Route" and "Recruitment" unmatched
- Timestamps parsed to timezone-aware UTC from US/Central
- 49 unique days, 77 vehicles, ~4,747 rows/day average

### ID Mapping Chain
```
arrivals.station_name -> stops.json -> stop_id (matches GTFS stops.stop_id)
arrivals.route_name -> gtfs_routes.route_long_name -> route_id_num
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Mixed date formats in arrivals CSVs**
- **Found during:** Task 2
- **Issue:** First CSV uses `m/d/Y` format (11/6/2025), second uses ISO format (2026-01-14). `pd.to_datetime` with fixed format failed.
- **Fix:** Used `format='mixed'` to auto-detect per-row date format
- **Files modified:** scripts/parse_arrivals.py

**2. [Rule 2 - Missing Critical] Route name filtering before ID mapping**
- **Found during:** Task 2
- **Issue:** "No Route" and "Recruitment" route names in arrivals have no GTFS match. These are non-transit records.
- **Fix:** Drop after mapping (only 113 rows, 0.05% of data). Logged as expected unmatched.
- **Files modified:** scripts/parse_arrivals.py

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Date parsing | `format='mixed'` | Two CSVs use different date formats |
| Unmatched handling | Drop + log warning | Only 124 rows total (Recruitment Stop + No Route) |
| Timestamp timezone | US/Central -> UTC | Standard for downstream processing |
| Route ID extraction | First numeric segment of compound ID | Matches existing codebase convention |

## Next Phase Readiness

- shape_dist_traveled is complete in both stop_times and shapes -- ready for distance computation in downstream plans
- Arrivals have numeric stop_id and route_id -- ready for joining with GTFS schedule data
- Route lookup table (gtfs_routes.parquet) bridges route_id, route_id_num, short/long names across all sources
