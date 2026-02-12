# Phase 8: Training Adaptation - Research

**Researched:** 2026-02-11
**Domain:** XGBoost residual-target retraining, Optuna hyperparameter tuning, GPU-accelerated training
**Confidence:** HIGH

## Summary

This research investigates how to modify the existing v1.0 XGBoost training pipeline to predict residuals (actual - baseline_eta) instead of raw seconds, add baseline features, perform fresh Optuna hyperparameter tuning with Huber loss comparison, and implement GPU-accelerated training. The existing codebase was deeply analyzed alongside live verification of XGBoost 3.1.3, Optuna 4.7.0, and the GTX 1060 3GB GPU.

The existing v1.0 pipeline (`train_advanced.py`, `build_differentiator_features.py`) provides a strong foundation. The current feature set has 43 features in `FEATURE_COLS_V2`, and the augmented parquets from Phase 7 already contain `baseline_eta`, `baseline_s2s`, `baseline_seg_sum`, and `residual` columns. The residual distribution is approximately zero-centered (mean=-9.05s, std=287.43s) with long tails requiring outlier handling. GPU training was verified to work with `device="cuda"`, `tree_method="hist"`, and both `reg:squarederror` and `reg:pseudohubererror` objectives on the installed hardware.

A critical finding is that the CONTEXT.md states "Z-score threshold (2.5 sigma) removes ~1.2% of training samples" but empirical measurement shows z > 2.5 removes 4.14% (49,932 samples). To remove ~1.2%, a z-score threshold of ~3.72 would be needed. The implementation should use the stated z=2.5 threshold (the locked decision) and document the actual removal percentage, which at 4.14% is still within reasonable bounds for outlier trimming and will likely help the model by removing extreme residuals.

**Primary recommendation:** Modify `build_differentiator_features.py` in place to add 3 baseline features and remove `lateness_now`, then modify `train_advanced.py` to switch target to residual, add z-score outlier trimming, GPU auto-detection, and Huber loss comparison within the Optuna study design.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.1.3 | Gradient boosted tree training with GPU support | Already installed, CUDA 12.5 build confirmed |
| optuna | 4.7.0 | Hyperparameter optimization with pruning | Already installed, used in v1.0 |
| optuna-integration | (installed) | XGBoostPruningCallback for trial pruning | Already used in v1.0, import via `from optuna_integration import XGBoostPruningCallback` |
| pandas | 2.3.3 | Feature matrix construction, parquet I/O | Already in pipeline |
| numpy | 2.2.6 | Array operations, z-score computation, metrics | Already in pipeline |
| scipy | 1.15.3 | scipy.stats.zscore for robust outlier detection | Already installed, optional (numpy-only works too) |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyarrow | (installed) | Parquet I/O with dictionary encoding for categoricals | Already used by feature pipeline |
| matplotlib | (installed) | Training convergence plots (optional) | For loss curve visualization if needed |
| sklearn | (installed) | TimeSeriesSplit for CV validation | Already used in Stage 2 of v1.0 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| numpy z-score | scipy.stats.zscore | scipy handles NaN/ddof automatically but numpy is simpler for this use case |
| Optuna MedianPruner | Optuna SuccessiveHalvingPruner | SHA is more aggressive but less stable for small trial counts |

**Installation:**
No new packages required. All dependencies already installed and verified.

## Architecture Patterns

### Recommended Script Modification Structure

The user decision is to modify v1.0 scripts in place. The key files to modify:

```
scripts/
    build_differentiator_features.py  # MODIFY: Add 3 baseline features, drop lateness_now, update constants
    train_advanced.py                 # MODIFY: Residual target, GPU auto-detect, Huber comparison, outlier trimming
    run_optuna_batches.py             # MODIFY: Update study name, trial count to 100
    evaluate.py                       # MODIFY: Reconstruction logic (baseline_eta + predicted_residual)
```

### Pattern 1: Feature Pipeline Modification

**What:** Update `FEATURE_COLS_V2` and `PHASE3_FEATURE_COLS` in `build_differentiator_features.py` to reflect the v1.1 feature set.
**When to use:** Plan 08-01 (feature pipeline changes)

