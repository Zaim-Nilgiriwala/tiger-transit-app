# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 4 in progress. Differentiator features v2 assembled, ready for retraining.

## Current Position

Phase: 4 of 6 (Differentiator Features) -- IN PROGRESS
Plan: 2 of 3 in current phase (04-01, 04-02 complete)
Status: In progress
Last activity: 2026-02-04 -- Completed 04-02-PLAN.md (Timepoint Features + v2 Assembly)

Progress: [████████░░] ~67%

## Performance Metrics

**Velocity:**
- Total plans completed: 9
- Average duration: 8m
- Total execution time: 1.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3/3 | 26m | ~9m |
| 02-row-explosion-labels | 2/2 | ~6m | ~3m |
| 03-baseline-model | 2/2 | ~23m | ~12m |
| 04-differentiator-features | 2/3 | ~11m | ~6m |

**Recent Trend:**
- Last 5 plans: 04-02 (~5m), 04-01 (~6m), 03-02 (~19m), 03-01 (~4m), 02-02 (~3m)

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
- [02-02]: merge_asof(direction='forward', tolerance=2h) for ground truth labels -- 88.8% success rate
- [02-02]: Per-route 99.5th percentile outlier removal (10,439 rows)
- [02-02]: Data ends Dec 13 (not Dec 20); test split has 4 days, 296K rows
- [02-02]: Temporal splits with 1-day gap to prevent trip leakage
- [03-01]: lateness_now has zero variance (scheduled_eta_seconds == eta_seconds in EtaSpot data)
- [03-01]: load_featured() helper needed for category dtype restoration (pandas 2.3.3 limitation)
- [03-02]: Baseline XGBoost MAE 394.7s vs naive 708.9s (44.3% improvement)
- [03-02]: SHAP top 3: pattern_id, route_progress, stop_index (distance_to_target #4)
- [03-02]: No early stopping at 2000 rounds -- model under-trained, needs more rounds or higher LR
- [03-02]: lateness_now confirmed zero SHAP importance (zero variance from 03-01)
- [03-02]: models/ added to .gitignore (reproducible artifacts)
- [04-01]: speed_std_30s has 99.9% NaN due to 60s ping intervals -- expected, larger windows compensate
- [04-01]: 1,212 valid segment combos (vs 2,550 research estimate) because training split is 58% of full data
- [04-01]: Dwell time resolution limited to ~60s minimum by ping interval
- [04-02]: Median scheduled time used as representative timepoint departure per (route, stop)
- [04-02]: is_timepoint set to NaN for routes 27/235 (no timepoint data at all)
- [04-02]: target_dwell 98% NaN acceptable -- only 58/119 stops have sufficient observations
- [04-02]: Phase 3 features inlined in v2 pipeline for self-contained execution

### Pending Todos

None.

### Blockers/Concerns

- ~~Timepoint Excel parsing (23 sheets, human-readable stop names) may require fuzzy matching to GTFS stop IDs -- validate in Phase 1.~~ RESOLVED: 27/28 matched after user review.
- ~~Label join success rate target (60%+ minimum, 70%+ ideal) -- validate in Phase 2 Plan 02-02.~~ RESOLVED: 88.8% success rate.
- Only 5 weeks of data -- aggressive regularization needed throughout.

## Phase 4 Data Artifacts

Phase 1-3 artifacts remain available. Phase 4 artifacts:

| Artifact | Script | Rows | Key Columns |
|----------|--------|------|-------------|
| historical_segments.parquet | build_differentiator_features.py | 1,953 | route_id, last_stop_id, hour_ct, day_type, segment_travel_median/p25/p75 |
| historical_dwells.parquet | build_differentiator_features.py | 588 | route_id, stop_id, hour_ct, day_type, dwell_median/p25/p75 |
| train_featured_v2.parquet | build_differentiator_features.py | 1,206,181 | 43 features + target + stops_away (45 cols) |
| val_featured_v2.parquet | build_differentiator_features.py | 384,002 | 43 features + target + stops_away (45 cols) |
| test_featured_v2.parquet | build_differentiator_features.py | 296,608 | 43 features + target + stops_away (45 cols) |

v2 features = 15 Phase 3 + 28 Phase 4 (rolling speed, dynamics, historical, timepoint, speed_ratio, is_rush_hour).

## Session Continuity

Last session: 2026-02-04
Stopped at: Completed 04-02-PLAN.md (Timepoint Features + v2 Assembly)
Resume file: None
