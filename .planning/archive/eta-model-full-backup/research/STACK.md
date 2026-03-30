# Stack Research: v1.1 Residual-Based ETA Prediction

**Domain:** Residual prediction on top of blended baseline ETA (XGBoost transit model)
**Researched:** 2026-02-11
**Confidence:** HIGH

## Scope

This research covers ONLY the incremental stack needs for v1.1's residual-based prediction approach. The validated v1.0 stack is retained unchanged:

| Retained (DO NOT change) | Version | Status |
|--------------------------|---------|--------|
| XGBoost | 3.1.3 | Validated, keep pinned |
| pandas | 2.3.3 | Validated, keep pinned |
| NumPy | 2.4.2 | Validated, keep pinned |
| scikit-learn | 1.8.0 | Validated, keep pinned |
| Optuna | 4.7.0 | Validated, keep pinned |
| SHAP | 0.50.0 | Validated, keep pinned |
| matplotlib | 3.10.8 | Validated, keep pinned |
| pyarrow | >=14.0 | Validated, keep pinned |

## New Stack Additions

### Verdict: No new libraries required

The residual-based prediction approach does not require any new dependencies. Every operation needed is covered by the existing stack:

| Operation | Needed For | Existing Tool | Why Sufficient |
|-----------|-----------|---------------|----------------|
| Segment-median sum computation | Baseline ETA (leg 1) | pandas groupby + cumsum on `historical_segments.parquet` | Standard groupby aggregation; no new library needed |
| Stop-to-stop historical average | Baseline ETA (leg 2) | pandas groupby on `historical_dwells.parquet` + `historical_segments.parquet` | Lookup table pattern already used in v1.0 feature engineering |
| Blended average | Combining two baseline legs | NumPy mean / pandas arithmetic | Trivial: `(segment_sum + s2s_avg) / 2` |
| Residual label creation | Training target | pandas column subtraction | `df["residual"] = df["time_to_arrival_seconds"] - df["baseline_eta"]` |
| Residual distribution analysis | Sanity checks on target | matplotlib histograms + NumPy percentiles | Already available; `plt.hist()` and `np.percentile()` cover it |
| QQ plots for residual normality | Diagnostic verification | scipy.stats (already installed as scikit-learn dependency) | `scipy.stats.probplot()` is available without adding a new dep |
| Symmetric squared error loss | Training objective | XGBoost `reg:squarederror` | This is the default XGBoost objective; no change needed |
| Prediction reconstruction | Inference: `baseline + residual` | NumPy addition | `final_eta = baseline_eta + model.predict(X)` |
| MAE evaluation on reconstructed | Comparing v1.1 vs v1.0 | scikit-learn `mean_absolute_error` or NumPy | Same metrics pipeline as v1.0 |
| Optuna re-tuning | Fresh hyperparameters | Optuna 4.7.0 | Same tuning approach, new study name to avoid contamination |

### scipy.stats (Already Available -- Not a New Addition)

scipy is already installed as a transitive dependency of scikit-learn 1.8.0. It provides useful diagnostic functions for residual analysis:

| Function | Purpose | When to Use |
|----------|---------|-------------|
| `scipy.stats.probplot(residuals, plot=plt)` | QQ plot for residual normality | After computing residual labels, to verify distribution shape |
| `scipy.stats.describe(residuals)` | Quick distribution summary (skew, kurtosis) | Sanity check that residuals are roughly centered near 0 |
| `scipy.stats.jarque_bera(residuals)` | Formal normality test | Optional diagnostic; not required for training |

**Important:** These are diagnostic tools, not training dependencies. The model does not require normally-distributed residuals to work -- XGBoost is nonparametric. These are useful for understanding the target distribution and debugging.

## Existing Data Assets for Baseline Computation

The baseline ETA requires two historical lookup tables. Both already exist:

| Asset | Path | Contents | How Used in Baseline |
|-------|------|----------|---------------------|
| `historical_segments.parquet` | `data/processed/` | Median segment travel time by (route_id, last_stop_id, hour_ct, day_type) | Sum segment medians from current stop to target stop |
| `historical_dwells.parquet` | `data/processed/` | Median dwell time by (route_id, stop_id, hour_ct, day_type) | Add dwell times at intermediate stops to segment sum |
| `stop_sequences.parquet` | `data/processed/` | Stop ordering by (route_id, stop_id, stop_sequence) | Enumerate intermediate segments/stops between observation and target |

No new data collection or parsing is needed. The baseline calculator consumes these existing parquets.

## XGBoost Configuration Changes for Residual Targets

The residual target changes the distribution the model sees. Key configuration implications:

### Target Distribution Shift

| Property | v1.0 (raw seconds) | v1.1 (residual) |
|----------|--------------------|--------------------|
| Range | 0 to ~2000+ seconds | Centered around 0, likely -500 to +500 |
| Distribution | Right-skewed, non-negative | Approximately symmetric, includes negatives |
| Mean | ~300s (estimated) | ~0s (by construction) |
| Objective | `reg:squarederror` | `reg:squarederror` (same, but semantics differ) |

### Hyperparameter Re-tuning Rationale

With a tighter, zero-centered target distribution:

- **`base_score`**: XGBoost defaults to using the mean of training labels. For residuals, this will be near 0, which is correct. No manual override needed -- XGBoost 3.1+ computes this automatically.
- **`learning_rate`**: May need smaller value since residual magnitudes are smaller than raw seconds. Optuna will find this.
- **`max_depth`**: Similar or shallower trees may suffice since the model is learning corrections, not the full signal. Optuna will find this.
- **`reg_alpha` / `reg_lambda`**: Regularization may need re-calibration for the new target scale. Optuna will find this.

