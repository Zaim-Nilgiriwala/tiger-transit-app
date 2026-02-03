# Pitfalls Research

**Domain:** Transit ETA prediction with XGBoost (campus bus system)
**Researched:** 2026-02-03
**Confidence:** HIGH (domain-specific, verified against existing codebase and official docs)

## Critical Pitfalls

Mistakes that cause fundamentally broken models or require rewrites.

### Pitfall 1: Data Leakage Through Future Arrival Information in Labels

**What goes wrong:**
When creating per-stop rows (observation x target_stop pairs), the label for a far-future stop (e.g., stop 5 downstream) is the actual arrival time at that stop. If features include anything derived from events that happen *between* the observation time and that far-future arrival (e.g., dwell times at intermediate stops, intermediate arrival info, rolling stats computed with data points after the observation), the model learns to use future information it will never have at inference time.

The existing `data_prep.py` code already has a version of this risk: `build_feature_vector` takes `arrival_info` as input and uses `dwell_sec`, `boardings`, and `alightings` from the target stop's arrival record as features (lines 821-823). These are features of the future event you are predicting -- they describe what happens when the bus *arrives* at the stop. At inference time, this information does not exist.

**Why it happens:**
The arrivals CSV has rich data (dwell time, boardings, alightings) that correlates strongly with travel patterns. It is tempting to include it as a feature. The original PyTorch pipeline used it because the matching happened post-hoc, and the feature "leaked" from the label join.

**How to avoid:**
- Features must only use information available at prediction time: current telemetry snapshot, historical averages (computed from training data only, not the current trip), schedule data, weather.
- For historical dwell/boarding features, use *historical averages per stop/route/time-of-day* computed from the training set, never from the current trip's actual arrivals.
- Audit every feature: "Would I have this number if I were making this prediction in real-time right now?"

**Warning signs:**
- Model achieves suspiciously high accuracy (MAE < 15 seconds on 5+ minute predictions).
- Features like `dwell_sec` or `boardings` have very high feature importance.
- Model performance degrades dramatically in deployment vs. offline evaluation.

**Phase to address:**
Data preparation phase -- feature engineering. Build a strict "available at prediction time" checklist before any feature is included.

---

### Pitfall 2: Random Train/Test Splitting of Temporal Data

**What goes wrong:**
If you randomly shuffle rows and split into train/test, rows from the same trip, same day, or same time period appear in both sets. The model memorizes temporal patterns (e.g., "on Tuesday at 2:15 PM, bus 3 was 2 minutes late") rather than learning generalizable relationships. Evaluation metrics look great, but the model fails on genuinely future data.

**Why it happens:**
Random splitting is the default in most ML tutorials and libraries. `sklearn.model_selection.train_test_split` defaults to random shuffling. It is the path of least resistance.

**How to avoid:**
- Always split by time: train on earlier dates, validate/test on later dates. The existing `pipeline.py` already does this correctly with `time_based_split()` (line 158-180). Preserve this approach for the XGBoost model.
- Use `sklearn.model_selection.TimeSeriesSplit` for cross-validation during hyperparameter tuning.
- Ensure a gap between train and validation periods (at least one full service day) to prevent same-trip leakage at the boundary.

**Warning signs:**
- Validation metrics are close to training metrics (suspiciously small gap).
- Model performs well on validation but poorly on data from a genuinely new week.
- Feature importance shows temporal features (hour, day_of_week) dominating everything else.

**Phase to address:**
Data preparation phase -- splitting. Enforce temporal split in the pipeline before any model training begins.

---

### Pitfall 3: Correlated Row Explosion from Per-Stop Row Structure

**What goes wrong:**
With the per-stop row design (one row per observation x target_stop pair), a single telemetry snapshot at time T generates N rows (one for each remaining stop). These N rows share identical features (same GPS position, same speed, same time) but have different labels. If these correlated rows land in both train and validation folds during cross-validation, the model effectively sees near-duplicate feature vectors in both sets, inflating metrics.

Worse: within an approach sequence, telemetry pings every ~10 seconds create rows with nearly identical features and highly correlated labels (labels differ by only ~10 seconds of travel time). This creates massive redundancy that XGBoost can memorize.

