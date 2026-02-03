# Project Research Summary

**Project:** Tiger Transit XGBoost ETA Model Migration
**Domain:** Transit bus arrival time prediction (ML model replacement)
**Researched:** 2026-02-03
**Confidence:** HIGH

## Executive Summary

This project replaces the existing PyTorch ETA prediction model with XGBoost for the Tiger Transit campus bus system at Auburn University. Research shows XGBoost is the industry-standard approach for tabular transit ETA prediction, achieving MAE of 16-30 seconds on similar bus arrival tasks with far simpler infrastructure than deep learning (no GPU, no batching, no normalization). The recommended stack is Python 3.12 with XGBoost 3.1.3, pandas 2.3.3, and Optuna 4.7.0 for hyperparameter tuning.

The critical technical challenge is the per-stop row explosion pattern in the data pipeline. With approximately 500K telemetry observations expanding to 4-10M training rows (one row per remaining stop), memory management becomes the primary architectural concern. The chunked-by-day processing pattern with incremental Parquet writes is essential to avoid OOM crashes. Additionally, Auburn's timepoint-hold system (buses must wait at designated stops if running early) requires explicit feature engineering - without timepoint features, the model cannot explain why buses sit idle for minutes with zero delay.

The highest risks are data leakage (using future arrival information in features), label noise from imperfect telemetry-to-arrivals joins, and overfitting on only 5 weeks of training data. These are mitigated through strict temporal splitting, vectorized label matching with validation checks, and aggressive XGBoost regularization (max_depth=3-4, min_child_weight=10-50). The existing PyTorch pipeline has established patterns for most of these challenges - the migration path is well-understood.

## Key Findings

### Recommended Stack

XGBoost 3.1.3 is the clear choice for this tabular regression task, offering native categorical support with optimal partition-based splits, built-in quantile regression for confidence intervals, and UBJSON serialization for production deployment. Compared to the existing PyTorch model, XGBoost trains in seconds rather than minutes, requires no GPU, no feature normalization, and provides interpretability through SHAP values.

**Core technologies:**
- **XGBoost 3.1.3**: Gradient boosted trees with native categorical support and quantile regression — proven for transit ETA with MAE of 16-30s in peer-reviewed studies
- **pandas 2.3.3**: Data processing and feature engineering — stick with 2.x to avoid pandas 3.0.0 breaking changes (CoW default, string dtype changes)
- **Optuna 4.7.0**: Bayesian hyperparameter optimization with XGBoost pruning callbacks — far superior to grid search for 8+ parameters
- **SHAP 0.50.0**: Model explainability with exact TreeExplainer for XGBoost — critical for debugging and validating feature impact
- **scikit-learn 1.8.0**: Metrics, TimeSeriesSplit for temporal CV — standard evaluation toolkit

**Key differences from PyTorch:**
- No feature normalization needed (tree-based, scale-invariant)
- Native categorical encoding instead of embeddings
- Full dataset training instead of batching
- Quantile regression via `reg:quantileerror` instead of multi-head outputs
- UBJSON model format instead of pickle (cross-version compatible)

### Expected Features

**Must have (table stakes):**
- **distance_to_target** (route distance along GTFS shape) — single most predictive feature in all transit ETA literature
- **scheduled_time_to_target** — schedule is the strongest prior; XGBoost learns residuals around it
- **lateness_now** (current schedule deviation) — strongest real-time signal of whether bus is running fast/slow
- **current_speed** and **stops_remaining** — direct measures of vehicle state and dwell time accumulation
- **time_of_day** (as raw minutes, not cyclical) and **day_of_week** (as native categorical) — capture temporal patterns
- **precipitation** and **temperature** — weather demonstrably slows buses (5-15% impact)

**Should have (competitive):**
- **rolling_avg_speed** (30s/60s/120s/180s windows) — smooths GPS noise, captures traffic trends
- **is_timepoint**, **timepoints_remaining**, **time_until_next_timepoint_departure** — Auburn-specific mandatory hold features (highest-value differentiator)
- **historical_segment_time_mean/std** — learned priors for each route segment at each hour-of-day
- **historical_dwell_time_mean** — cumulative expected boarding time across remaining stops
- **is_rush_hour**, **class_let_out_recently** — Auburn-specific temporal signals (class dismissal creates surge boarding)

