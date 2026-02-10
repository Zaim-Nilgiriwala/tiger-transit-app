# Phase 6: Evaluation & Analysis - Research

**Researched:** 2026-02-09
**Domain:** ML model evaluation, SHAP explainability, residual analysis, comparison reporting
**Confidence:** HIGH

## Summary

This phase produces a comprehensive evaluation of the tuned XGBoost model (MAE 123.1s, 43 features, XGBoost 3.1.3) through four deliverables: sliced metrics report (EVAL-01), SHAP TreeExplainer analysis with waterfall plots (EVAL-02), comparison table vs naive baseline (EVAL-03), and residual analysis for systematic bias detection (EVAL-04).

Much of the sliced metrics infrastructure already exists in prior training scripts (train_advanced.py, train_asymmetric_quantile.py, train_differentiator.py). The existing helper functions -- `stops_bucket()`, `tod_bucket()`, `distance_bucket()`, `mae()`, `rmse()`, `mape()` -- and the `compute_sliced_metrics()` function can be reused directly. The existing metrics JSONs already contain per-route, per-stops-bucket, per-time-of-day, and per-distance breakdowns. The primary NEW work is: (1) consolidating all sliced metrics into a single comprehensive report with MAPE added to all slices, (2) SHAP TreeExplainer with proper waterfall plots (the existing code only uses `pred_contribs` for global importance, not sample-level explanations), (3) a proper comparison table document, and (4) residual analysis with systematic bias pattern identification.

A critical finding: Python 3.10.2 is installed, which means SHAP must be pinned to version 0.49.1 (the last version supporting Python 3.10; version 0.50.0+ requires Python 3.11+). SHAP 0.49.0 added categorical splits support in the C++ library, which is needed because the project's XGBoost models use native categorical features (route_id, day_of_week, pattern_id). However, there may still be compatibility issues with TreeExplainer on models trained with `enable_categorical=True`. Two approaches exist: (A) use `shap.TreeExplainer` with `feature_perturbation="tree_path_dependent"`, or (B) use XGBoost's native `bst.predict(pred_contribs=True)` and construct `shap.Explanation` objects manually for waterfall plots. Approach B is the safer fallback and matches the existing codebase pattern.

**Primary recommendation:** Build a single `evaluate.py` script that loads the tuned model and test data, produces all four deliverables (sliced metrics JSON, SHAP analysis with waterfall PNGs, comparison markdown table, residual analysis with bias detection), and saves outputs to `models/evaluation/`. Use `shap==0.49.1` for TreeExplainer and waterfall plots, with XGBoost `pred_contribs` as fallback if categorical compatibility fails.

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.1.3 (installed) | Model loading, prediction, native pred_contribs | Already in use; the models are .ubj files loaded as xgb.Booster |
| shap | 0.49.1 (to install) | TreeExplainer, waterfall plots, global importance bar plot | Industry standard for ML explainability; last version supporting Python 3.10 |
| matplotlib | 3.10.8 (installed) | Plot generation, saving PNGs | Already in use throughout project |
| numpy | 2.2.6 (installed) | Metrics computation, residual analysis | Already in use |
| pandas | 2.3.3 (installed) | Data loading, slicing, groupby aggregations | Already in use |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | -- | Loading existing metrics JSONs, saving new reports | All report generation |
| pathlib (stdlib) | -- | Cross-platform path handling | All file I/O |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| shap.TreeExplainer | XGBoost pred_contribs only | pred_contribs gives values but no built-in waterfall plots; need shap.Explanation wrapper anyway |
| shap 0.49.1 | shap 0.50.0 | 0.50.0 requires Python 3.11+; project is Python 3.10.2 |
| Single evaluate.py | Separate scripts per requirement | Single script is cleaner since all 4 requirements share the same data loading |

**Installation:**
```bash
pip install shap==0.49.1
```

## Architecture Patterns

### Recommended Output Structure
```
models/
  evaluation/
    eval_metrics_sliced.json       # EVAL-01: Complete sliced metrics
    eval_shap_global.png           # EVAL-02: Global feature importance bar plot
    eval_shap_waterfall_1.png      # EVAL-02: Sample waterfall (high error)
    eval_shap_waterfall_2.png      # EVAL-02: Sample waterfall (low error)
    eval_shap_waterfall_3.png      # EVAL-02: Sample waterfall (typical)
    eval_comparison.json           # EVAL-03: Comparison table data
    eval_comparison.md             # EVAL-03: Formatted markdown comparison table
    eval_residuals.json            # EVAL-04: Residual analysis data
    eval_residuals_by_route.png    # EVAL-04: Mean residual per route bar chart
    eval_residuals_by_tod.png      # EVAL-04: Mean residual per time-of-day
    eval_report.md                 # Master report summarizing all findings
```

