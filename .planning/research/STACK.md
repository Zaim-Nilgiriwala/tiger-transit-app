# Stack Research

**Domain:** Transit ETA prediction with XGBoost (replacing PyTorch model)
**Researched:** 2026-02-03
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | >=3.11 | Runtime | Required by pandas 3.0, numpy 2.4, xgboost 3.1. Use 3.12 for broadest library compat. |
| XGBoost | 3.1.3 | Gradient boosted tree model | Latest stable (Jan 2026). Native categorical support with auto re-coding (3.1+), built-in quantile regression via `reg:quantileerror`, UBJSON serialization. Well-proven for transit ETA -- studies show MAE of 16-30s on bus arrival tasks. |
| pandas | 2.3.3 | Data loading, feature engineering, pipeline orchestration | Existing codebase uses pandas heavily. 2.3.3 is last stable 2.x -- avoid pandas 3.0.0 (Jan 2026) for now due to breaking changes (CoW default, string dtype changes) that would require pipeline rewrites. Upgrade later. |
| NumPy | 2.4.2 | Numerical operations, array manipulation | Latest stable (Jan 2026). Required by pandas, scikit-learn, xgboost. |
| scikit-learn | 1.8.0 | Metrics, preprocessing utilities, cross-validation | Latest stable (Dec 2025). Provides `mean_absolute_error`, `mean_pinball_loss` for quantile eval, `TimeSeriesSplit` for temporal CV. |
| Optuna | 4.7.0 | Bayesian hyperparameter optimization | Latest stable (Jan 2026). Define-by-run API with TPE sampler is ideal for XGBoost tuning. Built-in `XGBoostPruningCallback` for early stopping of bad trials. Far superior to grid/random search for 10+ hyperparameters. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| SHAP | 0.50.0 | Model explainability, feature importance | After training to understand which features drive predictions. `TreeExplainer` gives exact SHAP values for XGBoost in milliseconds. Critical for debugging and validating model behavior. |
| matplotlib | 3.10.8 | Plotting: residual analysis, feature importance, learning curves | During evaluation phase. Standard for ML visualization. |
| pyarrow | >=14.0 | Parquet read/write backend | Already used by existing pipeline (data_prep outputs .parquet). Required by pandas for Parquet I/O. |
| tqdm | >=4.66 | Progress bars | Already in existing pipeline. Useful for data prep steps. |
| joblib | >=1.3 | Parallel computation, model serialization helper | Bundled with scikit-learn. Use for parallel feature engineering if needed. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest | Unit/integration testing for pipeline | Test feature engineering, model training, serialization round-trips |
| ruff | Linting and formatting | Fast, replaces flake8+black+isort. Single tool. |

## XGBoost Configuration Recommendations

### Regression Objective

Use `reg:squarederror` as baseline, then explore asymmetric options:

```python
# Baseline model
params_baseline = {
    "objective": "reg:squarederror",
    "tree_method": "hist",
    "device": "cpu",
    "enable_categorical": True,
    "eval_metric": ["mae", "rmse"],
    "max_depth": 8,
    "learning_rate": 0.05,
    "n_estimators": 1000,
    "early_stopping_rounds": 50,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 10,
    "reg_alpha": 0.1,
    "reg_lambda": 1.0,
}
```

### Quantile Regression (for confidence intervals)

The existing PyTorch model has P50/P80 quantile heads. XGBoost 3.1 supports this natively:

```python
# Multi-quantile model for P50 + P80
params_quantile = {
    "objective": "reg:quantileerror",
    "quantile_alpha": [0.5, 0.8],
    "tree_method": "hist",         # Required for quantile regression
    "enable_categorical": True,
    "eval_metric": "mae",
}
# Output shape: (n_samples, 2) -- column 0 = P50, column 1 = P80
```

### Asymmetric Loss (matching existing 5x overestimate penalty)

XGBoost does not have a built-in asymmetric loss like the existing PyTorch model's `AsymmetricETALoss`. Two approaches:

1. **Quantile approach (recommended):** Use `reg:quantileerror` with `quantile_alpha=0.65`. This naturally penalizes underestimation more than overestimation, achieving a similar effect to the asymmetric loss. Tune alpha between 0.55-0.75.

2. **Custom objective:** Write a custom gradient/hessian function. More complex, harder to debug.

### Categorical Feature Handling

XGBoost 3.1 has mature native categorical support. Use it instead of one-hot encoding:

```python
# In pandas, mark categorical columns
df["route_id"] = df["route_id"].astype("category")
df["hour_of_day"] = df["hour_of_day"].astype("category")
df["day_of_week"] = df["day_of_week"].astype("category")

# XGBoost handles them natively with enable_categorical=True
# For the existing config.py CATEGORICAL_COLUMNS: ['hour_of_day', 'day_of_week', 'route_id']
```

### Model Serialization

Use UBJSON format (default since XGBoost 2.1). Do NOT use pickle.

```python
# Save (production)
model.save_model("eta_model.ubj")

# Save (debugging/inspection)
model.save_model("eta_model.json")

# Load
model = xgb.XGBRegressor()
model.load_model("eta_model.ubj")
```

