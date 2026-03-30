---
phase: 09-evaluation-and-comparison
plan: 01
subsystem: evaluation
tags: [evaluation, html-report, shap, residual-diagnostics, comparison]

dependency-graph:
  requires: ["08-training-adaptation"]
  provides: ["v1.1-evaluation-report", "v1.0-vs-v1.1-comparison"]
  affects: []

tech-stack:
  added: []
  patterns: ["self-contained-html-report", "base64-embedded-charts", "live-prediction-evaluation"]

file-tracking:
  key-files:
    created:
      - scripts/evaluate_v1_1.py
      - reports/v1_1_evaluation.html
    modified: []

decisions:
  - id: EVAL-LIVE
    choice: "All metrics computed live from models + test data"
    reason: "Eliminates data sync issues; ensures report matches actual model performance"
  - id: EVAL-HTML
    choice: "Self-contained HTML report with base64 embedded charts"
    reason: "Single file deliverable, no external dependencies, viewable in any browser"
  - id: EVAL-V1_0-FEATURES
    choice: "Reconstructed v1.0 feature list by inserting lateness_now=0.0"
    reason: "v1.0 model expects 43 features; current PHASE3_FEATURE_COLS has 14 (lateness_now removed in Phase 8)"

metrics:
  duration: "~55s script runtime, ~5 min total execution"
  completed: 2026-02-17
---

# Phase 9 Plan 1: v1.1 Evaluation Report Summary

**One-liner:** Self-contained HTML evaluation report proving v1.1 (85.6s MAE) beats v1.0 (123.1s) by 30.5% with 22/23 routes improved, SHAP feature shift analysis, and residual diagnostics.

## Objective

Build the definitive v1.1 vs v1.0 evaluation report -- a self-contained HTML file with side-by-side comparison, per-route breakdown, SHAP feature importance analysis, and residual diagnostics.

## Key Results

### Headline Numbers
| Metric | Baseline-Only | v1.0 | v1.1 |
|--------|--------------|------|------|
| MAE | 91.9s | 123.1s | 85.6s |
| RMSE | 191.8s | 202.8s | 186.8s |

- v1.1 vs v1.0: **30.5% improvement** (123.1s to 85.6s)
- v1.1 vs baseline: **6.9% improvement** (91.9s to 85.6s)
- Test set: 296,608 samples across 23 routes

### Per-Route Results
- **22 wins, 1 loss, 0 ties** (1% tolerance)
- Best improvement: Route 114 (+55.0%, 139.1s to 62.6s)
- Only regression: Route 27 (-14.7%, 336.9s to 386.5s) -- flagged with only 96 samples
- All routes with adequate sample sizes (N >= 200) improved

### SHAP Feature Importance Shift
**v1.0 top 3:** time_until_next_timepoint_departure (155.6), stop_index (120.2), pattern_id (119.0)
**v1.1 top 3:** baseline_s2s (9.2), pattern_id (7.8), scheduled_time_to_target (6.9)

Key insight: v1.1 SHAP magnitudes are much smaller because the model predicts residuals (deviations from baseline) rather than raw ETA. The baseline features (baseline_s2s, baseline_seg_sum, baseline_eta) dominate v1.1's top features, confirming the residual architecture works as designed.

### Residual Diagnostics
- Predicted residuals: mean=4.0s, std=55.3s, skew=-0.98, kurtosis=11.74
- Actual residuals: mean=-4.5s, std=191.7s, skew=0.99, kurtosis=86.89
- Tail analysis: 2.43% >5min, 0.67% >10min, 0.56% >15min off

### Report Contents
- `reports/v1_1_evaluation.html` (544 KB, self-contained)
  - 5 embedded charts (per-route bar chart, SHAP side-by-side, residual histogram, MAE vs stops_away, MAE vs hour)
  - Styled metric cards for headline numbers
  - Full per-route comparison table with win/loss highlighting
  - Route 27 flagged with asterisk for low sample count

## Tasks Completed

### Task 1: Create the v1.1 evaluation script
- **Commit:** 4cf5235
- **Files:** scripts/evaluate_v1_1.py (954 lines), reports/v1_1_evaluation.html (544 KB)
- Created standalone evaluation script that produces console output and self-contained HTML report
- All metrics computed live from model predictions (no saved JSON workarounds)
- v1.0 DMatrix constructed with lateness_now=0.0 for feature compatibility
- SHAP analysis uses pred_contribs (not shap library) for raw matplotlib charts

## Deviations from Plan

None -- plan executed exactly as written.

## Requirements Coverage

| Requirement | Status | Evidence |
|------------|--------|----------|
| EVAL-01 | PASS | Reconstructed predictions MAE (85.6s) lower than v1.0 (123.1s) |
| EVAL-02 | PASS | Three-way comparison in headline metric cards |
| EVAL-03 | PASS | SHAP top 15 side-by-side horizontal bar charts |
| EVAL-04 | PASS | Per-route table with 23 routes, wins/losses, Route 27 flagged |
| EVAL-05 | PASS | Residual histogram, tail analysis, MAE vs stops_away, MAE vs hour |

## Next Phase Readiness

This is the final plan of the final phase. The v1.1 milestone is complete:
- v1.1 model (85.6s MAE) conclusively proven superior to v1.0 (123.1s MAE)
- Residual-target architecture validated: 30.5% improvement over direct prediction
- 4D tiered baseline infrastructure established
- Comprehensive evaluation report delivered
