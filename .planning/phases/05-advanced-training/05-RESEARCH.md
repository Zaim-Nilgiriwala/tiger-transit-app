# Phase 5: Advanced Training - Research

**Researched:** 2026-02-04
**Domain:** XGBoost custom objectives, Optuna hyperparameter tuning, quantile regression
**Confidence:** HIGH

## Summary

This phase optimizes the existing differentiator model (175.7s MAE, 43 features, XGBoost 3.1.3) through three techniques: asymmetric loss to penalize overestimation 3:1, Optuna hyperparameter tuning with cross-validation, and multi-quantile predictions (P20/P50/P75) for confidence intervals. No new features are added -- this is purely training configuration.

XGBoost 3.1.3 (already installed) natively supports all required functionality: custom objective functions via gradient/hessian callbacks, `reg:quantileerror` with multi-quantile `QuantileDMatrix`, and the `xgb.train` native API that integrates cleanly with Optuna. Optuna (not yet installed) provides Bayesian optimization with an XGBoost pruning callback that early-terminates unpromising trials, dramatically reducing total tuning time.

The pipeline is three-step as decided: (1) Optuna tunes hyperparameters with `reg:squarederror`, (2) retrain best params with custom asymmetric loss, (3) train quantile models with best params. All intermediate models are saved for comparison.

**Primary recommendation:** Use XGBoost native `xgb.train` API throughout (not sklearn wrapper) since custom objectives and `QuantileDMatrix` require it. Train quantile models separately per quantile rather than multi-output, since our 3 quantiles are few and separate models produce more accurate individual quantile estimates.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.1.3 (installed) | Gradient boosting, custom objectives, quantile regression | Already in use; native support for all needed features |
| optuna | 4.x (latest) | Bayesian hyperparameter optimization | Industry standard for ML tuning; tree-structured Parzen estimator |
| optuna-integration | 4.x | XGBoostPruningCallback for early trial termination | Separate package since Optuna 4.0; prunes bad trials mid-training |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| numpy | (installed) | Gradient/hessian computation in custom objectives | Always -- vectorized math for loss functions |
| pandas | (installed) | Data loading, date manipulation for CV splits | Always -- feature data is parquet-based |
| scikit-learn | (installed) | TimeSeriesSplit for cross-validation | During Optuna tuning for temporal CV folds |
| matplotlib | (installed) | Comparison charts, loss curve visualization | Post-training comparison table generation |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate quantile models | Multi-output QuantileDMatrix | Multi-output shares tree structure across quantiles, reducing individual quantile accuracy; separate models are better for only 3 quantiles |
| TimeSeriesSplit | GroupKFold by date | TimeSeriesSplit better matches temporal structure; with 26 training days, 5-fold TSS gives ~5 days per fold which is reasonable |
| Optuna MedianPruner | Optuna HyperbandPruner | MedianPruner is simpler and well-suited; Hyperband better for very large search spaces |

**Installation:**
```bash
pip install optuna optuna-integration[xgboost]
```

## Architecture Patterns

### Recommended Script Structure
```
scripts/
    train_advanced.py            # Main orchestrator: Optuna tuning + asymmetric + quantile
models/
    tuned_v1.ubj                 # Optuna best (squared error)
    tuned_metrics.json           # Tuned model metrics
    asymmetric_v1.ubj            # Asymmetric loss retrained
    asymmetric_metrics.json      # Asymmetric model metrics
    quantile_p20_v1.ubj          # P20 quantile model
    quantile_p50_v1.ubj          # P50 quantile model
    quantile_p75_v1.ubj          # P75 quantile model
    quantile_metrics.json        # Quantile evaluation metrics
    phase5_comparison.json       # Full comparison across all phases
```

