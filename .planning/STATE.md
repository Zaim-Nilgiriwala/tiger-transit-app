# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 1 complete. Ready for Phase 2 - Row Explosion & Label Generation.

## Current Position

Phase: 1 of 6 (Data Foundation) -- COMPLETE
Plan: 3 of 3 in current phase (01-01, 01-02, 01-03 complete)
Status: Phase complete
Last activity: 2026-02-03 -- Completed 01-03-PLAN.md (Timepoint Mapping & Parsing)

Progress: [██░░░░░░░░] ~15%

## Performance Metrics

**Velocity:**
- Total plans completed: 3
- Average duration: 9m
- Total execution time: 0.4 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3/3 | 26m | ~9m |

**Recent Trend:**
- Last 5 plans: 01-03 (~8m), 01-02 (6m), 01-01 (12m)
- Trend: stable

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- [Roadmap]: 6 phases derived from 30 requirements at standard depth. Incremental build: data foundation, row explosion, baseline model, differentiator features, advanced training, evaluation.
- [Roadmap]: Phase 3 combines core feature engineering with baseline training (validates pipeline end-to-end in one phase).
- [Roadmap]: Phase 5 combines asymmetric loss, Optuna tuning, and quantile regression (all are training-config concerns, not feature concerns).
- [01-02]: Mixed date formats in arrivals CSVs handled with pandas format='mixed'
- [01-02]: Route ID extraction uses first numeric segment of compound GTFS IDs (e.g., 215_202_201_156 -> 215)
- [01-02]: Arrivals timestamps converted from US/Central to UTC
- [01-01]: Filter per-file before concat to avoid OOM with 38M+ raw telemetry rows
- [01-01]: Skip raw_data_2026-01-07.jsonl (incompatible device-report schema)
- [01-01]: Gitignore data/processed/ -- 296MB telemetry parquet is reproducible from scripts
- [01-03]: Fuzzy matching with human review for timepoint-to-GTFS mapping (27/28 matched)
- [01-03]: 8 manual sheet-to-route overrides for informal naming (P&R, Heath Science, etc.)
- [01-03]: Marathon Gas Station skipped (outdated stop, no GTFS match)

### Pending Todos

None yet.

### Blockers/Concerns

- ~~Timepoint Excel parsing (23 sheets, human-readable stop names) may require fuzzy matching to GTFS stop IDs -- validate in Phase 1.~~ RESOLVED: 27/28 matched after user review.
- Label join success rate target (60%+ minimum, 70%+ ideal) -- validate in Phase 2.
- Only 5 weeks of data -- aggressive regularization needed throughout.

## Phase 1 Data Artifacts

All data foundation artifacts are now complete:

| Artifact | Script | Rows | Key Columns |
|----------|--------|------|-------------|
| telemetry.parquet | parse_telemetry.py | 13.47M | timestamp, lat, lon, speed, route_id, vehicle_id |
| weather.parquet | parse_weather.py | 1,680 | timestamp, temperature_c, precipitation_mm |
| stops.parquet | parse_gtfs_stops.py | 213 | stop_id, stop_name, lat, lon |
| arrivals.parquet | parse_arrivals.py | 145K | route_id, stop_id, arrival_time |
| timepoints.parquet | parse_timepoints.py | 1,958 | route_id, stop_id, scheduled_time |
| timepoint_mapping.json | generate_timepoint_mapping.py | 28 entries | timepoint_name -> stop_id |

## Session Continuity

Last session: 2026-02-03
Stopped at: Completed 01-03-PLAN.md (Timepoint Mapping & Parsing) -- Phase 1 complete
Resume file: None
