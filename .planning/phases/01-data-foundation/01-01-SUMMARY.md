---
phase: 01-data-foundation
plan: 01
subsystem: data-pipeline
tags: [telemetry, weather, parquet, parsing, filtering]
depends_on: []
provides: [telemetry-parquet, weather-parquet]
affects: [01-02, 01-03, 02-01]
tech_stack:
  added: []
  patterns: [per-file-filter-for-memory, PROJECT_ROOT-relative-paths]
key_files:
  created:
    - scripts/parse_telemetry.py
    - scripts/parse_weather.py
    - data/processed/telemetry.parquet
    - data/processed/weather.parquet
  modified:
    - .gitignore
decisions:
  - id: data-parquet-gitignore
    decision: "Add data/processed/ to .gitignore since parquet files are large (296MB telemetry) and reproducible from scripts"
  - id: per-file-filtering
    decision: "Filter each JSONL file individually before concat to avoid OOM with 38M+ rows in memory"
  - id: skip-incompatible-schema
    decision: "raw_data_2026-01-07.jsonl has different device-report schema; skip files missing expected columns"
metrics:
  duration: ~12 minutes
  completed: 2026-02-03
---

# Phase 01 Plan 01: Telemetry & Weather Parsing Summary

**Parse telemetry JSONL files and weather CSV into clean parquet files for downstream feature engineering.**

## One-liner

Telemetry (52 JSONL -> 13.47M filtered rows) and weather (1,680 hourly records) parsed to parquet with snake_case columns, bounding-box/speed/vehicle/route filters, and zero-null weather validation.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create telemetry parser script | 5908df2 | scripts/parse_telemetry.py, .gitignore |
| 2 | Create weather parser script | f24a394 | scripts/parse_weather.py |

## Key Results

### Telemetry (data/processed/telemetry.parquet)
- **Raw input:** 52 JSONL files, 38,099,352 rows
- **After filtering:** 13,471,208 rows (64.6% removed)
- **Columns:** 18 snake_case columns including timestamp (UTC datetime)
- **24 unique routes**, 68 unique vehicles, 31 days (2025-11-06 to 2025-12-20)
- **Filters applied:** Auburn bounding box, speed<=65, no jAUnt/Shuttle/empty vid, no NIS (pattern 9998), no staging/charter/gameday routes (777, 230, 231, 216-228), no inactive (progress=-1)
- **File size:** 295.8 MB

### Weather (data/processed/weather.parquet)
- **Rows:** 1,680 hourly records
- **Columns:** timestamp, hour, temperature_c, precipitation_mm
- **Zero nulls** confirmed
- **Date range:** 2025-11-06 to 2026-01-14
- **Temperature:** -5.4C to 25.9C (mean 11.6C)
- **Precipitation:** 95 hours with precip > 0, max 21.5mm
- **File size:** 39 KB

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] OOM risk with full in-memory load**
- **Found during:** Task 1 (initial run hung at file 8)
- **Issue:** Loading all 38M rows into memory as list-of-dicts before filtering caused excessive memory usage (~2.1GB+)
- **Fix:** Restructured to filter per-file before concatenation, freeing raw data after each file
- **Files modified:** scripts/parse_telemetry.py

**2. [Rule 3 - Blocking] Incompatible schema in raw_data_2026-01-07.jsonl**
- **Found during:** Task 1 (KeyError on 'lat')
- **Issue:** File uses raw device-report format (nested objects, `lt`/`ln` instead of `lat`/`lon`)
- **Fix:** Added required-column check, skipping files missing expected columns with a warning
- **Files modified:** scripts/parse_telemetry.py

**3. [Rule 2 - Missing Critical] Large parquet files not gitignored**
- **Found during:** Task 1 commit
- **Issue:** 296MB telemetry.parquet would be committed to git
- **Fix:** Added `data/processed/` to .gitignore since files are reproducible from scripts
- **Files modified:** .gitignore

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Filter per-file before concat | Avoids OOM -- 38M rows of raw telemetry would exceed available memory |
| Skip incompatible schema files | raw_data_2026-01-07.jsonl has device-report format, not simplified telemetry |
| Gitignore data/processed/ | 296MB parquet is reproducible from scripts; too large for git |

## Verification Results

- Both parquet files exist and are loadable
- Telemetry has snake_case columns, all exclusion filters verified via assertions
- Weather has exactly 4 columns with zero nulls
- Both scripts run independently without errors
- Both scripts print validation summaries

## Next Phase Readiness

- Telemetry parquet is ready for feature engineering (stop-pair extraction, trip segmentation)
- Weather parquet is ready for hour-based joins to telemetry
- No blockers identified for downstream plans