### Pattern 1: XGBoost Custom Objective Function (Asymmetric Loss)
**What:** Custom gradient/hessian function passed to `xgb.train(obj=...)` that penalizes overestimation 3x
**When to use:** Step 2 of pipeline -- retrain with best Optuna params but asymmetric loss
**Example:**
```python
# Source: https://xgboost.readthedocs.io/en/latest/tutorials/custom_metric_obj.html
def make_asymmetric_objective(alpha=3.0, threshold_seconds=480):
    """
    Asymmetric squared error: penalizes overestimation (pred > actual) more heavily.

    Overestimation = model says bus is further away than reality = rider might miss bus.
    Proximity scaling: penalty ramps up as predicted time decreases below threshold.

    Args:
        alpha: Penalty multiplier for overestimation (3.0 = 3:1 ratio)
        threshold_seconds: Time threshold for proximity scaling (480 = 8 minutes)
    """
    def asymmetric_obj(predt: np.ndarray, dtrain: xgb.DMatrix):
        y = dtrain.get_label()
        residual = predt - y  # positive = overestimation

        # Base weight: 1.0 for underestimation, alpha for overestimation
        is_over = (residual > 0).astype(float)
        weight = 1.0 + (alpha - 1.0) * is_over

        # Proximity scaling: ramp up penalty when predicted time is short
        # At pred=0, scale=alpha; at pred>=threshold, scale=1.0
        proximity_scale = np.clip(1.0 + (alpha - 1.0) * (1.0 - predt / threshold_seconds), 1.0, alpha)
        # Only apply proximity scaling to overestimation
        weight = np.where(is_over > 0, weight * proximity_scale, weight)

        # Gradient and hessian of weighted squared error: weight * (pred - y)^2
        grad = weight * residual           # d/dp [w * (p-y)^2 / 2] = w * (p-y)
        hess = weight * np.ones_like(y)    # d2/dp2 = w

        return grad, hess
    return asymmetric_obj
```

### Pattern 2: Optuna Objective with Native xgb.train API
**What:** Optuna trial function using xgb.train with pruning callback and TimeSeriesSplit
**When to use:** Step 1 of pipeline -- hyperparameter search
**Example:**
```python
# Source: https://github.com/optuna/optuna-examples/blob/main/xgboost/xgboost_integration.py
from optuna_integration import XGBoostPruningCallback
from sklearn.model_selection import TimeSeriesSplit

def objective(trial, dtrain_full, y_train_full, feature_cols):
    params = {
        "objective": "reg:squarederror",
        "eval_metric": "mae",
        "tree_method": "hist",
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "min_child_weight": trial.suggest_int("min_child_weight", 5, 100),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        "max_cat_to_onehot": 10,
        "seed": 42,
    }
    num_round = trial.suggest_int("num_boost_round", 500, 5000)

    # TimeSeriesSplit CV on training data
    tscv = TimeSeriesSplit(n_splits=4)
    cv_scores = []

    for fold, (train_idx, val_idx) in enumerate(tscv.split(dtrain_full)):
        # ... create DMatrix for fold, train with pruning callback
        pruning_callback = XGBoostPruningCallback(trial, f"val-mae")
        bst = xgb.train(
            params, d_fold_train,
            num_boost_round=num_round,
            evals=[(d_fold_val, "val")],
            early_stopping_rounds=50,
            callbacks=[pruning_callback],
            verbose_eval=False,
        )
        cv_scores.append(bst.best_score)

    return np.mean(cv_scores)

study = optuna.create_study(direction="minimize", pruner=optuna.pruners.MedianPruner())
study.optimize(lambda trial: objective(trial, ...), n_trials=150)
```

### Pattern 3: Separate Quantile Model Training
**What:** Train one model per quantile using `reg:quantileerror`
**When to use:** Step 3 of pipeline -- quantile models with best params from Optuna
**Example:**
```python
# Source: https://xgboost.readthedocs.io/en/stable/python/examples/quantile_regression.html
quantiles = [0.20, 0.50, 0.75]  # P20, P50, P75

for q in quantiles:
    params = {**best_params}  # Copy Optuna best params
    params["objective"] = "reg:quantileerror"
    params["quantile_alpha"] = q

    # QuantileDMatrix for memory efficiency (optional, DMatrix also works)
    Xy = xgb.QuantileDMatrix(X_train, y_train)
    Xy_val = xgb.QuantileDMatrix(X_val, y_val, ref=Xy)

    bst = xgb.train(
        params, Xy,
        num_boost_round=best_num_round,
        evals=[(Xy_val, "val")],
        early_stopping_rounds=50,
        verbose_eval=100,
    )
    bst.save_model(f"models/quantile_p{int(q*100)}_v1.ubj")
```