### Pattern 1: Two-Path SHAP Strategy
**What:** Try shap.TreeExplainer first; if it fails with categorical features, fall back to XGBoost native pred_contribs + manual shap.Explanation construction.
**When to use:** Always, because SHAP categorical support in v0.49 may not be fully compatible with XGBoost 3.1.3 native categoricals.
**Example:**
```python
# Source: SHAP docs + XGBoost docs
import shap
import xgboost as xgb
import numpy as np

bst = xgb.Booster()
bst.load_model("models/tuned_v1.ubj")
dtest = xgb.DMatrix(X_test, enable_categorical=True)

# Approach A: Try shap.TreeExplainer directly
try:
    explainer = shap.TreeExplainer(
        bst,
        feature_perturbation="tree_path_dependent"
    )
    shap_values_obj = explainer(X_test)
    print("TreeExplainer succeeded with categorical model")
except Exception as e:
    print(f"TreeExplainer failed: {e}, using pred_contribs fallback")
    # Approach B: Fallback to XGBoost native + manual Explanation
    contribs = bst.predict(dtest, pred_contribs=True,
                           iteration_range=(0, bst.best_iteration + 1))
    shap_vals = contribs[:, :-1]  # (n_samples, n_features)
    base_val = contribs[0, -1]    # bias term (same for all samples)
    shap_values_obj = shap.Explanation(
        values=shap_vals,
        base_values=np.full(len(shap_vals), base_val),
        data=X_test.values if hasattr(X_test, 'values') else X_test,
        feature_names=FEATURE_COLS_V2,
    )

# Now both paths produce a shap.Explanation object usable for plots
shap.plots.waterfall(shap_values_obj[idx], show=False)
plt.tight_layout()
plt.savefig("models/evaluation/eval_shap_waterfall_1.png", dpi=150, bbox_inches="tight")
plt.close()
```

### Pattern 2: Strategic Sample Selection for Waterfall Plots
**What:** Select 3+ samples that illustrate different model behaviors for waterfall explanations.
**When to use:** EVAL-02 requires "at least 3 sample-level waterfall explanations showing sensible feature contributions."
**Example:**
```python
# Compute absolute errors
abs_errors = np.abs(y_test - y_pred)

# Select representative samples:
# 1. High error prediction (worst 5th percentile) -- shows where model struggles
idx_high_err = np.argsort(abs_errors)[-int(len(abs_errors) * 0.05)]

# 2. Low error prediction (best 5th percentile) -- shows model at its best
idx_low_err = np.argsort(abs_errors)[int(len(abs_errors) * 0.05)]

# 3. Typical prediction (closest to median error) -- shows average behavior
median_err = np.median(abs_errors)
idx_typical = np.argmin(np.abs(abs_errors - median_err))

# Optionally: 4. High stops_away, 5. Near-arrival (stops_away=1)
selected_indices = [idx_high_err, idx_low_err, idx_typical]
```

### Pattern 3: Residual Bias Detection via Signed Mean Residual
**What:** Compute mean signed residual (not absolute) per slice to detect systematic over/under-prediction.
**When to use:** EVAL-04 requires identifying "routes where model consistently over/under-predicts."
**Example:**
```python
residuals = y_pred - y_test  # positive = overprediction

# Per-route signed mean residual
for rid in unique_routes:
    mask = test_route_ids == rid
    mean_res = np.mean(residuals[mask])
    median_res = np.median(residuals[mask])
    pct_over = np.mean(residuals[mask] > 0) * 100
    # Flag bias: mean residual > 15s (roughly 10% of overall MAE)
    bias_flag = "OVER" if mean_res > 15 else ("UNDER" if mean_res < -15 else "OK")
```

