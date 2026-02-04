# Phase 5: Advanced Training - Context

**Gathered:** 2026-02-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Optimize the differentiator model (175.7s MAE) with asymmetric loss, Optuna hyperparameter tuning, and quantile predictions. No new features are added — this phase is purely training configuration. Produces tuned point-prediction and quantile models as final artifacts.

</domain>

<decisions>
## Implementation Decisions

### Loss Asymmetry
- **Direction:** Penalize overestimation of time-to-arrival (predicting bus is further than reality, causing riders to miss buses)
- **Penalty ratio:** 3:1 aggressive — overestimation errors penalized 3x vs underestimation
- **Proximity scaling:** Penalty ramps up as predicted time decreases, with 8-minute threshold (campus walking distance consideration)
- **Scaling dimension:** Time-only (not stops_remaining)
- **Fresh design:** Do not replicate PyTorch loss formula — design optimal custom objective for XGBoost
- **Validation metric:** Median residual sign — should be slightly negative (model predicts bus arrives sooner than reality)
- **MAE tradeoff:** Claude's discretion — balance rider protection vs raw accuracy based on actual numbers

### Tuning Strategy
- **CV method:** Claude's discretion (TimeSeriesSplit vs GroupKFold) — pick what works best with 5 weeks of data
- **Trial count:** Claude's discretion — based on search space size and data volume (minimum 100 per roadmap)
- **Optuna objective:** Minimize MAE (not asymmetric loss) — asymmetric loss shapes training gradients but MAE is the scoreboard
- **Loss parameter tuning:** Claude's discretion — decide whether to include penalty ratio/threshold in Optuna search space or fix them

### Quantile Outputs
- **App display:** Show range to rider (e.g., "arriving in 3-6 min")
- **Default range pair:** P20 / P75 (asymmetric — optimistic lower bound, moderately conservative ceiling)
- **Quantiles to train:** Minimal set — P20, P50, P75 (3 quantiles)
- **Narrow range behavior:** Collapse to single number (P50) when P20 and P75 are within ~1 min

### Training Pipeline
- **Step order:** 1) Optuna tunes with squared error loss, 2) Retrain best params with asymmetric loss, 3) Train quantile models with best params
- **Checkpoints:** Save all intermediate models (Optuna best, asymmetric, quantile) for comparison and rollback
- **Production artifacts:** Both deployed — asymmetric model for primary ETA, quantile model for range display
- **Comparison output:** Auto-generate full comparison table (naive -> baseline -> differentiator -> tuned -> asymmetric) across all phase checkpoints

</decisions>

<specifics>
## Specific Ideas

- Asymmetric range P20/P75 intentionally mirrors the loss asymmetry — tighter on the conservative side, more buffer on the optimistic side
- 8-minute proximity threshold chosen for campus context (typical walking time from building to bus stop)
- Rider-facing display: show range when wide, collapse to single number when predictions are confident

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 05-advanced-training*
*Context gathered: 2026-02-04*
