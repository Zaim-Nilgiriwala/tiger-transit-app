# Project Research Summary

**Project:** Tiger Transit v1.1 Residual-Based ETA Prediction
**Domain:** Transit bus arrival time prediction using XGBoost
**Researched:** 2026-02-11
**Confidence:** HIGH

## Executive Summary

The v1.1 upgrade transforms the XGBoost ETA model from predicting raw arrival times (0-2000+ seconds) to predicting residuals (deviations from a historical baseline). This follows the industry-proven pattern used by Uber's DeepETA: a baseline predictor handles the structural component (distance, route, typical travel times), while the ML model focuses on explaining real-time deviations (traffic, weather, delays). The baseline is computed as the average of (1) summed segment medians along the route and (2) direct stop-to-stop historical averages, both derived exclusively from training data.

The critical architectural insight is that this approach requires NO new dependencies—the entire stack from v1.0 remains unchanged. The residual target fundamentally shifts which features matter: distance and stop-count features become redundant (absorbed by the baseline), while real-time condition features (speed anomalies, timepoint holds, weather) become dominant. The tighter, zero-centered residual distribution should help XGBoost focus capacity on learnable patterns rather than the gross time-distance relationship.

The primary risk is baseline quality variation by route. Routes with stable patterns (campus loops) will get excellent baselines, while sparse routes (Route 27 with only 96 test samples) may get poor baselines that the residual model cannot salvage. Three critical pitfalls must be avoided: (1) using test-period data to build baseline lookups (data leakage), (2) evaluating residual MAE instead of reconstructed final prediction MAE (meaningless metrics), and (3) missing baselines for sparse route/time combinations (requires robust fallback hierarchy).

## Key Findings

### Recommended Stack

**Verdict: No new libraries required.** The residual-based approach is a mathematical transformation of the target variable, not a new algorithmic technique. Every operation needed—historical aggregations, residual computation, baseline reconstruction, diagnostic plots—is already covered by the validated v1.0 stack.

**Core technologies (retained from v1.0):**
- **XGBoost 3.1.3**: Core gradient boosting engine — symmetric squared error loss works for zero-centered residuals; stay on 3.1.3 (3.2.0 released yesterday, too new)
- **pandas 2.3.3**: Historical lookups and baseline computation — groupby aggregations handle segment medians and stop-to-stop averages efficiently
- **NumPy 2.4.2**: Residual arithmetic and reconstruction — `residual = actual - baseline`, `final_eta = baseline + predicted_residual`
- **scikit-learn 1.8.0**: Evaluation metrics — MAE, RMSE on reconstructed predictions; scipy.stats comes free for residual diagnostics
- **Optuna 4.7.0**: Hyperparameter tuning — fresh study needed because residual distribution differs from raw-seconds distribution
- **pyarrow >=14.0**: Parquet I/O for historical lookup tables and augmented splits

**What NOT to add:**
- seaborn (matplotlib already handles residual plots)
- statsmodels (heavyweight, scipy.stats sufficient)
- XGBoost 3.2.0 (released Feb 10, day-one risk)
- pandas 3.0.0 (breaking changes, no benefit)
- Polars (baseline lookups are small, pandas fast enough)

### Expected Features

The residual target fundamentally changes feature importance. Features that encode route structure and distance become redundant (the baseline already captured that signal), while features that explain deviations from historical norms become dominant.

**Features gaining importance (explain deviations):**
- **speed_mean_{30,60,120,180}s**: Real-time traffic state — if current speed is slower than historical median, residual is positive (late)
- **speed_ratio**: Direct anomaly detector — `current_speed / historical_median_speed` literally generates the residual
- **time_until_next_timepoint_departure**: Timepoint holds are NOT in baseline medians — remains top feature
- **precipitation_mm**: Systematic weather slowdowns exceed average-weather baseline
- **acceleration**: Trend indicator (decelerating = approaching delay)
- **is_rush_hour / class_let_out_recently**: Temporal demand anomalies
- **timepoint_adherence**: Schedule deviation propagates to future delays
- **is_idle / seconds_idle**: Active real-time delay accumulation

**Features losing importance (absorbed by baseline):**
- **stop_index**: Was #2 in v1.0 (SHAP 120.2) — baseline already sums medians to this stop
- **distance_to_target**: Baseline is a function of distance
- **stops_remaining**: More stops = larger baseline; residual should not scale with stops
- **segment_travel_median/p25/p75**: These FEED the baseline — expect near-zero importance
- **pattern_id**: Was #3 in v1.0 (SHAP 119.0) — only route-specific deviation patterns remain relevant
- **scheduled_time_to_target**: Baseline uses actuals (more accurate than schedule)