### Anti-Patterns to Avoid
- **Using only absolute metrics for bias detection:** MAE/RMSE hide directional bias. Must use signed residuals to find systematic over/under-prediction.
- **Computing SHAP on entire test set:** With 296K rows, computing SHAP for all samples is wasteful and slow. Use full test set only for `pred_contribs` (fast in XGBoost native) and TreeExplainer on a subsample if needed.
- **Hardcoding metric values from prior phases:** Always load from JSON files (baseline_metrics.json, differentiator_metrics.json, tuned_metrics.json) to avoid stale values.
- **Ignoring sample size in sliced metrics:** Route 27 has only 96 test samples; metrics on small slices should be flagged with sample count.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHAP waterfall plots | Custom matplotlib bar charts | `shap.plots.waterfall()` | Standard visualization, shows base value + cumulative contributions correctly |
| Global feature importance | Custom mean-abs-SHAP bar chart | `shap.plots.bar()` or existing `pred_contribs` approach | Consistent styling, handles feature name display |
| SHAP value computation | Manual tree traversal | XGBoost `pred_contribs=True` or `shap.TreeExplainer` | Exact tree SHAP in C++, handles categorical splits |
| Sliced metric aggregation | New helper functions | Reuse `stops_bucket()`, `tod_bucket()`, `distance_bucket()`, `mae()`, `rmse()`, `mape()` from existing scripts | Already tested in prior phases |
| Markdown table formatting | Manual string concatenation | Python f-strings with alignment | Readable, maintainable |

**Key insight:** The existing codebase already has 90% of the metrics infrastructure. The evaluation script should import from `build_differentiator_features` for data loading and feature definitions, and adapt the slicing patterns from `train_advanced.py`.

## Common Pitfalls

### Pitfall 1: SHAP TreeExplainer Fails on Categorical XGBoost Models
**What goes wrong:** `shap.TreeExplainer(bst)` raises an error because XGBoost models trained with `enable_categorical=True` use JSON/UBJSON serialization, and SHAP's internal model loader historically expected binary format.
**Why it happens:** SHAP 0.49 added C++ categorical support but it may not fully work with XGBoost 3.1.3's categorical encoding in UBJSON format.
**How to avoid:** Use the two-path strategy (Pattern 1 above). Try TreeExplainer first, fall back to `pred_contribs` + manual `shap.Explanation` construction.
**Warning signs:** `Exception: XGBoost model is not supported` or serialization errors on `shap.TreeExplainer()`.

### Pitfall 2: Distance Bucket Shows Only "<1km" (Data Issue)
**What goes wrong:** The tuned_metrics.json already shows `per_distance` has only one bucket: `"<1km": {n: 296608}`. This means ALL 296K test samples have `distance_to_target < 1000m`.
**Why it happens:** The feature `distance_to_target` is computed as `(target_stop_progress - progress) * max_shape_dist`. Since max_shape_dist is in shape_dist_traveled units (not meters directly), the actual distance values may be small, or the feature is already normalized.
**How to avoid:** Investigate the actual distribution of `distance_to_target` values. If all values are indeed < 1km, the distance bucket slicing is not informative. Use `stops_away` as the primary distance proxy instead, or adjust bucket thresholds to match actual data distribution.
**Warning signs:** All test samples falling into a single bucket.

### Pitfall 3: MAPE on Zero/Near-Zero Targets
**What goes wrong:** MAPE is undefined when `y_true == 0` and inflated for very small `y_true` values.
**Why it happens:** Division by `y_true` in the MAPE formula. Existing code already filters `y_true > 0`.
**How to avoid:** Always mask `y_true > 0` for MAPE (existing pattern). Report the percentage of excluded samples. For slices with many near-zero targets (e.g., stops_away=1), MAPE will be inflated; note this in the report.
**Warning signs:** MAPE > 100% for any slice.

### Pitfall 4: Confusing pred_contribs Bias Term with Base Value
**What goes wrong:** XGBoost `pred_contribs=True` returns a matrix of shape `(n_samples, n_features + 1)`. The last column is the bias term (base value), not a feature contribution. If included as a feature contribution, the global importance ranking is wrong.
**Why it happens:** Easy to forget to slice off the last column.
**How to avoid:** Always use `contribs[:, :-1]` for SHAP values and `contribs[0, -1]` for base value. The existing codebase already does this correctly.
**Warning signs:** An "extra" feature with very high mean absolute SHAP value.

