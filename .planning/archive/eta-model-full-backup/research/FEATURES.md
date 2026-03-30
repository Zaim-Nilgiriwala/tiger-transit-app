# Feature Research: Residual-Based ETA Prediction (v1.1)

**Domain:** Transit bus arrival time prediction -- residual target (actual - baseline_ETA)
**Researched:** 2026-02-11
**Confidence:** MEDIUM-HIGH
**Supersedes:** v1.0 FEATURES.md (2026-02-03, raw-seconds target)

---

## Context: Why Feature Behavior Changes with Residual Target

The v1.0 model predicts raw `time_to_arrival_seconds` (range 0-2000+s, mean ~300s). The v1.1 model predicts `residual = actual_arrival - baseline_ETA` (range centered around 0, much tighter distribution).

The baseline is the average of:
1. **Segment-median sum:** Sum of historical median travel times for each segment between current position and target stop
2. **Stop-to-stop historical average:** Direct historical average travel time from current stop to target stop

This baseline already encodes distance, route structure, stop count, and typical travel time patterns. Features that primarily encode the same information become **redundant** -- the model no longer needs to "learn" that 5 stops away takes longer than 2 stops. Instead, the model needs features that explain **why this trip deviates from the historical norm**.

### The Fundamental Shift

| Aspect | v1.0 (Raw Target) | v1.1 (Residual Target) |
|--------|-------------------|------------------------|
| What model learns | "How long will this trip take?" | "How much faster/slower than usual?" |
| Target range | 0 - 2000+ seconds | Centered ~0, tighter spread |
| Dominant signal | Distance, route structure | Real-time conditions, anomalies |
| Feature role | Spatial features dominate | Condition features dominate |
| Baseline absorbed | Nothing -- model learns everything | Distance, segment times, stop count |

**Confidence:** HIGH -- this follows directly from the mathematical definition of the residual target. When `baseline = f(distance, stops, historical_times)`, the residual `y - baseline` is orthogonal to those components. Uber's DeepETA system uses the identical pattern: a routing engine provides the baseline, and the ML model predicts the residual, focusing on dynamic factors the routing engine cannot capture ([Uber DeepETA blog](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/)).

---

## Feature Importance Reclassification for v1.1

### Features That Become MORE Important (Explain Deviations)

These features capture **why this trip differs from the historical average**. They become the primary signal when the baseline absorbs route structure and distance.

| Feature | v1.0 SHAP Rank | v1.1 Expected Role | Why More Important | Confidence |
|---------|----------------|--------------------|--------------------|------------|
| **speed_mean_30s** | Mid-range | HIGH -- primary real-time signal | Current traffic/speed directly determines whether bus is running faster or slower than the historical median used in the baseline. If baseline assumes 25 mph for a segment but bus is doing 15 mph, the residual is positive (late). | HIGH |
| **speed_mean_60s / 120s / 180s** | Mid-range | HIGH -- traffic corridor state | Longer rolling windows capture sustained congestion vs. momentary slowdowns. 180s window captures corridor-level traffic state that drives systematic deviations from historical medians. | HIGH |
| **acceleration** | Low | MEDIUM -- trend indicator | Decelerating bus signals upcoming delay (approaching congestion, red light queue). Accelerating bus signals clearing conditions. Neither is captured by the static baseline. | MEDIUM |
| **speed_ratio** | Low | HIGH -- direct anomaly detector | `current_speed / historical_median_speed` is literally the ratio that generates residuals. If speed_ratio < 1.0, the bus is slower than the historical median that informs the baseline. This feature should jump to top-5 importance. | HIGH |
| **precipitation_mm** | Low | MEDIUM-HIGH -- explains systematic slowdowns | Rain slows all buses on all segments. The historical median baseline reflects average-weather conditions. Rain creates a systematic positive residual (bus takes longer than usual). | MEDIUM |
| **temperature_c** | Very low | LOW-MEDIUM -- extreme weather effects | Extreme cold/heat affects boarding times and road conditions. Only matters at temperature extremes. | LOW |
| **is_rush_hour** | Low | MEDIUM -- temporal deviation pattern | Rush hour creates congestion-driven delays that exceed historical segment medians (which blend rush and non-rush data). If the baseline already conditions on hour_ct and day_type, this is partially captured. **Depends on baseline granularity.** | MEDIUM |
| **class_let_out_recently** | Low | MEDIUM -- Auburn-specific anomaly | Class dismissal creates surge demand and pedestrian congestion not captured in segment-level historical medians. Affects boarding dwell time and intersection delays. | MEDIUM |
| **is_idle / seconds_idle** | Very low | MEDIUM -- active delay signal | An idling bus right now is accumulating delay that the baseline does not know about. The seconds_idle feature directly measures accumulated real-time delay beyond what historical medians predict. | MEDIUM |
| **gps_speed_mps** | Low | MEDIUM -- instantaneous condition | Raw GPS speed captures the immediate condition. Less informative than rolling averages (noisy) but still signals current-moment anomalies. | MEDIUM |
| **passenger_load** | Very low | LOW-MEDIUM -- dwell time predictor | Higher load = longer dwell at remaining stops. The baseline uses historical dwell medians. A bus with unusually high load will have above-average dwell times, creating positive residuals. | LOW |
| **timepoint_adherence** | Mid-range | MEDIUM-HIGH -- schedule deviation context | How far ahead/behind the bus is relative to the timepoint schedule. A bus running 3 minutes late at the last timepoint will likely continue running late -- the baseline does not have this real-time information. | MEDIUM |
| **speed_std_30s / 60s / 120s / 180s** | Low | LOW-MEDIUM -- variability signal | High speed variance indicates stop-and-go conditions (traffic lights, congestion). Consistently low variance indicates free-flow or consistently stopped. Helps explain residual variability. | LOW |

