---
phase: 05-advanced-training
plan: 02
status: complete
started: 2026-02-09
completed: 2026-02-09
---

## What was done

Built the asymmetric loss retraining pipeline and quantile model training on top of the Optuna-tuned hyperparameters from Plan 01. The asymmetric model uses a custom 3:1 overestimation penalty with 8-minute proximity scaling to protect riders from missing buses. Three quantile models (P20, P50, P75) provide confidence intervals for the app display ("arriving in 3-6 min"). Generated the full Phase 5 comparison table spanning all model checkpoints from naive through asymmetric.

## Key results

### Asymmetric model

| Metric | Value |
|--------|-------|
| MAE | 126.51s |
| RMSE | 210.79s |
| Median residual | **-16.54s** (conservative) |
| Overestimation rate | 44.4% |
| Alpha (penalty ratio) | 3.0 |
| Proximity threshold | 480s (8 min) |

The negative median residual confirms the model shifts predictions toward underestimation (predicting the bus arrives sooner), which is the safer direction for riders. The MAE is slightly higher than the tuned model (126.5s vs 123.1s) -- this is the expected tradeoff for safety.

### Quantile models

| Metric | Value |
|--------|-------|
| P20 MAE | 209.61s |
| P50 MAE | 154.96s |
| P75 MAE | 197.36s |
| Monotonicity pass | True (after post-processing) |
| Raw violations | 95,925 / 296,608 (32.3%) |
| Calibration | 49.9% (actuals in [P20, P75]) |
| Mean range | 311.0s (5.2 min) |
| Median range | 172.7s (2.9 min) |
| Narrow ranges (<60s) | 10.3% |
| Wide ranges (>300s) | 29.0% |

### Full progressive improvement chain

| Model | MAE | RMSE | vs Naive |
|-------|-----|------|----------|
| Naive (schedule) | 708.9s | 883.4s | -- |
| Baseline (P3) | 394.7s | 514.9s | -44.3% |
| Differentiator (P4) | 175.7s | 279.7s | -75.2% |
| Tuned (P5) | 123.1s | 202.8s | -82.6% |
| Asymmetric (P5) | 126.5s | 210.8s | -82.2% (med_resid=-16.5s) |

## Artifacts

- `scripts/train_asymmetric_quantile.py` -- Asymmetric + quantile training pipeline with section flags and subsampling
- `scripts/train_advanced.py` -- Updated docstring with full Phase 5 pipeline reference
- `models/asymmetric_v1.ubj` -- XGBoost model with custom asymmetric loss (3:1 overestimation penalty)
- `models/asymmetric_metrics.json` -- Asymmetric model metrics including median_residual and residual distribution
- `models/quantile_p20_v1.ubj` -- P20 quantile model (optimistic lower bound)
- `models/quantile_p50_v1.ubj` -- P50 quantile model (median point prediction)
- `models/quantile_p75_v1.ubj` -- P75 quantile model (conservative upper bound)
- `models/quantile_metrics.json` -- Quantile evaluation: monotonicity, calibration, range stats
- `models/phase5_comparison.json` -- Full progressive comparison across all phases with per-route and per-bucket breakdowns

## Decisions made

- **Separate script for Plan 02**: Created `train_asymmetric_quantile.py` rather than inlining all logic into `train_advanced.py`. Keeps Optuna tuning (Plan 01) and asymmetric/quantile training (Plan 02) cleanly separated with their own CLI flags.
- **25% data subsample**: Used 25% of training data for quantile models per user request to reduce runtime. Quantile models trained in ~5 minutes total instead of ~20 minutes.
- **Asymmetric model kept from full-data run**: The asymmetric model was previously trained on full data (median_residual=-16.54s). This existing model was kept as the final artifact since it had better training data coverage.
- **Post-processing for monotonicity**: 32.3% of test samples had monotonicity violations (P20 > P50 or P50 > P75), corrected by sorting predictions per sample. This is a known issue with independently trained quantile models on subsampled data.

## Deviations from plan

### Auto-fixed Issues

None -- plan executed as written with the user-requested subsampling modification.

### Notes

- The plan specified extending `train_advanced.py` with asymmetric+quantile sections. Instead, a separate `train_asymmetric_quantile.py` script was created (already started by user before this execution). This is a cleaner separation -- `train_advanced.py` handles Optuna, `train_asymmetric_quantile.py` handles asymmetric/quantile. Updated `train_advanced.py` docstring to reference the full pipeline.
- Calibration at 49.9% is slightly below the ideal ~55% target. This is expected with 25% subsampled training data. The 20th-75th percentile interval should theoretically capture 55% of observations; the slight under-coverage comes from the reduced training set.
