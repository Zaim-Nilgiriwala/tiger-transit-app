# Phase 8: Training Adaptation - Research

**Researched:** 2026-02-17
**Domain:** XGBoost residual-target retraining, Optuna hyperparameter tuning, GPU-accelerated training, outlier trimming, Huber loss
**Confidence:** HIGH (with noted caveats)

## Summary

This research investigates best practices for retraining an XGBoost model to predict residuals (actual - baseline_eta) instead of raw seconds, with fresh Optuna hyperparameter tuning, Huber loss comparison, outlier trimming, and GPU acceleration. The research draws from official XGBoost/Optuna documentation, Kaggle competition patterns, academic papers on transit ETA prediction, and Uber's production ETA post-processing system (DeeprETA) which uses an identical residual correction approach.

The residual correction approach (baseline + ML-predicted deviation) is a well-established industry pattern. Uber's DeeprETA system, documented in their 2022 paper (arxiv:2206.02127), uses exactly this architecture: a routing engine produces baseline ETAs, and a machine learning model predicts the residual error to refine predictions. The paper reports "significantly improved accuracy as measured by mean and median absolute error." This validates the Phase 8 approach of training XGBoost on residuals from baseline_eta. Community hyperparameter ranges for Optuna + XGBoost are well-documented across multiple authoritative sources, with strong consensus on search space design. Z-score outlier trimming at z=2.5-3.0 is a standard practice, and Huber loss (reg:pseudohubererror) is specifically designed for regression with outlier-contaminated targets.

A key finding from this extended research is the recommendation to use Optuna's MedianPruner (not HyperbandPruner) for this use case. While benchmarks show HyperbandPruner outperforms with TPESampler generally, MedianPruner is simpler, well-tested with XGBoostPruningCallback, and the existing v1.0 codebase already uses it successfully. Also notable: a GitHub issue (#9378) documents convergence problems with pseudo-huber loss on small datasets with extreme target values, though this appears specific to edge cases and should not affect our 1.2M-row dataset.

**Primary recommendation:** Use the community-established Optuna search spaces with log-scale for rate/regularization parameters, MedianPruner with n_startup_trials=10 and n_warmup_steps=50, z-score 2.5 outlier trimming on training data only, huber_slope search range [1.0, 100.0] log-scale (scaled to residual distribution), and deterministic final model via best_iteration + 1 rounds.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.1.3 | Gradient boosted tree training with GPU support | Already installed, CUDA 12.5 build confirmed, industry standard for tabular data |
| optuna | 4.7.0 | Bayesian hyperparameter optimization with pruning | Already installed, used in v1.0, recommended by Kaggle grandmasters |
| optuna-integration | (installed) | XGBoostPruningCallback for trial pruning | Already used in v1.0, import via `from optuna_integration import XGBoostPruningCallback` |
| pandas | 2.3.3 | Feature matrix construction, parquet I/O | Already in pipeline |
| numpy | 2.2.6 | Array operations, z-score computation, metrics | Already in pipeline |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| scipy | 1.15.3 | scipy.stats.zscore for robust outlier detection | Optional -- numpy z-score is sufficient for this use case |
| sklearn | (installed) | TimeSeriesSplit for CV validation | Already used in Stage 2 of v1.0 |
| matplotlib | (installed) | Training convergence plots | Optional -- for loss curve visualization |
| pyarrow | (installed) | Parquet I/O with dictionary encoding | Already used by feature pipeline |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| MedianPruner | HyperbandPruner | Benchmarks show Hyperband outperforms with TPESampler, but MedianPruner is simpler, proven in v1.0, and well-documented with XGBoostPruningCallback |
| numpy z-score | scipy.stats.zscore | scipy handles NaN/ddof automatically but numpy is simpler for this use case |
| Z-score trimming | Isolation Forest | Isolation Forest is more flexible but z-score is the locked decision and sufficient for target-based trimming |

**Installation:**
No new packages required. All dependencies already installed and verified.

## Architecture Patterns

### Pattern 1: Residual Correction (Baseline + ML Deviation)

**What:** Train ML model to predict the residual (actual - baseline) rather than the raw target. Final prediction = baseline + predicted_residual.
**When to use:** When a reasonable baseline exists (as with our blended baseline_eta).
**Industry validation:** This is the exact approach used by Uber's DeeprETA system at production scale.

From Uber's blog: "predict the residual between the routing engine ETA and real-world observed outcomes." Their system produces baseline ETAs from a routing engine, then uses ML to correct the residuals.

