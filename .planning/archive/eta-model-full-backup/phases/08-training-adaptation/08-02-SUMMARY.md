---
phase: 08-training-adaptation
plan: 02
subsystem: ml-pipeline
tags: [xgboost, optuna, residual-target, pseudo-huber, gpu-training, outlier-trimming, hyperparameter-tuning]

# Dependency graph
requires:
  - phase: 08-training-adaptation
    plan: 01
    provides: "v1.1 featured parquets with 45 features, residual target, and reconstruction columns"
  - phase: 07-baseline-infrastructure
    provides: "baseline_eta, baseline_s2s, baseline_seg_sum columns"
provides:
  - "v1.1 XGBoost model (v1_1_residual.ubj) trained on residuals with pseudo-Huber loss"
  - "v1.1 metrics JSON (v1_1_metrics.json) with reconstructed MAE, per-route breakdown, Optuna study summary"
  - "Optuna study v1_1_residual_tuning with 100 trials in SQLite database"
  - "GPU auto-detection function (detect_xgb_device) for portable training"
  - "Z-score outlier trimming utility (trim_outliers) for training data preprocessing"
affects: [09-deployment, future-retraining]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Residual correction: final_pred = baseline_eta + predicted_residual"
    - "Pseudo-Huber loss (reg:pseudohubererror) with tuned huber_slope for outlier-robust regression"
    - "GPU auto-detection via XGBoost probe training (device='cuda' with CPU fallback)"
    - "Deterministic final model: exact round count from best Optuna trial, no early stopping"
    - "Z-score outlier trimming on training data only, per-fold independent trimming in CV"
    - "Optuna SQLite persistence with batch execution for long-running tuning"

key-files:
  created:
    - "models/v1_1_residual.ubj (18.3 MB, gitignored)"
    - "models/v1_1_metrics.json (gitignored)"
  modified:
    - "scripts/train_advanced.py"
    - "scripts/run_optuna_batches.py"
    - "models/optuna_study.db (gitignored)"

key-decisions:
  - "Pseudo-Huber loss won over squared error: 100.51s vs next best squared error trial on validation MAE"
  - "huber_slope = 8.32 (residual std ~287s; slope << residuals makes loss MAE-like, good for outlier robustness)"
  - "Best iteration was 655 (0-indexed), so deterministic retrain used 656 rounds"
  - "gamma = 4.52 (high for residual targets -- conservative splits help zero-centered distribution)"
  - "Z-score 2.5 trimming removed 4.14% of training data (49,932 of 1,206,181 samples)"

patterns-established:
  - "Huber loss preferred for transit ETA residuals: slope ~8 balances MAE/MSE behavior for std~287 distribution"
  - "Optuna batch execution via run_optuna_batches.py with SQLite persistence handles long tuning sessions"
  - "Per-fold outlier trimming in CV: each fold independently trims its training portion"
  - "GPU memory management: del bst + gc.collect() between Optuna trials prevents VRAM leaks"

# Metrics
duration: 98min
completed: 2026-02-17
---

# Phase 8 Plan 02: v1.1 Residual Model Training Summary