### Anti-Patterns to Avoid
- **Using sklearn XGBRegressor wrapper for custom objectives:** The native `xgb.train` API is required for `obj=` parameter and gives direct control over DMatrix, callbacks, and iteration ranges.
- **Multi-output quantile model for few quantiles:** Shared tree structure degrades individual quantile accuracy. Only use multi-output when training many quantiles (10+).
- **Optimizing asymmetric loss in Optuna:** The decision is to optimize MAE in Optuna (scoreboard metric), then apply asymmetric loss as a post-tuning refinement. Mixing them conflates the search signal.
- **Shuffled cross-validation:** Data is temporal (Nov-Dec 2025). Always use TimeSeriesSplit to prevent future leakage.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Hyperparameter search | Grid search or random search loops | Optuna with TPE sampler | Bayesian optimization finds better params in fewer trials; pruning saves 50-70% compute |
| Cross-validation splitting | Manual date-based fold logic | sklearn TimeSeriesSplit | Handles fold indices, works with Optuna, tested edge cases |
| Trial pruning | Manual early stopping across trials | XGBoostPruningCallback | Reports intermediate results to Optuna, handles async pruning |
| Quantile loss function | Custom pinball loss gradient/hessian | `reg:quantileerror` built-in | XGBoost's native implementation is optimized and tested |
| Model comparison tables | Manual metric collection | JSON checkpoint + pandas comparison | Each step saves metrics JSON; final script loads all and generates table |

**Key insight:** XGBoost 3.x has native quantile regression support. The only custom code needed is the asymmetric loss objective -- everything else uses built-in functionality.

## Common Pitfalls

### Pitfall 1: Gradient Sign Convention
**What goes wrong:** Model error increases instead of decreasing during training
**Why it happens:** The gradient must be d(loss)/d(prediction). Getting the sign wrong (subtracting in wrong order) inverts the optimization direction.
**How to avoid:** For asymmetric squared error, gradient = weight * (pred - y), NOT weight * (y - pred). Verify on first 10 iterations that training loss decreases.
**Warning signs:** Training MAE going up in first 100 rounds

### Pitfall 2: Hessian Must Be Positive
**What goes wrong:** XGBoost clips negative hessian values, causing poor convergence
**Why it happens:** Custom objectives with proximity scaling can produce negative second derivatives if the scaling function is non-convex
**How to avoid:** Use weight * 1.0 as hessian (constant positive), not the true second derivative of the proximity-scaled loss. This is a common approximation that works well in practice.
**Warning signs:** NaN or Inf in predictions; model predicting constant values

### Pitfall 3: Optuna CV Data Leakage with DMatrix
**What goes wrong:** Creating DMatrix from full training data then splitting indices leaks categorical encoding info
**Why it happens:** DMatrix categorical encoding sees all data at construction time
**How to avoid:** Create fresh DMatrix objects for each CV fold from the raw DataFrame/numpy arrays, not by slicing a pre-built DMatrix
**Warning signs:** CV scores much better than holdout validation score

### Pitfall 4: TimeSeriesSplit Fold Imbalance
**What goes wrong:** First fold has very few training samples, biasing CV mean
**Why it happens:** TimeSeriesSplit with n_splits=5 gives fold 1 only ~1/6 of data for training
**How to avoid:** Use n_splits=3 or 4 with 26 days of training data. With 4 folds: ~6/12/18/22 days per fold training set, which is reasonable.
**Warning signs:** Fold 1 score much worse than other folds