### Features That Become LESS Important (Already Captured by Baseline)

These features primarily encode **route structure, distance, and stop count** -- exactly what the baseline already computes. The model no longer needs these to predict the gross time magnitude; it only needs them if they interact with deviation patterns.

| Feature | v1.0 SHAP Rank | v1.1 Expected Role | Why Less Important | Keep/Drop? | Confidence |
|---------|----------------|--------------------|--------------------|------------|------------|
| **stop_index** | #2 (120.2) | LOW -- positional context only | v1.0: stop_index encoded cumulative distance and typical delay patterns. v1.1: the baseline already sums segment medians up to this stop_index. The model no longer needs stop_index to estimate "how far away." It may still help as a context feature (early-route vs. late-route deviation patterns differ). | KEEP but expect massive SHAP drop | HIGH |
| **distance_to_target** | High | LOW -- route geometry redundant with baseline | The baseline's segment-median-sum IS a function of distance. When baseline = sum(segment_medians), distance_to_target provides negligible additional information for predicting the residual. May help marginally for within-segment interpolation. | KEEP but expect SHAP drop to near-zero | HIGH |
| **stops_remaining** | High | LOW -- absorbed by baseline | Same logic as distance_to_target. More stops = larger baseline ETA. The residual should not scale with stops_remaining because the baseline already accounts for it. Exception: if more stops = more variance = more room for deviation, it adds a weak heteroscedasticity signal. | KEEP but expect minimal contribution | HIGH |
| **pattern_id** | #3 (119.0) | MEDIUM-LOW -- route-level bias only | v1.0: pattern_id was a dominant feature because different routes have fundamentally different travel times. With residual prediction, pattern_id only matters if certain routes systematically deviate from their historical medians more than others. Some routes may be more variable (campus-adjacent vs. highway). | KEEP -- still useful for route-specific deviation patterns | MEDIUM |
| **route_id** | Moderate | LOW -- similar to pattern_id | Largely redundant with pattern_id. Route-specific bias in residuals is the only remaining signal. | KEEP for consistency | MEDIUM |
| **scheduled_time_to_target** | High | LOW-MEDIUM -- schedule is a weaker baseline | The baseline uses historical actuals, not schedule. scheduled_time_to_target provides schedule-based context. Since baseline already uses historical medians (more accurate than schedule), this feature's role diminishes. However, the difference (scheduled - baseline) could indicate schedule tension. | KEEP -- provides complementary schedule perspective | MEDIUM |
| **segment_travel_median / p25 / p75** | High | LOW -- directly feeds baseline | These features ARE the baseline (or very close to it). The segment_travel_median summed across remaining segments IS component 1 of the blended baseline. Including them as features while predicting residuals from a baseline that uses them creates near-perfect collinearity. | **KEEP but expect near-zero importance** -- see Anti-Features discussion | HIGH |
| **dwell_median / p25 / p75** | Moderate | LOW -- partially feeds baseline | Historical dwell medians at current and remaining stops inform the baseline's estimated travel time. Similar collinearity concern. | KEEP but expect reduced importance | MEDIUM |
| **target_dwell_median / p25 / p75** | Low-Moderate | LOW -- dwell at destination | Target stop dwell time is less relevant for arrival time (it is the stop we are predicting arrival AT, not departure FROM). May have been marginal in v1.0 already. | KEEP -- low cost, might capture destination-specific patterns | LOW |
| **minutes_since_midnight** | Moderate | LOW-MEDIUM -- time already in baseline via hour_ct conditioning | If the baseline's historical segment medians are conditioned on (hour_ct, day_type), then time-of-day is already partially captured. Residual patterns by time exist (e.g., midday overprediction from v1.0) but the primary temporal signal is absorbed. | KEEP -- captures fine-grained temporal patterns not in hourly baseline | MEDIUM |
| **day_of_week** | Low | LOW -- mostly absorbed if baseline conditions on day_type | If historical medians use weekday/weekend conditioning, day_of_week adds little. May help for Friday vs. Monday differences within weekdays. | KEEP -- low cost categorical | LOW |

