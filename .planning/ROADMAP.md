# Roadmap: Tiger Transit XGBoost ETA Model

## Milestones

- v1.0 XGBoost ETA Model - Phases 1-6 (shipped 2026-02-11)
- v1.1 Model Reapproach - Phases 7-9 (in progress)

## Phases

<details>
<summary>v1.0 XGBoost ETA Model (Phases 1-6) - SHIPPED 2026-02-11</summary>

Phases 1-6 delivered the initial XGBoost ETA model: 123.1s MAE across 23 routes, 82.6% improvement over naive schedule. 13 plans completed across 6 phases. See MILESTONES.md for full details.

</details>

### v1.1 Model Reapproach (In Progress)

**Milestone Goal:** Rearchitect the XGBoost model to predict residuals (actual - baseline_ETA) instead of raw seconds, beating v1.0's 123.1s MAE on the same test set.

- [x] **Phase 7: Baseline Infrastructure** - Compute historical baselines and residual labels for all data splits ✓
- [x] **Phase 8: Training Adaptation** - Retrain XGBoost on residual targets with fresh hyperparameter tuning ✓
- [ ] **Phase 9: Evaluation and Comparison** - Prove v1.1 beats v1.0 with reconstructed prediction metrics

## Phase Details

### Phase 7: Baseline Infrastructure
**Goal**: Historical baseline ETAs exist for every row in every split, and residual labels are computed, enabling all downstream training and evaluation
**Depends on**: v1.0 pipeline (existing parquet splits, historical_segments.parquet, stop_sequences.parquet)
**Requirements**: BASE-01, BASE-02, BASE-03, BASE-04, BASE-05
**Success Criteria** (what must be TRUE):
  1. Stop-to-stop historical average lookup table exists, built exclusively from training data (no val/test leakage)
  2. Every row in train/val/test parquets has a non-NaN baseline_eta value (after fallback hierarchy), with fewer than 5% of rows requiring tier-3+ fallback
  3. Residual column (time_to_arrival_seconds - baseline_eta) exists in all splits, with training-set mean within +/-30s of zero
  4. Baseline-only MAE on test set is reported and falls between 150s and 500s (sanity check -- better than naive 708.9s, worse than v1.0 123.1s)
**Plans**: 1 plan

Plans:
- [x] 07-01-PLAN.md -- Build baseline computation pipeline (s2s lookups, segment-median-sum, 50/50 blend, residual labels, diagnostic report)

### Phase 8: Training Adaptation
**Goal**: A trained v1.1 XGBoost model that predicts residuals, with optimized hyperparameters for the zero-centered residual target distribution
**Depends on**: Phase 7 (baseline_eta and residual columns must exist in augmented parquets)
**Requirements**: TRAIN-01, TRAIN-02, TRAIN-03, TRAIN-04, TRAIN-05
**Success Criteria** (what must be TRUE):
  1. Training pipeline uses residual as target variable while preserving time_to_arrival_seconds for reconstruction
  2. baseline_eta is included as feature #44 in the feature matrix
  3. Optuna completes a fresh study with best parameters that differ from v1.0 (confirming the different target distribution was accounted for)
  4. Both squared error and Huber loss are tested, with the better-performing objective selected based on validation MAE
  5. Outlier trimming removes the worst 1-2% of training samples, and training converges without loss oscillation
**Plans**: 2 plans

Plans:
- [x] 08-01-PLAN.md -- Update feature pipeline for v1.1 (drop lateness_now, add 3 baselines, residual target, rebuild parquets)
- [x] 08-02-PLAN.md -- Optuna tuning with GPU, outlier trimming, Huber comparison, deterministic final model

### Phase 9: Evaluation and Comparison
**Goal**: Definitive proof that v1.1 beats v1.0, with reconstructed predictions evaluated apples-to-apples on the same test set
**Depends on**: Phase 8 (trained v1.1 model must exist)
**Requirements**: EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05
**Success Criteria** (what must be TRUE):
  1. Reconstructed final predictions (baseline_eta + predicted_residual) produce MAE lower than v1.0's 123.1s on the test set
  2. Side-by-side report shows three MAEs: baseline-only, v1.0 raw (123.1s), and v1.1 final -- with v1.1 the lowest
  3. Per-route comparison table identifies which routes improved and which regressed, with majority of routes showing improvement
  4. SHAP analysis shows real-time condition features (speed_mean_*, speed_ratio) gaining importance relative to spatial features (stop_index, distance_to_target) compared to v1.0
  5. Residual distribution analysis (histogram, skew, kurtosis) documents the target distribution characteristics for informing future loss function decisions
**Plans**: TBD (1-2 plans)

Plans:
- [ ] 09-01: Reconstruct predictions, compare to v1.0, SHAP analysis, per-route breakdown, residual diagnostics

## Progress

**Execution Order:** Phase 7 -> Phase 8 -> Phase 9 (strict linear dependency)

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 7. Baseline Infrastructure | v1.1 | 1/1 | Complete | 2026-02-11 |
| 8. Training Adaptation | v1.1 | 2/2 | Complete | 2026-02-17 |
| 9. Evaluation and Comparison | v1.1 | 0/1 | Not started | - |

---
*Roadmap created: 2026-02-11*
*Last updated: 2026-02-17*