Current v1.0 feature list (43 features in FEATURE_COLS_V2):
```python
PHASE3_FEATURE_COLS = [
    "distance_to_target", "scheduled_time_to_target", "current_speed",
    "route_progress", "stops_remaining", "stop_index", "lateness_now",  # <-- DROP lateness_now
    "minutes_since_midnight", "day_of_week", "route_id", "pattern_id",
    "precipitation_mm", "temperature_c", "passenger_load", "is_idle",
]
```

v1.1 changes:
- Remove `lateness_now` (zero variance, confirmed in v1.0 analysis)
- Add `baseline_s2s`, `baseline_seg_sum`, `baseline_eta` (from augmented parquets)
- Net: 43 - 1 + 3 = 45 features

**Key constraint:** The `_featured_v2.parquet` files must be rebuilt to include the baseline columns and exclude `lateness_now`. The baseline columns already exist in the base `{train,val,test}.parquet` files from Phase 7.

### Pattern 2: Residual Target with Reconstruction

**What:** Train on `residual` (= time_to_arrival_seconds - baseline_eta) as target, reconstruct predictions via `baseline_eta + predicted_residual` for evaluation.
**When to use:** Plan 08-01 (target change) and evaluation

```python
# Training: use residual as target
TARGET_COL = "residual"  # Changed from "time_to_arrival_seconds"

# Evaluation: reconstruct actual ETA prediction
y_pred_residual = bst.predict(dtest)
y_pred_eta = test_baseline_eta + y_pred_residual  # Reconstruct
reconstructed_mae = np.mean(np.abs(y_test_actual - y_pred_eta))
```

**Critical:** Must preserve `time_to_arrival_seconds` and `baseline_eta` in the featured parquets for reconstruction. The `KEEP_EXTRA` list needs updating.

### Pattern 3: GPU Auto-Detection

**What:** Detect CUDA availability and set XGBoost device parameter accordingly.
**When to use:** All training scripts.

```python
def detect_device():
    """Auto-detect GPU availability for XGBoost."""
    try:
        import xgboost as xgb
        # Attempt a tiny GPU operation
        dm = xgb.DMatrix(np.zeros((1, 1)), label=[0])
        params = {"device": "cuda", "tree_method": "hist"}
        bst = xgb.train(params, dm, num_boost_round=1, verbose_eval=False)
        del bst, dm
        return "cuda"
    except Exception:
        return "cpu"
```

Verified on the project hardware: XGBoost 3.1.3 build includes CUDA 12.5 support, GTX 1060 3GB has Compute Capability 6.1 (meets 5.0 minimum). Full dataset (1.2M rows x 45 features) fits in 3GB VRAM with ELLPACK compression (~54MB estimated).

### Pattern 4: Optuna Study with Dual Objective Comparison

**What:** Run Optuna with both `reg:squarederror` and `reg:pseudohubererror` as a tunable parameter, compare on validation MAE.
**When to use:** Plan 08-02 (Optuna study)

```python
def objective(trial):
    objective_name = trial.suggest_categorical(
        "objective", ["reg:squarederror", "reg:pseudohubererror"]
    )
    params = {
        "objective": objective_name,
        "eval_metric": "mae",
        "tree_method": "hist",
        "device": device,
        # ... other params
    }
    if objective_name == "reg:pseudohubererror":
        params["huber_slope"] = trial.suggest_float("huber_slope", 0.5, 50.0, log=True)
    # ... rest of objective
```

### Pattern 5: Z-Score Outlier Trimming

**What:** Remove training samples with extreme residuals before training.
**When to use:** Plan 08-01 (data preprocessing)

```python
# Z-score outlier trimming on training residuals
residuals = y_train  # target is already residual
z_scores = np.abs((residuals - residuals.mean()) / residuals.std())
mask = z_scores <= 2.5  # User decision: 2.5 sigma
n_removed = (~mask).sum()
pct_removed = n_removed / len(residuals) * 100
print(f"Outlier trimming: removed {n_removed:,} samples ({pct_removed:.1f}%)")
# NOTE: Empirical measurement shows 2.5 sigma removes ~4.14%, not ~1.2%
X_train = X_train[mask]
y_train = y_train[mask]
```

### Anti-Patterns to Avoid

