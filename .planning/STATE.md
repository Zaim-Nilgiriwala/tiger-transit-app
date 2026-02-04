# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 3 complete. Baseline model trained (394.7s MAE, 44.3% over naive). Ready for Phase 4 differentiator features.

## Current Position

Phase: 3 of 6 (Baseline Model) -- COMPLETE
Plan: 2 of 2 in current phase (03-02 complete)
Status: Phase complete
Last activity: 2026-02-04 -- Completed 03-02-PLAN.md (Baseline Model Training)

Progress: [████████░░] ~53%

## Performance Metrics

**Velocity:**
- Total plans completed: 7
- Average duration: 8m
- Total execution time: 0.9 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3/3 | 26m | ~9m |
| 02-row-explosion-labels | 2/2 | ~6m | ~3m |
| 03-baseline-model | 2/2 | ~23m | ~12m |

**Recent Trend:**
- Last 5 plans: 03-02 (~19m), 03-01 (~4m), 02-02 (~3m), 02-01 (~3m), 01-03 (~8m)
- Trend: 03-02 longer due to XGBoost training time (2000 rounds x2 runs)

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

### Pending Todos

None.

### Blockers/Concerns

- ~~Timepoint Excel parsing (23 sheets, human-readable stop names) may require fuzzy matching to GTFS stop IDs -- validate in Phase 1.~~ RESOLVED: 27/28 matched after user review.
- ~~Label join success rate target (60%+ minimum, 70%+ ideal) -- validate in Phase 2 Plan 02-02.~~ RESOLVED: 88.8% success rate.
- Only 5 weeks of data -- aggressive regularization needed throughout.

## Phase 3 Data Artifacts

Phase 1-2 artifacts remain available. Phase 3 artifacts:

| Artifact | Script | Rows | Key Columns |
|----------|--------|------|-------------|
| stop_sequences.parquet | build_stop_sequences.py | 202 | route_id, stop_id, stop_sequence, stop_progress |
| exploded.parquet | explode_rows.py | 2.34M | all telemetry + target_stop_id, target_stop_progress, stops_away |
| labeled.parquet | label_join.py | 2.08M | + actual_arrival, time_to_arrival_seconds |
| train.parquet | temporal_split.py | 1.21M | + date, is_weekday (Nov 6 - Dec 1) |
| val.parquet | temporal_split.py | 384K | + date, is_weekday (Dec 3 - Dec 8) |
| test.parquet | temporal_split.py | 297K | + date, is_weekday (Dec 10 - Dec 13) |
| train_featured.parquet | build_features.py | 1.21M | 15 features + target + stops_away |
| val_featured.parquet | build_features.py | 384K | 15 features + target + stops_away |
| test_featured.parquet | build_features.py | 297K | 15 features + target + stops_away |
| baseline_v1.ubj | train_baseline.py | - | XGBoost model (2000 rounds, MAE 394.7s) |
| baseline_metrics.json | train_baseline.py | - | Overall + sliced metrics + SHAP |
| shap_summary.png | train_baseline.py | - | Feature importance bar chart |

## Session Continuity

Last session: 2026-02-04
Stopped at: Completed 03-02-PLAN.md (Baseline Model Training) -- Phase 3 complete
Resume file: None