**Why it happens:**
The per-stop row structure is the right design for prediction (you do want per-stop predictions), but naive evaluation ignores the correlation structure. Standard k-fold cross-validation treats each row as independent.

**How to avoid:**
- For cross-validation: use `GroupKFold` from sklearn with groups defined by `trip_id` or `(vehicle_id, date)`. All rows from the same trip must stay in the same fold.
- For train/val/test split: split by date (already done in pipeline). But also ensure the same trip does not span the split boundary.
- Consider subsampling within approach sequences (the v2 pipeline already does this with `sample_rate`) to reduce redundancy. A sample_rate of 5-10 is reasonable.
- Add `trip_segment_id` as an explicit column to facilitate grouped splitting.

**Warning signs:**
- Cross-validation scores are much better than held-out test scores.
- Model has very high R-squared (> 0.98) on validation, which is unrealistic for transit ETA.
- Removing correlated features causes large performance drops.

**Phase to address:**
Data preparation phase (add trip/segment grouping columns) and model training phase (use grouped CV).

---

### Pitfall 4: Asymmetric Loss Implementation with XGBoost Custom Objective

**What goes wrong:**
The existing PyTorch model uses a 5x penalty for overestimation (predicting bus arrives later than it does, causing riders to miss the bus). Porting this to XGBoost requires a custom objective function returning gradient and hessian. Common mistakes:
1. **Hessian of zero**: If the hessian is zero for some regions, XGBoost cannot split those nodes (gain = gradient^2 / hessian). A constant hessian of 0 means no tree growth.
2. **Sign errors**: Confusing whether `error = pred - actual` or `actual - pred`. Getting the sign wrong causes the model to optimize in the wrong direction.
3. **Non-smooth loss boundary**: The asymmetric loss has a kink at error=0 (transition between normal and penalized region). The hessian is technically discontinuous there, which can cause tree-building instability.
4. **Scale mismatch**: Custom objectives return raw gradients. XGBoost's built-in `reg:squarederror` has implicit scaling. Your custom loss gradients may be orders of magnitude different, requiring learning rate adjustment.

**Why it happens:**
XGBoost's custom objective API is powerful but unforgiving. Unlike PyTorch where autograd handles derivatives, you must manually compute and verify gradient and hessian. The XGBoost documentation explicitly warns: "If you find the training error goes up instead of down, this might be the reason."

**How to avoid:**
- Implement the asymmetric squared error explicitly:
  ```python
  def asymmetric_obj(predt, dtrain):
      labels = dtrain.get_label()
      error = predt - labels
      alpha = 5.0  # overestimation penalty
      # Gradient: d(loss)/d(pred)
      grad = np.where(error > 0, 2 * alpha * error, 2 * error)
      # Hessian: d^2(loss)/d(pred)^2
      hess = np.where(error > 0, 2 * alpha, 2.0)
      return grad, hess
  ```
- Verify hessian is always positive (never zero). For the above, hessian is always >= 2.0.
- Test on a small synthetic dataset where you know the correct predictions. Confirm loss decreases.
- Start with `reg:squarederror` as baseline, then add custom objective. Compare gradient magnitudes to ensure learning rate is appropriate.
- Consider quantile regression (`reg:quantileerror` with `quantile_alpha`) as an alternative to custom objectives -- it achieves similar asymmetric behavior and is built into XGBoost.

**Warning signs:**
- Training loss increases instead of decreasing.
- Model predicts a constant value (all predictions identical).
- Predictions are all extremely large or extremely small.
- Loss values are NaN or Inf.

**Phase to address:**
Model training phase. Implement custom objective with unit tests before training on real data. Consider `reg:quantileerror` as simpler alternative first.

---

### Pitfall 5: Label Noise from Imperfect Telemetry-to-Arrivals Joins