### Pitfall 5: Comparing Models Trained on Different Subsamples
**What goes wrong:** Asymmetric and quantile models were trained on 25% subsample (`training_subsample_frac: 0.25`), while the tuned model was trained on full data. Direct MAE comparison may be slightly unfair.
**Why it happens:** Phase 5 used subsampling for speed.
**How to avoid:** Document the training subsample fractions in the comparison table. The tuned model (full data) is the primary model for evaluation; asymmetric/quantile are supplementary analyses.
**Warning signs:** Asymmetric model MAE (126.5s) higher than tuned (123.1s) partly due to subsampling.

### Pitfall 6: SHAP Waterfall Plot show=False + Agg Backend
**What goes wrong:** SHAP waterfall plots may not render correctly with the Agg backend or may error on `plt.show()`.
**Why it happens:** SHAP's plotting code sometimes assumes interactive display.
**How to avoid:** Always use `matplotlib.use("Agg")` before importing shap. Always call `shap.plots.waterfall(..., show=False)` then `plt.savefig()` then `plt.close()`. Never call `plt.show()` in headless mode.
**Warning signs:** Blank PNG files or runtime errors from matplotlib.

## Code Examples

### Loading the Best Model and Test Data
```python
# Source: Existing pattern from train_advanced.py
import sys
from pathlib import Path
import numpy as np
import xgboost as xgb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_differentiator_features import (
    FEATURE_COLS_V2, CATEGORICAL_COLS_V2, TARGET_COL, load_featured_v2,
)

MODELS_DIR = Path("models")
EVAL_DIR = MODELS_DIR / "evaluation"

# Load test data
df_test = load_featured_v2("test")
X_test = df_test[FEATURE_COLS_V2].copy()
y_test = df_test[TARGET_COL].values

# Test metadata for slicing
test_route_ids = df_test["route_id"].astype(int).values
test_stops_away = df_test["stops_away"].values
test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)
test_distances = df_test["distance_to_target"].values.astype(float)
test_minutes = df_test["minutes_since_midnight"].values
test_hour_ct = (test_minutes // 60).astype(int)

# Load tuned model
bst = xgb.Booster()
bst.load_model(str(MODELS_DIR / "tuned_v1.ubj"))
dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)
y_pred = bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))
```

### SHAP TreeExplainer with Fallback (EVAL-02)
```python
# Source: SHAP 0.49.1 docs + XGBoost pred_contribs docs
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import shap

# Two-path SHAP strategy
try:
    explainer = shap.TreeExplainer(bst, feature_perturbation="tree_path_dependent")
    # Subsample for TreeExplainer (296K rows is too many)
    sample_idx = np.random.RandomState(42).choice(len(X_test), size=1000, replace=False)
    X_sample = X_test.iloc[sample_idx]
    shap_values_obj = explainer(X_sample)
except Exception as e:
    print(f"TreeExplainer failed ({e}), using pred_contribs fallback")
    contribs = bst.predict(dtest, pred_contribs=True,
                           iteration_range=(0, bst.best_iteration + 1))
    shap_vals = contribs[:, :-1]
    base_val = float(contribs[0, -1])
    shap_values_obj = shap.Explanation(
        values=shap_vals,
        base_values=np.full(len(shap_vals), base_val),
        data=X_test.values,
        feature_names=list(FEATURE_COLS_V2),
    )

# Global importance bar plot
shap.plots.bar(shap_values_obj, show=False)
plt.tight_layout()
plt.savefig(EVAL_DIR / "eval_shap_global.png", dpi=150, bbox_inches="tight")
plt.close()

# Waterfall plots for selected samples
for i, (idx, label) in enumerate(zip(selected_indices, labels)):
    shap.plots.waterfall(shap_values_obj[idx], show=False)
    plt.tight_layout()
    plt.savefig(EVAL_DIR / f"eval_shap_waterfall_{i+1}.png",
                dpi=150, bbox_inches="tight")
    plt.close()
```

### Comprehensive Sliced Metrics (EVAL-01)
```python
# Source: Pattern from train_advanced.py, extended with MAPE
def compute_full_sliced_metrics(y_true, y_pred, route_ids, stops_away,
                                 hour_ct, distances, scheduled):
    """Compute comprehensive sliced metrics including MAPE."""
    results = {"overall": {
        "mae": round(mae(y_true, y_pred), 2),
        "rmse": round(rmse(y_true, y_pred), 2),
        "mape": round(mape(y_true, y_pred), 2),
        "n": len(y_true),
    }}

    # Per-route
    results["per_route"] = {}
    for rid in sorted(set(route_ids)):
        m = route_ids == rid
        results["per_route"][str(rid)] = {
            "mae": round(mae(y_true[m], y_pred[m]), 2),
            "rmse": round(rmse(y_true[m], y_pred[m]), 2),
            "mape": round(mape(y_true[m], y_pred[m]), 2),
            "n": int(m.sum()),
        }

    # Per stops_away bucket, per time-of-day, per distance
    # (same pattern with bucket functions)
    return results
```

