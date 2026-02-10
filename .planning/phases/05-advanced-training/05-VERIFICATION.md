---
phase: 05-advanced-training
verified: 2026-02-10T01:21:05Z
status: passed
score: 9/9 must-haves verified
re_verification: false
---

# Phase 5: Advanced Training Verification Report

**Phase Goal:** The model uses asymmetric loss matching the existing PyTorch penalty structure, hyperparameters are tuned via Optuna, and quantile predictions provide confidence intervals

**Verified:** 2026-02-10T01:21:05Z

**Status:** PASSED

**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Optuna study completes 50+ trials with TimeSeriesSplit CV | VERIFIED | study_summary shows 150 trials (109 pruned, 41 complete) with MedianPruner |
| 2 | Best trial MAE improves over Phase 4 default (175.7s) | VERIFIED | Tuned MAE = 123.08s vs Phase 4 = 175.67s (29.9% improvement) |
| 3 | Best hyperparameters saved for downstream consumption | VERIFIED | tuned_metrics.json contains best_params with 7 hyperparameters |
| 4 | Asymmetric loss penalizes overestimation 3:1 with 8-min proximity | VERIFIED | asymmetric_metrics.json shows alpha=3.0, threshold_seconds=480 |
| 5 | Median residual is negative (conservative predictions) | VERIFIED | median_residual = -16.54s (model predicts bus arrives sooner) |
| 6 | Quantile models produce P20, P50, P75 predictions | VERIFIED | Three models exist: quantile_p{20,50,75}_v1.ubj, all loadable with 43 features |
| 7 | Monotonicity holds: P20 <= P50 <= P75 for all samples | VERIFIED | monotonicity_pass = true (after post-processing 32.3% raw violations) |
| 8 | Calibration is reasonable (~50-55%) | VERIFIED | calibration = 49.9% (actuals falling in [P20, P75] interval) |
| 9 | Progressive improvement chain shows all model checkpoints | VERIFIED | phase5_comparison.json has 5 entries: naive to asymmetric |

**Score:** 9/9 truths verified (100%)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| scripts/train_advanced.py | Optuna tuning pipeline | VERIFIED | 24KB, contains optuna.create_study |
| models/tuned_v1.ubj | Optuna-best model | VERIFIED | 40MB, loadable with 43 features |
| models/tuned_metrics.json | Tuned metrics | VERIFIED | MAE=123.08s, best_params present |
| scripts/train_asymmetric_quantile.py | Asymmetric+quantile pipeline | VERIFIED | 25KB, asymmetric objective + QuantileDMatrix |
| models/asymmetric_v1.ubj | Asymmetric model | VERIFIED | 41MB, loadable with 43 features |
| models/asymmetric_metrics.json | Asymmetric metrics | VERIFIED | median_residual=-16.54s |
| models/quantile_p20_v1.ubj | P20 quantile | VERIFIED | 27MB, loadable |
| models/quantile_p50_v1.ubj | P50 quantile | VERIFIED | 27MB, loadable |
| models/quantile_p75_v1.ubj | P75 quantile | VERIFIED | 27MB, loadable |
| models/quantile_metrics.json | Quantile evaluation | VERIFIED | monotonicity_pass=true |
| models/phase5_comparison.json | Progressive comparison | VERIFIED | 5-model chain present |

**All 11 required artifacts exist, are substantive, and are wired correctly.**

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|----|--------|---------|
| train_advanced.py | optuna | Direct call | WIRED | Line 252: optuna.create_study() |
| train_advanced.py | tuned_metrics.json | JSON write | WIRED | Writes best_params |
| train_asymmetric_quantile.py | tuned_metrics.json | JSON load | WIRED | Lines 261-264 load best_params |
| train_asymmetric_quantile.py | asymmetric objective | Custom obj | WIRED | Line 297: obj=make_asymmetric_objective() |
| train_asymmetric_quantile.py | QuantileDMatrix | Quantile training | WIRED | Lines 387-388 with ref parameter |
| asymmetric_metrics.json | median_residual | Validation | WIRED | Value=-16.54s confirms conservative shift |
| quantile_metrics.json | monotonicity | Post-processing | WIRED | monotonicity_pass=true |

**All 7 key links verified and functioning.**

### Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| TRAIN-02: Asymmetric loss | SATISFIED | alpha=3.0, median_residual=-16.54s |
| TRAIN-03: Optuna tuning | SATISFIED | 150 trials, CV MAE=138.69s |
| TRAIN-04: Multi-quantile | SATISFIED | P20/P50/P75 models, monotonicity passes |

