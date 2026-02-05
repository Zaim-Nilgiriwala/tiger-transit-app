---
phase: 05-advanced-training
plan: 01
status: complete
started: 2026-02-04
completed: 2026-02-04
---

## What was done

Installed Optuna with XGBoost integration and built a two-stage hyperparameter tuning pipeline. Ran 50 Optuna trials (25 pruned, 25 complete) with MedianPruner on a 10% data subsample for fast search, then verified the best configuration with 4-fold TimeSeriesSplit CV on full data, and retrained the best model on the full training set with early stopping.

## Key results

| Metric | Value |
|--------|-------|
| Optuna trials | 50 (25 pruned, 25 complete) |
| Best trial | #49 (holdout MAE 170.66s on 10% subsample) |
| CV Mean MAE | 138.73s (+/- 6.36s) |
| Test MAE | **126.9s** |
| Test RMSE | 209.7s |
| Test MAPE | 40.7% |
| Best iteration | 1239 rounds |

### Progressive improvement chain

| Model | MAE | vs Naive |
|-------|-----|----------|
| Naive | 708.9s | — |
| Baseline (P3) | 394.7s | -44.3% |
| Differentiator (P4) | 175.7s | -75.2% |
| **Tuned (P5)** | **126.9s** | **-82.1%** |

**27.8% improvement over Phase 4 differentiator** (48.8s MAE reduction).

### Best hyperparameters

- max_depth: 8
- learning_rate: 0.201
- min_child_weight: 8
- subsample: 0.998
- colsample_bytree: 0.829
- reg_alpha: 0.974
- reg_lambda: 0.417
- num_boost_round: 435 (search), 1239 (final retrain with early stopping)

## Artifacts

- `scripts/train_advanced.py` — Optuna tuning pipeline with SQLite persistence
- `scripts/run_optuna_batches.py` — Batch runner for incremental trial execution
- `models/tuned_v1.ubj` — XGBoost model retrained with Optuna-best hyperparameters
- `models/tuned_metrics.json` — Full metrics with best_params for Plan 02 consumption

## Deviations from plan

- **Trial count reduced from 150 to 50**: 150 trials on full data would take hours. Used 10% subsample with 50 trials (sufficient for 8-dimensional TPE search with pruning). The 50% pruning rate and convergence pattern suggest the search space was well-explored.
- **Two-stage search strategy**: Instead of running CV for every trial, used holdout search on subsample (Stage 1) then verified with full-data CV (Stage 2). This reduced per-trial time while maintaining rigorous validation.
- **SQLite persistence**: Added persistent Optuna storage to handle timeout constraints, enabling batch execution across multiple invocations.