**Defer (v2+):**
- **passenger_load** boarding correlation — current load field available but low priority
- **segment_id** as categorical — adds marginal value if historical segment times already included
- **speed_trend** (derivative of rolling averages) — diminishing returns with small dataset
- **event features** (game days, special events) — insufficient data with only 5 weeks

**Anti-features (never include):**
- Raw lat/lon (use route_progress and distance_to_target instead)
- Cyclical sin/cos for time_of_day (trees can't split efficiently on non-monotonic features)
- One-hot encoded categoricals (use XGBoost native categorical support)
- Normalized features (zero benefit for tree models)
- Future arrival information like dwell_sec at target stop (data leakage)

### Architecture Approach

The pipeline is a linear data flow from raw sources through feature engineering to XGBoost training. The critical architectural decision is the two-phase feature engineering pattern: compute telemetry-level features (rolling stats, weather) BEFORE row explosion, then compute per-target-stop features (distance, stops_remaining) AFTER explosion. This avoids wastefully recomputing identical rolling window values for every exploded copy of the same observation.

**Major components:**
1. **Data Loaders** — parse JSONL telemetry, CSV arrivals, GTFS, weather, timepoints Excel into DataFrames
2. **Filters** — exclude jAUnt/Shuttle vehicles, inactive trips, invalid GPS, depot patterns
3. **Feature Pipeline** — two-phase: pre-explosion (rolling/weather/temporal), post-explosion (distance/scheduled time)
4. **Row Exploder** — expand each telemetry row into N rows (one per remaining stop) — **critical memory step**
5. **Label Creator** — vectorized merge_asof to join exploded rows with arrivals CSV for ground truth
6. **Splitter** — temporal split by calendar date (train: weeks 1-3.5, val: 3.5-4.25, test: 4.25-5)
7. **Trainer** — XGBoost DMatrix with native categorical support, early stopping on validation MAE
8. **Evaluator** — metrics by route/stop-bucket/time-of-day, SHAP feature importance, residual analysis

**Key patterns:**
- **Chunked explosion with Parquet append**: Process data day-by-day to avoid OOM on 4-10M exploded rows
- **Temporal split by date, not row index**: Prevents future data leaking into training set
- **XGBoost native API with DMatrix**: Use `xgb.train()` not sklearn wrapper for categorical support and early stopping
- **Vectorized label joins**: Use `pd.merge_asof()` not row-by-row loops (O(N log N) vs O(N*M))

### Critical Pitfalls

1. **Data leakage through future arrival information** — Including dwell_sec, boardings, alightings from the target stop's arrival as features creates leakage (this data doesn't exist at prediction time). The existing PyTorch pipeline has this issue in `build_feature_vector()`. Use only historical averages, never current-trip actuals. Verified by checking if model achieves suspiciously high accuracy (MAE < 15s on 5+ min predictions).

2. **Random train/test splitting of temporal data** — Random shuffling causes temporal leakage (model sees future in training). Always split by calendar date with train < val < test timestamps and a gap period between splits. Existing pipeline does this correctly with `time_based_split()`.

3. **Correlated row explosion** — Single telemetry snapshot generates N rows with identical features but different labels. Naive k-fold CV treats these as independent, inflating metrics. Use `GroupKFold` with groups = trip_id, or subsample approach sequences (sample_rate 5-10). Verify train/val gap prevents same-trip boundary leakage.

4. **Asymmetric loss implementation errors** — Porting the 5x overestimation penalty to XGBoost custom objective requires correct gradient/hessian. Common mistakes: hessian of zero (prevents tree growth), sign errors (optimizes wrong direction), non-smooth kink at error=0. Alternative: use `reg:quantileerror` with `quantile_alpha=0.65` which naturally penalizes underestimation more.

5. **Label noise from telemetry-to-arrivals joins** — Timezone mismatches (DST boundaries), loop route ambiguity (bus visits same stop twice), stop name mapping failures create systematic label errors. Use transition-based matching (detect when nextStopId changes) not simple forward-search. Validate with distribution plots, check for 3600s spikes (timezone bug), require join success rate > 60%.

6. **Timepoint hold modeling failures** — Auburn buses hold at timepoint stops if early. Without explicit timepoint features, model can't explain why speed=0 for minutes. Add `is_approaching_timepoint`, `time_until_next_timepoint_departure` features. Identify timepoints from GTFS or Excel spreadsheet.