### Features with UNCHANGED Importance

| Feature | v1.0 Role | v1.1 Expected Role | Rationale | Confidence |
|---------|-----------|--------------------|--------------------|------------|
| **time_until_next_timepoint_departure** | #1 (155.6) | HIGH -- remains top feature | Timepoint holds are NOT captured by segment-median baselines. A bus that arrives 4 minutes early at a timepoint will wait 4 minutes -- this delay is not in historical medians (medians include the hold but the baseline does not know current adherence). This feature provides real-time information about forced waits that remain invisible to the baseline. | HIGH |
| **is_timepoint** | Moderate | MODERATE -- context for timepoint logic | Whether the target stop is a timepoint affects whether a hold applies. Same role in residual prediction. | HIGH |
| **timepoints_remaining** | Moderate | MODERATE -- cumulative hold potential | More timepoints = more potential for schedule-recovery holds. The baseline does not account for current schedule adherence, so this remains relevant. | MEDIUM |
| **scheduled_departure_seconds** | Low-Moderate | LOW-MODERATE -- timepoint schedule reference | When the next timepoint departure is scheduled. Relevant for computing expected hold duration. | MEDIUM |
| **route_progress** | Low | LOW -- within-segment interpolation | Captures position within current segment. Marginal in both v1.0 and v1.1 since it is a fine-grained spatial feature. | LOW |
| **current_speed** | Mid | MEDIUM -- instantaneous snapshot | Captured more cleanly by rolling averages, but provides raw signal. Similar role in both models. | MEDIUM |
| **lateness_now** | High (but zero variance in v1.0!) | ZERO VARIANCE -- remains broken | `scheduled_eta_seconds - eta_seconds` is always 0 because EtaSpot's scheduled_eta == eta. This feature has zero variance in v1.0 and will have zero variance in v1.1. It contributes nothing. | HIGH |

---

## New Features Worth Adding for Residual Prediction

These features are specifically valuable when the target is a residual (deviation from baseline), because they directly encode information about HOW and WHY the current trip deviates.

### Table Stakes for Residual Prediction

| Feature | Description | Why Essential for Residuals | Complexity | Priority |
|---------|-------------|----------------------------|------------|----------|
| **baseline_eta** | The blended baseline ETA value itself (seconds) | The model needs to know the baseline magnitude to contextualize the residual. A 10-second residual on a 30-second baseline is very different from a 10-second residual on a 600-second baseline. Without this, the model cannot learn that residuals scale with trip length (longer trips have larger absolute residuals). Uber's DeepETA includes the routing engine ETA as a feature. | LOW -- already computed for labels | **P1** |
| **baseline_confidence** | Measure of baseline reliability -- e.g., (p75 - p25) / median from historical segment data, or count of observations | When the baseline is built from sparse data (few historical observations), it is less reliable and residuals will be larger/noisier. The model should know when to trust the baseline vs. when to rely more on real-time features. | MEDIUM -- derive from historical aggregates | **P2** |

### Differentiator Features for Residual Prediction