The `.ubj` format is:
- Cross-version compatible (unlike pickle)
- Binary efficient (no floating-point precision loss)
- Cross-language portable (can load in Node.js xgboost binding if ever needed)

### Hyperparameter Tuning with Optuna

```python
import optuna
from xgboost import XGBRegressor

def objective(trial):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 200, 2000),
        "max_depth": trial.suggest_int("max_depth", 4, 12),
        "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 50),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
        "gamma": trial.suggest_float("gamma", 0, 5.0),
        "max_cat_to_onehot": trial.suggest_int("max_cat_to_onehot", 1, 10),
    }
    model = XGBRegressor(
        **params,
        objective="reg:squarederror",
        tree_method="hist",
        enable_categorical=True,
        early_stopping_rounds=50,
        device="cpu",
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_val, y_val)],
        verbose=False,
        callbacks=[optuna.integration.XGBoostPruningCallback(trial, "validation_0-mae")],
    )
    return mean_absolute_error(y_val, model.predict(X_val))

study = optuna.create_study(direction="minimize")
study.optimize(objective, n_trials=200, timeout=3600)
```

## Installation

```bash
# Core ML stack
pip install xgboost==3.1.3 pandas==2.3.3 numpy==2.4.2 scikit-learn==1.8.0

# Hyperparameter tuning
pip install optuna==4.7.0

# Explainability
pip install shap==0.50.0

# Visualization
pip install matplotlib==3.10.8

# Data I/O (likely already installed via pandas)
pip install pyarrow>=14.0 tqdm>=4.66

# Development
pip install pytest ruff
```

Or as a `requirements-xgboost.txt`:

```
xgboost==3.1.3
pandas==2.3.3
numpy==2.4.2
scikit-learn==1.8.0
optuna==4.7.0
shap==0.50.0
matplotlib==3.10.8
pyarrow>=14.0
tqdm>=4.66
openpyxl>=3.1
```

Note: `openpyxl` is needed for reading the timepoint Excel spreadsheet.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| XGBoost 3.1.3 | LightGBM 4.x | If training speed is bottleneck on very large datasets (millions of rows). LightGBM is ~2x faster to train but XGBoost has better quantile regression support and wider deployment ecosystem. Our ~5 weeks of data is small enough that XGBoost training is fast. |
| XGBoost 3.1.3 | CatBoost 1.x | If dataset had many high-cardinality categorical features. CatBoost excels with categories but our categoricals are low-cardinality (23 routes, 7 days, 24 hours). |
| pandas 2.3.3 | Polars 1.37 | If data processing pipeline is a bottleneck. Polars is 10-30x faster for large datasets. Our data is ~5 weeks of telemetry which fits comfortably in pandas memory. Not worth rewriting the existing pipeline. |
| pandas 2.3.3 | pandas 3.0.0 | After stabilization. pandas 3.0.0 (Jan 2026) has breaking changes: Copy-on-Write default, new string dtype. The existing pipeline code needs auditing before upgrading. Pin to 2.3.3 for now. |
| Optuna 4.7.0 | Hyperopt | Never. Optuna has better API, better XGBoost integration (pruning callback), better visualization, and is more actively maintained. |
| Optuna 4.7.0 | sklearn GridSearchCV/RandomizedSearchCV | Only for quick 2-3 parameter sweeps. Optuna's Bayesian approach is far more efficient for the 8-10 parameters XGBoost needs tuned. |
| SHAP 0.50.0 | XGBoost built-in feature_importances_ | For quick checks only. Built-in importance is gain/weight/cover based and can be misleading. SHAP gives theoretically sound per-prediction explanations. |
| scikit-learn metrics | Custom metrics | Only if you need domain-specific metrics not in sklearn (e.g., "% within 60s"). Use sklearn for MAE/RMSE/pinball, write custom for transit-specific ones. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| PyTorch for this model | Massive overkill for tabular regression. XGBoost trains in seconds vs minutes, needs no GPU, no batching, no learning rate scheduling. PyTorch adds complexity without benefit for structured/tabular data. | XGBoost |
| pickle for model serialization | Not cross-version compatible. XGBoost docs explicitly warn against it. Models saved with pickle in XGBoost 3.1 may not load in 3.2+. | `model.save_model("model.ubj")` |
| One-hot encoding for categoricals | Wastes splits on sparse binary features. XGBoost 3.1 native categorical support with optimal partitioning is strictly better for tree models. | `enable_categorical=True` + pandas `category` dtype |
| The old XGBoost binary format | Removed in XGBoost 3.1. No longer supported. | UBJSON (`.ubj`) or JSON (`.json`) |
| Manual feature scaling/normalization | XGBoost is tree-based and invariant to monotonic feature transformations. The existing PyTorch pipeline normalizes features -- this is unnecessary and harmful (harder to interpret) for XGBoost. | Use raw feature values. Only exception: cyclical encoding (sin/cos) for time is still useful as it captures the circular relationship. |
| pandas 3.0.0 (for now) | Released Jan 21, 2026 -- too new. Breaking changes with Copy-on-Write and string dtype defaults. Existing pipeline code would need audit. | Pin pandas==2.3.3 |
| Dask / Spark | Our dataset is ~5 weeks of bus telemetry for 23 routes. This comfortably fits in memory on a laptop. Distributed computing adds complexity for zero benefit at this scale. | pandas (single machine) |

