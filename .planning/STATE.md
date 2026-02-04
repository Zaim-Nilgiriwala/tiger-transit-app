# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 2 in progress. Plan 02-01 complete, 02-02 (label join) next.

## Current Position

Phase: 2 of 6 (Row Explosion & Labels) -- IN PROGRESS
Plan: 1 of 2 in current phase (02-01 complete)
Status: In progress
Last activity: 2026-02-04 -- Completed 02-01-PLAN.md (Stop Sequences & Explosion)

Progress: [███░░░░░░░] ~25%

## Performance Metrics

**Velocity:**
- Total plans completed: 4
- Average duration: 8m
- Total execution time: 0.5 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3/3 | 26m | ~9m |
| 02-row-explosion-labels | 1/2 | ~3m | ~3m |

**Recent Trend:**
- Last 5 plans: 02-01 (~3m), 01-03 (~8m), 01-02 (6m), 01-01 (12m)
- Trend: improving

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
- [02-01]: Canonical shape selection by trip count (most trips per shape_id)
- [02-01]: Explosion produced 2.34M rows (vs 4-6M estimate) -- avg 3.2 stops ahead per observation is correct

### Pending Todos

None yet.

### Blockers/Concerns

- ~~Timepoint Excel parsing (23 sheets, human-readable stop names) may require fuzzy matching to GTFS stop IDs -- validate in Phase 1.~~ RESOLVED: 27/28 matched after user review.
- Label join success rate target (60%+ minimum, 70%+ ideal) -- validate in Phase 2 Plan 02-02.
- Only 5 weeks of data -- aggressive regularization needed throughout.

## Phase 2 Data Artifacts

Phase 1 artifacts remain available. New Phase 2 artifacts:

| Artifact | Script | Rows | Key Columns |
|----------|--------|------|-------------|
| stop_sequences.parquet | build_stop_sequences.py | 202 | route_id, stop_id, stop_sequence, stop_progress |
| exploded.parquet | explode_rows.py | 2.34M | all telemetry + target_stop_id, target_stop_progress, stops_away |

## Session Continuity

Last session: 2026-02-04
Stopped at: Completed 02-01-PLAN.md (Stop Sequences & Explosion)
Resume file: None
