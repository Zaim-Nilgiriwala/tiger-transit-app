# Phase 8: Training Adaptation - Context

**Gathered:** 2026-02-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Retrain the XGBoost model to predict residuals (actual - baseline_eta) instead of raw seconds, with fresh hyperparameter tuning optimized for the zero-centered residual target distribution. Outputs a trained v1.1 model that beats v1.0's 123.1s MAE when predictions are reconstructed (baseline_eta + predicted_residual).

</domain>

<decisions>
## Implementation Decisions

### Loss function & outlier handling
- Z-score threshold (2.5 sigma) for outlier trimming -- removes ~1.2% of training samples
- Compare both Huber and squared error loss on validation MAE + per-route breakdown
- Overall validation MAE is the deciding metric -- per-route breakdown is informational, not a tiebreaker
- If losses are close, overall MAE wins regardless of per-route differences

### Optuna study design
- 100 trials with fresh wide search ranges (no warm-start from v1.0)
- Tune 9 hyperparameters: learning_rate, max_depth, n_estimators, subsample, colsample_bytree, min_child_weight, reg_alpha, reg_lambda, **gamma** (added for residual targets)
- Use Optuna pruning to stop underperforming trials early
- Early stopping used within Optuna trials only -- final model trains for exact n_estimators from best trial (deterministic)

### Feature pipeline changes
- Add all three baseline features: baseline_s2s, baseline_seg_sum, baseline_eta (blended) -- lets model learn which baseline is better per-context
- Drop lateness_now (zero variance in v1.0, provides no signal)
- Final feature count: 45 (43 original - 1 dropped + 3 baselines)
- Keep time_to_arrival_seconds in parquets alongside residual target for easy reconstruction
- Modify existing v1.0 scripts in place (v1.0 preserved in git history)
- Feature importance analysis deferred to Phase 9 (full SHAP analysis there)

### GPU acceleration
- Use XGBoost gpu_hist tree method where GPU is available
- Auto-detect GPU and fall back to hist (CPU) if unavailable -- scripts work anywhere without manual config

### Claude's Discretion
- Exact Optuna search space ranges for each hyperparameter
- Huber delta parameter value
- Optuna pruning strategy and patience settings
- GPU detection implementation details
- Training convergence monitoring approach

</decisions>

<specifics>
## Specific Ideas

- User wants GPU used wherever possible to speed up training and tuning
- Deterministic final training (exact round count from Optuna, no early stopping in final model)
- Three baselines as features gives the model context about which baseline signal is strongest per prediction

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope

</deferred>

---

*Phase: 08-training-adaptation*
*Context gathered: 2026-02-11*
