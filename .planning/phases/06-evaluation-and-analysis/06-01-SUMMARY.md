---
phase: 06-evaluation-and-analysis
plan: 01
subsystem: evaluation
tags: [xgboost, shap, evaluation, residuals, bias-detection, model-comparison]
requires: [05-01, 05-02]
provides: [evaluation-pipeline, sliced-metrics, shap-analysis, comparison-table, residual-bias-detection, master-report]
affects: [06-02]
tech-stack:
  added: [shap-0.46.0]
  patterns: [pred_contribs-shap, quantile-based-distance-bucketing, bias-threshold-detection]
key-files:
  created:
    - scripts/evaluate.py
    - models/evaluation/eval_metrics_sliced.json
    - models/evaluation/eval_comparison.json
    - models/evaluation/eval_comparison.md
    - models/evaluation/eval_residuals.json
    - models/evaluation/eval_residuals_by_route.png
    - models/evaluation/eval_residuals_by_tod.png
    - models/evaluation/eval_shap_global.png
    - models/evaluation/eval_shap_waterfall_1.png
    - models/evaluation/eval_shap_waterfall_2.png
    - models/evaluation/eval_shap_waterfall_3.png
    - models/evaluation/eval_shap_meta.json
    - models/evaluation/eval_report.md
  modified: []
decisions:
  - id: "06-01-shap-path"
    choice: "pred_contribs over TreeExplainer"
    reason: "TreeExplainer on 2158-iteration GPU model is prohibitively slow. pred_contribs computes exact SHAP values natively in XGBoost, taking ~5 min on 2000-row subsample vs estimated hours for TreeExplainer."
  - id: "06-01-distance-buckets"
    choice: "Quantile-based distance bucketing (Q25/Q50/Q75)"
    reason: "distance_to_target values are fractional km (max ~7.0). The original meter-based thresholds (<1000, 1-3k, etc.) placed 100% of 296K samples in '<1km' bucket. Quantile-based thresholds create 4 roughly equal-sized buckets."
  - id: "06-01-bias-threshold"
    choice: "15s bias threshold (~12% of overall MAE)"
    reason: "Mean signed residual > 15s flags systematic overprediction; < -15s flags underprediction. Threshold is meaningful relative to the 123.1s overall MAE."
  - id: "06-01-shap-subsample"
    choice: "2000-row subsample for SHAP"
    reason: "pred_contribs on full 296K test set estimated at ~8 hours. 2000 rows provides stable mean |SHAP| estimates in ~5 minutes while covering the error distribution for waterfall sample selection."
metrics:
  duration: ~15m
  completed: 2026-02-09
---

# Phase 6 Plan 01: Comprehensive Evaluation Pipeline Summary

Full evaluation pipeline covering EVAL-01 (sliced metrics), EVAL-02 (SHAP explainability), EVAL-03 (naive comparison with 23/23 route wins), and EVAL-04 (residual bias detection identifying 6 OVER and 2 UNDER biased routes), plus master synthesis report.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create evaluate.py with all four EVAL requirements | 75f5b9c | scripts/evaluate.py (1217 lines), 13 output artifacts in models/evaluation/ |
| 2 | Generate master evaluation report | 75f5b9c (included in Task 1) | models/evaluation/eval_report.md (244 lines) |

## Key Findings

### EVAL-01: Sliced Metrics
- **Overall:** MAE=123.1s, RMSE=202.8s, MAPE=38.1% (296,608 test samples)
- **Best route:** Route 33 (MAE=77.1s), Route 9 (MAE=79.6s)
- **Worst route:** Route 27 (MAE=336.9s, only 96 samples -- extreme outlier)
- **By stops:** 4-6 stops ahead is the sweet spot (MAE=118.1s), 1-stop worst (MAE=127.7s)
- **By TOD:** Afternoon best (MAE=111.3s), Evening worst (MAE=132.5s), no morning data
- **Distance bucketing:** Quantile-based thresholds (Q25=0.82, Q50=1.68, Q75=2.70 km) used because all distances < 7 km

### EVAL-02: SHAP Feature Importance
- **Path used:** pred_contribs (native XGBoost, 2000-row subsample)
- **Top 3 features:**
  1. time_until_next_timepoint_departure (155.62)
  2. stop_index (120.19)
  3. pattern_id (118.98)
- Phase 4 features dominate top 10: timepoint departure, segment travel (p25/median/p75)
- 3 waterfall plots: high-error (346.7s), low-error (7.3s), typical (83.1s)