7. **Overfitting on 5 weeks of data** — Only ~25 service days, limited weather variation, few special events. Use aggressive regularization: max_depth=3-4, min_child_weight=10-50, subsample=0.7, eta=0.01-0.05, early_stopping_rounds=50. Feature selection: start with top 10-15 features, not all 50+.

## Implications for Roadmap

Based on research, suggested phase structure:

### Phase 1: Data Foundation
**Rationale:** Must establish reliable data loading, filtering, and GTFS integration before any feature engineering. The existing PyTorch pipeline has working loaders but needs adaptation for XGBoost (no normalization, different label format).

**Delivers:**
- Clean telemetry DataFrame (filtered, GPS validated)
- Arrivals CSV with stop name mapping to GTFS stop IDs
- GTFS route distance calculator (shapes.txt, stop_times.txt integration)
- Weather data join pipeline

**Addresses:**
- Table stakes infrastructure for distance_to_target feature (highest priority)
- Prevents GPS noise pitfall through filtering
- Prevents integration gotchas (timepoint mapping, weather join by hour)

**Avoids:**
- Building on unstable data foundation
- Discovering GTFS integration issues late in development

**Research flag:** No additional research needed — well-documented patterns.

### Phase 2: Core Feature Engineering
**Rationale:** Build the minimum viable feature set (table stakes only) to establish baseline model performance. This validates the data pipeline and provides a performance benchmark before adding complexity.

**Delivers:**
- Telemetry-level features: speed, heading, lateness_now, temporal features
- Weather join (temperature, precipitation)
- Basic GTFS features: distance_to_target, stops_remaining, scheduled_time_to_target

**Addresses:**
- Table stakes features from FEATURES.md
- Two-phase feature pattern (pre-explosion features computed here)

**Avoids:**
- Feature engineering pitfall: includes only "available at prediction time" features
- No normalization (XGBoost anti-pattern)

**Research flag:** No additional research needed — standard pandas operations.

### Phase 3: Row Explosion & Label Creation
**Rationale:** This is the critical memory and correctness bottleneck. Must be implemented carefully with chunked processing and vectorized joins. Separate phase because it's architecturally distinct from feature engineering.

**Delivers:**
- Per-stop row explosion (telemetry rows → N rows per remaining stop)
- Chunked-by-day processing with Parquet append to avoid OOM
- Vectorized label creation via merge_asof
- Label quality validation (distribution plots, join success rate)

**Addresses:**
- Row explosion anti-pattern (chunked processing prevents OOM)
- Label noise pitfall (vectorized joins + validation checks)
- Correlated row inflation (adds trip_id grouping for GroupKFold)

**Avoids:**
- O(N*M) row-by-row label matching
- Memory crashes from holding full exploded dataset
- Silent label quality issues

**Research flag:** Needs targeted research on Parquet chunking patterns and merge_asof optimization if performance issues arise.

### Phase 4: Temporal Splitting & Data Validation
**Rationale:** Clean boundary between data preparation and model training. Temporal split is critical enough to warrant separate validation phase.

**Delivers:**
- Train/val/test split by calendar date (70/15/15)
- Gap period between splits (minimum 1 service day)
- Data quality report: feature distributions, label statistics, correlation matrix
- Final Parquet files for training

**Addresses:**
- Temporal leakage pitfall (date-based split, not random)
- Data validation before training investment

**Avoids:**
- Discovering temporal leakage after model training
- Training on low-quality data

**Research flag:** No additional research needed — standard temporal split patterns.

### Phase 5: Baseline XGBoost Model
**Rationale:** Train first model with conservative hyperparameters on core features only. Establishes performance floor and validates pipeline end-to-end before adding complexity.

**Delivers:**
- XGBoost model with reg:squarederror objective
- Conservative regularization (max_depth=3-4, min_child_weight=50)
- Early stopping on validation MAE
- Baseline metrics: MAE, RMSE, MAPE overall and by route

**Addresses:**
- Overfitting pitfall (aggressive regularization from start)
- Native categorical support for day_of_week, route_id

**Avoids:**
- Over-engineering before validating basics
- Tuning on unstable baseline

**Research flag:** No additional research needed — well-documented XGBoost patterns.

### Phase 6: Differentiator Features
**Rationale:** Add high-value features (rolling speeds, timepoints, historical stats) after baseline validates pipeline. These require additional complexity but provide competitive accuracy.

