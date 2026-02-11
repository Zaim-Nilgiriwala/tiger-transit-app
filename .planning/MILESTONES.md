# Project Milestones: Tiger Transit XGBoost ETA Model

## v1.0 XGBoost ETA Model (Shipped: 2026-02-11)

**Delivered:** XGBoost-based ETA prediction model for Tiger Transit achieving 123.1s MAE across all 23 routes (82.6% improvement over naive schedule baseline), with asymmetric loss, quantile confidence intervals, and comprehensive evaluation.

**Phases completed:** 1-6 (13 plans total, 06-02 skipped)

**Key accomplishments:**

- Built complete data pipeline from raw JSONL telemetry, CSV arrivals, GTFS, weather CSV, and timepoint Excel (23 sheets) into clean joined Parquet files with 88.8% label join success rate
- Engineered 43 features across 6 categories: vehicle state, route context, temporal, weather, timepoint holds, and historical segment/dwell statistics
- Trained XGBoost model progressing from 394.7s MAE (baseline) to 175.7s (differentiator features) to 123.1s (Optuna-tuned) -- 82.6% total improvement over naive schedule
- Implemented asymmetric loss with 3:1 overestimation penalty and quantile models (P20/P50/P75) for confidence intervals
- Optuna hyperparameter tuning (50 trials, 25 pruned) found optimal max_depth=8, lr=0.201, 1239 rounds
- Comprehensive evaluation: 23/23 route wins vs naive, SHAP explainability (time_until_next_timepoint_departure #1 feature), residual bias detection (6 overpredicting routes, 2 underpredicting)

**Stats:**

- 78 files created/modified
- ~22,550 lines of Python
- 6 phases, 13 plans
- 7 days from start to ship (Feb 3 → Feb 9, 2026)
- ~1.8 hours total execution time

**Git range:** `docs: initialize project` → `docs(06-01): complete comprehensive-evaluation plan`

**What's next:** Deployment integration, production API, or continued model refinement

---
