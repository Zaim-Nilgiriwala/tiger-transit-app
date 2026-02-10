# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-03)

**Core value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.
**Current focus:** Phase 5 complete. All advanced training models built: Optuna-tuned (123.1s MAE), asymmetric loss (126.5s MAE, median_residual=-16.5s), and P20/P50/P75 quantile models. Ready for Phase 6 evaluation.

## Current Position

Phase: 5 of 6 (Advanced Training) -- COMPLETE
Plan: 2 of 2 in current phase (all complete)
Status: Phase complete
Last activity: 2026-02-09 -- Completed 05-02-PLAN.md (Asymmetric + Quantile Training)

Progress: [█████████░] ~86%

## Performance Metrics

**Velocity:**
- Total plans completed: 12
- Average duration: ~8m
- Total execution time: ~1.6 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-data-foundation | 3/3 | 26m | ~9m |
| 02-row-explosion-labels | 2/2 | ~6m | ~3m |
| 03-baseline-model | 2/2 | ~23m | ~12m |
| 04-differentiator-features | 3/3 | ~23m | ~8m |
| 05-advanced-training | 2/2 | ~20m | ~10m |

**Recent Trend:**
- Last 5 plans: 05-02 (~10m), 05-01 (~10m), 04-03 (~12m), 04-02 (~5m), 04-01 (~6m)

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
- [04-03]: Differentiator MAE 175.7s vs baseline 394.7s (55.5% improvement)
- [04-03]: time_until_next_timepoint_departure is #2 SHAP feature (145.11), highest new Phase 4 feature
- [04-03]: 5 Phase 4 features in top 10: timepoint departure, segment travel (median/p25/p75), speed_mean_180s
- [04-03]: Model used all 3000 rounds without early stopping -- still improving, needs Optuna tuning in Phase 5
- [04-03]: Hyperparameters kept identical to baseline (reg_lambda=5.0) to isolate feature impact
- [05-01]: Optuna 50 trials (25 pruned). Best: max_depth=8, lr=0.201, 435 rounds. CV MAE 138.7s, test MAE 123.1s
- [05-01]: 10% subsample for Optuna search, 5x rounds with early stopping for final retrain (best_iter=1239)
- [05-02]: Asymmetric loss alpha=3.0, threshold=480s. Median residual=-16.54s (conservative predictions)
- [05-02]: Quantile models trained on 25% subsample. 32.3% monotonicity violations corrected by sorting
- [05-02]: Calibration 49.9% (actuals in [P20, P75]), mean range 311s (5.2 min)
- [05-02]: Separate script train_asymmetric_quantile.py for Plan 02 (cleaner separation from Optuna pipeline)

### Pending Todos

None.

### Blockers/Concerns

- ~~Timepoint Excel parsing (23 sheets, human-readable stop names) may require fuzzy matching to GTFS stop IDs -- validate in Phase 1.~~ RESOLVED: 27/28 matched after user review.
- ~~Label join success rate target (60%+ minimum, 70%+ ideal) -- validate in Phase 2 Plan 02-02.~~ RESOLVED: 88.8% success rate.
- Only 5 weeks of data -- aggressive regularization needed throughout.
- ~~Model still improving at 3000 rounds -- Phase 5 should explore higher learning rates and/or more rounds via Optuna.~~ RESOLVED: Optuna found optimal lr=0.201, max_depth=8, best iteration 1239 with early stopping.
- Quantile model monotonicity violations (32.3%) suggest independent quantile training on subsampled data has limitations. Consider joint quantile training or full-data retrain if higher quality intervals needed.

## Model Performance Tracker

| Model | MAE | RMSE | vs Naive | Features | Rounds |
|-------|-----|------|----------|----------|--------|
| Naive (schedule) | 708.9s | 883.4s | -- | 1 | -- |
| Baseline (P3) | 394.7s | 514.9s | 44.3% | 15 | 2000 |
| Differentiator (P4) | 175.7s | 279.7s | 75.2% | 43 | 3000 |
| Tuned (P5) | 123.1s | 202.8s | 82.6% | 43 | 1239 |
| Asymmetric (P5) | 126.5s | 210.8s | 82.2% | 43 | 2174 |

## Phase 5 Model Artifacts

Phase 1-4 artifacts remain available. Phase 5 artifacts:

| Artifact | Script | Description |
|----------|--------|-------------|
| tuned_v1.ubj | train_advanced.py | Optuna-tuned XGBoost (MAE 123.1s) |
| tuned_metrics.json | train_advanced.py | Best params, study summary, sliced metrics |
| asymmetric_v1.ubj | train_asymmetric_quantile.py | 3:1 asymmetric loss model (MAE 126.5s, med_resid=-16.5s) |
| asymmetric_metrics.json | train_asymmetric_quantile.py | Residual distribution, overestimation rate |
| quantile_p20_v1.ubj | train_asymmetric_quantile.py | P20 quantile (optimistic lower bound) |
| quantile_p50_v1.ubj | train_asymmetric_quantile.py | P50 quantile (median prediction) |
| quantile_p75_v1.ubj | train_asymmetric_quantile.py | P75 quantile (conservative upper bound) |
| quantile_metrics.json | train_asymmetric_quantile.py | Monotonicity, calibration, range stats |
| phase5_comparison.json | train_asymmetric_quantile.py | Full progressive chain across all phases |

## Session Continuity

Last session: 2026-02-09
Stopped at: Completed 05-02-PLAN.md (Asymmetric + Quantile Training) -- Phase 5 complete
Resume file: None