### Residual Bias Detection (EVAL-04)
```python
# Source: Standard residual analysis pattern
residuals = y_pred - y_test  # positive = model overpredicts (bus arrives sooner)

# Overall residual distribution
residual_stats = {
    "mean": round(float(np.mean(residuals)), 2),
    "median": round(float(np.median(residuals)), 2),
    "std": round(float(np.std(residuals)), 2),
    "pct_overprediction": round(float(np.mean(residuals > 0) * 100), 2),
    "percentiles": {
        "p5": round(float(np.percentile(residuals, 5)), 2),
        "p25": round(float(np.percentile(residuals, 25)), 2),
        "p50": round(float(np.percentile(residuals, 50)), 2),
        "p75": round(float(np.percentile(residuals, 75)), 2),
        "p95": round(float(np.percentile(residuals, 95)), 2),
    },
}

# Per-route bias detection
BIAS_THRESHOLD = 15.0  # seconds, ~12% of overall MAE
route_biases = {}
for rid in sorted(set(test_route_ids)):
    m = test_route_ids == rid
    mean_res = float(np.mean(residuals[m]))
    route_biases[str(rid)] = {
        "mean_residual": round(mean_res, 2),
        "median_residual": round(float(np.median(residuals[m])), 2),
        "pct_overprediction": round(float(np.mean(residuals[m] > 0) * 100), 2),
        "n": int(m.sum()),
        "bias": "OVER" if mean_res > BIAS_THRESHOLD else
                "UNDER" if mean_res < -BIAS_THRESHOLD else "OK",
    }
```