**XGBoost v1.1 trained on residual target with pseudo-Huber loss (huber_slope=8.32), 100 Optuna trials, z-score 2.5 trimming, achieving 102.8s reconstructed MAE (16.5% improvement over v1.0's 123.1s)**

## Performance

- **Duration:** ~98 min (93 min Optuna tuning + 5 min CV/retrain/eval)
- **Started:** 2026-02-17T19:56:25Z
- **Completed:** 2026-02-17T21:34:00Z
- **Tasks:** 2
- **Files modified:** 2 scripts + 3 model artifacts (gitignored)

## Accomplishments

- v1.1 model achieves 102.8s reconstructed MAE, beating v1.0 (123.1s) by 20.3s (16.5% improvement)
- Pseudo-Huber loss decisively won over squared error (85 of 100 trials used pseudohubererror; best trial was Huber)
- GPU (CUDA) auto-detection working; all 100 trials ran on GTX 1060
- Z-score 2.5 outlier trimming removed 4.14% of training data (49,932 extreme residuals)
- 4-fold TimeSeriesSplit CV confirmed stability: 100.44s mean MAE (+/- 5.11s)
- Deterministic final model: 656 rounds, no early stopping, reproducible

## Model Results

### v1.1 vs v1.0 Comparison

| Metric | v1.0 (Tuned P5) | v1.1 (Residual) | Change |
|--------|------------------|------------------|--------|
| Reconstructed MAE | 123.1s | 102.8s | -20.3s (16.5%) |
| Reconstructed RMSE | 202.8s | 208.9s | +6.1s (3.0%) |
| Features | 43 | 45 | +2 |
| Rounds | 1239 | 656 | -583 (47% fewer) |
| Loss function | squarederror | pseudohubererror | changed |

### Optuna Study Summary

| Metric | Value |
|--------|-------|
| Study name | v1_1_residual_tuning |
| Total trials | 100 |
| Complete | 46 |
| Pruned | 54 |
| squarederror trials | 15 |
| pseudohubererror trials | 85 |
| Best trial | #91 |
| Best val MAE | 100.51s |
| CV mean MAE | 100.44s (+/- 5.11s) |

### Best Hyperparameters

| Parameter | Value |
|-----------|-------|
| objective | reg:pseudohubererror |
| huber_slope | 8.322 |
| learning_rate | 0.0795 |
| max_depth | 10 |
| subsample | 0.895 |
| colsample_bytree | 0.972 |
| min_child_weight | 12 |
| reg_alpha | 0.000151 |
| reg_lambda | 3.912 |
| gamma | 4.519 |
| num_boost_round | 656 (best_iteration + 1) |

### Per-Route Breakdown (Top 5 + Worst 3)

| Route | N | Recon MAE | v1.0 Context |
|-------|---|-----------|--------------|
| 6 | 16,656 | 60.3s | Best performer |
| 9 | 9,233 | 61.5s | |
| 33 | 2,522 | 68.7s | |
| 96 | 10,062 | 72.5s | |
| 99 | 9,687 | 78.2s | |
| ... | | | |
| 2 | 11,636 | 142.1s | |
| 215 | 19,668 | 129.7s | |
| 27 | 96 | 425.2s | Still sparse (96 test samples) |

### Outlier Trimming

| Metric | Value |
|--------|-------|
| Z-score threshold | 2.5 |
| Samples removed | 49,932 |
| Percentage removed | 4.14% |
| Training before | 1,206,181 |
| Training after | 1,156,249 |

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite train_advanced.py for v1.1 residual training** - `5b48759` (feat)
2. **Task 2: Update batch runner and execute full training pipeline** - `a0c067e` (feat)

## Files Created/Modified

- `scripts/train_advanced.py` - Complete rewrite for v1.1: GPU auto-detection, outlier trimming, Huber+squarederror comparison, 9+1 hyperparameters, deterministic final training, reconstructed MAE evaluation
- `scripts/run_optuna_batches.py` - Updated study name to v1_1_residual_tuning, target trials to 100
- `models/v1_1_residual.ubj` - Trained v1.1 XGBoost model (18.3 MB, gitignored)
- `models/v1_1_metrics.json` - Full metrics with reconstructed MAE, per-route breakdown, Optuna summary (gitignored)
- `models/optuna_study.db` - SQLite database with v1_1_residual_tuning study (gitignored)

## Decisions Made

- **Pseudo-Huber loss is the winner:** Optuna strongly preferred pseudohubererror (85/100 trials), with the best trial (#91) using huber_slope=8.32. The slope being ~3% of the residual std (287s) means the loss is strongly MAE-like, providing robustness against the heavy-tailed residual distribution.
- **high gamma (4.52):** The best trial's gamma was near the upper bound (5.0), indicating that conservative tree splits help with zero-centered residual targets. This is consistent with XGBoost docs: "larger gamma = more conservative."
- **656 rounds (deterministic):** The best Optuna trial's best_iteration was 655 (0-indexed). Final model trained for exactly 656 rounds with no early stopping, ensuring reproducibility.
- **Reconstruction identity:** Residual MAE equals reconstructed MAE (102.8s = 102.8s) because the model correctly learns to cancel the baseline error term. This is a healthy sign -- it means baseline_eta + predicted_residual closely tracks the actual target.

## Deviations from Plan

None -- plan executed exactly as written.

## Issues Encountered

None. GPU training, batch execution, and deterministic retrain all completed without errors.

## User Setup Required

None -- no external service configuration required.

## Next Phase Readiness

- v1.1 model (102.8s MAE) is ready for Phase 9 deployment/comparison
- Metrics JSON provides all data needed for Phase 9 analysis
- Progressive improvement chain: 708.9s (naive) -> 394.7s (P3) -> 175.7s (P4) -> 123.1s (P5/v1.0) -> 102.8s (v1.1)
- v1.1 represents 85.5% improvement over naive schedule baseline
- Route 27 remains problematic (425.2s MAE, only 96 test samples) -- sparse data issue persists from Phase 7
- RMSE slightly increased (+6.1s) despite MAE improvement, suggesting Huber loss trades extreme-error precision for average-error accuracy -- expected behavior

---
*Phase: 08-training-adaptation*
*Completed: 2026-02-17*