**New features worth adding:**
- **baseline_eta** (P1 — required): The baseline value itself, so model knows residual context (10s residual on 30s baseline != 10s on 600s baseline)
- **baseline_confidence** (P2): Measure of baseline reliability (e.g., percentile spread) — model should know when baseline is uncertain
- **baseline_component_diff** (P2): Disagreement between segment-sum and stop-to-stop components signals unreliable baseline
- **lateness_at_last_timepoint** (P2): More informative than clock-time adherence for predicting upcoming holds

**Anti-features (avoid):**
- Using segment_travel_median as both feature AND baseline component (creates collinearity)
- Normalizing residuals by baseline_eta (predicting relative error creates heteroscedastic target)
- Removing "absorbed" features entirely (baseline is imperfect; features may capture baseline errors)
- Asymmetric loss on residuals initially (semantics change; start symmetric)

### Architecture Approach

The residual approach inserts a new pipeline step between temporal splitting and feature engineering. The existing 9-script pipeline gains one new script (`compute_baseline.py`) and modifies four existing scripts.

**Major components:**

1. **compute_baseline.py (NEW)** — Builds historical lookup tables from training data only, computes blended baseline ETA for all splits, generates residual labels
   - Input: `train.parquet`, `val.parquet`, `test.parquet`, `historical_segments.parquet`, `stop_sequences.parquet`
   - Output: `historical_stop_to_stop.parquet` (new lookup), augmented splits with `baseline_eta` and `residual` columns
   - Baseline formula: `avg(segment_median_sum, stop_to_stop_historical_avg)` with fallback hierarchy for sparse combinations

2. **build_differentiator_features.py (MODIFIED)** — Propagates baseline_eta and residual through feature pipeline, changes target column from `time_to_arrival_seconds` to `residual`
   - Add `baseline_eta` to `KEEP_EXTRA` list
   - Dual-target support: residual for training, baseline_eta for reconstruction
   - Retain all 43 existing features for first experiment (prune after SHAP analysis)

3. **train_*.py scripts (MODIFIED)** — Train on residual target with symmetric loss, reconstruct at evaluation
   - Change target: `y_train = df["residual"]` instead of `df["time_to_arrival_seconds"]`
   - Use `reg:squarederror` (symmetric) initially; defer asymmetric to v1.2
   - Fresh Optuna study (target distribution is zero-centered, not right-skewed)
   - At eval: `final_pred = baseline_eta + predicted_residual`, then compute MAE on final_pred

4. **evaluate.py (MODIFIED)** — Reconstruct predictions before all metrics, add baseline quality analysis
   - Load `baseline_eta` alongside features
   - Reconstruct: `predicted_arrival = baseline_eta + predicted_residual`
   - Report three MAEs: (1) v1.0 raw model (123.1s), (2) baseline-only, (3) v1.1 final
   - Add residual distribution analysis (should be centered ~0 if baseline is good)

**Data flow:**
```
[1-6] UNCHANGED: parse, explode, label, split
   |
[6.5] compute_baseline.py: Build lookups from TRAIN ONLY, apply to all splits
   |
[7b] build_differentiator_features.py: Add baseline_eta to features, target = residual
   |
[8] train_*.py: XGBoost predicts residual
   |
[9] evaluate.py: Reconstruct final_eta = baseline + residual, compare to v1.0
```

**Critical leakage prevention:**
- All baseline lookups built from `train.parquet` (Nov 6-29) ONLY
- Same frozen lookups applied to val/test for baseline computation
- Never include val/test data in historical aggregates

### Critical Pitfalls

1. **Baseline uses test-period data (data leakage)** — The baseline must be computed from training data (before Nov 30) exclusively. If validation (Dec 1-6) or test (Dec 8-18) data leaks into historical aggregates, the baseline will be biased toward test distribution, artificially reducing residuals and inflating evaluation metrics. **Prevention:** Build `historical_stop_to_stop.parquet` from `train.parquet` only; assert `max(baseline_source.timestamp) < val_start_date`.

2. **Evaluating residual MAE instead of final prediction MAE (meaningless metrics)** — The model predicts residuals, but the metric that matters is `MAE(actual_arrival, baseline_eta + predicted_residual)`, not `MAE(actual_residual, predicted_residual)`. Residual MAE of 80s tells you nothing about whether v1.1 beats v1.0's 123.1s MAE. **Prevention:** Always evaluate on reconstructed predictions; report three MAEs side-by-side: v1.0 raw, baseline-only, v1.1 final.

