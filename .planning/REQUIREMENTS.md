# Requirements: Tiger Transit XGBoost ETA Model v1.1

**Defined:** 2026-02-11
**Core Value:** Accurate arrival time predictions for all remaining stops on a bus route, accounting for timepoint holds, schedule adherence, and real-world conditions.

## v1.1 Requirements

### Baseline Computation

- [x] **BASE-01**: Compute stop-to-stop historical average travel times from training data, aggregated by (route_id, from_stop_id, target_stop_id, hour, day_type)
- [x] **BASE-02**: Compute segment-median-sum baseline by summing historical segment median travel times along the route path from current position to target stop
- [x] **BASE-03**: Blend both baselines into a single baseline_eta column (average of segment-sum and stop-to-stop)
- [x] **BASE-04**: Generate residual labels (time_to_arrival_seconds - baseline_eta) for all rows in train/val/test splits
- [x] **BASE-05**: Measure and report baseline-only MAE on test set as fail-fast checkpoint (expected 200-400s)

### Training Pipeline

- [x] **TRAIN-01**: Modify training scripts to use residual as target variable (preserve original time_to_arrival_seconds alongside)
- [x] **TRAIN-02**: Add baseline_eta as feature #44 in the feature matrix (so model learns residuals scale with trip length)
- [x] **TRAIN-03**: Fresh Optuna hyperparameter tuning with new study name, adjusted search space for zero-centered residual target distribution
- [x] **TRAIN-04**: Implement outlier trimming (remove worst 1-2% training samples by Z-score or percentile before training)
- [x] **TRAIN-05**: Test Huber loss (reg:pseudohubererror) alongside squared error, report which performs better on validation set

### Evaluation

- [x] **EVAL-01**: Reconstruct final predictions (baseline_eta + predicted_residual) and compute MAE/RMSE on test set
- [x] **EVAL-02**: Side-by-side comparison: v1.1 final MAE vs v1.0 123.1s MAE (the success metric -- must be lower)
- [x] **EVAL-03**: SHAP feature importance analysis showing expected shift from spatial to real-time condition features
- [x] **EVAL-04**: Per-route comparison table (v1.1 vs v1.0 MAE per route, wins/losses identified)
- [x] **EVAL-05**: Residual distribution analysis (histogram, QQ plot, skew/kurtosis) to document target distribution and inform loss function choice

## Future Requirements

### Advanced Residual Modeling

- **ADV-01**: Asymmetric loss on residuals (requires careful sign convention analysis)
- **ADV-02**: Quantile residual models for confidence intervals
- **ADV-03**: Route-specific baseline weighting (optimize blend ratio per route)
- **ADV-04**: Cascade imputation for high-NaN features (route-level fallback instead of NaN)
- **ADV-05**: Feature pruning based on v1.1 SHAP analysis (remove features redundant with baseline)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Deployment/production API | Deferred until model accuracy validated |
| New data collection | Using existing Nov 6 - Dec 12 dataset |
| Per-route models | Single model approach maintained |
| Asymmetric loss | Start symmetric; add asymmetry in future milestone if needed |
| Feature set changes (add/remove) | Keep same 43 + baseline_eta only; prune after SHAP evidence |
| Redundant feature cleanup | Defer until v1.1 SHAP confirms which features are truly redundant |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BASE-01 | Phase 7 | Complete |
| BASE-02 | Phase 7 | Complete |
| BASE-03 | Phase 7 | Complete |
| BASE-04 | Phase 7 | Complete |
| BASE-05 | Phase 7 | Complete |
| TRAIN-01 | Phase 8 | Complete |
| TRAIN-02 | Phase 8 | Complete |
| TRAIN-03 | Phase 8 | Complete |
| TRAIN-04 | Phase 8 | Complete |
| TRAIN-05 | Phase 8 | Complete |
| EVAL-01 | Phase 9 | Complete |
| EVAL-02 | Phase 9 | Complete |
| EVAL-03 | Phase 9 | Complete |
| EVAL-04 | Phase 9 | Complete |
| EVAL-05 | Phase 9 | Complete |

**Coverage:**
- v1.1 requirements: 15 total
- Mapped to phases: 15
- Unmapped: 0

---
*Requirements defined: 2026-02-11*
*Last updated: 2026-02-17 after Phase 9 completion*