### Comparison Table Generation (EVAL-03)
```python
# Source: Pattern from existing phase5_comparison.json structure
import json

# Load all phase metrics from existing JSON files
metrics_sources = {
    "Naive (schedule)": {"mae": 708.91, "rmse": 883.41},
}
for name, path in [
    ("Baseline (P3)", "baseline_metrics.json"),
    ("Differentiator (P4)", "differentiator_metrics.json"),
    ("Tuned (P5)", "tuned_metrics.json"),
]:
    with open(MODELS_DIR / path) as f:
        data = json.load(f)
    metrics_sources[name] = data["xgboost"]

# Build comparison table with overall and per-route
comparison = {"overall": [], "per_route": {}}
for name, m in metrics_sources.items():
    entry = {
        "model": name,
        "mae": m["mae"],
        "rmse": m["rmse"],
        "vs_naive_pct": round((708.91 - m["mae"]) / 708.91 * 100, 2),
    }
    if m["mae"] < 708.91:
        entry["wins_vs_naive"] = True
    comparison["overall"].append(entry)

# Per-route: identify where XGBoost wins/loses vs naive
naive_per_route = {}  # Compute naive MAE per route from test_scheduled
for rid in sorted(set(test_route_ids)):
    m = test_route_ids == rid
    naive_per_route[str(rid)] = round(mae(y_test[m], test_scheduled[m]), 2)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| XGBoost `pred_contribs` for global importance only | SHAP TreeExplainer + waterfall plots for sample-level | SHAP 0.40+ (2022) | Richer explainability with visual per-prediction explanations |
| Manual bar charts for SHAP | `shap.plots.bar()` and `shap.plots.waterfall()` | SHAP 0.40+ (2022) | Standardized, publication-quality visualizations |
| SHAP incompatible with XGBoost categoricals | SHAP 0.49.0 adds C++ categorical splits | Oct 2025 | May now work with enable_categorical models |
| SHAP required Python 3.9+ | SHAP 0.50.0 requires Python 3.11+ | Nov 2025 | Must pin to 0.49.1 on Python 3.10 |

**Deprecated/outdated:**
- `shap.summary_plot()` and `shap.force_plot()` legacy APIs -- use `shap.plots.bar()`, `shap.plots.waterfall()`, `shap.plots.beeswarm()` instead (new API since 0.40)
- `shap.TreeExplainer(model, feature_dependence=...)` parameter -- renamed to `feature_perturbation` (deprecated parameter removed in 0.45+)

## Open Questions

1. **Whether shap.TreeExplainer works with XGBoost 3.1.3 + UBJSON categorical models**
   - What we know: SHAP 0.49 added C++ categorical splits support. XGBoost 3.1.3 uses UBJSON for categorical models. The GitHub issue #2662 was about this incompatibility.
   - What's unclear: Whether 0.49's fix fully resolves the issue for XGBoost 3.1.3 specifically.
   - Recommendation: Implement the two-path strategy (try TreeExplainer, fall back to pred_contribs + manual Explanation). The fallback is robust and produces identical SHAP values.

2. **Distance bucket granularity**
   - What we know: All 296K test samples show `distance_to_target < 1000m` in the existing metrics. This makes the distance bucket slice useless as currently configured.
   - What's unclear: Whether the raw feature values are actually all < 1km or if the bucket thresholds are wrong for the data distribution.
   - Recommendation: During evaluation, examine `df_test["distance_to_target"].describe()` and adjust bucket thresholds to produce at least 3-4 meaningful buckets. Use quantile-based thresholds if the existing fixed thresholds don't work.

3. **Best iteration for tuned model**
   - What we know: tuned_metrics.json says `best_iteration: 2158`. The model is loaded as a Booster and needs `iteration_range=(0, bst.best_iteration + 1)` for correct prediction.
   - What's unclear: Whether `bst.best_iteration` is correctly restored when loading from .ubj file.
   - Recommendation: After loading, verify `bst.best_iteration` matches 2158. If not, load the value from tuned_metrics.json and use it explicitly.

## Sources

### Primary (HIGH confidence)
- [SHAP official documentation - TreeExplainer](https://shap.readthedocs.io/en/latest/generated/shap.TreeExplainer.html) -- API parameters, feature_perturbation options, model type support
- [SHAP official documentation - Explanation class](https://shap.readthedocs.io/en/latest/generated/shap.Explanation.html) -- Constructor signature for manual Explanation creation
- [SHAP official documentation - waterfall plot](https://shap.readthedocs.io/en/latest/generated/shap.plots.waterfall.html) -- Parameters: shap_values, max_display, show
- [SHAP official documentation - XGBoost front page example](https://shap.readthedocs.io/en/latest/example_notebooks/tabular_examples/tree_based_models/Front%20page%20example%20(XGBoost).html) -- Complete workflow: explainer(X), waterfall, bar plots
- [SHAP Release Notes](https://shap.readthedocs.io/en/latest/release_notes.html) -- v0.49.0 categorical splits, v0.50.0 Python 3.11+ requirement
- [SHAP PyPI](https://pypi.org/project/shap/) -- v0.50.0 latest; v0.49.1 last for Python 3.10
- [XGBoost prediction documentation](https://xgboost.readthedocs.io/en/stable/prediction.html) -- pred_contribs output format, iteration_range

### Secondary (MEDIUM confidence)
- [SHAP GitHub Issue #2662](https://github.com/slundberg/shap/issues/2662) -- TreeExplainer + XGBoost categorical features incompatibility, pred_contribs workaround
- [DeepWiki SHAP TreeExplainer](https://deepwiki.com/shap/shap/3.1-treeexplainer) -- Categorical limitations, tree_path_dependent recommendation
- Existing project codebase (train_baseline.py, train_differentiator.py, train_advanced.py) -- Established patterns for pred_contribs, sliced metrics, bucket functions

### Tertiary (LOW confidence)
- General ML evaluation best practices (residual analysis, bias detection) -- based on standard statistical methodology, not verified against specific source

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- All libraries verified (XGBoost 3.1.3 installed, SHAP 0.49.1 confirmed compatible with Python 3.10, matplotlib installed)
- Architecture: HIGH -- Patterns directly derived from existing codebase (scripts/train_*.py) and official SHAP documentation
- SHAP TreeExplainer compatibility: MEDIUM -- 0.49 added categorical support but untested with this specific XGBoost version; fallback strategy mitigates risk
- Pitfalls: HIGH -- Distance bucket issue confirmed from existing metrics JSON; categorical SHAP issue documented in official GitHub issues

**Research date:** 2026-02-09
**Valid until:** 2026-03-11 (stable libraries, 30 days)