3. **Missing baseline for sparse route/stop/time combinations (data loss)** — Fine-grained `(route, stop, hour, day_type)` keys have limited observations in 24 days of training data. Route 27 (96 test samples) and evening/weekend runs are at risk. If both baseline components are NaN, residual is undefined. **Prevention:** Implement fallback hierarchy—(1) blended average, (2) segment-sum only, (3) route-level median, (4) scheduled_time_to_target. Report tier distribution; if >30% use tier 3+, baseline is too sparse.

4. **Heavy-tail residual distribution dominated by outliers under squared loss** — Residuals will have heavy tails (breakdowns, detours). A single +600s residual contributes 360,000 to squared loss, distorting the model to accommodate outliers. This is worse for residuals than raw targets because residuals can be extreme in both directions. **Prevention:** Plot residual distribution before training; if kurtosis > 5 or extreme outliers (>5x IQR), consider Huber loss (`reg:pseudohubererror`) or winsorize to [P1, P99].

5. **Segment-median sum accumulates errors over many stops (error propagation)** — The baseline sums 8+ segment medians for far stops. Errors compound if there's systematic bias (e.g., consistently underestimating a time-of-day). Routes with 15+ stops (Route 1) will have higher baseline error variance for far stops, creating heteroscedastic residuals. **Prevention:** Analyze baseline MAE by stops_remaining bucket; if growth is super-linear (3x+ at 7 stops vs 1 stop), consider weighting the two baseline components by distance (more weight to direct stop-to-stop for far stops).

## Implications for Roadmap

Based on combined research, the implementation requires three distinct phases: baseline infrastructure, feature/training adaptation, and evaluation/comparison. The dependency chain is strict—baseline must exist before residual labels can be created, residuals must exist before training, model must exist before evaluation.

### Phase 1: Baseline Infrastructure
**Rationale:** All downstream work depends on having valid baseline_eta and residual columns. This is the foundational data transformation that enables the entire residual approach.

**Delivers:**
- `compute_baseline.py` script that builds historical lookups and computes baselines
- `historical_stop_to_stop.parquet` lookup table (new artifact)
- Augmented `train/val/test.parquet` with `baseline_eta` and `residual` columns
- Baseline quality report (per-route MAE, fallback tier distribution, residual distribution stats)

**Addresses (from FEATURES.md):**
- Baseline computation logic (segment-sum + stop-to-stop blending)
- Fallback hierarchy for sparse combinations
- Residual label creation with correct sign convention

**Avoids (from PITFALLS.md):**
- Pitfall #2: Baseline uses test-period data (build from train.parquet only)
- Pitfall #3: Missing baseline for sparse combos (implement 4-tier fallback)
- Pitfall #14: Residual sign confusion (assert mean ~0, spot-check 3-5 rows)

**Success criteria:**
- Baseline-only MAE reported on test set (between 708.9s naive schedule and 123.1s v1.0 model)
- Residual distribution mean within +/-30s on training data
- No split has >5% NaN baselines after fallback
- Per-route baseline MAE variance <10x (identify problematic routes early)

### Phase 2: Feature and Training Adaptation
**Rationale:** With baselines computed, adapt the feature pipeline and training scripts to use residual targets. Fresh hyperparameter tuning is required because the residual distribution (zero-centered, tighter range) differs fundamentally from raw-seconds distribution (right-skewed, 0-2000+).

**Delivers:**
- Modified `build_differentiator_features.py` (propagates baseline_eta, target = residual)
- Modified `train_baseline.py` (symmetric squared error on residuals)
- Fresh Optuna study with adjusted search ranges for residual target
- Trained v1.1 model artifact with residual predictions
- SHAP analysis showing expected importance shift (speed features up, distance features down)

**Uses (from STACK.md):**
- XGBoost 3.1.3 with `reg:squarederror` objective
- Optuna 4.7.0 for fresh hyperparameter search
- pandas/NumPy for residual arithmetic and reconstruction
- scipy.stats (via scikit-learn) for residual distribution diagnostics

**Implements (from ARCHITECTURE.md):**
- Dual-target support in feature pipeline (residual for training, baseline_eta for reconstruction)
- Reconstruction at evaluation: `final_pred = baseline_eta + predicted_residual`
- All 43 existing features retained initially; add `baseline_eta` as feature #44