**Recommendation:** Fresh Optuna study (new study name, e.g., `tiger_transit_v11_residual`). Do not reuse v1.0 hyperparameters -- the target distribution is fundamentally different.

### Loss Function: Start with Symmetric

| Objective | Rationale |
|-----------|-----------|
| `reg:squarederror` | Residuals are centered at 0; asymmetric loss semantics are inverted for residuals (a positive residual means the bus took longer than baseline, not the same as overprediction in v1.0). Start symmetric, add asymmetry only if bias analysis reveals a systematic direction. |

## What NOT to Add

| Temptation | Why Resist | What to Do Instead |
|------------|-----------|-------------------|
| **seaborn** for residual plots | matplotlib already handles histograms, scatter plots, and bar charts. Adding seaborn increases dependency surface for marginal aesthetic improvement. | Use `plt.hist()`, `plt.scatter()`, `plt.axhline()` |
| **statsmodels** for formal residual diagnostics | Heavyweight dependency (~40MB) for functions that scipy.stats already provides. OLS residual analysis is irrelevant for XGBoost (no linearity assumption). | Use `scipy.stats.probplot()` and `scipy.stats.describe()` |
| **XGBoost 3.2.0** (released Feb 10, 2026) | Released yesterday. Key changes are multi-target vector leaf trees, external memory improvements, and pandas 3.0 compatibility -- none relevant to this project. Risk of day-one bugs in a critical dependency. | Stay on XGBoost 3.1.3 until 3.2.x stabilizes |
| **pandas 3.0.0** | Breaking changes (Copy-on-Write default, string dtype). The entire pipeline was built and validated against 2.3.3. Upgrading introduces risk with zero benefit for v1.1. | Keep pandas 2.3.3 |
| **Polars** for faster baseline computation | Baseline ETA computation involves small lookup tables (historical_segments has ~5K rows, historical_dwells ~3K). pandas handles this in milliseconds. Polars adds a learning curve for zero performance gain. | Stay on pandas |
| **Custom XGBoost objective** for residual-aware loss | Custom gradient/hessian functions are error-prone and hard to debug. `reg:squarederror` is the correct starting point for zero-centered residuals. | Start with `reg:squarederror`, evaluate bias, only then consider custom |
| **New evaluation metrics library** | scikit-learn 1.8.0 provides `mean_absolute_error`, `mean_squared_error`, `r2_score`, and `mean_pinball_loss` -- everything needed for both residual-space and reconstructed-space evaluation. | Use existing scikit-learn metrics |

## Installation

No new installations required. The v1.0 `requirements-xgboost.txt` remains valid:

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

scipy is included transitively via scikit-learn. If you want to make it explicit (recommended for reproducibility):

```
# Optional: make scipy explicit since v1.1 uses it directly for diagnostics
scipy>=1.14.0
```

## Version Compatibility

No changes from v1.0. All versions remain compatible:

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| xgboost 3.1.3 | Python 3.10-3.13, numpy >=1.22 | Tested with scikit-learn 1.8 |
| pandas 2.3.3 | Python 3.10-3.14, numpy >=1.22 | Works with pyarrow >=10.0 |
| scikit-learn 1.8.0 | Python 3.11-3.14, numpy >=1.21 | Brings scipy as dependency |
| optuna 4.7.0 | Python 3.9+ | New study name for v1.1 tuning |
| scipy >=1.14 | Python 3.10+ | Already installed via scikit-learn |

## Integration Points with Existing Scripts

The residual approach modifies existing scripts, not the stack. Here is how each script interacts with the unchanged stack:

| Script | Stack Interaction | What Changes (Code, Not Stack) |
|--------|-------------------|-------------------------------|
| `build_differentiator_features.py` | pandas, numpy, pyarrow | Add baseline ETA computation and residual label column to output parquets |
| `train_baseline.py` / `train_differentiator.py` | xgboost, numpy | Change `y_train` from `time_to_arrival_seconds` to `residual`; keep same DMatrix creation |
| `run_optuna_batches.py` / `train_advanced.py` | optuna, xgboost | New study name; same Optuna API; same XGBoostPruningCallback |
| `evaluate.py` | xgboost, numpy, matplotlib, shap | Add reconstruction step (`baseline_eta + predicted_residual`); evaluate in both residual-space and real-space |

## Sources

- [XGBoost 3.2.0 release notes](https://xgboost.readthedocs.io/en/latest/changes/v3.2.0.html) -- verified 3.2.0 released Feb 9, 2026; confirmed not needed for this project (HIGH confidence)
- [XGBoost 3.1.3 on PyPI](https://pypi.org/project/xgboost/) -- version verification (HIGH confidence)
- [SciPy 1.17.0 on PyPI](https://pypi.org/project/SciPy/) -- latest stable, already installed as scikit-learn dep (HIGH confidence)
- [scipy.stats.normaltest docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.normaltest.html) -- residual normality testing API (HIGH confidence)
- [scipy.stats.probplot docs](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.probplot.html) -- QQ plot API (HIGH confidence)
- [XGBoost parameters documentation](https://xgboost.readthedocs.io/en/stable/parameter.html) -- base_score auto-computation, reg:squarederror objective (HIGH confidence)
- [pandas groupby documentation](https://pandas.pydata.org/docs/user_guide/groupby.html) -- groupby aggregation for baseline computation (HIGH confidence)
- Existing codebase: `build_differentiator_features.py`, `historical_segments.parquet`, `historical_dwells.parquet` -- verified data assets exist and contain needed fields (HIGH confidence, direct inspection)

---
*Stack research for: v1.1 Residual-based ETA prediction (Tiger Transit)*
*Researched: 2026-02-11*