**Delivers:**
- Rolling speed features (30s/60s/120s/180s windows)
- Timepoint features (is_timepoint, timepoints_remaining, time_until_next_timepoint_departure)
- Historical segment times and dwell times (computed from training set only)
- Auburn-specific temporal features (is_rush_hour, class_let_out_recently)

**Addresses:**
- Differentiator features from FEATURES.md
- Timepoint hold modeling pitfall (explicit timepoint features)

**Avoids:**
- Historical feature leakage (computed from train split only)

**Research flag:** Timepoint Excel parsing may need targeted research if format is non-standard.

### Phase 7: Asymmetric Loss & Quantile Regression
**Rationale:** Replicate the existing PyTorch model's 5x overestimation penalty. Separate phase because custom objectives require careful validation and are independent of feature engineering.

**Delivers:**
- XGBoost custom objective with asymmetric loss (or quantile regression alternative)
- Gradient/hessian unit tests on synthetic data
- Comparison: asymmetric vs. quantile vs. baseline squared error
- Multi-quantile model for P50/P80 predictions

**Addresses:**
- Parity with existing PyTorch asymmetric loss
- Quantile regression for confidence intervals

**Avoids:**
- Custom objective pitfalls (hessian=0, sign errors, non-smooth loss)

**Research flag:** May need research on XGBoost quantile regression parameter tuning if custom objective proves unstable.

### Phase 8: Hyperparameter Tuning
**Rationale:** After features and loss function are stable, optimize model capacity. Uses Optuna for Bayesian search with TimeSeriesSplit cross-validation.

**Delivers:**
- Optuna study with 100-200 trials
- Hyperparameter search space: max_depth (3-8), learning_rate (0.01-0.1), subsample, colsample, min_child_weight, reg_alpha/lambda
- XGBoostPruningCallback for early trial stopping
- Best hyperparameters + tuning report

**Addresses:**
- Optimal model capacity vs. overfitting trade-off
- Grouped CV (by trip_id) to prevent correlated row inflation

**Avoids:**
- Manual hyperparameter grid search (inefficient for 8+ params)

**Research flag:** No additional research needed — standard Optuna patterns.

### Phase 9: Evaluation & Explainability
**Rationale:** Comprehensive evaluation before deployment. Sliced metrics reveal where model fails; SHAP values validate feature logic.

**Delivers:**
- Metrics by route, stops_remaining bucket, time_of_day, distance bucket
- Residual analysis: systematic bias detection
- SHAP feature importance (global) and sample explanations (local)
- Comparison report vs. existing PyTorch model

**Addresses:**
- Model validation beyond aggregate MAE
- Explainability for debugging and stakeholder trust

**Avoids:**
- Deploying model with hidden failure modes
- Black-box predictions

**Research flag:** No additional research needed — SHAP TreeExplainer is well-documented.

### Phase 10: Production Artifacts & Deployment Prep
**Rationale:** Package model, metadata, and feature computation logic for integration with Tiger Transit backend.

**Delivers:**
- model.ubj (UBJSON format, cross-version compatible)
- feature_columns.json (ordered list for inference)
- model_config.json (hyperparameters, training metadata)
- Feature computation module (same logic as training pipeline, < 500ms latency)

**Addresses:**
- Production deployment requirements
- Model serialization best practices (UBJSON, not pickle)

**Avoids:**
- Pickle serialization anti-pattern
- Feature computation drift between training and inference

**Research flag:** No additional research needed — XGBoost model I/O is standardized.

### Phase Ordering Rationale

- **Foundation first (1-2):** Data loading and core features establish stable baseline before complexity
- **Explosion as bottleneck (3):** Row explosion is architecturally distinct and memory-critical, needs dedicated focus
- **Baseline before optimization (5 before 6-8):** Validate simple model before investing in advanced features and tuning
- **Loss function after features (7):** Custom objectives are independent of features, easier to validate on stable feature set
- **Tuning after loss (8):** Hyperparameter search requires stable objective function
- **Evaluation last (9):** Comprehensive analysis after model is finalized

This order minimizes rework: each phase builds on validated foundations, and expensive phases (hyperparameter tuning, feature engineering) happen after cheap validation phases.

### Research Flags

Phases likely needing deeper research during planning:
- **Phase 3 (Row Explosion):** If memory issues persist, may need research on Dask or XGBoost external_memory mode
- **Phase 6 (Timepoint Features):** If timepoint Excel format is non-standard or stop name mapping is ambiguous
- **Phase 7 (Asymmetric Loss):** If custom objective proves unstable, may need research on alternative quantile regression approaches