**What goes wrong:**
Ground truth labels come from joining GPS telemetry timestamps with a separate arrivals CSV by vehicle ID and time proximity. This join is inherently noisy:
1. **Timezone mismatches**: The existing code handles Central Time to UTC conversion, but off-by-one-hour errors from DST boundaries create 3600-second label errors.
2. **Vehicle ID mismatches**: Arrival data uses names like "jAUnt 1" while telemetry may use different ID formats. Partial matching creates false joins.
3. **Loop route ambiguity**: On loop routes, a bus visits the same stop multiple times per trip. The `find_next_arrival` function may match to the wrong visit, creating label errors of one full loop duration (10-15 minutes).
4. **Stop name mapping failures**: The `StopNameMapper` uses fuzzy matching. "Eagles West Apartments" mapping to the wrong physical stop creates systematic label errors for that stop.
5. **Dwell time vs. arrival time**: The arrivals CSV records when the bus opens doors (arrival) and closes them (departure). If a bus is held at a timepoint, the "arrival" time might be the initial stop, but passengers can board until departure. Which timestamp should the label use?

**Why it happens:**
Transit agencies provide arrivals data in a different format and system than real-time telemetry. There is no shared trip_id or arrival event linking the two datasets. The join is inherently fuzzy.

**How to avoid:**
- Use the transition-based matching from `data_prep_v2` (which detects when `nextStopId` changes in telemetry and matches to arrivals in a narrow window). This is more reliable than the simple forward-search in v1.
- Add validation checks after label creation: plot label distributions, check for bimodal distributions (suggests systematic mismatches), check for labels that are exactly 3600 seconds off (timezone bug).
- For loop routes, ensure matching uses the sequential order of stops visited, not just the next occurrence of a stop ID.
- Implement outlier filtering: remove labels where `abs(predicted_by_schedule - actual_label) > threshold` (e.g., 5 minutes), as these are likely bad joins.
- Cross-validate label quality by checking that ETA decreases as the bus approaches (for consecutive telemetry pings heading to the same stop, later pings should have smaller labels).

**Warning signs:**
- Label distribution has unexpected spikes at round numbers (3600, 7200 seconds -- timezone errors).
- Mean label value is much higher or lower than expected from schedule data.
- Many labels are exactly 0 or negative (filtered in existing code, but check counts).
- Label quality report shows low join success rate (< 60%).

**Phase to address:**
Data preparation phase -- label creation. This must be validated thoroughly before model training. The existing `check_label_quality()` and `check_join_quality()` functions in `data_quality.py` are a good foundation but should be extended with the checks above.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| One-hot encoding route_id (23 routes) instead of native categorical | Simple, no API concerns | 23 sparse columns, slower training, loses ordinal partitioning benefit | Never -- use XGBoost native categorical (`enable_categorical=True`, `tree_method='hist'`) |
| Computing normalization stats on full dataset before splitting | Simpler pipeline | Leaks test distribution into training scaling | Only for XGBoost (tree-based models are invariant to monotonic feature transforms, so normalization leakage does not affect them) |
| Using straight-line distance instead of route distance | No GTFS dependency | Missing the single most predictive feature; straight-line is terrible on loop routes | Only as fallback when GTFS data unavailable for a specific trip |
| Training single global model across all 23 routes | Simple, more training data per model | Routes have vastly different characteristics (loop vs. linear, campus vs. city) | Acceptable for MVP; split into per-route models if performance varies >30% across routes |
| Ignoring timepoint holds in feature engineering | Fewer features to manage | Model cannot explain why bus sits at a stop for 3 minutes with zero delay | Never for routes with timepoints -- add `is_timepoint_stop` and `scheduled_hold_duration` features |

## Integration Gotchas

Common mistakes when connecting data sources for this system.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Telemetry to Arrivals join | Using forward-search `find_next_arrival` which matches wrong visit on loop routes | Use transition-based matching: detect when `nextStopId` changes in telemetry, then find arrivals in narrow window around transition |
| Weather data join | Joining by exact timestamp (misses if weather is hourly and telemetry is per-second) | Join by `floor(timestamp, 1 hour)` key. Already done correctly in existing `WeatherData.get_weather()` |
| GTFS schedule data | Assuming `trip_id` in telemetry matches GTFS `trip_id` | Telemetry may use `patternId` not `trip_id`. Map through GTFS `trips.txt` (pattern -> trip -> shape). The existing code has this mapping in `GTFSRouteData` |
| Historical stats | Computing historical averages including test period data | Compute historical stats only from training split timestamps, not from full arrivals CSV |
| ETA SPOT `etaSeconds` field | Treating as "seconds until arrival" | It is actually "minutes since midnight" in local time (lines 1082-1089 of data_prep.py). Must convert: `(etaSeconds - current_minutes_since_midnight) * 60` |