### Pitfall 5: Quantile Crossing
**What goes wrong:** P20 prediction > P50 prediction for some samples (impossible in reality)
**Why it happens:** Separately trained quantile models don't enforce monotonicity
**How to avoid:** Post-process with sorting: `p20, p50, p75 = sorted([p20_pred, p50_pred, p75_pred])`. This is standard practice.
**Warning signs:** Any sample where lower quantile > higher quantile

### Pitfall 6: Asymmetric Loss Inflates MAE
**What goes wrong:** Asymmetric model has worse MAE than squared-error model
**Why it happens:** By design -- asymmetric loss biases predictions toward underestimation, trading MAE for rider safety
**How to avoid:** This is expected and acceptable. The validation metric is median residual sign (should be slightly negative). Track both MAE and median residual in comparison table.
**Warning signs:** Only a concern if MAE degrades by more than ~15-20% vs the tuned model

### Pitfall 7: QuantileDMatrix ref= Requirement
**What goes wrong:** Validation/test QuantileDMatrix fails or produces wrong predictions
**Why it happens:** QuantileDMatrix for validation must reference the training QuantileDMatrix via `ref=` parameter to share quantile sketches
**How to avoid:** Always create val/test QuantileDMatrix with `ref=Xy_train`
**Warning signs:** Error during QuantileDMatrix construction; inconsistent prediction shapes

## Code Examples

### Custom Evaluation Metric for Asymmetric Validation
```python
# Source: XGBoost custom metric docs
def median_residual_eval(predt: np.ndarray, dtrain: xgb.DMatrix):
    """Custom eval: median residual. Negative = model predicts arrival sooner (desired)."""
    y = dtrain.get_label()
    residual = predt - y
    median_res = float(np.median(residual))
    return "median_residual", median_res
```

### Comparison Table Generation
```python
# Load all checkpoint metrics and generate comparison
models = {
    "Naive (schedule)": {"mae": 708.9, "rmse": 883.4},
    "Baseline (P3)": json.load(open("models/baseline_metrics.json"))["xgboost"],
    "Differentiator (P4)": json.load(open("models/differentiator_metrics.json"))["xgboost"],
    "Tuned (P5)": json.load(open("models/tuned_metrics.json"))["xgboost"],
    "Asymmetric (P5)": json.load(open("models/asymmetric_metrics.json"))["xgboost"],
}
# Print formatted table with vs-naive percentages
```

