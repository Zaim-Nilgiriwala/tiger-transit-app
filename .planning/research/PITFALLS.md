# Pitfalls Research: Residual-Based ETA Prediction

**Domain:** Residual (actual - baseline_ETA) target for XGBoost transit ETA model
**Researched:** 2026-02-11
**Confidence:** HIGH (grounded in codebase analysis, verified ML principles, Uber DeeprETA architecture, XGBoost documentation)

---

## Critical Pitfalls

Mistakes that cause the v1.1 model to perform worse than v1.0, produce incorrect evaluations, or require rework of the approach.

### Pitfall 1: Baseline Leaking into Features

**What goes wrong:**
The baseline ETA is computed as the average of (sum of segment medians from current to target) and (direct stop-to-stop historical average). Many of the existing 43 features are derived from the same historical aggregates used to build the baseline. For example, `segment_travel_median`, `segment_travel_p25`, `segment_travel_p75`, `dwell_median`, `dwell_p25`, `dwell_p75`, `target_dwell_median`, and `scheduled_time_to_target` all overlap heavily with the baseline computation. If these features appear in the model alongside the residual target, the model is learning to reconstruct part of the baseline it was subtracted from. This is not data leakage in the traditional sense -- the model will not get suspiciously good results -- but it creates multicollinearity and wastes model capacity on learning trivially recoverable information. Worse, the model may learn to "un-subtract" the baseline instead of learning genuinely useful deviation patterns.

**Why it happens:**
The v1.0 feature set was designed for raw time prediction, where historical medians are strong predictive features. When switching to residual targets, features that explain the baseline's behavior become near-constant or near-zero in their relationship to the residual (since the baseline already captured that signal). The developer reuses the same 43 features without auditing which ones still carry signal for the residual target.

**How to avoid:**
- Audit each of the 43 features against the baseline formula. Features that are direct inputs to the baseline (segment medians, stop-to-stop historical averages) will have degraded signal for the residual target.
- Do NOT drop these features outright without testing. Some may still carry residual signal if the baseline uses coarser aggregation (e.g., overall median) while the feature has finer granularity (e.g., hour+day_type median). The p25/p75 features encode *variance* not captured by the baseline's median.
- Run SHAP analysis on the residual model after initial training. If `segment_travel_median` or `dwell_median` have near-zero SHAP importance, they are redundant and can be removed to reduce noise.
- Consider adding new features that capture what the baseline *cannot*: current-trip speed anomalies (speed_ratio, rolling speed deviations), real-time delay propagation, timepoint hold state.

**Warning signs:**
- SHAP importance for historical median features drops to near-zero in the residual model vs. their high importance in v1.0.
- Model predictions are tightly clustered near zero regardless of actual residual magnitude (model learned that baseline explains everything).
- Features like `segment_travel_median` and `distance_to_target` have almost identical SHAP profiles (they encode overlapping information).

**Phase to address:**
Feature engineering / baseline computation phase. Audit features before training, but keep all 43 for the first experiment; prune after SHAP analysis.

---

### Pitfall 2: Baseline Computation Uses Test-Period Data

**What goes wrong:**
The baseline ETA relies on historical segment medians and stop-to-stop historical averages. These aggregates must be computed exclusively from training data (Nov 6 - Nov 29). If the baseline computation inadvertently includes validation (Dec 1-6) or test (Dec 8-18) period data, the baseline will be biased toward the test distribution, making the residual target artificially smaller and the model's job easier. The evaluation will show improvement that will not generalize.

The current `build_differentiator_features.py` correctly computes historical aggregates from training pings only (lines 1006-1043). However, the new baseline computation is a separate pipeline step that must respect the same boundary. If the baseline is computed from a single call across the full labeled dataset, it will incorporate future data.

**Why it happens:**
The baseline computation is a new piece of code added for v1.1. It is tempting to compute "all historical medians" from the entire arrivals dataset for simplicity. The temporal split boundaries from `temporal_split.py` (train ends Nov 29, 1-day gap, val starts Dec 1) must be enforced again in the baseline computation code.