**Avoids (from PITFALLS.md):**
- Pitfall #8: Optuna search space not adjusted (fresh study with ranges tuned for residuals)
- Pitfall #5: Heavy-tail residuals dominate loss (check distribution before training; consider Huber if kurtosis > 5)
- Pitfall #1: Baseline leaking into features (run SHAP to confirm historical median features drop in importance)

**Success criteria:**
- Optuna best params differ from v1.0 (residual distribution is different)
- SHAP shows `speed_ratio` and `speed_mean_*` in top 5 (real-time features gain importance)
- SHAP shows `distance_to_target` and `stops_remaining` drop to bottom 10 (spatial features absorbed)
- Training converges without oscillation (residual distribution is learnable)

### Phase 3: Evaluation and Comparison
**Rationale:** The final test is whether v1.1 beats v1.0's 123.1s MAE on the same test set. The evaluation must reconstruct final predictions and compare apples-to-apples. This phase also establishes what the residual model contributes beyond the baseline alone.

**Delivers:**
- Modified `evaluate.py` with reconstruction logic and baseline-only comparison
- Side-by-side evaluation report: v1.0 raw MAE vs baseline-only MAE vs v1.1 final MAE
- Per-route breakdown (identify which routes benefit most from residual approach)
- Per-stops_remaining and per-hour slicing on reconstructed predictions
- Residual error analysis (are corrections helping or hurting?)

**Addresses (from FEATURES.md):**
- Validation that feature importance shifts occurred as predicted
- Identification of routes where baseline is insufficient (candidates for route-specific tuning)
- Decision on whether to prune low-importance features for v1.2

**Avoids (from PITFALLS.md):**
- Pitfall #4: Evaluating residual MAE not final MAE (all metrics on reconstructed predictions)
- Pitfall #11: Not comparing against baseline-only (report baseline-only MAE as context)
- Pitfall #13: MAPE on residuals (MAPE only on final predictions, not residuals)

**Success criteria:**
- v1.1 final MAE < 123.1s (beats v1.0 on same test set)
- Baseline-only MAE provides context (gap between baseline and v1.1 shows model contribution)
- Per-route evaluation identifies winners and losers (some routes may not benefit)
- Residual predictions improve baseline (positive contribution, not hurting)

### Phase Ordering Rationale

- **Phase 1 first:** All downstream scripts depend on `baseline_eta` and `residual` columns existing in parquets. Cannot train or evaluate without baseline.
- **Phase 2 before Phase 3:** Evaluation needs a trained model. Training needs residual targets.
- **Within Phase 2:** Modify feature pipeline before training scripts (training imports from feature pipeline module). Train baseline model before Optuna (verify approach works before investing compute in tuning).
- **No parallelization:** Strict dependency chain. Each phase consumes outputs of previous phase.

**Dependencies discovered from research:**
- Baseline computation requires `historical_segments.parquet` (already exists from v1.0 feature pipeline)
- Baseline uses `stop_sequences.parquet` for route traversal (already exists from GTFS parsing)
- Residual labels require both actual arrival labels AND baseline_eta (circular dependency avoided by temporal holdout)
- Evaluation requires baseline_eta propagated through to test_featured_v2.parquet

### Research Flags

**Needs research during planning:**
- **Phase 1 (baseline):** STANDARD PATTERN — pandas groupby aggregations and lookup merges are well-documented. Skip `/gsd:research-phase`. Uber DeepETA blog provides architectural precedent.
- **Phase 2 (training):** STANDARD PATTERN — XGBoost residual prediction with symmetric loss is straightforward. Optuna tuning follows same process as v1.0. Skip research unless heavy-tail distribution requires Huber loss investigation.
- **Phase 3 (evaluation):** STANDARD PATTERN — Reconstruction is simple arithmetic. Evaluation framework exists. Skip research.

**Standard patterns (no additional research needed):**
- Historical lookup table construction (v1.0 already does this for segments/dwells)
- Residual computation and reconstruction (basic arithmetic)
- XGBoost training with changed target (same API, different column)
- SHAP analysis (same process as v1.0)