### Proximity-Scaled Asymmetric Weight Computation
```python
def compute_weights(predt, y, alpha=3.0, threshold=480):
    """
    Weight logic:
    - Underestimation (pred < actual): weight = 1.0 (normal)
    - Overestimation (pred > actual): weight = alpha (3.0)
    - Overestimation near arrival: weight = alpha * proximity_scale (up to alpha^2 = 9.0)

    Proximity scale: linear ramp from 1.0 (at threshold) to alpha (at pred=0)
    """
    residual = predt - y
    is_over = (residual > 0).astype(float)

    base_weight = 1.0 + (alpha - 1.0) * is_over

    # Proximity: only applied to overestimation
    proximity = np.clip(1.0 + (alpha - 1.0) * (1.0 - predt / threshold), 1.0, alpha)
    weight = np.where(is_over > 0, base_weight * proximity, base_weight)

    return weight
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `optuna.integration` imports | `optuna_integration` separate package | Optuna 4.0 (Sep 2024) | Must `pip install optuna-integration[xgboost]` separately |
| Separate model per quantile only | `reg:quantileerror` with multi-quantile QuantileDMatrix | XGBoost 2.0 (2023) | Single model can predict multiple quantiles; but separate models better for few quantiles |
| Manual quantile loss implementation | Built-in `reg:quantileerror` | XGBoost 2.0 (2023) | No need for custom pinball loss gradient/hessian |

**Deprecated/outdated:**
- `optuna.integration.XGBoostPruningCallback` -- moved to `optuna_integration.XGBoostPruningCallback` (may still work via shim but deprecated)
- Manual pinball loss for quantile regression -- use `reg:quantileerror` built-in

## Open Questions

1. **Optuna trial count recommendation**
   - What we know: 1.2M training rows, 43 features, ~8 hyperparameters to tune. Each trial with 4-fold CV trains 4 models. With pruning, bad trials terminate early.
   - Recommendation: Start with 150 trials. With pruning, this should complete in reasonable time. The search space is moderate (8 params) so 150 trials gives good coverage.

2. **Whether to include loss parameters in Optuna search space**
   - What we know: Context decision says Claude's discretion. Alpha (penalty ratio) and threshold are semantically meaningful business parameters, not typical ML hyperparameters.
   - Recommendation: Fix alpha=3.0 and threshold=480s as decided. Do NOT include in Optuna search space. These are business decisions, not optimization targets. If MAE tradeoff is too large, manually adjust alpha downward (e.g., 2.0).

3. **TimeSeriesSplit vs GroupKFold**
   - What we know: 26 training days, temporal ordering matters, no group/trip IDs readily available for GroupKFold.
   - Recommendation: Use TimeSeriesSplit with n_splits=4. This gives 4 folds with progressive training sizes (~6/12/18/22 days). GroupKFold would need a grouping column (date) and doesn't enforce temporal ordering naturally.

4. **QuantileDMatrix vs regular DMatrix for quantile training**
   - What we know: QuantileDMatrix provides memory efficiency for quantile regression. With 1.2M rows it may matter.
   - Recommendation: Use QuantileDMatrix for quantile models. It is specifically designed for `reg:quantileerror` and handles quantile sketch computation correctly.

## Sources

### Primary (HIGH confidence)
- XGBoost 3.1.3 (installed) -- verified via `pip show xgboost`
- [XGBoost Custom Objective Tutorial](https://xgboost.readthedocs.io/en/latest/tutorials/custom_metric_obj.html) -- gradient/hessian function signature, squared log error example
- [XGBoost Advanced Custom Objectives](https://xgboost.readthedocs.io/en/latest/tutorials/advanced_custom_obj.html) -- convexity requirements, hessian constraints, multi-output handling
- [XGBoost Quantile Regression Example](https://xgboost.readthedocs.io/en/stable/python/examples/quantile_regression.html) -- QuantileDMatrix, multi-quantile setup, quantile_alpha parameter
- [XGBoost Parameters](https://xgboost.readthedocs.io/en/latest/parameter.html) -- reg:quantileerror objective, quantile_alpha configuration

### Secondary (MEDIUM confidence)
- [Optuna-Integration XGBoostPruningCallback](https://optuna-integration.readthedocs.io/en/latest/reference/generated/optuna_integration.XGBoostPruningCallback.html) -- import path, constructor parameters
- [Optuna XGBoost Examples](https://github.com/optuna/optuna-examples/blob/main/xgboost/xgboost_simple.py) -- objective function pattern, study creation
- [Optuna-Integration PyPI](https://pypi.org/project/optuna-integration/) -- version 4.7.0, separate package since Optuna 4.0

### Tertiary (LOW confidence)
- [AppsFlyer Asymmetric Loss](https://medium.com/appsflyerengineering/building-a-tunable-and-configurable-custom-objective-function-for-xgboost-d3ced8967809) -- closure pattern for parameterized objectives, asymmetric weighting approach
- [XGBoosting.com Quantile Intervals](https://xgboosting.com/xgboost-prediction-interval-using-quantile-regression/) -- separate model per quantile recommendation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- XGBoost 3.1.3 verified installed, Optuna well-documented
- Architecture: HIGH -- Custom objectives, quantile regression, and Optuna integration all have official documentation and examples
- Pitfalls: HIGH -- Gradient sign, hessian positivity, and quantile crossing are well-documented issues in XGBoost custom objective literature

**Research date:** 2026-02-04
**Valid until:** 2026-03-06 (stable libraries, 30 days)