**How to avoid:**
- Compute segment medians and stop-to-stop historical averages using only data from the training period (before Nov 30).
- Store the precomputed baseline lookup tables as parquet files (analogous to `historical_segments.parquet` and `historical_dwells.parquet` in the current pipeline).
- Apply the same lookup tables to compute baseline_ETA for train, val, and test rows. The lookup is "frozen" at training time -- it does not adapt per split.
- Add an assertion: `max(baseline_computation_data.timestamp) < val_start_date`.

**Warning signs:**
- Baseline MAE on test set is suspiciously close to or lower than on training set.
- Residual distribution on test set is narrower than on training set (baseline "knows" the test period).
- Performance degrades significantly when deploying with genuinely new data.

**Phase to address:**
Baseline computation phase. Must be the first step, before residual labels are created.

---

### Pitfall 3: Missing Baseline for Sparse Route/Stop/Time Combinations

**What goes wrong:**
The baseline uses two components averaged together: (1) sum of segment medians from current to target, and (2) direct stop-to-stop historical average. Both require sufficient historical observations. The existing historical aggregates use `MIN_OBS = 10` and set sparse combinations to NaN. For the baseline, a NaN in any segment between current and target stop makes the segment-sum component undefined. A NaN in the stop-to-stop lookup makes the direct component undefined.

If both components are NaN, the baseline_ETA is undefined and the residual cannot be computed. These rows must be dropped from training, reducing data volume. If only one component is NaN, the "average of two" degrades to a single estimate with higher variance. Route 27 (only 96 test samples) and Route 235 (no timepoint data) are especially at risk, as are evening/weekend combinations where transit operates at reduced frequency.

**Why it happens:**
5 weeks of training data (Nov 6-29 = 24 days, including weekends) provides limited coverage for fine-grained (route, stop, hour, day_type) combinations. Some segments have fewer than 10 observations in the training period.

**How to avoid:**
- Implement a fallback hierarchy for missing baseline components:
  1. Primary: average of (segment-median sum, stop-to-stop historical average)
  2. If stop-to-stop historical is NaN: use segment-median sum alone
  3. If any segment median is NaN: use route-level fallback median for that segment (aggregated across all hours/day_types)
  4. If stop-to-stop and segment sum both NaN: use scheduled_time_to_target as baseline
- Track and report what fraction of rows use each fallback tier. If >20% use tier 3+, the baseline is too sparse.
- Do NOT drop rows with missing baseline. Fill with fallback values so the model can still train on these examples. The residual for fallback-baseline rows will be noisier, which is acceptable.

**Warning signs:**
- Significant drop in training data volume after baseline computation (>5% rows lost).
- Route 27 or Route 235 have mostly NaN baselines.
- Baseline MAE varies wildly by route (some routes have good baselines, others are near-random).
- The "average of two components" is actually "one component" for >30% of rows.

**Phase to address:**
Baseline computation phase. Implement fallback hierarchy and report tier distribution before computing residuals.

---

### Pitfall 4: Evaluating Residual Model MAE Instead of Final Prediction MAE

**What goes wrong:**
The residual model predicts `residual_hat = f(features)`. The metric that matters is `MAE(actual_arrival, baseline_ETA + residual_hat)`, not `MAE(actual_residual, residual_hat)`. If the developer optimizes and reports the residual MAE, it is meaningless for comparison to v1.0's 123.1s MAE. A residual MAE of 50s sounds great but says nothing about whether the final prediction (baseline + residual) beats v1.0.

Furthermore, the residual MAE can be low even if the final prediction MAE is high. Consider: if the baseline is systematically 200s too high for a route, and the model learns to predict residuals of -200s, the residual MAE might be small, but the final prediction accuracy depends entirely on how well the model captures this -200s bias. If the model predicts -180s instead of -200s, the residual MAE is only 20s (great!) but the final prediction is still 20s off (which may or may not beat v1.0).

**Why it happens:**
The training loop naturally reports the loss on the target variable, which is the residual. XGBoost's eval_metric will report MAE on residuals during training. The developer sees "val MAE: 80s" and thinks this is the model's performance, forgetting that the final prediction requires adding the baseline back.