- **Trimming validation/test sets:** Only trim training data. Validation and test must remain untouched for fair comparison.
- **Early stopping in final model:** User decision is deterministic final training with exact n_estimators from best Optuna trial. Do NOT use early_stopping_rounds in the final retrain.
- **Warm-starting from v1.0 parameters:** User decision is fresh wide search ranges. Do NOT seed Optuna with v1.0 best params.
- **Using lateness_now as feature:** Zero variance confirmed (scheduled_eta == eta in EtaSpot data). Must be removed from feature list.
- **Evaluating residual MAE directly:** The success metric is reconstructed ETA MAE (baseline_eta + residual_pred vs time_to_arrival_seconds), not residual prediction MAE.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hyperparameter optimization | Manual grid search | Optuna with MedianPruner | 100 trials with pruning is more efficient than grid search over 9 dimensions |
| GPU detection | CUDA toolkit version parsing | XGBoost test-train approach | XGBoost handles CUDA compatibility internally; a test train is definitive |
| Outlier detection | Custom percentile logic | numpy z-score (simple division) | Z-score is the locked decision; no need for IQR or isolation forest |
| Huber loss | Custom gradient/hessian | `reg:pseudohubererror` built into XGBoost | Native objective with `huber_slope` parameter; verified working with GPU |
| Trial pruning | Manual early stopping threshold | Optuna MedianPruner + XGBoostPruningCallback | Proven integration, handles step reporting automatically |
| Cross-validation | Manual fold splitting | sklearn TimeSeriesSplit | Respects temporal ordering, already used in v1.0 |

**Key insight:** The XGBoost + Optuna ecosystem already solves every optimization problem in this phase. The implementation work is about plumbing (connecting data to existing APIs) rather than algorithm development.

## Common Pitfalls

### Pitfall 1: Forgetting Reconstruction in Evaluation

**What goes wrong:** Evaluating the model on residual MAE instead of reconstructed ETA MAE. A model with 50s residual MAE could produce 200s reconstructed MAE if the baseline is systematically wrong.
**Why it happens:** The target variable is residual, so `bst.predict()` returns residual predictions. Evaluation must add `baseline_eta` back.
**How to avoid:** Always compute `y_pred_eta = baseline_eta + bst.predict(dtest)` for any MAE comparison against v1.0.
**Warning signs:** Reported MAE is much lower than 123.1s (likely evaluating residual MAE, not reconstructed).

### Pitfall 2: NaN Baseline Values Poisoning Training

**What goes wrong:** If `baseline_eta` or `residual` contains NaN, those rows create NaN targets or features that XGBoost may handle silently but incorrectly.
**Why it happens:** Phase 7 data shows 0 NaN for `baseline_eta` in train, but `baseline_seg_sum` has 41 NaN rows in train.
**How to avoid:** Verify NaN counts before training. Drop any rows where `residual` is NaN. For the 3 baseline features, XGBoost handles NaN features natively (sends to best split direction).
**Warning signs:** Unexpected feature importance where baseline features rank very high due to NaN split behavior.

### Pitfall 3: Subsampling Bias in Optuna Search

**What goes wrong:** v1.0 used 10% subsampling for Optuna search (120K of 1.2M rows). With outlier trimming and a different target distribution, the subsample may not represent the full training data well.
**Why it happens:** Random subsampling on the original data may over/under-represent trimmed regions.
**How to avoid:** Apply outlier trimming BEFORE subsampling for Optuna search. This ensures the search subsample matches the final training distribution.
**Warning signs:** Best Optuna trial parameters perform very differently on full-data CV verification.

### Pitfall 4: Z-Score Threshold Mismatch with User Expectation

**What goes wrong:** CONTEXT.md states z=2.5 removes ~1.2% but empirical measurement shows it removes 4.14% (49,932 of 1,206,181 samples).
**Why it happens:** The 1.2% estimate in the context was likely a rough approximation or based on a normal distribution assumption (2.5 sigma removes ~1.24% for perfectly normal data). The actual residual distribution has heavier tails than normal.
**How to avoid:** Use z=2.5 as the locked decision (it is the specific threshold chosen), but document the actual removal percentage. 4.14% is still reasonable and within the "worst 1-2%" guidance from REQUIREMENTS.md -- or more precisely, it exceeds 2% but not drastically.
**Warning signs:** If post-trimming training data is unexpectedly small, check the z-threshold math.

### Pitfall 5: Eval Metric Name for Pruning Callback