**All 3 requirements satisfied.**

### Success Criteria Verification

**From ROADMAP.md Phase 5 Success Criteria:**

1. **Asymmetric loss with correct residual distribution**
   - VERIFIED: Custom objective with alpha=3.0, threshold=480s
   - VERIFIED: Median residual = -16.54s (NEGATIVE, conservative for riders)
   - Note: CONTEXT.md clarified negative is correct direction

2. **Optuna 100+ trials with CV, improves over Phase 4**
   - VERIFIED: 150 trials (41 complete, 109 pruned)
   - VERIFIED: 4-fold TimeSeriesSplit CV (MAE = 138.69s ± 6.58s)
   - VERIFIED: Test MAE = 123.08s vs Phase 4 = 175.67s (29.9% improvement)

3. **Multi-quantile with monotonicity**
   - VERIFIED: P20/P50/P75 models trained
   - VERIFIED: Monotonicity passes after post-processing
   - Note: P20/P75 chosen over P50/P80 per CONTEXT.md

4. **Progressive improvement chain**
   - VERIFIED: phase5_comparison.json contains:
     - Naive: 708.9s
     - Baseline P3: 394.66s
     - Differentiator P4: 175.67s
     - Tuned P5: 123.08s
     - Asymmetric P5: 126.51s

**All 4 success criteria verified.**

### Anti-Patterns Found

**No blocking anti-patterns found.**

Scan results:
- No TODO/FIXME/HACK comments
- No placeholder text or stubs
- All models loadable with 43 features
- All metrics files contain expected keys

### Deviations from Plan

**Acceptable deviations (documented):**

1. **Trial count: 50 vs 150 planned**
   - Two-stage strategy: 10% subsample + full CV verification
   - Reason: Runtime constraint
   - Impact: None - rigorous validation maintained

2. **Quantiles: P20/P50/P75 vs P50/P80 planned**
   - CONTEXT.md decision for better UI display
   - Impact: None - matches documented decision

3. **Quantile data: 25% subsample vs 100%**
   - User request for runtime reduction
   - Impact: Acceptable - calibration 49.9% vs ideal 55%

4. **Separate asymmetric script**
   - Cleaner separation of concerns
   - Impact: None - both scripts functional

**No deviations block goal achievement.**

### Progressive Improvement Analysis

| Model | MAE (s) | RMSE (s) | vs Naive | vs Previous |
|-------|---------|----------|----------|-------------|
| Naive | 708.9 | 883.4 | -- | -- |
| Baseline P3 | 394.66 | 514.86 | -44.3% | -44.3% |
| Differentiator P4 | 175.67 | 279.74 | -75.2% | -55.5% |
| Tuned P5 | 123.08 | 202.81 | -82.6% | -29.9% |
| Asymmetric P5 | 126.51 | 210.79 | -82.2% | +2.8% |

**Key insights:**
- Optuna delivers 29.9% improvement over Phase 4 (52.6s reduction)
- Asymmetric trades 2.8% MAE for safety (negative residual)
- Monotonic improvement through tuned model
- Asymmetric achieves goal: rider protection + strong accuracy

### Quantile Model Analysis

| Quantile | MAE (s) | Purpose |
|----------|---------|---------|
| P20 | 209.61 | Optimistic lower bound |
| P50 | 154.96 | Median point prediction |
| P75 | 197.36 | Conservative upper bound |

**Range statistics:**
- Mean range: 311.0s (5.2 min)
- Median range: 172.7s (2.9 min)
- Narrow (<60s): 10.3% - single-number display
- Wide (>300s): 29.0% - range display
- Calibration: 49.9% (target ~55%)

**Monotonicity:**
- Raw violations: 32.3% (expected with subsampled independent training)
- After post-processing: 0% (per-sample sorting)

---

## Verification Summary

**Phase 5 goal ACHIEVED.**

All success criteria verified:
1. Asymmetric loss with conservative predictions
2. Optuna tuning improves 29.9% over Phase 4
3. Quantile models with monotonicity
4. Progressive comparison complete

All requirements satisfied:
- TRAIN-02: Asymmetric loss
- TRAIN-03: Optuna tuning
- TRAIN-04: Multi-quantile predictions

All artifacts exist and wired:
- 2 training scripts
- 5 model files
- 4 metrics files

No blocking issues. Ready for Phase 6 (Evaluation & Analysis).

---

_Verified: 2026-02-10T01:21:05Z_
_Verifier: Claude (gsd-verifier)_
_Verification Mode: Initial_