| Feature | Description | Value for Residuals | Complexity | Priority |
|---------|-------------|---------------------|------------|----------|
| **baseline_component_diff** | `abs(segment_median_sum - stop_to_stop_average)` | When the two baseline components disagree, the blended average may be poor. Large disagreement = unreliable baseline = larger expected residual. Gives model a signal about baseline quality. | LOW -- computed during baseline calc | **P2** |
| **lateness_at_last_timepoint** | Actual seconds ahead/behind schedule at the most recent passed timepoint | More informative than `timepoint_adherence` (which uses clock time). Directly encodes whether the bus is running ahead or behind, which predicts whether upcoming timepoint holds will add delay. | MEDIUM -- requires timepoint schedule lookup | **P2** |
| **residual_momentum** | Change in residual over last N observations for same vehicle-route | If a bus has been running increasingly late over the last 5 pings (residual increasing), it signals worsening conditions. If residual is decreasing, conditions are improving. This is a temporal derivative of the thing we are predicting. | MEDIUM -- requires per-vehicle tracking | **P3** |
| **segment_speed_vs_historical** | `speed_mean_60s / segment_historical_speed_at_this_hour` for current segment | Direct measure of how much faster/slower the bus is traveling ON THIS SEGMENT compared to the historical norm for this segment. More specific than global speed_ratio. | MEDIUM -- requires segment-specific historical lookup | **P2** |

### Confidence Assessment for New Features

| Feature | Confidence | Reasoning |
|---------|-----------|-----------|
| baseline_eta | HIGH | Uber's DeepETA includes routing engine ETA as a feature. Mathematically necessary for residual scaling. |
| baseline_confidence | MEDIUM | Theoretically sound but no transit-specific literature confirming impact. Need to validate empirically. |
| baseline_component_diff | MEDIUM | Novel feature -- logical but unvalidated. Low implementation cost makes it worth trying. |
| lateness_at_last_timepoint | MEDIUM | Auburn-specific. Theoretically valuable but depends on timepoint schedule accuracy. |
| residual_momentum | LOW | Requires temporal tracking infrastructure. May not add much over speed_mean features which already capture trajectory. Defer to v1.2. |
| segment_speed_vs_historical | MEDIUM | Essentially a more specific version of speed_ratio. May not add enough over speed_ratio to justify complexity. |

---

## Anti-Features for Residual Prediction

Features that seem useful but create problems when the target is a residual.

| Anti-Feature | Why Tempting | Why Problematic | What to Do Instead |
|--------------|-------------|-----------------|-------------------|
| **Using segment_travel_median as both a feature AND a baseline component** | It was important in v1.0 and is already computed | If segment_travel_median feeds into the baseline_ETA, and the target is `actual - baseline_ETA`, then the model is given an input that is a direct component of the subtracted term. This creates a mathematical dependency: the feature can almost perfectly predict one component of the target with a coefficient of -1. In XGBoost this manifests as a split that subtracts the baseline component, effectively "undoing" the baseline. The model wastes capacity reconstructing raw_seconds from residual + segment_median. | KEEP the features (XGBoost is robust enough to handle this -- it will simply assign them low importance) but **do not expect them to contribute meaningfully**. More importantly, do not be alarmed when their SHAP values drop to near-zero. If feature count is a concern, they are safe to drop. |
| **Normalizing residuals by baseline_eta** (predicting relative error instead) | Relative error seems more "fair" across short and long trips | Creates heteroscedastic target where short-trip residuals are amplified. A 5-second error on a 30-second trip becomes 16.7% but only 0.5% on a 1000-second trip. XGBoost with squared error loss will over-weight short trips. Also makes the target distribution asymmetric and harder to learn. | Keep absolute residuals as target. Include baseline_eta as a FEATURE so the model can learn the scaling relationship itself. |
| **Removing "absorbed" features entirely** | Distance, stops_remaining, stop_index are theoretically redundant with baseline | The baseline is a BLENDED AVERAGE of two components, not a perfect predictor. The segment-median-sum may disagree with the stop-to-stop average. Residuals may still correlate with spatial features due to baseline imperfections. Removing them risks losing signal from baseline errors. Also, these features may interact with real-time features (e.g., "3 stops away AND raining" = different residual pattern than "1 stop away AND raining"). | KEEP all 43 features. Let XGBoost determine importance via SHAP. Only drop features after v1.1 evaluation confirms they contribute nothing. |
| **Asymmetric loss for residual prediction** | v1.0 used 3:1 overestimation penalty | With residual target, the semantics of asymmetric loss change. Over-predicting the residual means predicting the bus will be LATER than it actually is (overpredicting arrival time), which is actually the SAFER direction for riders. The penalty direction may need to flip. More importantly, residuals centered at 0 benefit from symmetric loss first to establish a clean baseline before adding asymmetric complexity. | Start with symmetric squared error loss (reg:squarederror). Add asymmetric loss only after v1.1 baseline is established and evaluated. Carefully verify penalty direction: positive residual = bus late, negative = bus early. |
| **Predicting log(residual) or abs(residual)** | Residuals may have heavy tails | Residuals can be negative (bus faster than baseline). Log transform is undefined for negative values. Abs loses sign information. Both destroy the semantic meaning of the residual. | Predict raw residual (can be positive or negative). Handle outliers with robust loss (Huber) if needed, or clip extreme residuals during preprocessing. |