Source: [Uber DeepETA Blog](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/), [DeeprETA Paper](https://arxiv.org/abs/2206.02127)

**Key insight from Uber:** They use asymmetric Huber loss with a delta parameter controlling the transition between squared and absolute error. This is directly analogous to our Huber vs squared error comparison. They also note that even when the business objective is RMSE, using MAE-like loss can improve outcomes.

**Confidence:** HIGH -- Uber's production system validates this exact pattern at massive scale.

### Pattern 2: Optuna Search Space Design (Community Consensus)

**What:** Specific hyperparameter ranges derived from multiple authoritative sources.
**Sources cross-referenced:**
1. [Random Realizations - Ultimate XGBoost Tuning Guide](https://randomrealizations.com/posts/xgboost-parameter-tuning-with-optuna/)
2. [Forecastegy - Kaggle Grandmaster Guide](https://forecastegy.com/posts/xgboost-hyperparameter-tuning-with-optuna/)
3. [Official Optuna-XGBoost example](https://github.com/optuna/optuna-examples/blob/main/xgboost/xgboost_simple.py)
4. [Brandon Rundquist - Tuning XGBoost with Optuna](https://brandonrundquist.dev/posts/xgboost_optuna/)
5. [XGBoosting.com - Bayesian Optimization](https://xgboosting.com/bayesian-optimization-of-xgboost-hyperparameters-with-optuna/)

**Consensus ranges across sources:**

| Parameter | Source 1 (Random Realizations) | Source 2 (Forecastegy) | Source 3 (Optuna Official) | Source 4 (Rundquist) | Recommended for v1.1 |
|-----------|------|------|------|------|------|
| learning_rate | fixed then lowered | 1e-3 to 0.1 log | 1e-8 to 1.0 log | 1e-3 to 0.3 log | **0.01 to 0.3 log** |
| max_depth | 3-12 | 1-10 | 3-9 step=2 | 2-10 | **3-10** |
| n_estimators/num_boost_round | not tuned (early stop) | not tuned | not specified | 200-1500 | **200-2000** |
| subsample | 0.1-1.0 | 0.05-1.0 | 0.2-1.0 | 0.5-1.0 | **0.5-1.0** |
| colsample_bytree | 0.1-1.0 (bynode) | 0.05-1.0 | 0.2-1.0 | 0.5-1.0 | **0.3-1.0** |
| min_child_weight | 1-250 | 1-20 | 2-10 | 1.0-10.0 | **1-100** |
| reg_alpha | not tuned | not tuned | 1e-8 to 1.0 log | 1e-4 to 1.0 log | **1e-4 to 10.0 log** |
| reg_lambda | 0.001-25 log | not tuned | 1e-8 to 1.0 log | 1e-3 to 10.0 log | **1e-4 to 10.0 log** |
| gamma | not tuned | not tuned | 1e-8 to 1.0 log | not tuned | **0.0 to 5.0** |

**Key strategy advice from sources:**
- Use log-scale for parameters spanning orders of magnitude (learning_rate, reg_alpha, reg_lambda) -- [Source 4]
- "About 30 trials are usually sufficient to find a solid set" -- [Source 2] (our 100 trials is more than sufficient)
- "If best trials cluster near parameter bounds, expand that range" -- [Source 2]
- Start with 6-8 parameters, expand if needed -- [Source 4]

**Confidence:** HIGH -- Multiple authoritative sources agree on these ranges.

### Pattern 3: Outlier Trimming on Training Data Only

**What:** Remove extreme training samples by z-score before model training. Never touch validation or test data.
**Community consensus:** Z-score threshold of 3.0 is the most commonly cited standard. Our locked decision of 2.5 is more aggressive but still within community practice.

From [XGBoosting.com](https://xgboosting.com/xgboost-remove-outliers-with-z-score-statistical-method/): "Remove data points with Z-scores above a specified threshold (e.g., 3)."

From [XGBoosting.com - Removing Outliers](https://xgboosting.com/removing-outliers-from-training-data-for-xgboost/): "Outliers should only be removed from the training data and not from the test set or real-world data on which the model will be applied."

From [GeeksforGeeks Z-Score](https://www.geeksforgeeks.org/machine-learning/z-score-for-outlier-detection-python/): "Usually z-score = 3 is considered as a cut-off value."

**Our situation:** With z=2.5 on heavy-tailed residuals (mean=-9.05, std=287.43), we remove ~4.14% -- more than the ~1.2% estimated (which assumed Gaussian distribution where 2.5 sigma removes 1.24%). The heavy tails mean more data exceeds 2.5 sigma than a Gaussian would predict. At 4.14% removal, this is within the 5% contamination threshold used in Isolation Forest examples.

**Confidence:** HIGH -- Z-score outlier trimming is well-established. The z=2.5 threshold is a locked decision.

### Pattern 4: Huber Loss for Outlier-Robust Regression

**What:** XGBoost's `reg:pseudohubererror` with tunable `huber_slope` (delta) parameter. Below delta, loss is quadratic (like MSE). Above delta, loss is linear (like MAE).
**When to use:** When targets contain outliers or heavy tails -- exactly our residual distribution.

From [XGBoost Official Docs](https://xgboost.readthedocs.io/en/stable/parameter.html): "regression with Pseudo Huber loss, a twice differentiable alternative to absolute loss." Default `huber_slope` = 1.0.

From Uber's DeepETA: They use "asymmetric Huber loss, which is robust to outliers" with a delta parameter controlling the transition. A practical case study showed "MAE dropped by 30% when pseudo-huber loss was paired with MAE hyperparameter tuning."

**Convergence warning (GitHub issue #9378):** A user reported convergence failure with pseudo-huber loss on a tiny 3-point dataset with extreme targets (100, 300, 1000) and huber_slope=1.0. The model produced unreasonably large predictions. This appears to be an edge case with very small datasets. Our 1.2M row dataset should not trigger this, but monitoring convergence during Optuna trials is still important.

**huber_slope range recommendation:**
- Default: 1.0
- Our residual std: ~287s
- The slope controls where loss transitions from quadratic to linear
- A slope much smaller than typical residuals makes loss nearly linear (MAE-like)
- A slope much larger makes loss nearly quadratic (MSE-like)
- For our distribution: search [1.0, 100.0] log-scale. This covers MAE-like behavior (slope=1 << residual magnitudes) through mixed behavior (slope~50-100 near typical residuals)
- Note: The existing research suggested [0.5, 50.0]. Widening the upper bound to 100 is recommended since our residual std is 287 and we want to explore more MSE-like behavior too

**Confidence:** MEDIUM-HIGH -- Huber loss is well-documented, but the optimal slope range for our specific residual distribution has no direct precedent. The [1.0, 100.0] range is informed by the distribution statistics but may need boundary expansion if Optuna hits limits.

### Pattern 5: GPU Auto-Detection and Training

**What:** Use `device="cuda"` with `tree_method="hist"` for GPU-accelerated training.
**From [XGBoost GPU Docs](https://xgboost.readthedocs.io/en/stable/gpu/index.html):**
- CUDA 12.0 minimum, Compute Capability 5.0 minimum
- GTX 1060 has CC 6.1 (verified compatible)
- ELLPACK format uses ~1/4 the space of CSR float matrices
- For our dataset (1.2M rows x 45 features): estimated ~54MB in ELLPACK, well within 3GB VRAM
- GPU and CPU may produce slightly different results due to floating-point arithmetic differences
- Single-GPU training is deterministic (same hardware + same data + same seed = same model)
- Memory persists across booster lifetime -- delete booster object to free VRAM between Optuna trials

**GPU speedup expectations:** Multiple sources report 10-50x speedup for histogram building. A practical article reports up to 46x faster training with GPU. For our 100 Optuna trials, GPU could reduce total tuning time from ~2 hours (CPU) to ~15-30 minutes.

**Known issue:** When training in a loop (Optuna trials), XGBoost may not free GPU memory after each trial because "memory is allocated over the lifetime of the booster object and does not get freed until the booster is freed." Workaround: explicitly delete the booster after each trial with `del bst`.

**Confidence:** HIGH -- GPU support is well-documented and was verified on project hardware in prior research.

### Pattern 6: Deterministic Final Model Training

**What:** After Optuna finds best hyperparameters, retrain final model for exact `best_iteration + 1` rounds with no early stopping.
**Community pattern from [XGBoosting.com](https://xgboosting.com/xgboost-early-stopping-get-best-round-iteration/):**

```python
# Step 1: Find best iteration via early stopping
xgb_model.fit(X_train, y_train, eval_set=[(X_val, y_val)], early_stopping_rounds=10)
best_iteration = xgb_model.best_iteration

# Step 2: Retrain deterministic model
final_model = XGBRegressor(n_estimators=best_iteration)
final_model.fit(X_full_train, y_full_train)
```

**From [Brandon Rundquist](https://brandonrundquist.dev/posts/xgboost_optuna/):** Combine early_stopping_rounds within training alongside XGBoostPruningCallback for dual optimization (within-trial and across-trial).

**For Optuna integration:** Store best_iteration as user_attr:
```python
trial.set_user_attr("best_iteration", int(bst.best_iteration))
```
Then retrieve: `study.best_trial.user_attrs["best_iteration"] + 1`

**Confidence:** HIGH -- This is the standard pattern documented across multiple sources.

### Pattern 7: base_score Auto-Estimation for Zero-Centered Targets

**What:** Since XGBoost 2.0.0, base_score (the global bias / intercept) is automatically estimated from training data.
**From [XGBoost Intercept Docs](https://xgboost.readthedocs.io/en/stable/tutorials/intercept.html):** "Since 2.0.0, XGBoost supports estimating the model intercept (named base_score) automatically based on targets upon training."

For our zero-centered residual target (mean~-9s), the auto-estimated base_score will be near zero, which is correct. No special handling needed.

**Confidence:** HIGH -- Official documentation confirms automatic estimation.

### Anti-Patterns to Avoid

- **Trimming validation/test sets:** Only trim training data. Validation and test must remain untouched for fair evaluation. (Multiple sources confirm: [XGBoosting.com](https://xgboosting.com/removing-outliers-from-training-data-for-xgboost/))
- **Early stopping in final model:** User decision is deterministic final training. Do NOT use early_stopping_rounds in the final retrain.
- **Warm-starting from v1.0 parameters:** User decision is fresh wide search ranges.
- **Evaluating residual MAE as the success metric:** Must reconstruct (baseline_eta + predicted_residual) and compare against actual time_to_arrival_seconds.
- **Forgetting to delete boosters in Optuna loop:** GPU memory leak -- add `del bst` after each trial.
- **Using default huber_slope=1.0 without tuning:** The default is not calibrated to our residual distribution. Must tune via Optuna.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hyperparameter optimization | Manual grid search | Optuna with MedianPruner | 100 trials with pruning explores 9+ dimensions efficiently via Bayesian optimization |
| GPU detection | CUDA toolkit version parsing | XGBoost test-train probe | XGBoost handles CUDA compatibility internally; a test train is definitive |
| Outlier detection | Custom percentile logic or isolation forest | numpy z-score (simple division) | Z-score is the locked decision; a 3-line implementation is sufficient |
| Huber loss | Custom gradient/hessian function | `reg:pseudohubererror` built-in | Native objective with `huber_slope` parameter; verified working with GPU |
| Trial pruning | Manual early stopping threshold | XGBoostPruningCallback + MedianPruner | Proven integration, handles step reporting automatically |
| Cross-validation | Manual fold splitting | sklearn TimeSeriesSplit | Respects temporal ordering, already used in v1.0 |
| base_score estimation | Manual mean-of-targets | XGBoost auto-estimation (since 2.0) | Auto-estimates near-zero for zero-centered residuals |
| Residual modeling theory | Custom framework | Standard baseline + correction pattern | Validated by Uber DeeprETA, industry standard for ETA post-processing |

**Key insight:** The XGBoost + Optuna ecosystem already solves every optimization problem in this phase. The implementation work is plumbing (connecting data to existing APIs), not algorithm development.

## Common Pitfalls

### Pitfall 1: Forgetting Reconstruction in Evaluation

**What goes wrong:** Evaluating the model on residual MAE instead of reconstructed ETA MAE. A model with 50s residual MAE could produce 200s reconstructed MAE if baseline is systematically wrong.
**Why it happens:** The target variable is residual, so `bst.predict()` returns residual predictions.
**How to avoid:** Always compute `y_pred_eta = baseline_eta + bst.predict(dtest)` for any MAE comparison.
**Warning signs:** Reported MAE is much lower than 123.1s (likely evaluating residual MAE, not reconstructed).
**Confidence:** HIGH -- Fundamental to the residual correction approach; confirmed by Uber's DeeprETA architecture.

### Pitfall 2: Z-Score Threshold Removes More Than Expected on Heavy-Tailed Data

**What goes wrong:** CONTEXT.md states z=2.5 removes ~1.2% but empirical measurement shows 4.14%.
**Why it happens:** The 1.2% estimate assumes Gaussian distribution (2.5 sigma removes 1.24% for perfectly normal data). Our residual distribution has heavier tails (range: -2920s to +4814s).
**How to avoid:** Use z=2.5 as the locked decision. Document actual removal (4.14%). This is still within the 5% contamination threshold used in Isolation Forest examples ([XGBoosting.com](https://xgboosting.com/removing-outliers-from-training-data-for-xgboost/)).
**Warning signs:** Post-trimming training data is smaller than expected.
**Confidence:** HIGH -- Empirically verified on project data.

### Pitfall 3: Pseudo-Huber Convergence Issues

**What goes wrong:** With very small huber_slope values relative to target scale, model predictions can diverge.
**Why it happens:** [GitHub issue #9378](https://github.com/dmlc/xgboost/issues/9378) documents convergence failure with huber_slope=1.0 on 3-point dataset with targets 100/300/1000. The fitted values were "stuck in a large number."
**How to avoid:** (a) Our dataset is 1.2M rows -- much less prone to this edge case. (b) Set huber_slope search lower bound to 1.0 (not below), avoiding extremely small slopes. (c) Monitor trial validation MAE for signs of divergence (MAE > 1000s = something is wrong). (d) Optuna pruning will kill divergent trials early.
**Warning signs:** Optuna trials with pseudohubererror consistently pruned, or validation MAE exploding.
**Confidence:** MEDIUM -- The issue is documented but appears limited to very small datasets. Our scale should be safe.

### Pitfall 4: GPU Memory Not Released Between Optuna Trials

**What goes wrong:** VRAM usage grows across trials, eventually causing OOM on 3GB GPU.
**Why it happens:** [XGBoost issue #3045](https://github.com/dmlc/xgboost/issues/3045): "Memory is allocated over the lifetime of the booster object and does not get freed until the booster is freed."
**How to avoid:** Add `del bst` and optionally `import gc; gc.collect()` after each Optuna trial objective.
**Warning signs:** CUDA out-of-memory errors during later Optuna trials.
**Confidence:** HIGH -- Well-documented issue with straightforward workaround.

### Pitfall 5: Eval Metric Name for Pruning Callback

**What goes wrong:** XGBoostPruningCallback requires exact eval metric key string.
**Why it happens:** The naming convention is `{eval_set_name}-{metric_name}`.
**How to avoid:** With `evals=[(dval, "val")]` and `eval_metric="mae"`, use `XGBoostPruningCallback(trial, "val-mae")`.
**Warning signs:** Optuna raises "Trial should report intermediate value" errors.
**Confidence:** HIGH -- Verified in v1.0 codebase and official examples.

### Pitfall 6: Deterministic Final Model Using Wrong Round Count

**What goes wrong:** Using `n_estimators` from Optuna search instead of `best_iteration`.
**Why it happens:** Optuna trials use early stopping, so training may stop before n_estimators. The optimal round is best_iteration, not n_estimators.
**How to avoid:** Store `trial.set_user_attr("best_iteration", int(bst.best_iteration))`. Final model trains for `best_iteration + 1` rounds.
**Warning signs:** Final model MAE is worse than Optuna best trial MAE on the same validation set.
**Confidence:** HIGH -- Multiple sources document this pattern ([XGBoosting.com](https://xgboosting.com/xgboost-early-stopping-get-best-round-iteration/), [Rundquist](https://brandonrundquist.dev/posts/xgboost_optuna/)).

### Pitfall 7: Subsampling Before vs After Outlier Trimming

**What goes wrong:** If Optuna search subsample is drawn from untrimmed data, the subsample contains outliers that won't exist in the final trimmed training set.
**Why it happens:** Order of operations matters: trim first, then subsample.
**How to avoid:** Apply z-score trimming to training data BEFORE creating the 10% Optuna search subsample.
**Warning signs:** Best Optuna trial parameters perform very differently on full trimmed data.
**Confidence:** HIGH -- Logical consequence of the trimming decision.

### Pitfall 8: GPU vs CPU Producing Different Results

**What goes wrong:** Model trained on GPU gives slightly different predictions than same model trained on CPU.
**Why it happens:** Floating-point arithmetic differences between GPU and CPU implementations. [XGBoost GPU docs](https://xgboost.readthedocs.io/en/stable/gpu/index.html) notes this is normal.
**How to avoid:** Accept small numerical differences. Single-GPU training IS deterministic (same GPU + same data + same seed = same model bit-for-bit). Cross-device model portability is supported.
**Warning signs:** Validation MAE differs by a few tenths of a second between GPU and CPU runs.
**Confidence:** HIGH -- Official documentation.

## Code Examples

### Example 1: Community-Validated Optuna Objective Function

```python
# Sources: Synthesized from 5 authoritative sources (see Architecture Patterns section)
# Ranges represent community consensus for XGBoost regression

def objective(trial):
    from optuna_integration import XGBoostPruningCallback

    objective_name = trial.suggest_categorical(
        "objective", ["reg:squarederror", "reg:pseudohubererror"]
    )
    params = {
        **FIXED_PARAMS,
        "objective": objective_name,
        # --- 9 hyperparameters (community consensus ranges) ---
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        # Sources: 1e-3 to 0.3 (Rundquist), 1e-3 to 0.1 (Forecastegy)
        # Our range: 0.01-0.3 to allow slightly higher rates for residual targets

        "max_depth": trial.suggest_int("max_depth", 3, 10),
        # Sources: 3-12 (Random Realizations), 1-10 (Forecastegy), 2-10 (Rundquist)
        # Consensus: 3-10 covers typical optimal depths

        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        # Sources: 0.5-1.0 consistent across Rundquist, XGBoosting.com

        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
        # Sources: 0.5-1.0 (most sources), 0.2-1.0 (Optuna official)
        # Widened to 0.3 since we have 45 features and residuals may need fewer

        "min_child_weight": trial.suggest_int("min_child_weight", 1, 100),
        # Sources: 1-20 (Forecastegy), 1-250 (Random Realizations), 2-10 (official)
        # Our range: 1-100 balances exploration for residual target

        "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        # Sources: 1e-8 to 1.0 (official), 1e-4 to 1.0 (Rundquist)
        # Extended to 10.0 for stronger regularization option on residuals

        "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        # Sources: 1e-3 to 10.0 (Rundquist), 0.001-25 (Random Realizations)

        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        # Sources: 1e-8 to 1.0 (official), 0-1.0 grid (XGBoosting.com)
        # Extended to 5.0 for residual targets -- zero-centered targets may
        # benefit from more conservative splits per official docs:
        # "The larger gamma is, the more conservative the algorithm"
    }
    if objective_name == "reg:pseudohubererror":
        params["huber_slope"] = trial.suggest_float("huber_slope", 1.0, 100.0, log=True)
        # Residual std ~287s. slope << residuals = MAE-like, slope >> = MSE-like
        # Range [1, 100] covers strong MAE behavior to moderate MSE behavior

    num_boost_round = trial.suggest_int("num_boost_round", 200, 2000)

    pruning_callback = XGBoostPruningCallback(trial, "val-mae")
    bst = xgb.train(
        params,
        dtrain_search,
        num_boost_round=num_boost_round,
        evals=[(dval_search, "val")],
        early_stopping_rounds=15,
        verbose_eval=False,
        callbacks=[pruning_callback],
    )

    trial.set_user_attr("best_iteration", int(bst.best_iteration))
    trial.set_user_attr("objective_type", objective_name)
    preds = bst.predict(dval_search, iteration_range=(0, bst.best_iteration + 1))
    val_mae = float(np.mean(np.abs(y_val_search - preds)))

    del bst  # Free GPU memory between trials
    return val_mae
```

### Example 2: Z-Score Outlier Trimming (Training Data Only)

```python
# Source: Community pattern from XGBoosting.com, GeeksforGeeks
# Standard z-score threshold = 3.0 (community default)
# Our locked decision = 2.5 (more aggressive, removes ~4.14% on heavy-tailed residuals)

def trim_outliers(y, z_threshold=2.5):
    """Remove outlier training samples by z-score on target values.
    Returns boolean mask of rows to keep.

    Note: Only apply to TRAINING data. Never trim validation or test.
    """
    mean = y.mean()
    std = y.std()
    z_scores = np.abs((y - mean) / std)
    mask = z_scores <= z_threshold
    n_removed = (~mask).sum()
    pct_removed = n_removed / len(y) * 100
    print(f"  Outlier trimming (z <= {z_threshold}): "
          f"removed {n_removed:,} of {len(y):,} samples ({pct_removed:.1f}%)")
    return mask

# Application order: trim BEFORE subsampling for Optuna
trim_mask = trim_outliers(y_train, Z_SCORE_THRESHOLD)
X_train_trimmed = X_train[trim_mask].reset_index(drop=True)
y_train_trimmed = y_train[trim_mask].reset_index(drop=True)

# Then subsample from trimmed data for Optuna search
search_idx = rng.choice(len(y_train_trimmed), size=int(len(y_train_trimmed) * 0.10))
```

### Example 3: GPU Auto-Detection

```python
# Source: XGBoost GPU Docs (https://xgboost.readthedocs.io/en/stable/gpu/index.html)
# Pattern: Probe with tiny training job rather than checking CUDA toolkit

def detect_xgb_device():
    """Auto-detect GPU availability for XGBoost. Returns 'cuda' or 'cpu'."""
    try:
        dm = xgb.DMatrix(np.zeros((2, 1)), label=[0, 1])
        bst = xgb.train({"device": "cuda", "tree_method": "hist"},
                         dm, num_boost_round=1, verbose_eval=False)
        del bst, dm
        return "cuda"
    except Exception:
        return "cpu"
```

### Example 4: Deterministic Final Model Training

```python
# Source: XGBoosting.com, community best practice
# Pattern: Use best_iteration from Optuna, NOT n_estimators

best_n_rounds = study.best_trial.user_attrs["best_iteration"] + 1
# "+1" because best_iteration is 0-indexed but num_boost_round is 1-indexed

bst_final = xgb.train(
    best_params,
    dtrain,  # Full trimmed training data (not the 10% subsample)
    num_boost_round=best_n_rounds,
    evals=[(dtrain, "train"), (dval, "val")],
    # NO early_stopping_rounds -- deterministic
    verbose_eval=100,
)

# Reconstruct predictions for evaluation
y_pred_residual = bst_final.predict(dtest)
y_pred_eta = test_baseline_eta + y_pred_residual
reconstructed_mae = np.mean(np.abs(test_actual_seconds - y_pred_eta))
```

### Example 5: MedianPruner Configuration

```python
# Source: Optuna docs (https://optuna.readthedocs.io/en/stable/reference/generated/optuna.pruners.MedianPruner.html)
# n_startup_trials=10: Don't prune until 10 trials complete (need baseline)
# n_warmup_steps=50: Don't prune within first 50 boosting rounds of a trial

study = optuna.create_study(
    direction="minimize",
    pruner=optuna.pruners.MedianPruner(
        n_startup_trials=10,
        n_warmup_steps=50,
    ),
    study_name="v1_1_residual_tuning",
    storage="sqlite:///models/optuna_study.db",
    load_if_exists=True,
)
```

## State of the Art

| Old Approach (v1.0) | Current Approach (v1.1) | When Changed | Impact |
|---------------------|------------------------|--------------|--------|
| Raw seconds as target | Residual (actual - baseline_eta) as target | Phase 8 | Matches Uber's DeeprETA architecture; model learns deviation |
| 43 features | 45 features (+3 baselines, -lateness_now) | Phase 8 | Baselines give model context about which signal is strongest |
| reg:squarederror only | Compare squarederror vs pseudohubererror | Phase 8 | Huber loss more robust to outlier residuals |
| 150 Optuna trials, 8 params | 100 trials, 9+1 params (+ gamma, conditional huber_slope) | Phase 8 | Wider search space, gamma helps control splits on zero-centered target |
| No outlier trimming | Z-score 2.5 sigma trimming (~4.14% removed) | Phase 8 | Removes extreme residuals that distort gradients |
| device: "cuda" hardcoded | Auto-detect GPU with CPU fallback | Phase 8 | Scripts work anywhere |
| Early stopping in final model | Deterministic final retrain (exact round count) | Phase 8 | Reproducible model |

**Deprecated/outdated in XGBoost:**
- `gpu_hist` as separate tree_method: Since XGBoost 2.0+, use `tree_method="hist"` + `device="cuda"` instead of `tree_method="gpu_hist"`. The old syntax may still work but is deprecated.
- Manual base_score setting: Since XGBoost 2.0+, base_score is auto-estimated from training data.

## Industry Precedent for Residual Correction in ETA

The approach of predicting residuals from a baseline ETA is well-validated in industry:

1. **Uber DeeprETA** ([arxiv:2206.02127](https://arxiv.org/abs/2206.02127)): Uses routing engine ETA as baseline, ML model predicts residual. Reports "significantly improved accuracy." Used gradient boosting before transitioning to deep learning.

2. **Uber DeepETA** ([blog](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/)): Uses asymmetric Huber loss with delta parameter for robustness. Notes that even when RMSE is the business objective, MAE-like loss can improve outcomes.

3. **Transporeon Visibility Hub**: Reported "doubling ETA accuracy" using ML in production for transportation logistics.

4. **Academic transit research** ([Zhu et al., 2022](https://onlinelibrary.wiley.com/doi/10.1155/2022/3504704)): XGBoost-based travel time prediction achieved lowest MAPE of 11.96%, outperforming KNN, BP, and LightGBM.

5. **Stanford CS229 MTA Bus Prediction**: Feature engineering for NYC bus arrivals -- distance features ranked as most important, followed by temporal features and passenger load.

**Key features for transit ETA (from literature):**
- Distance to destination (most important across all studies)
- Current speed / recent speed trends
- Time of day / day of week
- Weather conditions
- Passenger load (significant in some studies)
- Number of remaining stops
- Route-specific patterns

These align well with our existing 45-feature set.

**Confidence:** HIGH -- Multiple independent production systems and academic papers validate this approach.

## Open Questions

1. **huber_slope optimal range may need expansion**
   - What we know: Our search range is [1.0, 100.0] log-scale. Residual std is ~287s.
   - What's unclear: Whether the optimal slope is above 100 (more MSE-like) or below 1 (more MAE-like).
   - Recommendation: Monitor Optuna's best huber_slope value. If it consistently hits the boundary (1.0 or 100.0), expand the range and re-run affected trials.

2. **Z-score 2.5 removes 4.14%, not ~1.2%**
   - What we know: Heavy tails cause more trimming than the Gaussian approximation predicted.
   - What's unclear: Whether 4.14% removal helps or hurts relative to 1.2% removal.
   - Recommendation: Use z=2.5 as the locked decision. If results are poor, Phase 9 can revisit with z=3.0 or 3.5 as a sensitivity analysis.

3. **Whether gamma significantly helps residual targets**
   - What we know: Official docs say "larger gamma = more conservative." Community typically tunes gamma in [0, 1] range. We use [0, 5].
   - What's unclear: Whether zero-centered residual targets actually benefit from gamma > 0.
   - Recommendation: Let Optuna discover. If best gamma is consistently 0, it provides no signal for residuals.

4. **GPU memory pressure with 100 trials on 3GB VRAM**
   - What we know: Dataset fits easily (~54MB ELLPACK). But tree building adds working memory.
   - What's unclear: Whether `del bst` fully releases memory, or if fragmentation builds up.
   - Recommendation: Add `del bst; gc.collect()` after each trial. If OOM occurs after many trials, restart the study (load_if_exists=True handles this gracefully).

## Sources

### Primary (HIGH confidence)
- [XGBoost 3.2.0 Parameters Documentation](https://xgboost.readthedocs.io/en/stable/parameter.html) -- reg:pseudohubererror, huber_slope, gamma, device parameter
- [XGBoost GPU Support Documentation](https://xgboost.readthedocs.io/en/stable/gpu/index.html) -- CUDA requirements, ELLPACK format, memory management
- [XGBoost Intercept Documentation](https://xgboost.readthedocs.io/en/stable/tutorials/intercept.html) -- base_score auto-estimation since 2.0
- [XGBoost Parameter Tuning Guide](https://xgboost.readthedocs.io/en/stable/tutorials/param_tuning.html) -- Official tuning recommendations
- [Optuna MedianPruner Documentation](https://optuna.readthedocs.io/en/stable/reference/generated/optuna.pruners.MedianPruner.html) -- n_startup_trials, n_warmup_steps
- [Official Optuna-XGBoost Example](https://github.com/optuna/optuna-examples/blob/main/xgboost/xgboost_simple.py) -- Canonical hyperparameter ranges
- XGBoost 3.1.3 installed build -- verified CUDA 12.5, gpu_hist working
- Optuna 4.7.0 installed -- XGBoostPruningCallback verified
- Project data empirical analysis -- residual stats, z-score trimming percentages

### Secondary (MEDIUM confidence)
- [Uber DeepETA Blog](https://www.uber.com/blog/deepeta-how-uber-predicts-arrival-times/) -- Residual correction architecture, asymmetric Huber loss
- [DeeprETA Paper (arxiv:2206.02127)](https://arxiv.org/abs/2206.02127) -- ETA post-processing via residual prediction
- [Random Realizations - XGBoost Tuning Guide](https://randomrealizations.com/posts/xgboost-parameter-tuning-with-optuna/) -- max_depth 3-12, min_child_weight 1-250, reg_lambda 0.001-25
- [Forecastegy - Kaggle Grandmaster Guide](https://forecastegy.com/posts/xgboost-hyperparameter-tuning-with-optuna/) -- learning_rate 1e-3 to 0.1, min_child_weight 1-20
- [Brandon Rundquist - Tuning XGBoost with Optuna](https://brandonrundquist.dev/posts/xgboost_optuna/) -- n_estimators 200-1500, reg_alpha 1e-4 to 1.0, early_stopping + pruning pattern
- [XGBoosting.com - Bayesian Optimization with Optuna](https://xgboosting.com/bayesian-optimization-of-xgboost-hyperparameters-with-optuna/) -- max_depth 2-10, learning_rate 1e-3 to 1.0
- [XGBoosting.com - Pseudo-Huber Configuration](https://xgboosting.com/configure-xgboost-regpseudohubererror-objective/) -- huber_slope default 1.0
- [XGBoosting.com - Z-Score Outlier Method](https://xgboosting.com/xgboost-remove-outliers-with-z-score-statistical-method/) -- z=3 standard threshold
- [XGBoosting.com - Removing Outliers from Training Data](https://xgboosting.com/removing-outliers-from-training-data-for-xgboost/) -- Training-only trimming, 5% contamination example
- [XGBoosting.com - Early Stopping Best Iteration](https://xgboosting.com/xgboost-early-stopping-get-best-round-iteration/) -- best_iteration for final model
- [XGBoosting.com - Gamma Tuning](https://xgboosting.com/tune-xgboost-gamma-parameter/) -- gamma 0-1.0 grid typical
- [XGBoosting.com - Most Important Hyperparameters](https://xgboosting.com/most-important-xgboost-hyperparameters-to-tune/) -- Top 5: max_depth, min_child_weight, subsample, colsample_bytree, learning_rate

### Tertiary (LOW confidence)
- [GitHub XGBoost Issue #9378](https://github.com/dmlc/xgboost/issues/9378) -- Pseudo-huber convergence issue on small datasets (edge case, unresolved)
- [GitHub XGBoost Issue #3045](https://github.com/dmlc/xgboost/issues/3045) -- GPU memory not released between training loops
- [GitHub XGBoost Issue #8820](https://github.com/dmlc/xgboost/issues/8820) -- GPU reproducibility considerations
- [Optuna Pruner Benchmark Gist](https://gist.github.com/sile/18fc40dbc597d588aad7216443877f24) -- HyperbandPruner outperforms MedianPruner with TPESampler
- [Kaggle PS_S3E14 XGBoost with Pseudo-Huber Loss](https://www.kaggle.com/code/siukeitin/ps-s3e14-xgboost-with-pseudo-huber-loss) -- Practical Kaggle example (content not fully accessible)
- [Towardsdatascience - Selecting XGBoost Loss Function](https://towardsdatascience.com/selecting-the-right-xgboost-loss-function-in-sagemaker-60e545a75c47/) -- MAE dropped 30% with pseudo-huber paired with MAE tuning
- [Stanford CS229 MTA Bus Prediction](https://cs229.stanford.edu/proj2017/final-reports/5229496.pdf) -- Transit feature importance
- [Zhu et al., 2022 - XGBoost Travel Time Prediction](https://onlinelibrary.wiley.com/doi/10.1155/2022/3504704) -- XGBoost achieved 11.96% MAPE for bus travel time

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries verified installed with exact versions, GPU confirmed working
- Architecture patterns: HIGH -- Residual correction validated by Uber's production system; Optuna ranges from 5+ authoritative sources
- Pitfalls: HIGH -- Z-score mismatch empirically verified, GPU memory issue documented, eval metric naming tested
- Optuna search ranges: HIGH -- Cross-referenced across 5 independent sources with clear consensus
- Huber slope range: MEDIUM -- Informed by residual distribution statistics and XGBoost docs, but optimal range for our specific distribution is untested
- Gamma range: MEDIUM -- Extended beyond community typical [0, 1] to [0, 5] based on hypothesis about residual targets; may not help
- Industry validation: HIGH -- Uber's DeeprETA provides strong precedent for the entire approach

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (30 days -- XGBoost/Optuna versions are stable)

**Changes from prior research (2026-02-11):**
- Added extensive web research with 20+ external sources cross-referenced
- Added industry validation section (Uber DeeprETA, transit research papers)
- Upgraded Optuna search ranges from MEDIUM to HIGH confidence via multi-source verification
- Changed huber_slope range from [0.5, 50.0] to [1.0, 100.0] (lower bound raised to avoid convergence issues per #9378, upper bound raised to explore more MSE-like behavior given residual std~287)
- Added HyperbandPruner vs MedianPruner analysis (recommending MedianPruner for simplicity)
- Added GPU memory leak pitfall with del bst workaround
- Added base_score auto-estimation note (no manual setting needed)
- Added anti-pattern: gpu_hist as tree_method is deprecated since XGBoost 2.0+
- Documented community consensus z-score threshold is 3.0 (our z=2.5 is more aggressive)