## Performance Traps

Patterns that work at small scale but fail as data or route coverage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Per-row label lookup with O(n) scan | Label creation takes hours | Pre-sort arrivals by (vehicle, timestamp), use binary search or merge_asof | With > 500K telemetry rows |
| Loading all telemetry into memory at once | OOM errors | Process in chunks by date or vehicle, use Parquet with column pruning | With > 2M telemetry records (roughly 3+ months of data) |
| Rolling features computed per-vehicle with pandas apply | Feature computation takes 10+ minutes | Use vectorized operations or pre-group by vehicle. Current code already groups by vehicle which is correct | With > 50 vehicles or > 1M records |
| XGBoost DMatrix from dense numpy array | Memory bloat from sparse one-hot features | Use native categorical support (`enable_categorical=True`) or sparse DMatrix | With > 100 categorical features after one-hot encoding |
| Hyperparameter tuning with full dataset | Each trial takes 10+ minutes, tuning takes days | Use subsample for tuning (25-50% of data), then train final model on full data | With > 500K training rows |

## Domain-Specific Pitfalls

### Pitfall 6: Timepoint Hold Modeling Failures

**What goes wrong:**
Auburn Transit uses a timepoint system where buses hold at certain designated stops until the scheduled time if they arrive early. A bus arriving 3 minutes early at a timepoint will sit there for 3 minutes, creating a pattern that looks like zero progress but is not delay. If the model does not account for this:
- It learns that "speed = 0 for 3 minutes" means something is wrong, overpredicting delay for downstream stops.
- It cannot explain bimodal dwell time distributions at timepoint stops (sometimes 30 seconds, sometimes 5 minutes).
- Predictions for stops immediately after timepoints are systematically wrong.

**How to avoid:**
- Add explicit features: `is_approaching_timepoint` (boolean), `scheduled_departure_from_timepoint` (seconds until scheduled departure), `timepoint_hold_expected` (scheduled departure - current time, clamped to 0).
- The timepoint hold feature is one of the most predictive features for transit ETA because it explains why buses sit idle.
- Identify timepoint stops from GTFS `stop_times.txt` where `timepoint = 1` or where `arrival_time != departure_time`.

**Warning signs:**
- Model consistently overpredicts ETA for stops immediately downstream of timepoints.
- Feature importance shows `speed` and `current_delay_sec` as top features but model accuracy is poor at timepoint stops.
- Residual analysis shows systematic bias at specific stops.

**Phase to address:**
Feature engineering phase. Must identify timepoint stops from GTFS data and compute hold-related features before model training.

---

### Pitfall 7: XGBoost Overfitting with 5 Weeks of Training Data

**What goes wrong:**
Five weeks of data (~25 service days) is small for a model covering 23 routes. With per-stop row expansion and multiple telemetry pings per approach, you may have 100K-500K rows, but the effective sample diversity is limited:
- Only ~25 unique days (limited day-of-week variation: ~3-4 Mondays).
- Weather variation is limited (5 weeks in Nov-Jan: mostly cold, occasional rain).
- Special events (football games, holidays) may appear once or not at all.
- XGBoost with default settings (max_depth=6, 100+ trees) will memorize the training data.

**How to avoid:**
- Aggressive regularization: `max_depth=3-4`, `min_child_weight=10-50`, `subsample=0.7`, `colsample_bytree=0.7`, `reg_lambda=1-10`.
- Low learning rate (`eta=0.01-0.05`) with early stopping (`early_stopping_rounds=50`).
- Limit `num_boost_round` to 200-500 maximum, relying on early stopping to find the right number.
- Use `TimeSeriesSplit` with at least 3-5 folds for hyperparameter tuning via Optuna or similar.
- Feature selection: with small data, fewer features generalize better. Start with the top 10-15 features, not all 50+.
- Consider that route distance to stop + scheduled ETA alone explain 70-80% of variance. Extra features provide diminishing returns on small data.