---

## Feature Dependencies for v1.1

```
[Baseline Computation] (NEW for v1.1)
    |-- baseline_eta = avg(segment_median_sum, stop_to_stop_historical_avg)
    |   |-- segment_median_sum: sum of segment_travel_median for remaining segments
    |   |-- stop_to_stop_avg: direct historical average from current stop to target
    |-- residual_label = actual_arrival - baseline_eta
    |-- baseline_eta as feature (RECOMMENDED)
    |-- baseline_confidence (OPTIONAL)
    |-- baseline_component_diff (OPTIONAL)

[Real-Time Features] (gain importance in v1.1)
    |-- speed_mean_{30,60,120,180}s --> PRIMARY residual explainers
    |-- speed_ratio --> direct anomaly signal
    |-- acceleration --> trend signal
    |-- is_idle / seconds_idle --> active delay

[Timepoint Features] (retain importance in v1.1)
    |-- time_until_next_timepoint_departure --> forced hold prediction
    |-- timepoint_adherence --> schedule deviation context
    |-- is_timepoint, timepoints_remaining --> hold structure

[Weather/Temporal] (gain importance in v1.1)
    |-- precipitation_mm --> systematic weather delay
    |-- is_rush_hour, class_let_out_recently --> demand/congestion anomalies

[Route/Distance Features] (lose importance in v1.1)
    |-- distance_to_target, stops_remaining, stop_index --> absorbed by baseline
    |-- pattern_id, route_id --> route-specific deviation patterns only
    |-- segment_travel_median/p25/p75 --> directly feeds baseline
```

### Dependency Notes

- **baseline_eta MUST be computed before labels:** The residual label requires the baseline. The baseline requires historical_segments and historical_dwells from training data. This creates the same circular dependency as v1.0's historical features -- use temporal holdout (train on earlier data, compute baseline from earlier data).
- **baseline_eta as feature requires the same value used for labeling:** If different baseline values are used for training labels vs. inference features, the model learns a corrupted relationship.
- **Segment/dwell historical features feed BOTH the baseline AND the feature matrix:** This is acceptable. The model may learn to correct for baseline errors by comparing the individual segment medians (features) against the blended baseline (also a feature).

---

## MVP Recommendation for v1.1

### Phase 1: Baseline + Residual Labels (Must Have)

- [ ] Compute blended baseline_ETA from historical_segments + stop-to-stop averages
- [ ] Generate residual labels: `residual = actual_arrival - baseline_ETA`
- [ ] Add `baseline_eta` as feature #44
- [ ] Keep all 43 existing features (do NOT drop any yet)
- [ ] Train with symmetric loss (reg:squarederror)
- [ ] Fresh Optuna hyperparameter tuning

### Phase 2: Feature Analysis (Validate Importance Shifts)

- [ ] Run SHAP on v1.1 model -- compare against v1.0 SHAP rankings
- [ ] Verify expected importance shifts (speed features up, distance features down)
- [ ] Identify any surprises (features that behave unexpectedly)
- [ ] Evaluate: does v1.1 beat 123.1s MAE?

### Phase 3: Residual-Specific Features (If Needed)

Only if v1.1 Phase 2 does not beat 123.1s MAE:

- [ ] Add baseline_confidence feature
- [ ] Add baseline_component_diff feature
- [ ] Add segment_speed_vs_historical feature
- [ ] Consider dropping zero-importance features to reduce noise

### Defer to v1.2+

- [ ] residual_momentum (temporal derivative tracking)
- [ ] Per-route residual bias correction
- [ ] Asymmetric loss tuned for residual target semantics
- [ ] Feature interaction constraints tuned for residual patterns

---

## Feature Prioritization Matrix (v1.1)