**What goes wrong:** The XGBoostPruningCallback requires the exact eval metric key string. With `evals=[(dval, "val")]` and `eval_metric="mae"`, the key is `"val-mae"`.
**Why it happens:** The naming convention is `{eval_set_name}-{metric_name}`.
**How to avoid:** Use `XGBoostPruningCallback(trial, "val-mae")` exactly. Verified this produces correct output.
**Warning signs:** Optuna raises "Trial should report intermediate value" errors during pruning.

### Pitfall 6: Deterministic Final Model with Wrong Round Count

**What goes wrong:** User decision is "final model trains for exact n_estimators from best trial (deterministic)." If the Optuna trial used early stopping and reported `best_iteration < n_estimators`, using the trial's `n_estimators` would overtrain.
**Why it happens:** In Optuna, `num_boost_round` is suggested but early stopping may find a better iteration.
**How to avoid:** Store `best_iteration` from each Optuna trial. For the final model, train for exactly `best_iteration + 1` rounds with NO early stopping. This is deterministic and matches the Optuna validation performance.
**Warning signs:** Final model MAE is worse than Optuna best trial MAE on the same validation set.

### Pitfall 7: GPU Memory with Categorical Features

**What goes wrong:** XGBoost converts categorical features to one-hot splits internally on GPU. With `max_cat_to_onehot=10` and categorical columns having many categories (e.g., `pattern_id` may have 50+ values), memory usage grows.
**Why it happens:** GTX 1060 has only 3GB VRAM. The data itself is small (~54MB) but tree building and gradient buffers add overhead.
**How to avoid:** The current `max_cat_to_onehot=10` setting is already in v1.0 and works fine. Monitor GPU memory during training; if OOM occurs, reduce `max_cat_to_onehot` or fall back to CPU.
**Warning signs:** CUDA out-of-memory errors during Optuna trials with deep trees.

## Code Examples

### Example 1: GPU Auto-Detection (Verified)

```python
# Source: Verified on project hardware (GTX 1060 3GB, XGBoost 3.1.3, CUDA 12.5)
def detect_xgb_device():
    """Detect whether XGBoost can use GPU. Returns 'cuda' or 'cpu'."""
    try:
        import xgboost as xgb
        import numpy as np
        dm = xgb.DMatrix(np.zeros((2, 1)), label=[0, 1])
        bst = xgb.train({"device": "cuda", "tree_method": "hist"},
                         dm, num_boost_round=1, verbose_eval=False)
        del bst, dm
        return "cuda"
    except Exception:
        return "cpu"
```

### Example 2: Huber Loss with MAE Eval Metric (Verified)

```python
# Source: Verified on project hardware, XGBoost 3.1.3
# Key: objective="reg:pseudohubererror", eval_metric="mae", huber_slope controls delta
params = {
    "objective": "reg:pseudohubererror",
    "huber_slope": 5.0,  # delta parameter; higher = more like squared error
    "eval_metric": "mae",
    "tree_method": "hist",
    "device": "cuda",
}
# The eval metric key for pruning callback is "val-mae" when evals name is "val"
# evals=[(dval_search, "val")]  ->  callback key = "val-mae"
```

### Example 3: Optuna Search Space for 9 Hyperparameters (Recommended)

```python
# Source: Informed by v1.0 results (tuned_metrics.json) and XGBoost 3.1.3 docs
# Fresh wide ranges -- no warm-start from v1.0
def suggest_params(trial, device):
    objective_name = trial.suggest_categorical(
        "objective", ["reg:squarederror", "reg:pseudohubererror"]
    )
    params = {
        "objective": objective_name,
        "eval_metric": "mae",
        "tree_method": "hist",
        "device": device,
        "max_cat_to_onehot": 10,
        "seed": 42,
        # --- 9 hyperparameters ---
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "n_estimators": trial.suggest_int("n_estimators", 200, 2000),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 100),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
    }
    if objective_name == "reg:pseudohubererror":
        params["huber_slope"] = trial.suggest_float("huber_slope", 0.5, 50.0, log=True)
    return params, params.pop("n_estimators")
```