**Warning signs:**
- Training RMSE is much lower than validation RMSE (ratio > 2:1).
- Adding more trees improves training but hurts validation (classic overfitting curve).
- Model performs well on training weeks but poorly on a held-out week.
- Feature importance is spread across many weak features instead of concentrated on a few strong ones.

**Phase to address:**
Model training phase. Set conservative defaults from the start. Build an overfitting monitoring dashboard (train vs. val loss curves).

---

### Pitfall 8: Treating ETA SPOT System ETA as a Simple Number

**What goes wrong:**
The `etaSeconds` and `scheduledEta` fields from the ETA SPOT telemetry API are not "seconds until arrival" despite the field name. They are actually **minutes since midnight in local time** (the existing v2 code on lines 1082-1098 already handles this conversion). If you feed these raw values into XGBoost as features without conversion:
- The model receives a number like `870` (meaning 2:30 PM = 870 minutes since midnight) and interprets it as an "ETA" feature.
- This creates a massive correlation with `time_of_day` features, not with actual ETA.
- The model may still "work" because time_of_day correlates with transit patterns, but the feature is semantically meaningless.

**How to avoid:**
- Always convert: `system_eta_seconds = (etaSeconds_field - current_minutes_since_midnight) * 60`.
- After conversion, clamp to `max(0, value)` to handle cases where the scheduled time has already passed.
- Validate by checking that converted values are in a reasonable range (0-1800 seconds for campus transit).
- The existing v2 pipeline handles this correctly. Ensure the XGBoost pipeline preserves this conversion.

**Warning signs:**
- `etaSeconds` feature has values in the range 400-1200 (minutes) instead of 0-900 (seconds).
- Feature importance shows `etaSeconds` as #1 feature but model still has high error.
- Model accuracy varies dramatically by time of day.

**Phase to address:**
Feature engineering phase. Verify conversion is applied before features are finalized.

---

### Pitfall 9: Ignoring GPS Noise in Position-Based Features

**What goes wrong:**
GPS positions from transit buses have 5-15 meter accuracy but can have occasional jumps of 50-200 meters due to urban canyon effects, tunnel exits, or cold starts. These jumps cause:
- Haversine distance calculations to spike (bus "teleports" 200m, making distance_to_stop suddenly change).
- Rolling speed features to spike (implied speed of 200+ mph for one ping).
- Route distance snapping to jump to a different segment of the shape.

**How to avoid:**
- Apply GPS noise filtering: remove pings where implied speed > 80 mph (impossible for campus bus).
- Use rolling median instead of rolling mean for speed features (more robust to outliers).
- Clamp distance changes between consecutive pings to a maximum reasonable value.
- The route distance calculation (snapping to GTFS shape) is more robust than raw haversine because it constrains to the route geometry, but still validate that `route_distance_to_stop` is monotonically decreasing for approach sequences.

**Warning signs:**
- `speed_max_30s` feature has values > 100 mph in the data.
- `distance_traveled_30s` has spikes > 500 meters (impossible at campus speeds in 30 seconds).
- Route distance to stop occasionally increases as bus approaches stop.