| Feature | Residual Value | Implementation Cost | Priority |
|---------|---------------|---------------------|----------|
| **baseline_eta** (NEW) | HIGH | LOW | P1 |
| speed_mean_{30,60,120,180}s (existing) | HIGH | NONE (already built) | P1 |
| speed_ratio (existing) | HIGH | NONE | P1 |
| time_until_next_timepoint_departure (existing) | HIGH | NONE | P1 |
| timepoint_adherence (existing) | MEDIUM-HIGH | NONE | P1 |
| precipitation_mm (existing) | MEDIUM | NONE | P1 |
| acceleration (existing) | MEDIUM | NONE | P1 |
| is_rush_hour (existing) | MEDIUM | NONE | P1 |
| class_let_out_recently (NOT in v2 features!) | MEDIUM | LOW | P1 |
| All 43 existing features | VARIES | NONE | P1 (keep all) |
| baseline_confidence (NEW) | MEDIUM | MEDIUM | P2 |
| baseline_component_diff (NEW) | MEDIUM | LOW | P2 |
| segment_speed_vs_historical (NEW) | MEDIUM | MEDIUM | P2 |
| lateness_at_last_timepoint (NEW) | MEDIUM | MEDIUM | P2 |
| residual_momentum (NEW) | LOW | MEDIUM | P3 |

**Priority key:**
- P1: Include in v1.1 initial training (keep all existing + add baseline_eta)
- P2: Add if v1.1 does not beat 123.1s MAE
- P3: Defer to v1.2+

---

## Expected SHAP Ranking Shift: v1.0 vs v1.1

| Rank | v1.0 (Raw Target) | v1.1 (Residual Target, Predicted) |
|------|-------------------|-----------------------------------|
| #1 | time_until_next_timepoint_departure (155.6) | time_until_next_timepoint_departure (stays #1 -- timepoint holds not in baseline) |
| #2 | stop_index (120.2) | speed_ratio or speed_mean_60s (real-time speed vs. historical norm) |
| #3 | pattern_id (119.0) | baseline_eta (trip length context for residual scaling) |
| #4 | segment_travel_p25 (high) | precipitation_mm or is_rush_hour (systematic deviation drivers) |
| #5 | segment_travel_median (high) | timepoint_adherence (schedule deviation propagation) |
| ... | distance, stops_remaining (high) | distance, stops_remaining (drop to bottom 10) |

**Confidence:** MEDIUM -- this ranking is predicted from first principles (what the baseline absorbs vs. what it does not). Actual SHAP analysis on the trained v1.1 model will confirm or contradict these predictions. The #1 position of `time_until_next_timepoint_departure` is HIGH confidence because timepoint hold durations are genuinely orthogonal to segment-median-based baselines.

---

## Note on class_let_out_recently

The v1.0 FEATURES.md recommended `class_let_out_recently` as a differentiator feature, but reviewing the actual v2 feature set in `build_differentiator_features.py`, this feature is NOT included in `PHASE4_FEATURE_COLS`. It was listed in the v1.0 research but never implemented. For v1.1, it should be added -- Auburn class dismissal creates localized congestion that historical segment medians (which average across all times) do not fully capture.

Implementation: `class_let_out_recently = 1 if (minutes_since_midnight % 60) in range(45, 60+15)` (classes end at :50/:00, window from :45 to :15 of next hour).

---

## Sources

- [Uber DeepETA Blog](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/) -- Residual prediction architecture where ML corrects routing engine baseline, MEDIUM confidence
- [DeeprETA Paper (arXiv 2206.02127)](https://arxiv.org/abs/2206.02127) -- Post-processing residual ETA system at scale, MEDIUM confidence
- [XGBoost Documentation: Intercept / Base Score](https://xgboost.readthedocs.io/en/stable/tutorials/intercept.html) -- How XGBoost handles initial predictions and residuals, HIGH confidence
- [Mathematical Theory of Collinearity Effects on ML Variable Importance](https://arxiv.org/html/2510.00557v1) -- How correlated features affect importance in tree models, MEDIUM confidence
- v1.0 Evaluation: `models/evaluation/eval_shap_meta.json`, `models/evaluation/eval_report.md` -- SHAP rankings for raw-target model, HIGH confidence (direct codebase)
- v1.0 Feature Engineering: `scripts/build_features.py`, `scripts/build_differentiator_features.py` -- 43-feature implementation, HIGH confidence (direct codebase)
- v1.0 FEATURES.md research (2026-02-03) -- Original feature landscape analysis, HIGH confidence (direct prior research)

---
*Feature research for: Tiger Transit XGBoost ETA Model v1.1 (residual target)*
*Researched: 2026-02-11*