### EVAL-03: Model Comparison
- **Progressive improvement:** Naive (708.9s) -> Baseline (394.7s, -44.3%) -> Differentiator (175.7s, -75.2%) -> Tuned (123.1s, -82.6%)
- **Per-route:** 23/23 routes WIN vs naive schedule (0 losses)
- **Best route improvement:** Route 93 (86.3% reduction, 1024.1s -> 140.4s)
- **Weakest win:** Route 27 (30.8% reduction, only 96 samples)

### EVAL-04: Residual Bias
- **Overall:** Mean residual +7.66s, 53.3% overprediction rate (slight positive bias)
- **Overprediction routes (>15s):** Routes 5, 7, 24, 31, 33, 96
- **Underprediction routes (<-15s):** Routes 1, 99
- **Time-of-day:** Midday shows overprediction bias (+24.93s)
- **Stops-remaining:** No systematic bias across any bucket

## Decisions Made

1. **pred_contribs over TreeExplainer:** TreeExplainer on 2158-iteration GPU model was prohibitively slow. pred_contribs provides exact SHAP values natively, completing in ~5 min on 2000-row subsample.
2. **Quantile-based distance bucketing:** All test distances are < 7 km (fractional values), so the original meter-based thresholds put everything in one bucket. Used Q25/Q50/Q75 percentiles for meaningful 4-bucket splits.
3. **15s bias threshold:** ~12% of overall MAE. Flags routes with systematic over/under-prediction for production monitoring.
4. **2000-row SHAP subsample:** Balances computation time (~5 min) against statistical stability for feature importance ranking.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] SHAP TreeExplainer timeout**

- **Found during:** Task 1 (EVAL-02 section)
- **Issue:** TreeExplainer with `feature_perturbation="tree_path_dependent"` on a 2158-iteration XGBoost model was prohibitively slow (hung for >10 minutes on 1000-row subsample). The model's depth (max_depth=8) and iteration count make TreeExplainer impractical.
- **Fix:** Swapped Path A/B order: pred_contribs (native XGBoost) tried first as primary path, TreeExplainer as fallback. Used 2000-row subsample for pred_contribs (~5 min). This produces equivalent SHAP values since pred_contribs is the exact tree-path-dependent algorithm.
- **Files modified:** scripts/evaluate.py
- **Commit:** 75f5b9c

**2. [Rule 1 - Bug] Distance bucketing placed all samples in single bucket**

- **Found during:** Task 1 (EVAL-01 section)
- **Issue:** distance_to_target values are in fractional km (0.00-6.99), but the original `distance_bucket()` function used meter thresholds (1000, 3000, 5000) which placed 100% of 296K samples in "<1km" bucket.
- **Fix:** Computed data-driven quantile thresholds (Q25=0.82, Q50=1.68, Q75=2.70 km) for meaningful 4-bucket distance analysis.
- **Files modified:** scripts/evaluate.py (inline quantile bucketing, not reusing distance_bucket())
- **Commit:** 75f5b9c

## Artifacts Produced

### In Git (committed)
- `scripts/evaluate.py` -- 1217-line evaluation pipeline with `--section` flag for selective execution

### Generated (gitignored, reproducible via `python scripts/evaluate.py`)
- `models/evaluation/eval_metrics_sliced.json` -- EVAL-01 sliced metrics
- `models/evaluation/eval_shap_global.png` -- EVAL-02 global importance bar plot
- `models/evaluation/eval_shap_waterfall_{1,2,3}.png` -- EVAL-02 waterfall plots
- `models/evaluation/eval_shap_meta.json` -- EVAL-02 metadata
- `models/evaluation/eval_comparison.json` -- EVAL-03 comparison data
- `models/evaluation/eval_comparison.md` -- EVAL-03 formatted comparison table
- `models/evaluation/eval_residuals.json` -- EVAL-04 residual bias data
- `models/evaluation/eval_residuals_by_route.png` -- EVAL-04 route bias chart
- `models/evaluation/eval_residuals_by_tod.png` -- EVAL-04 time-of-day bias chart
- `models/evaluation/eval_report.md` -- Master synthesis report (244 lines)

## Next Phase Readiness

Plan 06-02 (visual QA and final model card) can proceed. All evaluation artifacts are generated and available. Key items for Plan 02:
- Visual inspection of SHAP plots and residual charts
- Model card generation from eval_report.md findings
- Final assessment of Route 27 (96 samples, 336.9s MAE -- likely insufficient data)