**Phase to address:**
Data preparation phase -- filtering and cleaning. Add GPS sanity checks before feature computation.

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Label creation:** Often missing loop route disambiguation -- verify that for routes where a bus visits the same stop twice per trip, the correct visit is matched.
- [ ] **Temporal split:** Often missing gap period between train/val -- verify there is at least one service day gap to prevent same-trip leakage at boundary.
- [ ] **Feature engineering:** Often missing timepoint features -- verify that `is_timepoint_stop` and hold duration are included, not just generic stop features.
- [ ] **Custom loss function:** Often missing gradient/hessian unit tests -- verify that loss decreases on synthetic data before running on real data.
- [ ] **Categorical encoding:** Often missing `enable_categorical=True` -- verify route_id and stop_id are treated as categoricals, not ordinal integers.
- [ ] **Historical features:** Often computed on full dataset instead of train-only -- verify that `segment_avg_travel_time_sec` and `stop_avg_dwell_time_sec` are computed only from training data timestamps.
- [ ] **Model evaluation:** Often shows only aggregate MAE -- verify per-route, per-stop, and per-ETA-bucket metrics (model may be great for 2-minute ETAs but terrible for 8-minute ETAs).
- [ ] **Inference pipeline:** Often ignores feature computation latency -- verify that all features can be computed in < 500ms for real-time prediction.

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Data leakage (future features) | MEDIUM | Remove leaked features, retrain. May need to rerun data pipeline if leak is in label creation |
| Random split instead of temporal | LOW | Re-split data by time, retrain. Model architecture unchanged |
| Correlated row inflation | MEDIUM | Add group columns, re-evaluate with GroupKFold. May reveal model is worse than expected |
| Custom loss sign error | LOW | Fix gradient/hessian signs, retrain. Easy to detect from loss curve |
| Label noise from bad joins | HIGH | Requires reworking the join logic, rerunning full pipeline, retraining. Hardest to detect |
| Timepoint modeling absent | MEDIUM | Add timepoint features, retrain. Requires GTFS analysis to identify timepoint stops |
| Overfitting on small data | LOW | Increase regularization, reduce max_depth, add early stopping. Quick hyperparameter changes |
| GPS noise in features | MEDIUM | Add filtering step, rerun feature pipeline, retrain |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Future information leakage | Data Prep: Feature Engineering | Audit each feature against "available at prediction time" checklist |
| Random temporal splitting | Data Prep: Splitting | Confirm train max timestamp < val min timestamp with gap |
| Correlated row explosion | Data Prep: Row Structure + Model Training: CV | Use GroupKFold, verify group IDs are assigned |
| Asymmetric loss implementation | Model Training: Custom Objective | Unit test on synthetic data: asymmetric predictions, loss decreases |
| Label noise from joins | Data Prep: Label Creation | Label quality report: distribution plots, join success rate > 60% |
| Timepoint hold modeling | Data Prep: Feature Engineering | Check that model residuals at timepoint stops are unbiased |
| XGBoost overfitting | Model Training: Regularization | Train vs. val loss curves converge, early stopping triggers |
| System ETA misinterpretation | Data Prep: Feature Engineering | Verify converted values in 0-1800 range, not 400-1200 |
| GPS noise | Data Prep: Filtering | Speed distribution has no values > 80 mph, distances are monotonic |

## Sources

- [XGBoost Custom Objective Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/custom_metric_obj.html) -- HIGH confidence: official docs on gradient/hessian requirements
- [XGBoost Advanced Custom Objectives](https://xgboost.readthedocs.io/en/latest/tutorials/advanced_custom_obj.html) -- HIGH confidence: official docs
- [XGBoost Categorical Data](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html) -- HIGH confidence: native categorical support details
- [XGBoost Parameter Tuning Notes](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html) -- HIGH confidence: official regularization guidance
- [NVIDIA: Categorical Features in XGBoost Without Manual Encoding](https://developer.nvidia.com/blog/categorical-features-in-xgboost-without-manual-encoding/) -- MEDIUM confidence: verified against official docs
- [Transit App: Public transit ETAs are often fantastically wrong](https://blog.transitapp.com/better-predictions/) -- MEDIUM confidence: domain expertise from transit app company
- [Arrival Time Prediction for Autonomous Shuttle Services (arxiv)](https://arxiv.org/html/2401.05322v1) -- MEDIUM confidence: peer-reviewed, temporal split methodology
- [Hidden Leaks in Time Series Forecasting (arxiv)](https://arxiv.org/html/2512.06932v1) -- MEDIUM confidence: recent research on temporal leakage
- [Capital One: How to Control Your XGBoost Model](https://www.capitalone.com/tech/machine-learning/how-to-control-your-xgboost-model/) -- MEDIUM confidence: practical XGBoost tuning advice
- Existing codebase analysis: `data_prep.py`, `loss.py`, `pipeline.py`, `config.py`, `label_creator.py` -- HIGH confidence: direct code inspection
- [AppsFlyer: Building a Custom Objective Function for XGBoost](https://medium.com/appsflyerengineering/building-a-tunable-and-configurable-custom-objective-function-for-xgboost-d3ced8967809) -- MEDIUM confidence: practical implementation pattern

---
*Pitfalls research for: Transit ETA prediction with XGBoost, Auburn University Tiger Transit*
*Researched: 2026-02-03*