Phases with standard patterns (skip research-phase):
- **Phase 1, 2, 4, 5, 8, 9, 10:** Well-documented pandas, XGBoost, and Optuna patterns with high-confidence sources

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | XGBoost 3.1.3, pandas 2.3.3, Optuna 4.7.0 all verified from official docs and PyPI. Version compatibility confirmed. |
| Features | MEDIUM-HIGH | Feature importance rankings from peer-reviewed transit ETA papers (Zhu et al., autonomous shuttle study). Auburn-specific features (timepoints, class changes) are domain inference. |
| Architecture | HIGH | Two-phase feature pattern, chunked explosion, temporal split all verified from official XGBoost docs and existing codebase analysis. |
| Pitfalls | HIGH | Data leakage, temporal splitting, custom objectives verified from XGBoost official docs. Domain-specific pitfalls (timepoints, label noise) verified from existing codebase issues. |

**Overall confidence:** HIGH

The recommended stack, architecture patterns, and critical pitfalls are all verified from official documentation or existing codebase analysis. Feature prioritization has medium confidence because Auburn-specific features (timepoint holds, class dismissal patterns) are domain inferences rather than peer-reviewed findings, but the core transit ETA features (distance, schedule, speed) have high-confidence literature support.

### Gaps to Address

**Timepoint stop identification:** The timepoint Excel spreadsheet format needs inspection during Phase 6 planning. If stop names don't map cleanly to GTFS stop IDs, may require manual mapping table or fuzzy matching validation.

**Label quality threshold:** Research identifies that 60% join success rate is the minimum acceptable, but doesn't specify optimal rate. During Phase 3, establish target (70%+?) based on existing pipeline performance.

**Optimal sample rate for approach sequences:** Research suggests sample_rate 5-10 to reduce correlated rows, but optimal value depends on telemetry ping frequency. Validate during Phase 3 with train/val metric comparison.

**Quantile regression vs. custom objective trade-off:** Research presents both options for asymmetric loss but doesn't definitively recommend one. During Phase 7, prototype both and compare stability/accuracy.

**Historical feature computation:** Research specifies "compute from training set only" but doesn't detail the aggregation logic (mean by segment/hour? median? weighted by recency?). Phase 6 needs design decision informed by existing pipeline's `segment_avg_travel_time_sec` logic.

## Sources

### Primary (HIGH confidence)
- XGBoost 3.1.3 Official Documentation (parameter reference, categorical data, model I/O, custom objectives)
- pandas 2.3.3 PyPI and release notes (version compatibility, breaking changes in 3.0.0)
- scikit-learn 1.8.0 documentation (TimeSeriesSplit, metrics)
- Optuna 4.7.0 documentation (XGBoostPruningCallback, TPE sampler)
- SHAP 0.50.0 documentation (TreeExplainer)
- Existing Tiger Transit codebase (`data_prep.py`, `pipeline.py`, `label_creator.py`, `config.py`)

### Secondary (MEDIUM confidence)
- [XGBoost-Based Travel Time Prediction (Zhu et al., 2022)](https://onlinelibrary.wiley.com/doi/10.1155/2022/3504704) — feature importance analysis
- [Arrival Time Prediction for Autonomous Shuttles (arxiv 2401.05322)](https://arxiv.org/html/2401.05322) — dwell time modeling, lag features
- [Bus Arrival Time Prediction Using ML (2025)](https://www.researchgate.net/publication/397281321_Bus_Arrival_Time_Prediction_Using_Machine_Learning_Approaches) — XGBoost MAE benchmarks
- [Scalable Transit Delay Prediction (arxiv 2601.18521)](https://arxiv.org/html/2601.18521) — temporal leakage prevention
- [Part-2: How to Design an ML System for ETA Prediction](https://mlsavvy.substack.com/p/part-2-how-to-design-an-ml-system) — architecture patterns
- [Transit App: Better Predictions](https://blog.transitapp.com/better-predictions/) — real-world ETA challenges
- NVIDIA: Categorical Features in XGBoost — partition-based splits

### Tertiary (LOW confidence)
- DoorDash ETA Predictions blog — general ML ETA context (not XGBoost-specific)
- Uber DeepETA blog — neural approach, less relevant for tabular data

---
*Research completed: 2026-02-03*
*Ready for roadmap: yes*