**How to avoid:**
- Always evaluate on the reconstituted prediction: `final_pred = baseline_ETA + predicted_residual`.
- Compute MAE, RMSE, MAPE on `(y_actual, final_pred)` and compare directly to v1.0's 123.1s MAE on the same test set.
- Add a custom XGBoost eval function that reconstructs final predictions during training:
  ```python
  def final_mae(predt, dtrain):
      residuals = dtrain.get_label()
      baselines = dtrain.get_weight()  # or stored separately
      actual = baselines + residuals
      final_pred = baselines + predt
      mae = float(np.mean(np.abs(actual - final_pred)))
      return 'final_mae', mae
  ```
  (This is actually identical to residual MAE, but making it explicit prevents confusion.)
- In the evaluation script, compute side-by-side: v1.0 raw MAE vs. v1.1 (baseline + residual) MAE on the same test rows.
- Report baseline-only MAE as a sanity check: `MAE(actual, baseline_ETA)`. If this is already close to 123.1s, the model needs to provide meaningful correction to beat v1.0.

**Warning signs:**
- Developer reports "v1.1 residual MAE = 80s" without converting to final prediction MAE.
- Final prediction MAE is worse than baseline-only MAE (model's corrections are hurting, not helping).
- Final prediction MAE and residual MAE are numerically identical (correct, but developer must understand why).

**Phase to address:**
Evaluation phase. Build the comparison framework before training so the evaluation is set up correctly from the start.

---

### Pitfall 5: Residual Distribution Has Heavy Tails and Outliers That Dominate Squared Loss

**What goes wrong:**
The residual (actual - baseline_ETA) distribution will not be a clean normal centered at zero. It will have:
- Heavy positive tail: trips where the bus was much slower than historical average (breakdowns, severe traffic, detours).
- Heavy negative tail: trips where the bus was much faster than historical average (empty roads, skipped stops).
- Multimodal patterns: some routes' baselines are systematically wrong in one direction.

With `reg:squarederror` (symmetric squared error), these tail observations contribute disproportionately to the loss. A single observation with residual = 600s (10 minutes off baseline) contributes 360,000 to the squared error, dominating thousands of well-predicted observations. The model will distort its predictions to accommodate outliers, worsening the majority of predictions.

This is a *bigger* problem for residual targets than for raw targets. Raw time_to_arrival_seconds is always positive and has a natural distribution. Residuals can be extreme in either direction, and the squared loss amplifies extremes.

**Why it happens:**
The project spec says "symmetric squared error loss, no asymmetric initially." This is a reasonable starting point, but the residual distribution may be poorly suited to squared loss. The v1.0 model used asymmetric loss (3:1 overestimation penalty) which partially handled this by not over-penalizing one direction.

**How to avoid:**
- Before training, plot the residual distribution. Compute skewness, kurtosis, and check for extreme tails.
- If residual distribution has kurtosis > 5 or extreme outliers (|residual| > 5x IQR), consider:
  1. Huber loss (`reg:pseudohubererror` in XGBoost) which is quadratic near zero but linear for large residuals.
  2. Winsorizing residuals: clip to [P1, P99] percentile before training.
  3. MAE loss (`reg:absoluteerror`) which is more robust to outliers but has slower convergence.
- Start with `reg:squarederror` as planned but compare against `reg:pseudohubererror` early.
- Report residual distribution statistics (mean, median, std, skewness, kurtosis, P1, P5, P95, P99) before training.

**Warning signs:**
- Residual distribution has skewness > |1.0| or kurtosis > 5.
- Model's predicted residuals cluster tightly near zero while actual residuals span [-500, +500].
- Training loss decreases but validation loss oscillates or increases.
- Per-route evaluation shows the model is very good at some routes but terrible at others (outlier routes dominating the loss).

**Phase to address:**
Residual computation phase (analyze distribution) and training phase (select appropriate loss). Run distribution analysis before choosing loss function.

---

### Pitfall 6: Segment-Median Sum Accumulates Errors Over Many Stops

**What goes wrong:**
The baseline component "sum of segment medians from current to target" chains individual segment-level estimates. If the bus is 8 stops away, the baseline sums 8 separate median values. Each median has estimation error. These errors do NOT cancel out on average if there is systematic bias (e.g., medians consistently underestimate a particular time-of-day or direction). The error grows roughly proportionally to the number of segments summed.

This is the "error accumulation" problem well-documented in ETA literature. Uber's routing engine faces the same issue and mitigates it with supersegment-level predictions rather than pure segment sums. Google Maps uses a GNN that predicts cumulative rather than per-segment times to avoid this.

For the Tiger Transit model, routes with many stops (like Route 1 with up to 15+ stops in a trip) will have baseline errors that grow with stops_remaining. This means the residual target will have higher variance for far-away stops, creating heteroscedasticity in the target variable.

**Why it happens:**
Summing independent estimates is the natural approach but ignores that segment travel times are correlated. If one segment is slow (traffic, construction), adjacent segments are likely slow too. The median captures the central tendency but not the correlation structure.

**How to avoid:**
- The baseline already averages the segment-sum with a direct stop-to-stop historical average, which partially mitigates accumulation (the direct average is a single estimate, not a chain). This is good design.
- Analyze baseline accuracy by stops_remaining bucket. If baseline MAE grows faster than linearly with stops_remaining, accumulation is a problem.
- Consider weighting the two baseline components: give more weight to the direct stop-to-stop average for far stops (where segment accumulation is worst) and more weight to segment-sum for near stops (where it is most accurate because fewer segments are summed).
- Add `stops_remaining` (or `stops_away`) as an interaction with the residual -- the model can learn that residuals are systematically larger for farther stops.

**Warning signs:**
- Baseline MAE at 7+ stops is 3x or more than baseline MAE at 1 stop (disproportionate growth).
- Residual variance at 7+ stops is 3x residual variance at 1 stop.
- The model's predicted residual magnitude increases with stops_remaining (it is learning to correct the accumulation, which is good, but indicates the baseline is weak for far stops).

**Phase to address:**
Baseline computation phase (analyze accuracy by stops_remaining) and evaluation phase (check for heteroscedastic residuals).

---

### Pitfall 7: Asymmetric Loss Semantics Change for Residual Targets

**What goes wrong:**
In v1.0, the 3:1 asymmetric loss penalized overprediction (pred > actual) more than underprediction. The rationale: if the model says the bus arrives in 5 minutes but it arrives in 3 minutes, the rider misses the bus. This makes sense for raw time_to_arrival predictions.

For residual targets, the semantics flip. The residual = actual - baseline. A positive residual means the bus took longer than the baseline predicted. If the model predicts residual_hat > actual_residual, the final prediction (baseline + residual_hat) overpredicts the arrival time. So the penalty direction is the same in terms of the residual sign, but the mapping from "residual error" to "rider experience" is indirect and confusing.

If a developer applies v1.0's asymmetric loss formula directly to residual targets without rethinking the sign convention, the penalty direction may be inverted, causing the model to optimize in the wrong direction.

**Why it happens:**
The v1.0 asymmetric loss was defined as:
```python
error = pred - actual  # positive = overprediction
grad = np.where(error > 0, 2 * alpha * error, 2 * error)
```
For raw targets, `pred - actual > 0` means "predicted arrival later than actual" = overprediction = bad.
For residual targets, `pred - actual > 0` means "predicted residual larger than actual residual." If actual residual is negative (bus was early), predicting a larger residual (closer to zero or positive) means predicting the bus is later than it actually is = still overprediction in absolute terms. The sign convention is preserved, but only if `error = pred_residual - actual_residual`, not if someone redefines the residual direction.

**How to avoid:**
- The project spec says "symmetric squared error first, no asymmetric initially." Follow this. Do not port the asymmetric loss to residual targets in the first iteration.
- If/when adding asymmetric loss later, verify sign conventions with a unit test:
  - Create a sample where actual residual = -10 (bus was 10s early relative to baseline)
  - Model predicts residual = +5 (bus would be 5s late relative to baseline)
  - Error = +5 - (-10) = +15. Final prediction overpredicts by 15s. This SHOULD be penalized with alpha multiplier.
  - Confirm gradient direction.
- Document the sign convention explicitly in code comments.

**Warning signs:**
- Asymmetric model systematically underpredicts instead of overpredicting (penalty direction reversed).
- Signed residuals on test set have opposite skew from v1.0 model.
- The model appears to ignore the asymmetry (produces symmetric residual distribution despite 3:1 penalty).

**Phase to address:**
Training phase. Use symmetric loss in first iteration. Only add asymmetric after verifying sign conventions.

---

## Moderate Pitfalls

Mistakes that cause delays, suboptimal results, or technical debt.

### Pitfall 8: Optuna Search Space Not Adjusted for Residual Target Distribution

**What goes wrong:**
v1.0's Optuna search found optimal params for predicting raw seconds (target range 0-2000+, mean ~300s). The residual target is centered near zero with a much narrower range (likely -300 to +300, mean ~0). The optimal hyperparameters will differ:
- `learning_rate`: May need to be lower because the target scale is smaller, or higher because the pattern is simpler.
- `max_depth`: The residual may require shallower trees since the dominant signal (distance/time) has been removed by the baseline.
- `num_boost_round`: May need fewer rounds since there is less signal to capture.
- `min_child_weight`: May need adjustment because the label distribution is different.

Reusing v1.0's search ranges or optimal params directly will likely produce suboptimal results.

**How to avoid:**
- Run a fresh Optuna study from scratch. Do not warm-start from v1.0's study.
- Adjust search ranges based on the residual distribution:
  - `learning_rate`: [0.01, 0.5] (wider range, since optimal may shift)
  - `max_depth`: [2, 6] (likely shallower than v1.0's 8)
  - `num_boost_round`: [100, 500] (likely fewer than v1.0's 600)
- Use the same `reg:squarederror` objective for initial Optuna runs.
- After Optuna, verify that the best params differ meaningfully from v1.0's params. If they are nearly identical, something may be wrong (the residual distribution should call for different params).

**Warning signs:**
- Optuna best params are identical to v1.0's params (unlikely if the target distribution changed).
- Best `max_depth` is >= 7 for residual targets (suggests model is overfitting to noise).
- Best `num_boost_round` is > 1000 for residual targets (suggests model is chasing noise).

**Phase to address:**
Training phase. Fresh Optuna study with adjusted search ranges.

---

### Pitfall 9: Baseline Quality Varies Dramatically by Route

**What goes wrong:**
The baseline's accuracy depends on how stable/predictable each route is. Some routes (short campus loops, consistent ridership) will have excellent baselines (MAE < 30s). Others (long routes through city traffic, Route 27 with sparse data) will have poor baselines (MAE > 200s). The residual distribution will be route-dependent: tight and centered for easy routes, wide and possibly biased for hard routes.

XGBoost trains a single model across all routes. If the residual variance is 10x higher for hard routes, the model's capacity will be disproportionately consumed by hard-route outliers. Easy routes (where the residual is already small) get negligible improvement.

**How to avoid:**
- Before training, compute and report baseline MAE per route. This is the "floor" that the residual model cannot improve upon -- it can only correct errors the baseline makes, not errors in the data.
- If baseline MAE varies by more than 5x across routes, consider route-specific baseline calibration (e.g., multiplicative correction factors per route computed from training data).
- The model should naturally learn route-specific corrections (route_id is a categorical feature), but verify this with per-route evaluation.

**Warning signs:**
- Baseline MAE ranges from 20s (best route) to 300s (worst route).
- The residual model's improvement is concentrated on 2-3 routes while others see negligible change.
- Routes where baseline MAE > 150s show no improvement from the residual model (model cannot learn corrections for noisy baselines).

**Phase to address:**
Baseline computation phase (compute per-route baseline MAE) and evaluation phase (per-route comparison).

---

### Pitfall 10: Forgetting to Store and Propagate baseline_ETA for Inference

**What goes wrong:**
At inference time, the final prediction is `baseline_ETA + predicted_residual`. The baseline_ETA must be computed for every prediction request using the same historical aggregates (frozen from training data). If the inference pipeline does not have access to the baseline computation, or if the baseline lookup tables are not serialized alongside the model, the model is useless.

In the current v1.0 pipeline, the model directly outputs `time_to_arrival_seconds` -- no additional computation needed at inference. Switching to residual prediction adds a dependency: the baseline computation must be available at prediction time.

**How to avoid:**
- Save the baseline lookup tables (segment medians, stop-to-stop averages) as serialized artifacts alongside the model file.
- Include the baseline computation function in the inference pipeline.
- Store `baseline_ETA` as a column in the test/val parquets so evaluation can reconstruct predictions without re-running baseline computation.
- Test the end-to-end inference pipeline: raw telemetry -> baseline computation -> feature engineering -> model prediction -> final_ETA = baseline + residual.

**Warning signs:**
- Evaluation script cannot reconstruct final predictions because baseline_ETA was not saved.
- Baseline lookup tables are regenerated at inference time from different data (should be frozen from training).
- `baseline_ETA` column is missing from featured parquets.

**Phase to address:**
Baseline computation phase (save artifacts) and evaluation phase (verify end-to-end pipeline).

---

### Pitfall 11: Not Comparing Against Baseline-Only Prediction

**What goes wrong:**
If the baseline itself achieves MAE < 123.1s (v1.0's result), then the entire residual model is unnecessary -- just use the baseline. If the baseline achieves MAE = 130s, the residual model only needs to shave off 7s, which may not justify the complexity. If the baseline achieves MAE = 200s, the residual model needs to contribute 77s of correction, which is ambitious.

Without knowing the baseline-only MAE, you cannot assess whether the residual approach is viable or how much correction the model needs to provide.

**How to avoid:**
- Compute baseline-only MAE on the test set BEFORE training any model.
- Report three numbers side-by-side:
  1. v1.0 raw model MAE (123.1s)
  2. Baseline-only MAE (baseline_ETA vs actual)
  3. v1.1 residual model MAE (baseline_ETA + residual_hat vs actual)
- The gap between (2) and (3) is what the ML model contributes. The gap between (1) and (3) is whether v1.1 beats v1.0.

**Warning signs:**
- Baseline-only MAE is already better than v1.0 (no model needed, just use baseline).
- Baseline-only MAE is much worse than v1.0 (200s+), making it unlikely the residual model can close the gap.
- Developer does not compute baseline-only MAE at all.

**Phase to address:**
Baseline computation phase. Report baseline-only MAE immediately after computing baselines.

---

## Minor Pitfalls

Mistakes that cause annoyance but are recoverable.

### Pitfall 12: XGBoost base_score Default Inappropriate for Zero-Centered Residuals

**What goes wrong:**
XGBoost versions >= 2.0 automatically estimate `base_score` from the training labels. For residual targets centered near zero, `base_score` will be estimated as approximately 0, which is correct. However, if using an older XGBoost version (< 2.0), `base_score` defaults to 0.5. For a residual target with mean ~0, starting all predictions at 0.5 adds a constant bias that the first trees must correct, wasting rounds.

**How to avoid:**
- Verify XGBoost version is >= 2.0 (which auto-estimates base_score). The v1.0 pipeline already uses `xgb.train()` with modern parameters.
- If unsure, explicitly set `base_score=0` in the params dict.
- This is self-correcting with enough rounds (trees will compensate), so it is low severity.

**Warning signs:**
- First few training iterations show large loss (model correcting the 0.5 offset).
- Very short training runs (< 50 rounds) show a constant bias in predictions.

**Phase to address:**
Training configuration phase. One-line param addition.

---

### Pitfall 13: MAPE Undefined or Misleading for Residual Targets Near Zero

**What goes wrong:**
MAPE (Mean Absolute Percentage Error) divides by the actual value: `|pred - actual| / |actual|`. For residual targets near zero, this denominator approaches zero, causing MAPE to explode to infinity or NaN for well-predicted observations where the actual residual is small. MAPE becomes meaningless as an evaluation metric for residual targets.

The v1.0 evaluation script already uses MAPE (see `evaluate.py` line 83-88). If applied to residual targets, it will produce garbage numbers.

**How to avoid:**
- Do NOT compute MAPE on residual targets. It is mathematically inappropriate.
- Compute MAPE on final predictions only: `|actual_arrival - final_pred| / |actual_arrival|`, where actual_arrival and final_pred are both positive (arrival times in seconds).
- Use MAE and RMSE as primary metrics for the residual model.

**Warning signs:**
- MAPE values in the thousands or NaN in evaluation output.
- MAPE appears to improve dramatically when it should not.

**Phase to address:**
Evaluation phase. Remove MAPE from residual evaluation, keep it only for final prediction evaluation.

---

### Pitfall 14: Residual Sign Convention Confusion

**What goes wrong:**
The residual is defined as `actual - baseline_ETA`. A positive residual means the bus arrived later than the baseline predicted (bus was slow). A negative residual means the bus arrived earlier (bus was fast). This is the natural convention, but it is easy to accidentally reverse it (`baseline_ETA - actual`) during implementation, which flips the meaning of the model's output.

If the sign is reversed during label creation but correct during evaluation (or vice versa), all predictions will be inverted: the model will add corrections when it should subtract, and vice versa.

**How to avoid:**
- Define the convention explicitly in a constant: `RESIDUAL_CONVENTION = "actual_minus_baseline"`.
- Add a sanity check: the mean residual on training data should be close to zero (within +/-30s). If it is consistently large in one direction, either the baseline is biased or the sign is wrong.
- Verify with a spot check: pick a row where actual arrival = 300s and baseline = 250s. Residual should be +50s. If it is -50s, the sign is reversed.

**Warning signs:**
- Mean residual is far from zero (>50s) in either direction on training data.
- Model's corrections consistently make predictions worse, not better.
- Final predictions are consistently double the expected arrival time (adding instead of subtracting).

**Phase to address:**
Residual computation phase. Add assertion and spot-check.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Using v1.0's 43 features unchanged for residual model | No feature engineering work | Wastes model capacity on features redundant with baseline; may need feature selection pass later | Acceptable for first experiment, but plan SHAP-based pruning for v1.2 |
| Hardcoding baseline as simple average of two components (equal weight) | Simple to implement | May leave accuracy on the table; optimal weighting could differ by route/time | Acceptable for v1.1; consider learned weights in v1.2 |
| Computing baseline_ETA at feature-engineering time, not as base_margin | Simpler code, baseline is just another column | Cannot use XGBoost's native base_margin support, which is designed for exactly this use case | Acceptable but suboptimal; switching to base_margin in v1.2 would be cleaner |
| Dropping rows where baseline is NaN instead of using fallback | Simpler pipeline | Loses data for sparse routes, reduces model's ability to learn about rare cases | Never acceptable if Route 27 or Route 235 lose >30% of data |
| Reusing v1.0's evaluation script without modification | Less code to write | Metrics report residual MAE instead of final MAE; comparison to v1.0 is invalid | Never acceptable -- must modify eval to report final prediction MAE |

## Performance Traps

Patterns that work at small scale but fail as data or route coverage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Recomputing baseline_ETA per row at inference time by summing segments | Latency > 100ms per prediction | Pre-compute and cache baseline lookups by (route, stop, hour, day_type) | When serving >10 prediction requests/second |
| Storing baseline lookup as Python dict instead of indexed DataFrame | Slow lookup for large number of combinations | Use merge-based lookup on DataFrames with sorted indexes | When routes/stops/hours exceed 10K combinations |
| Running full Optuna study on full dataset for residual model | Hours of compute per study | Use 10-25% subsample for Optuna (same strategy as v1.0), verify on full data | With >500K training rows (already at 2.08M) |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Baseline computation:** Often missing fallback for sparse combinations -- verify that NaN baselines use fallback hierarchy (route-level median, then scheduled time)
- [ ] **Residual label creation:** Often has sign reversed -- verify `residual = actual_arrival - baseline_ETA` with a manual spot check on 3-5 rows
- [ ] **Evaluation script:** Often reports residual MAE instead of final prediction MAE -- verify that the comparison to v1.0 uses `MAE(actual, baseline + residual_hat)`, not `MAE(actual_residual, residual_hat)`
- [ ] **Baseline-only MAE:** Often not computed -- verify that `MAE(actual, baseline_ETA)` is reported alongside model MAE
- [ ] **Historical aggregates source:** Often computed from wrong data -- verify segment medians and stop-to-stop averages use training-period data only (before Nov 30)
- [ ] **Residual distribution analysis:** Often skipped -- verify distribution statistics (mean, std, skew, kurtosis, percentiles) are reported before training
- [ ] **Per-route baseline quality:** Often not checked -- verify baseline MAE is reported per route to identify weak baselines
- [ ] **Feature audit against baseline:** Often not done -- verify SHAP analysis is run to identify features redundant with baseline
- [ ] **base_score parameter:** Often left at default -- verify XGBoost >= 2.0 auto-detects, or explicitly set to 0
- [ ] **MAPE metric:** Often computed on residuals where it is undefined -- verify MAPE is only on final predictions (positive values)

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Baseline uses test-period data | MEDIUM | Recompute baseline from training data only, regenerate residual labels, retrain model |
| Missing baseline for sparse combos | LOW | Add fallback hierarchy, recompute baselines for affected rows only |
| Evaluating residual MAE instead of final MAE | LOW | Fix eval script, rerun evaluation (no retraining needed) |
| Heavy-tail residuals dominate loss | LOW | Switch to Huber loss or winsorize, retrain (quick experiment) |
| Segment-sum error accumulation | MEDIUM | Adjust baseline weighting by stops_remaining, recompute baselines, retrain |
| Asymmetric loss sign reversed | LOW | Fix sign, retrain (only relevant if asymmetric loss is added) |
| Optuna search space wrong | MEDIUM | New Optuna study with adjusted ranges, retrain with best params |
| Features redundant with baseline | LOW | Prune features based on SHAP, retrain |
| baseline_ETA not stored for inference | LOW | Add column to parquets, save lookup tables (no retraining) |
| Residual sign convention wrong | MEDIUM | Fix label creation, regenerate residuals, retrain |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Baseline leaking into features | Feature engineering | SHAP analysis: historical median features have meaningful importance for residual target |
| Baseline uses test data | Baseline computation | Assert: max timestamp in baseline source data < val start date |
| Missing baseline for sparse combos | Baseline computation | Report: % rows using each fallback tier; no tier has >30% |
| Evaluating residual MAE not final MAE | Evaluation | Side-by-side table: v1.0 raw MAE, baseline-only MAE, v1.1 final MAE |
| Heavy-tail residuals | Training | Residual distribution stats: skewness < |1.5|, kurtosis < 8 |
| Segment-sum error accumulation | Baseline computation | Baseline MAE by stops_remaining bucket: growth is sub-linear |
| Asymmetric loss semantics | Training (deferred) | Unit test with known residuals verifying penalty direction |
| Optuna search space | Training | Fresh study; best params differ from v1.0 |
| Baseline quality varies by route | Baseline computation, Evaluation | Per-route baseline MAE report; max/min ratio < 10x |
| baseline_ETA not stored | Baseline computation | baseline_ETA column exists in all featured parquets |
| Baseline-only MAE not computed | Evaluation | Baseline-only MAE reported; provides context for model contribution |
| base_score default | Training config | Verify auto-detection or set explicitly |
| MAPE on residuals | Evaluation | MAPE only computed on final predictions |
| Residual sign convention | Residual computation | Spot check: 3-5 rows verified manually |

## Sources

- [Uber DeepETA Blog Post](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/) -- MEDIUM confidence: industry approach to residual ETA prediction, describes post-processing architecture
- [Google Maps ETA Prediction with GNNs](https://arxiv.org/pdf/2108.11482/1000) -- MEDIUM confidence: discusses supersegment approach to avoid segment-level error accumulation
- [XGBoost Intercept Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/intercept.html) -- HIGH confidence: official docs on base_score auto-estimation in >= 2.0
- [XGBoost Prediction Documentation](https://xgboost.readthedocs.io/en/stable/prediction.html) -- HIGH confidence: official docs on base_margin for stacking/residual approaches
- [XGBoost Parameters](https://xgboost.readthedocs.io/en/stable/parameter.html) -- HIGH confidence: official parameter documentation
- [Transit App: ETAs are often fantastically wrong](https://blog.transitapp.com/better-predictions/) -- MEDIUM confidence: domain expertise on transit prediction challenges
- [Capital One: Pitfalls of Incorrectly Tuned XGBoost Hyperparameters](https://www.capitalone.com/tech/machine-learning/tuning-xgboost-hyperparameters/) -- MEDIUM confidence: practical XGBoost tuning guidance
- [MachineLearningMastery: Model Residual Errors for Time Series](https://machinelearningmastery.com/model-residual-errors-correct-time-series-forecasts-python/) -- MEDIUM confidence: general approach to residual correction in forecasting
- Existing codebase analysis: `build_differentiator_features.py` (historical aggregates, 43 features), `evaluate.py` (evaluation framework), `train_advanced.py` (Optuna tuning), `temporal_split.py` (data splitting), `build_features.py` (v1 features) -- HIGH confidence: direct code inspection

---
*Pitfalls research for: Residual-based ETA prediction, Tiger Transit XGBoost v1.1*
*Researched: 2026-02-11*