**Potential research triggers during implementation:**
- If baseline-only MAE > 300s (much worse than expected): research better baseline algorithms
- If residual distribution has kurtosis > 8 (extreme outliers): research robust loss functions beyond Huber
- If Route 27/235 have >50% missing baselines: research sparse-data baseline strategies

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | No new dependencies needed. All operations covered by v1.0 stack. XGBoost docs confirm `reg:squarederror` works for residuals. |
| Features | MEDIUM-HIGH | Theoretical predictions about importance shifts are sound (based on what baseline captures), but actual SHAP rankings need empirical validation. New features (baseline_eta, baseline_confidence) are novel. |
| Architecture | HIGH | Pipeline modifications are well-defined. Uber DeepETA validates the residual approach at scale. Codebase inspection confirms exact integration points. |
| Pitfalls | HIGH | Grounded in codebase analysis and XGBoost best practices. Data leakage, evaluation metrics, and sparse baseline pitfalls are well-documented risks. |

**Overall confidence:** HIGH

The residual-based approach is a proven pattern (Uber DeepETA, DeeprETA paper) applied to an existing validated pipeline. The stack requires zero changes (high confidence there). The architecture is a single new script plus minor modifications to four existing scripts (well-scoped). The primary uncertainty is empirical: will the baseline be good enough (expected MAE 200-400s) and will the residual model learn meaningful corrections? These questions can only be answered by building Phase 1 and measuring baseline quality.

### Gaps to Address

**Gap 1: Baseline quality is unknowable until built**
- Research predicts baseline MAE between 200-400s (between naive schedule at 708.9s and v1.0 at 123.1s), but this is untested.
- **Mitigation:** Phase 1 includes baseline quality report. If baseline-only MAE > 300s, the residual model faces an uphill battle. Consider this a "fail fast" checkpoint before investing in Phases 2-3.

**Gap 2: Optimal baseline blending weights are assumed equal (50/50)**
- The baseline averages segment-sum and stop-to-stop components with equal weight. This is simple but may be suboptimal (one component might be consistently better).
- **Mitigation:** Start with equal weights for v1.1. If baseline quality varies dramatically by route/distance, consider learned per-route weights in v1.2.

**Gap 3: Feature importance shifts are predicted but not validated**
- The theory says `speed_ratio` and real-time features should gain importance while `distance_to_target` should drop. This is logical but unproven on Tiger Transit data.
- **Mitigation:** Phase 2 includes SHAP analysis as a success criterion. If importance patterns do NOT shift as predicted, it signals the baseline is not capturing what we think it is.

**Gap 4: Route 27 and Route 235 may have insufficient baseline coverage**
- Route 27 has only 96 test samples. Route 235 has no timepoint data. Sparse routes may have >30% NaN baselines even with fallback.
- **Mitigation:** Phase 1 reports per-route fallback tier distribution. If Route 27/235 are unrecoverable, document this as a known limitation and exclude from v1.1 evaluation (same as v1.0 handled sparse routes).

**Gap 5: Asymmetric loss semantics for residuals are deferred**
- v1.0 used 3:1 asymmetric loss (penalize overprediction). For residuals, the sign convention changes and applying asymmetric loss is non-trivial. Starting with symmetric loss is safe but may leave performance on the table.
- **Mitigation:** Defer asymmetric loss to v1.2 after establishing symmetric baseline. Unit test sign conventions carefully if/when adding asymmetric.

## Sources

### Primary (HIGH confidence)
- Existing codebase: `build_differentiator_features.py`, `train_baseline.py`, `evaluate.py`, `temporal_split.py` — Direct inspection of all scripts, column names, data flow, existing feature engineering
- XGBoost 3.1.3 documentation: Parameters, base_score auto-estimation, reg:squarederror objective — Official docs confirm behavior with zero-centered targets
- pandas 2.3.3 documentation: groupby aggregations for baseline computation — Standard pandas operations
- v1.0 SHAP rankings: `eval_shap_meta.json`, `eval_report.md` — Empirical feature importance baseline for comparison

### Secondary (MEDIUM confidence)
- Uber DeepETA blog post — Industry precedent for baseline + residual architecture, but different domain (rideshare, not transit)
- DeeprETA paper (arXiv 2206.02127) — Post-processing residual ETA at scale, validates approach
- Google Maps ETA with GNNs (arXiv 2108.11482) — Discusses supersegment approach to avoid segment accumulation errors
- Transit App blog on ETA prediction challenges — Domain expertise on transit-specific pitfalls
- MachineLearningMastery residual modeling tutorial — General technique for residual correction in forecasting

### Tertiary (LOW confidence)
- Mathematical collinearity effects paper — Theory on correlated features in tree models, but abstract (not transit-specific)
- Hybrid LSTM-XGBoost residual paper (Springer) — Different domain (air quality), but validates residual correction pattern

---
*Research completed: 2026-02-11*
*Ready for roadmap: yes*