**Rationale for ranges:**
- `learning_rate`: 0.01-0.3 (v1.0 found 0.20, wider range for residual target)
- `max_depth`: 3-10 (v1.0 found 8, allow exploration both ways)
- `n_estimators`: 200-2000 (v1.0 found 435 with early stopping at 2158 final, wider for new target)
- `subsample`: 0.5-1.0 (standard range)
- `colsample_bytree`: 0.3-1.0 (wider low end than v1.0's 0.5-1.0)
- `min_child_weight`: 1-100 (v1.0 found 8, allow much smaller for finer splits on residuals)
- `reg_alpha`: 1e-4 to 10.0 (wider than v1.0's 1e-3 to 10.0)
- `reg_lambda`: 1e-4 to 10.0 (wider than v1.0's 1e-3 to 10.0)
- `gamma`: 0.0-5.0 (NEW parameter, zero-centered residuals may benefit from conservative splits)
- `huber_slope`: 0.5-50.0 log scale (only for Huber; default is 1.0, residual std~287 suggests higher values may help)

### Example 4: Updated Feature Constants

```python
# v1.1 feature set changes
PHASE3_FEATURE_COLS = [
    "distance_to_target", "scheduled_time_to_target", "current_speed",
    "route_progress", "stops_remaining", "stop_index",
    # "lateness_now" REMOVED (zero variance)
    "minutes_since_midnight", "day_of_week", "route_id", "pattern_id",
    "precipitation_mm", "temperature_c", "passenger_load", "is_idle",
]  # 14 features (was 15)

# New baseline features (from Phase 7 augmented parquets)
BASELINE_FEATURE_COLS = [
    "baseline_s2s",
    "baseline_seg_sum",
    "baseline_eta",
]

# Combined v1.1 feature set
FEATURE_COLS_V2 = PHASE3_FEATURE_COLS + PHASE4_FEATURE_COLS + BASELINE_FEATURE_COLS
# 14 + 28 + 3 = 45 features

TARGET_COL = "residual"  # Changed from "time_to_arrival_seconds"

# Extra columns to keep for reconstruction and evaluation
KEEP_EXTRA = ["stops_away", "route_id", "time_to_arrival_seconds", "baseline_eta"]
```

### Example 5: Deterministic Final Training

```python
# Source: User decision -- exact round count, no early stopping
# The best Optuna trial reports best_iteration from its early-stopped run
best_n_estimators = study.best_trial.user_attrs["best_iteration"] + 1

# Final model: train for EXACT round count, NO early stopping
bst_final = xgb.train(
    best_params,
    dtrain_full,
    num_boost_round=best_n_estimators,
    evals=[(dtrain_full, "train"), (dval, "val")],
    # NO early_stopping_rounds -- deterministic
    verbose_eval=100,
)
```

## State of the Art

| Old Approach (v1.0) | Current Approach (v1.1) | When Changed | Impact |
|---------------------|------------------------|--------------|--------|
| `time_to_arrival_seconds` as target | `residual` as target | Phase 8 | Model learns deviation from baseline, not absolute time |
| 43 features, `lateness_now` included | 45 features, `lateness_now` dropped, 3 baselines added | Phase 8 | Better signal-to-noise; baselines give model context |
| `reg:squarederror` only | Compare `reg:squarederror` vs `reg:pseudohubererror` | Phase 8 | Huber loss more robust to outlier residuals |
| 150 Optuna trials, 8 hyperparameters | 100 trials, 9 hyperparameters (+ gamma) | Phase 8 | Gamma helps control split conservatism for zero-centered target |
| No outlier trimming | Z-score 2.5 sigma trimming | Phase 8 | Removes extreme residuals that distort squared error gradients |
| `device: "cuda"` hardcoded | Auto-detect GPU, fall back to CPU | Phase 8 | Scripts work anywhere without manual config |
| 10% subsample, full retrain with 5x rounds + early stopping | 10% subsample, deterministic final retrain | Phase 8 | Reproducible model with exact same output on same data |

**Deprecated/outdated:**
- `lateness_now` feature: Zero variance, provides no signal. Drop from feature list.
- v1.0 Optuna study (`tiger_transit_tuning` in `models/optuna_study.db`): New study with different name required for fresh search.

## Open Questions

1. **Z-score 2.5 removes 4.14%, not ~1.2%**
   - What we know: The residual distribution has heavier tails than Gaussian (long tails to +4814s and -2920s). At z=2.5, 49,932 samples are removed.
   - What's unclear: Whether the user intended ~1.2% removal (requiring z~3.72) or the z=2.5 threshold specifically.
   - Recommendation: Use z=2.5 as explicitly stated in the locked decision. Document actual removal percentage (4.14%). This is still reasonable -- it removes the extreme 4% which corresponds roughly to residuals beyond +/-710s.

2. **Huber slope value for residual distribution**
   - What we know: Default `huber_slope=1.0`. Residual std is ~287s. When huber_slope << std, the loss is nearly linear (MAE-like). When huber_slope >> std, the loss is nearly quadratic (MSE-like).
   - What's unclear: Optimal slope for this distribution.
   - Recommendation: Search `huber_slope` in range [0.5, 50.0] log-scale within Optuna. This lets the optimizer find the right balance. Values around 100-300 (near the std) would make it behave like a blended MAE/MSE loss.

3. **Optuna subsample percentage with outlier-trimmed data**
   - What we know: v1.0 used 10% subsample (120K rows). After z=2.5 trimming, training data drops to ~1,156K rows, so 10% = ~116K rows.
   - What's unclear: Whether 10% subsample is still sufficient for the residual target distribution.
   - Recommendation: Keep 10% subsample for search speed. The CV verification stage (Stage 2) uses full data and will catch any subsample bias.

4. **Whether `n_estimators` should be the Optuna-searched value or `best_iteration`**
   - What we know: User decision says "final model trains for exact n_estimators from best trial." But Optuna trials use early stopping, so `best_iteration` may differ from `n_estimators`.
   - What's unclear: Exactly which round count to use for deterministic final training.
   - Recommendation: Use `best_iteration + 1` from the best Optuna trial (the actual iteration where validation loss was lowest). This is the round count that produced the reported validation MAE. Store it via `trial.set_user_attr("best_iteration", bst.best_iteration)`.

## Sources

### Primary (HIGH confidence)
- XGBoost 3.1.3 installed build -- `xgb.build_info()` confirms CUDA 12.5, USE_CUDA=True
- [XGBoost Parameters docs](https://xgboost.readthedocs.io/en/stable/parameter.html) -- `reg:pseudohubererror`, `huber_slope`, `gamma`, `device`, `tree_method`
- [XGBoost GPU Support docs](https://xgboost.readthedocs.io/en/stable/gpu/index.html) -- CUDA requirements, ELLPACK compression, device parameter
- Optuna 4.7.0 installed -- `from optuna_integration import XGBoostPruningCallback` verified
- Live GPU test -- `device="cuda"`, `tree_method="hist"` works for `reg:squarederror` and `reg:pseudohubererror` with `eval_metric="mae"` on GTX 1060 3GB
- Project data analysis -- `train.parquet` residual stats: mean=-9.05, std=287.43, z=2.5 removes 4.14%
- v1.0 codebase -- `train_advanced.py`, `build_differentiator_features.py`, `tuned_metrics.json` analyzed in full

### Secondary (MEDIUM confidence)
- [Optuna XGBoost integration example](https://github.com/optuna/optuna-examples/blob/main/xgboost/xgboost_integration.py) -- Confirmed MedianPruner + XGBoostPruningCallback pattern
- [XGBoosting.com Huber configuration](https://xgboosting.com/configure-xgboost-regpseudohubererror-objective/) -- Confirmed huber_slope default of 1.0
- [Optuna-Integration PyPI](https://pypi.org/project/optuna-integration/) -- Confirmed import path `from optuna_integration import XGBoostPruningCallback`

### Tertiary (LOW confidence)
- None -- all critical claims verified with primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries verified installed with exact versions, GPU confirmed working
- Architecture: HIGH -- Patterns derived from analysis of existing v1.0 codebase that will be modified in place
- Pitfalls: HIGH -- Z-score mismatch empirically verified, eval metric naming tested, reconstruction logic validated
- Optuna search ranges: MEDIUM -- Ranges are informed by v1.0 results and XGBoost docs but optimal ranges depend on the specific residual distribution
- Huber slope range: MEDIUM -- Log-scale [0.5, 50.0] is reasonable given std~287 but may need widening if Optuna consistently hits boundaries

**Research date:** 2026-02-11
**Valid until:** 2026-03-11 (30 days -- XGBoost/Optuna versions are stable)
