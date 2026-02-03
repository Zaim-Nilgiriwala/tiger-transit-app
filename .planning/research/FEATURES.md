# Feature Research: XGBoost ETA Model Input Features

**Domain:** Transit bus arrival time prediction (ML model input features)
**Researched:** 2026-02-03
**Confidence:** MEDIUM-HIGH (well-studied domain; specific Auburn/timepoint aspects are domain-specific inference)

---

## Feature Landscape

This document covers ML model input features (not product features) for the Tiger Transit XGBoost ETA model. Features are categorized by their impact on model accuracy: table stakes features that any competent model must include, differentiator features that separate a good model from a great one, and anti-features that seem useful but hurt performance.

### Table Stakes Features (Must Have or Model Is Weak)

These are the baseline features that every transit ETA model in the literature uses. Omitting any of these will produce a noticeably worse model than a simple schedule-based baseline.

| Feature | Why Essential | Complexity | Encoding Notes | Confidence |
|---------|--------------|------------|----------------|------------|
| **distance_to_target** (route distance along shape from current position to target stop, in meters) | Single most predictive feature in virtually every transit ETA paper. Without it the model has no spatial anchor. | MEDIUM -- requires snapping GPS to GTFS shape and computing cumulative `shape_dist_traveled` | Continuous, no encoding needed. Use route distance, NOT haversine. | HIGH |
| **scheduled_time_to_target** (seconds from now until scheduled arrival at target stop) | The schedule is the strongest available prior. XGBoost learns residuals around schedule. Zhu et al. (2022) and multiple studies confirm schedule deviation as top feature. | LOW -- join GTFS stop_times to current trip, subtract current time | Continuous (seconds). Can be negative if bus is late. | HIGH |
| **current_speed** (v, instantaneous GPS speed) | Direct measure of current travel conditions. In Zhu et al., speed variation was a top-3 influencing factor. | LOW -- available directly from telemetry | Continuous. Clip outliers (e.g., > 80 mph = GPS error). | HIGH |
| **stops_remaining** (integer count of stops between current position and target stop) | Captures dwell time accumulation. More stops = more variability. Core in every multi-stop model. | LOW -- count from stop sequence | Integer, treat as continuous. | HIGH |
| **lateness_now** (current schedule deviation in seconds: actual_time - scheduled_time at last stop) | Strongest real-time signal of whether bus is running fast or slow. Captures current trip's deviation pattern. | LOW -- `lastStop.time - lastStop.sdTime` | Continuous (positive = late, negative = early). | HIGH |
| **time_of_day** (minutes since midnight or fractional hours) | Travel times vary dramatically by time of day (rush hour, midday, evening). Universal in all studies. | LOW | **For XGBoost: use raw minutes_since_midnight as continuous.** Trees can split on arbitrary thresholds, so cyclical sin/cos encoding is unnecessary and can actually hurt tree models (see Anti-Features). | HIGH |
| **day_of_week** (0-6) | Weekend vs. weekday patterns are fundamentally different. Saturday service differs from Tuesday. | LOW | **Use XGBoost native categorical** (`enable_categorical=True`, dtype `category`). Do NOT one-hot encode -- native partition splits are optimal. | HIGH |
| **stop_index** (ordinal position of target stop in the route's stop sequence) | Captures systematic patterns: early stops on a route behave differently than late stops (cumulative delay, passenger accumulation). | LOW | Continuous integer. | HIGH |
| **route_progress** (nextStopPercentProgress -- fraction of current segment completed) | Interpolates position between last stop and next stop. Critical for accuracy within a segment. | LOW -- available from telemetry | Continuous [0, 1]. | HIGH |
| **precipitation** (mm/hr from weather data) | Rain demonstrably slows buses. Zhu et al. found weather in the top influencing factors. Even small precipitation increases travel time 5-15%. | LOW -- join weather_data.csv by hour | Continuous. The `is_raining` binary is redundant if you include precipitation_mm -- XGBoost can learn the threshold itself. | MEDIUM |
| **temperature** (Celsius) | Extreme temperatures affect boarding times (passengers slower, doors open longer) and road conditions. | LOW -- from weather CSV | Continuous. | MEDIUM |

### Differentiator Features (Give Competitive Advantage Over Baselines)

These features separate a well-engineered model from one that just uses the basics. Each has evidence of improving accuracy in the literature or strong domain-specific reasoning for the Auburn context.

| Feature | Value Proposition | Complexity | Encoding Notes | Confidence |
|---------|-------------------|------------|----------------|------------|
| **rolling_avg_speed_30s / 60s / 120s / 180s** (exponential or simple moving average of GPS speed) | Smooths GPS noise and captures traffic trend. A bus decelerating over 2 minutes is more informative than instantaneous speed. The Lag Model approach in the autonomous shuttle study (arXiv 2401.05322) found recent lag features highly predictive. 30s captures stop-and-go; 180s captures corridor-level congestion. | MEDIUM -- requires windowed aggregation over recent telemetry | Four continuous features. Consider also **speed_trend** (180s - 30s) as a derivative feature capturing acceleration/deceleration pattern. | HIGH |
| **historical_segment_time_mean** (average travel time for this segment at this hour-of-day, from training data) | Encodes "how long does this segment usually take at 8am on a Tuesday?" Acts as a learned prior. Multiple papers use segment-level historical averages as a strong baseline feature. | HIGH -- requires pre-computing from training data, keyed by (segment_id, hour, day_type) | Continuous (seconds). Also compute **historical_segment_time_std** to capture variability. | HIGH |
| **historical_dwell_time_mean** (average dwell time at each stop between current position and target) | Dwell time is "among the most important factors" per the autonomous shuttle study. Cumulative dwell across multiple stops can dominate travel time on short routes. | HIGH -- requires computing from arrivals data, keyed by (stop_id, hour, day_type) | Continuous (seconds). Sum of expected dwell times between current position and target. | MEDIUM |
| **is_timepoint** (boolean: is the target stop a timepoint?) | Tiger Transit-specific. Timepoint stops have mandatory holds -- the bus CANNOT depart before scheduled time. This creates a hard floor on ETA when bus is early. Without this feature, model will systematically underpredict for timepoint stops when bus is running ahead of schedule. | MEDIUM -- requires timepoint mapping from Excel spreadsheet | Binary (0/1). | HIGH |
| **timepoints_remaining** (count of timepoint stops between current position and target) | Each intervening timepoint adds potential forced dwell time. A target that is 3 timepoints away has more schedule-recovery opportunities (and delays) than one with 0 timepoints. | MEDIUM -- requires timepoint list per route | Integer, treat as continuous. | HIGH |
| **time_until_next_timepoint_departure** (seconds until scheduled departure at next timepoint, if bus is ahead of schedule) | Directly encodes the forced wait. If bus is 3 minutes early and next timepoint departure is in 5 minutes, the bus will wait 3 minutes there. This is the single most important Auburn-specific feature. | HIGH -- requires real-time schedule calculation | Continuous (seconds). Zero if bus is behind schedule or no upcoming timepoint. | HIGH |
| **is_rush_hour** (boolean: is current time in a defined rush window?) | Captures bimodal traffic pattern. Auburn campus has distinct rush patterns around class changes. | LOW | Binary (0/1). Define windows: 7:30-9:00 AM, 11:30-1:00 PM, 3:30-5:30 PM for Auburn. | MEDIUM |
| **class_let_out_recently** (boolean: did a class period end within last 15 minutes?) | Auburn-specific. Class dismissal at :50 and :00 creates surge boarding demand and pedestrian/traffic congestion. This is a differentiator that generic transit models lack. | LOW -- approximate from clock time | Binary (0/1). Classes end at :50 of each hour (50-min classes) and :00 (for some). Window: 5 min before to 15 min after. | MEDIUM |
| **passenger_load** (current occupancy from telemetry) | Higher load = longer dwell times at remaining stops (more alighting). Also correlates with route demand patterns. | LOW -- from telemetry `load` field | Continuous integer. | MEDIUM |
| **heading_alignment** (cosine similarity between bus heading and bearing to target stop) | Captures whether bus is moving toward or away from target. A bus heading away from its next stop (loop routes, turning) will take longer. Already used in existing PyTorch model. | MEDIUM -- requires bearing calculation | Continuous [-1, 1]. Better than raw heading for XGBoost. | MEDIUM |
| **is_idle / idle_duration** (bus stationary for > threshold seconds) | A currently-idling bus adds direct delay. Idle duration captures severity (traffic light vs. breakdown vs. driver break). | LOW -- from telemetry `isIdle` and `idle` fields | Binary + continuous pair. | MEDIUM |
| **segment_id** (identifier for the route segment between consecutive stops) | Allows model to learn per-segment patterns (a segment with traffic lights vs. highway). | LOW -- derived from route stop sequence | **Use XGBoost native categorical** with partition splits. Do NOT one-hot encode (too many segments). | MEDIUM |
| **patternID** (route pattern / direction variant) | Different patterns of the same route may have different stop sequences and travel characteristics. Subsumes route + direction information. | LOW -- from telemetry | **Use XGBoost native categorical.** | MEDIUM |
| **offroute** (boolean: is bus flagged as off-route?) | Off-route buses have unpredictable travel times. Model should learn higher uncertainty. | LOW -- from telemetry | Binary (0/1). | LOW-MEDIUM |

### Anti-Features (Seem Useful but Hurt Performance)

These are features that appear reasonable but introduce problems including data leakage, encoding issues, or noise that degrades XGBoost performance.

| Anti-Feature | Why Tempting | Why Problematic | What to Do Instead |
|--------------|-------------|-----------------|-------------------|
| **Raw lat/lon as features** | GPS position contains spatial info | For tree-based models, raw lat/lon creates axis-aligned splits that poorly capture route geometry. A bus at (32.605, -85.485) and one at (32.606, -85.485) may be on completely different routes or opposite sides of campus. Lat/lon are only meaningful relative to the route shape. | Use **route_progress**, **distance_to_target**, and **segment_id** instead. These encode position relative to the route, which is what matters. |
| **Cyclical sin/cos encoding for time_of_day** | Standard for neural networks to handle midnight wraparound | XGBoost splits on `feature < threshold`. Sin/cos creates a non-monotonic mapping where 11:55 PM and 12:05 AM have similar sin values but ALSO 11:55 AM has a similar sin value. Trees cannot efficiently learn from this. One split cannot isolate "8-9 AM rush hour" from sin/cos. | Use **raw minutes_since_midnight** (0-1439). XGBoost naturally handles the fact that minute 1435 is "close to" minute 5 through learning patterns, and the midnight boundary is irrelevant for daytime-only transit. |
| **One-hot encoded day_of_week (7 binary columns)** | Common approach in older tutorials | Wastes 6 degrees of freedom. XGBoost with native categorical support using partition-based splits can optimally group days (e.g., {Mon,Tue,Wed,Thu} vs {Fri} vs {Sat,Sun}) in a single split, which is more powerful and efficient than binary columns. | Use **native categorical** with `enable_categorical=True` and `dtype="category"`. |
| **One-hot encoded patternID or stop IDs** | Seems like proper categorical encoding | High cardinality (23+ routes with patterns, 100+ stops). One-hot creates sparse features that XGBoost struggles with. Also massively increases feature dimensionality. | Use **native categorical** for patternID and segment_id. For target stop, use stop_index (ordinal position) plus distance_to_target. |
| **tripID as a feature** | Unique identifier per trip, might capture trip-specific patterns | Near-unique per observation. Extremely high cardinality with almost no reuse across training examples. Model memorizes specific trips rather than learning patterns. This is a form of target leakage -- the tripID effectively encodes the time-of-day and route. | **Drop tripID entirely.** Its information is captured by patternID + time_of_day + day_of_week. If vehicle-specific patterns matter, use a vehicle_id categorical (low cardinality, ~40 buses). |
| **trainID (vehicle ID) as high-cardinality feature** | Different buses might have different speeds | With only ~5 weeks of data and ~40 vehicles, per-vehicle patterns are sparse. Risk of overfitting to specific vehicle assignments that change semester to semester. | Either **drop** or include as **native categorical** with low importance weight. Vehicle-specific speed patterns are better captured by rolling_avg_speed features. |
| **schedule.stops (raw array of upcoming stop schedule data)** | Contains rich schedule information | Raw nested/array data cannot be directly fed to XGBoost. Must be decomposed into scalar features. Feeding a serialized array is meaningless. | Decompose into: **scheduled_time_to_target**, **timepoints_remaining**, **next_stop_scheduled_arrival**. |
| **eta.stopID (the stop for which ETA Spot provides an ETA)** | System already predicts ETA, use it as a feature | Using the existing system's ETA prediction as a feature creates a dependency on the old system and is a form of soft leakage -- if the old system's prediction correlates with actual arrival time, the new model may just learn to copy it rather than learning from raw signals. Also limits the new model to only being as good as the old one. | **Drop.** Build predictions from raw signals only. If you want to use the old model as a benchmark, compare against it, do not feed it as input. |
| **Normalization / z-score scaling** | Standard ML preprocessing | XGBoost is scale-invariant. Tree splits compare `feature < threshold` -- scaling does not change split points or tree structure at all. Normalization adds unnecessary preprocessing complexity with zero benefit for tree models. | **Do not normalize any features for XGBoost.** This is a key difference from the existing PyTorch pipeline. |
| **lastStop.time as raw timestamp** | Records when bus left last stop | Raw Unix timestamps are meaningless to the model (monotonically increasing, never repeats). The useful information is the DIFFERENCE: `current_time - lastStop.time` = time since last stop, and `lastStop.time - lastStop.sdTime` = lateness_now. | Derive **time_since_last_stop** (seconds) and **lateness_now** (seconds). Drop raw timestamps. |

---

## Feature Encoding Recommendations for XGBoost

### XGBoost Native Categorical (Preferred for All Categoricals)

Since XGBoost 1.5, native categorical support with optimal partition-based splits outperforms both label encoding and one-hot encoding. Use this for all categorical features.

**Setup:**
```python
import pandas as pd

# Mark categoricals with pandas dtype
df['patternID'] = df['patternID'].astype('category')
df['segment_id'] = df['segment_id'].astype('category')
df['day_of_week'] = df['day_of_week'].astype('category')

# Enable in XGBoost
model = xgb.XGBRegressor(
    enable_categorical=True,
    max_cat_to_onehot=4,  # auto one-hot if <= 4 categories, partition otherwise
    tree_method='hist',    # required for categorical support
)
```

**Key parameter:** `max_cat_to_onehot` controls the threshold. Features with fewer categories than this value get one-hot treatment (fast); features with more get partition-based splits (powerful for high cardinality). Default of 4 is reasonable.

Source: [XGBoost Categorical Data Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html)

### Continuous Features (No Encoding Needed)

XGBoost handles continuous features natively. Do NOT:
- Normalize or standardize (scale-invariant)
- Bin/bucket continuous values (loses granularity; XGBoost finds optimal splits itself)
- Apply log transforms unless distribution is extremely skewed AND you want to compress the scale

The only preprocessing needed for continuous features is:
- **Clip outliers** (GPS speed > 80 mph, negative distances, etc.)
- **Fill missing values** with a sentinel (XGBoost handles NaN natively with `missing` parameter, which is often the best approach -- let XGBoost learn the optimal direction for missing values)

### Binary Features

Binary features (0/1) work fine as-is. No special encoding needed.

### Time Features

| Feature | Encoding | Rationale |
|---------|----------|-----------|
| time_of_day | `minutes_since_midnight` (0-1439) | Trees split on thresholds; raw minutes lets XGBoost isolate any time window |
| day_of_week | Native categorical (0-6 as `category` dtype) | Partition splits can group days optimally (e.g., weekday vs weekend) |
| is_rush_hour | Binary (0/1) | Pre-computed convenience feature; trees could learn this from time_of_day alone but explicit is faster |
| class_let_out_recently | Binary (0/1) | Domain-specific temporal signal that trees would struggle to derive from time_of_day |

---

## Feature Interaction Recommendations for XGBoost

XGBoost supports explicit [feature interaction constraints](https://xgboost.readthedocs.io/en/stable/tutorials/feature_interaction_constraint.html) that control which features can appear together in a tree path. This prevents spurious interactions while allowing known-useful ones.

### Recommended Interaction Groups

For this model, consider these interaction constraint groups if overfitting is observed:

1. **Spatial group:** `[distance_to_target, stops_remaining, stop_index, route_progress, segment_id, patternID, timepoints_remaining]` -- These features describe WHERE the bus is relative to the target. They should interact freely.

2. **Temporal group:** `[minutes_since_midnight, day_of_week, is_rush_hour, class_let_out_recently]` -- Time context features should interact (rush hour on Monday differs from rush hour on Saturday).

3. **Real-time vehicle state group:** `[current_speed, rolling_avg_speed_30s, rolling_avg_speed_60s, rolling_avg_speed_120s, rolling_avg_speed_180s, is_idle, idle_duration, passenger_load, offroute]` -- Current conditions should interact (idle + high load = long boarding dwell).

4. **Schedule adherence group:** `[lateness_now, scheduled_time_to_target, is_timepoint, time_until_next_timepoint_departure]` -- Schedule features should interact (early bus + upcoming timepoint = forced wait).

5. **Environmental group:** `[precipitation, temperature]` -- Weather features.

6. **Historical group:** `[historical_segment_time_mean, historical_segment_time_std, historical_dwell_time_mean]` -- Historical averages.

**Recommendation:** Start WITHOUT interaction constraints (let XGBoost find all interactions). Only add constraints if feature importance analysis reveals suspicious interactions or if cross-validation shows overfitting. With ~5 weeks of data, overfitting is a real risk, and constraints may help.

---

## Feature Dependencies

```
[GPS Telemetry]
    |-- current_speed, heading, lat, lon, load, isIdle, idle, offroute
    |-- rolling_avg_speed_* (requires buffering recent telemetry)
    |-- route_progress (from nextStopPercentProgress)
    |-- lateness_now (requires lastStop.time and lastStop.sdTime)
    |-- time_since_last_stop (requires lastStop.time)

[GTFS Static Data]
    |-- distance_to_target (requires shapes.txt + stop_times.txt + shape_dist_traveled)
    |-- stop_index (requires stop_times.txt ordered by stop_sequence)
    |-- scheduled_time_to_target (requires stop_times.txt)
    |-- segment_id (derived from consecutive stop pairs)

[Timepoint Spreadsheet]
    |-- is_timepoint (requires parsed timepoint mapping to stop IDs)
    |-- timepoints_remaining (requires timepoint list per route)
    |-- time_until_next_timepoint_departure (requires timepoint schedule + current lateness)

[Historical Pre-computation] (requires training data)
    |-- historical_segment_time_mean/std (aggregate from training data)
    |-- historical_dwell_time_mean (aggregate from arrivals data)

[Weather CSV]
    |-- precipitation, temperature (join by hour)

[Clock Time]
    |-- minutes_since_midnight, day_of_week, is_rush_hour, class_let_out_recently
```

### Dependency Notes

- **distance_to_target requires GTFS shape processing:** This is the highest-complexity table stakes feature. The existing `distance.py` module already computes route distance using `shape_dist_traveled`, so the infrastructure exists.
- **Timepoint features require spreadsheet parsing:** The Excel spreadsheet with 23 sheets must be parsed and human-readable stop names mapped to numeric stop IDs before timepoint features can be computed. This is a prerequisite for all timepoint features.
- **Historical features require a completed training data pipeline:** You must build the dataset once to compute historical averages, then add them as features. This creates a circular dependency -- use leave-one-out or time-windowed approach to avoid leakage.
- **Rolling speed features require temporal buffering:** During both training (from JSONL sequences) and inference (from real-time stream), you need to maintain a sliding window of recent telemetry per vehicle.

---

## MVP Feature Set (v1 Model)

### Launch With (v1 -- first trainable model)

Build the model with these features first. They cover the table stakes and are achievable with existing data:

- [x] distance_to_target (route distance)
- [x] scheduled_time_to_target
- [x] current_speed
- [x] stops_remaining
- [x] stop_index
- [x] lateness_now
- [x] route_progress
- [x] minutes_since_midnight
- [x] day_of_week (native categorical)
- [x] patternID (native categorical)
- [x] precipitation
- [x] temperature
- [x] passenger_load
- [x] is_idle

**Expected baseline:** MAE of 60-120 seconds for next-stop prediction, degrading for farther stops. This should already beat a pure schedule-based model.

### Add After Baseline Validated (v1.1)

- [ ] rolling_avg_speed_30s / 60s / 120s / 180s -- requires telemetry windowing
- [ ] is_rush_hour, class_let_out_recently -- easy temporal features
- [ ] heading_alignment to target stop
- [ ] time_since_last_stop
- [ ] offroute flag
- [ ] is_timepoint, timepoints_remaining -- requires timepoint parsing

### Add After Timepoint Mapping Complete (v1.2)

- [ ] time_until_next_timepoint_departure -- the high-value Auburn-specific feature
- [ ] historical_segment_time_mean / std -- requires pre-computation pass
- [ ] historical_dwell_time_mean -- requires arrivals data analysis
- [ ] segment_id as native categorical

### Future Consideration (v2+)

- [ ] Interaction constraints tuning based on feature importance analysis
- [ ] Speed trend (derivative of rolling averages)
- [ ] Fleet-level lag features (how are OTHER buses on this route performing right now?)
- [ ] Event features (game days, special events) -- insufficient data in current 5-week window

---

## Feature Prioritization Matrix

| Feature | Model Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| distance_to_target | HIGH | MEDIUM | P1 |
| scheduled_time_to_target | HIGH | LOW | P1 |
| lateness_now | HIGH | LOW | P1 |
| current_speed | HIGH | LOW | P1 |
| stops_remaining | HIGH | LOW | P1 |
| stop_index | HIGH | LOW | P1 |
| minutes_since_midnight | HIGH | LOW | P1 |
| day_of_week | MEDIUM | LOW | P1 |
| patternID | MEDIUM | LOW | P1 |
| route_progress | MEDIUM | LOW | P1 |
| precipitation + temperature | MEDIUM | LOW | P1 |
| rolling_avg_speed (4 windows) | HIGH | MEDIUM | P2 |
| is_timepoint | HIGH | MEDIUM | P2 |
| timepoints_remaining | HIGH | MEDIUM | P2 |
| time_until_next_timepoint_departure | HIGH | HIGH | P2 |
| historical_segment_time_mean/std | MEDIUM | HIGH | P2 |
| historical_dwell_time_mean | MEDIUM | HIGH | P2 |
| is_rush_hour | LOW | LOW | P2 |
| class_let_out_recently | MEDIUM | LOW | P2 |
| passenger_load | LOW | LOW | P1 |
| heading_alignment | LOW | MEDIUM | P3 |
| segment_id (categorical) | MEDIUM | LOW | P2 |
| is_idle / idle_duration | LOW | LOW | P2 |
| offroute | LOW | LOW | P3 |

**Priority key:**
- P1: Must have for first model training
- P2: Add after baseline is working; significant accuracy improvement expected
- P3: Nice to have; marginal improvement expected

---

## Comparison with Existing PyTorch Model Features

| Existing PyTorch Feature | New XGBoost Feature | Change | Rationale |
|--------------------------|---------------------|--------|-----------|
| heading_sin, heading_cos | heading_alignment OR drop | Simplified | Sin/cos needed for NN continuity; XGBoost doesn't need it |
| time_of_day_sin, time_of_day_cos | minutes_since_midnight | Changed encoding | Trees split on thresholds; cyclical encoding hurts trees |
| day_of_week one-hot (7 cols) | day_of_week native categorical (1 col) | Changed encoding | Native partition splits are optimal for XGBoost |
| vehicle embedding | Drop (or vehicle_id as categorical) | Removed | Embeddings are NN-specific; insufficient data for per-vehicle patterns |
| route_distance_stop{1,2,3} | distance_to_target (single) | Restructured | Per-stop row structure means one target per row |
| stops_remaining_{1,2,3} | stops_remaining (single) | Restructured | Per-stop row structure |
| is_game_day, hours_to_kickoff | Drop for v1 | Deferred | Only ~5 weeks of data with maybe 1-2 game days; insufficient signal |
| 3-stop output | 1-stop output (per-stop rows) | Architecture change | Single target variable; each row predicts one stop |
| Asymmetric loss (5x overestimate) | XGBoost quantile regression or custom objective | Needs design | Discussed below |

### Loss Function Note

The existing model uses 5x penalty for overestimation (bus arrives earlier than predicted = rider misses bus). For XGBoost, implement this as either:
1. **Custom objective function** with asymmetric gradient (preferred -- direct control)
2. **Quantile regression** predicting a conservative quantile (e.g., 60th-70th percentile)
3. **Sample weighting** (weight overestimation errors higher in the loss)

This is an architecture decision, not a feature decision, but noted here because it affects how features interact with the loss.

---

## Sources

- [XGBoost-Based Travel Time Prediction (Zhu et al., 2022)](https://onlinelibrary.wiley.com/doi/10.1155/2022/3504704) -- Feature importance analysis, MEDIUM confidence
- [Arrival Time Prediction for Autonomous Shuttles (2024)](https://arxiv.org/html/2401.05322) -- Dwell time modeling, lag features, MEDIUM confidence
- [Bus Arrival Time Prediction Using ML (2025)](https://www.researchgate.net/publication/397281321_Bus_Arrival_Time_Prediction_Using_Machine_Learning_Approaches) -- XGBoost outperforming baselines, MEDIUM confidence
- [Scalable Transit Delay Prediction (2025)](https://arxiv.org/html/2601.18521) -- Multi-resolution feature engineering, temporal leakage prevention, MEDIUM confidence
- [XGBoost Categorical Data Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html) -- Native categorical support, HIGH confidence
- [XGBoost Feature Interaction Constraints](https://xgboost.readthedocs.io/en/stable/tutorials/feature_interaction_constraint.html) -- Interaction constraint syntax, HIGH confidence
- [NVIDIA: Categorical Features in XGBoost](https://developer.nvidia.com/blog/categorical-features-in-xgboost-without-manual-encoding/) -- Partition-based splits, HIGH confidence
- [DeepETA: Uber's ETA Prediction](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/) -- Feature quantile bucketization, MEDIUM confidence
- [DoorDash ETA Predictions](https://careersatdoordash.com/blog/deep-learning-for-smarter-eta-predictions/) -- Limitations of tree models, MEDIUM confidence
- [Transit App: Better Predictions](https://blog.transitapp.com/better-predictions/) -- Real-world ETA challenges, LOW confidence
- Existing codebase: `mobile/src/ETA-Model/src/features.py`, `mobile/src/ETA-Model/src/preprocess.py` -- HIGH confidence (direct code review)

---
*Feature research for: Tiger Transit XGBoost ETA Model*
*Researched: 2026-02-03*