## Stack Patterns by Data Size

**Current data (~5 weeks, likely 500K-2M rows after expansion to per-stop):**
- pandas for all data processing
- XGBoost trains in seconds to low minutes on CPU
- Optuna 200 trials completes in under 1 hour
- No need for GPU, sampling, or distributed training

**If data grows to 6+ months (5-10M rows):**
- Still pandas-viable (10M rows x 70 features ~ 5GB)
- XGBoost training may take 1-5 minutes per trial
- Consider reducing Optuna trials or using more aggressive pruning
- Still no distributed computing needed

**If data grows to 50M+ rows:**
- Consider Polars for data prep pipeline
- Consider XGBoost `external_memory` mode
- Optuna with aggressive pruning becomes important

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| xgboost 3.1.3 | Python 3.10-3.13, numpy >=1.22 | Tested with scikit-learn 1.8 |
| pandas 2.3.3 | Python 3.10-3.14, numpy >=1.22 | Works with pyarrow >=10.0 for parquet |
| scikit-learn 1.8.0 | Python 3.11-3.14, numpy >=1.21 | |
| optuna 4.7.0 | Python 3.9+ | XGBoost integration via `optuna.integration.XGBoostPruningCallback` |
| shap 0.50.0 | Python 3.9-3.14, xgboost 3.x | `TreeExplainer` works natively with XGBoost |
| numpy 2.4.2 | Python 3.11+ | If using Python 3.10, pin numpy <2.4 |

**Recommended Python version: 3.12** -- broadest compatibility across all listed packages.

## Key Differences from Existing PyTorch Pipeline

The XGBoost model changes several aspects of the stack:

| Aspect | PyTorch (current) | XGBoost (new) |
|--------|-------------------|---------------|
| Feature normalization | Required (z-score) | Not needed (tree-invariant) |
| Categorical encoding | Integer encoding, embedded | Native `category` dtype |
| Data format | numpy .npy arrays | pandas DataFrame / Parquet directly |
| Batch processing | DataLoader, batches | Full dataset at once |
| Training loop | Manual epoch loop | `model.fit()` with early stopping |
| GPU | Optional but helps | Not needed at this scale |
| Quantile output | Separate prediction heads | `reg:quantileerror` with `quantile_alpha` |
| Model size | ~100KB-1MB .pt file | ~1-10MB .ubj file (more trees = larger) |
| Inference speed | ~1ms per batch | ~0.1ms per sample (faster for single predictions) |
| Hyperparameter tuning | Manual | Optuna automated |
| Explainability | Black box | SHAP gives per-feature attribution |

## Sources

- [XGBoost 3.1.3 releases](https://github.com/dmlc/xgboost/releases) -- version and release dates (HIGH confidence)
- [XGBoost parameters documentation](https://xgboost.readthedocs.io/en/stable/parameter.html) -- objective, eval_metric, categorical config (HIGH confidence)
- [XGBoost quantile regression docs](https://xgboost.readthedocs.io/en/stable/python/examples/quantile_regression.html) -- reg:quantileerror usage (HIGH confidence)
- [XGBoost categorical data docs](https://xgboost.readthedocs.io/en/stable/tutorials/categorical.html) -- enable_categorical, 3.1 re-coding (HIGH confidence)
- [XGBoost model IO docs](https://xgboost.readthedocs.io/en/stable/tutorials/saving_model.html) -- UBJSON default, pickle warning (HIGH confidence)
- [pandas PyPI](https://pypi.org/project/pandas/) -- version 2.3.3 and 3.0.0 release info (HIGH confidence)
- [scikit-learn 1.8.0 release notes](https://scikit-learn.org/stable/whats_new.html) -- version verification (HIGH confidence)
- [Optuna 4.7.0 releases](https://github.com/optuna/optuna) -- version and XGBoost integration (HIGH confidence)
- [SHAP 0.50.0 PyPI](https://pypi.org/project/shap/) -- version verification (HIGH confidence)
- [NumPy 2.4.2 PyPI](https://pypi.org/project/numpy/) -- version verification (HIGH confidence)
- [Bus arrival prediction with XGBoost (Phnom Penh study)](https://www.researchgate.net/publication/397281321_Bus_Arrival_Time_Prediction_Using_Machine_Learning_Approaches) -- MAE 16s, MAPE 2.61% (MEDIUM confidence)
- [Dynamic bus arrival model with XGBoost (Tumakuru study)](https://arxiv.org/abs/2210.00733) -- spatial pattern approach, 18s error (MEDIUM confidence)
- [XGBoost hyperparameter optimization with Optuna guide](https://xgboosting.com/xgboost-hyperparameter-optimization-with-optuna/) -- tuning patterns (MEDIUM confidence)

---
*Stack research for: Transit ETA prediction with XGBoost*
*Researched: 2026-02-03*
