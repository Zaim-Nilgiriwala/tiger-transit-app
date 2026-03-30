# Phase 9: Evaluation and Comparison - Research

**Researched:** 2026-02-17
**Domain:** XGBoost model evaluation, HTML report generation, SHAP analysis, matplotlib visualization
**Confidence:** HIGH

## Summary

This phase builds a single evaluation script (`scripts/evaluate_v1_1.py`) that produces a comprehensive HTML report comparing v1.0 (123.1s MAE) vs v1.1 (94.6s MAE), with per-route breakdowns, SHAP feature importance, and residual diagnostics. The output goes to `reports/`.

The project already has a working evaluation pipeline (`scripts/evaluate.py`) from Phase 6 that handles v1.0. The new script follows the same patterns but targets the v1.1 residual model and produces HTML instead of markdown/JSON. All required libraries (xgboost 3.1.3, matplotlib 3.10.8, scipy 1.15.3, shap 0.46.0, pandas 2.3.3, numpy 2.2.6, jinja2 3.1.6) are already installed. Seaborn is NOT installed and should not be added -- matplotlib alone is sufficient.

**CRITICAL DATA SYNC ISSUE:** The current `build_baselines.py` implements a 4D tiered fallback (elapsed+segment+is_stopped+on_time_bin) that was written AFTER the v1.1 model was trained on a progress-decile baseline. The featured_v2 parquets were rebuilt with the new baselines at 21:16, but the model was trained at 18:40 on the old baselines. Live prediction yields 103.4s MAE instead of the documented 94.6s. The evaluation script must handle this by either: (a) using saved metrics from `v1_1_metrics.json` for headline numbers, or (b) retraining the model first (out of Phase 9 scope). Recommendation: use saved metrics for the headline comparison, run live predictions only for SHAP analysis.

**Primary recommendation:** Build a standalone `scripts/evaluate_v1_1.py` that loads both models, uses saved per-route metrics from JSON files for the comparison table, runs live SHAP analysis via `pred_contribs`, computes residual diagnostics from live v1.1 predictions, and generates a self-contained HTML report with base64-embedded matplotlib charts.

## Standard Stack

The established libraries/tools for this domain:

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| xgboost | 3.1.3 | Model loading, pred_contribs SHAP | Already installed, both models saved as .ubj |
| matplotlib | 3.10.8 | All visualization (bar charts, histograms, line charts) | Already installed, used throughout project |
| numpy | 2.2.6 | Metric computation (MAE, RMSE, percentiles) | Already installed, core dependency |
| pandas | 2.3.3 | Data loading, groupby operations | Already installed, parquet I/O |
| scipy | 1.15.3 | `scipy.stats.skew()`, `scipy.stats.kurtosis()` for residual diagnostics | Already installed |
| jinja2 | 3.1.6 | HTML templating (optional -- string formatting also works) | Already installed |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| shap | 0.46.0 | Only if TreeExplainer fallback needed | pred_contribs is preferred, shap only for Explanation wrapper |
| base64 | stdlib | Embedding PNG charts in HTML | Every chart embed |
| io | stdlib | BytesIO for in-memory PNG buffers | Every chart embed |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| matplotlib | seaborn | NOT INSTALLED -- do not add. matplotlib is sufficient |
| jinja2 | f-strings | f-strings are simpler for a single-file template; jinja2 better for complex templates |
| SHAP TreeExplainer | pred_contribs | pred_contribs is faster and already validated in this project |

**Installation:**
```bash
# No new packages needed -- all already installed
```

## Architecture Patterns

### Recommended Project Structure
```
scripts/
  evaluate_v1_1.py       # New Phase 9 evaluation script
reports/
  v1_1_evaluation.html   # Self-contained HTML report (output)
models/
  tuned_v1.ubj           # v1.0 model (43 features, existing)
  tuned_metrics.json      # v1.0 metrics (existing)
  v1_1_residual.ubj      # v1.1 model (45 features, existing)
  v1_1_metrics.json       # v1.1 metrics (existing)
  evaluation/
    eval_metrics_sliced.json  # v1.0 sliced metrics (existing)
    eval_shap_meta.json       # v1.0 SHAP metadata (existing)
```

### Pattern 1: Base64 Image Embedding for Self-Contained HTML
**What:** Save matplotlib figures to in-memory BytesIO buffers, base64-encode them, and embed directly in HTML img tags. No external image files needed.
**When to use:** Always, for every chart in the HTML report.
**Example:**
```python
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def fig_to_base64(fig, dpi=150):
    """Convert matplotlib figure to base64-encoded PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    plt.close(fig)
    return b64

# Usage in HTML:
# <img src="data:image/png;base64,{b64_string}" />
```

### Pattern 2: Dual-Model Feature Set Handling
**What:** v1.0 has 43 features (includes `lateness_now`), v1.1 has 45 features (no `lateness_now`, adds 3 baseline features). The evaluation script must construct the correct DMatrix for each model.
**When to use:** When loading models for SHAP analysis.
**Example:**
```python
# v1.0 feature list (43 features)
V1_0_FEATURES = PHASE3_FEATURES_WITH_LATENESS + PHASE4_FEATURES  # 15 + 28 = 43
# lateness_now is always 0 -- add it as a column
df["lateness_now"] = 0.0

# v1.1 feature list (45 features)
V1_1_FEATURES = FEATURE_COLS_V2  # 14 + 28 + 3 = 45
# Import from build_differentiator_features

# v1.0 model
bst_v1_0 = xgb.Booster()
bst_v1_0.load_model("models/tuned_v1.ubj")
dtest_v1_0 = xgb.DMatrix(df[V1_0_FEATURES], enable_categorical=True)
# Use iteration_range=(0, 2159) for v1.0

# v1.1 model
bst_v1_1 = xgb.Booster()
bst_v1_1.load_model("models/v1_1_residual.ubj")
dtest_v1_1 = xgb.DMatrix(df[V1_1_FEATURES], enable_categorical=True)
# v1.1 has 274 rounds, no iteration_range needed
```

### Pattern 3: pred_contribs for SHAP (Both Models)
**What:** Use XGBoost's native `pred_contribs=True` to get SHAP values. Returns array of shape (n_samples, n_features+1) where the last column is the bias term.
**When to use:** For all SHAP analysis (global importance bar charts).
**Example:**
```python
# Subsample for speed
SHAP_N = 2000
rng = np.random.RandomState(42)
idx = rng.choice(len(X), size=min(SHAP_N, len(X)), replace=False)
idx.sort()

dsample = xgb.DMatrix(X.iloc[idx], enable_categorical=True)
contribs = bst.predict(dsample, pred_contribs=True)
shap_vals = contribs[:, :-1]  # Drop bias column

# Global importance = mean |SHAP| per feature
mean_abs_shap = np.mean(np.abs(shap_vals), axis=0)
top_15_idx = np.argsort(mean_abs_shap)[::-1][:15]
```

### Pattern 4: Metric Comparison from Saved JSON
**What:** Load per-route MAE/RMSE from existing metrics JSONs rather than re-computing live predictions. Both models have complete per-route metrics saved.
**When to use:** For the per-route comparison table (EVAL-04 requirement). Live predictions would give wrong numbers for v1.1 due to data sync issue.
**Example:**
```python
import json

with open("models/tuned_metrics.json") as f:
    v1_0_metrics = json.load(f)
with open("models/v1_1_metrics.json") as f:
    v1_1_metrics = json.load(f)

# Per-route comparison
for route_id in sorted(v1_0_metrics["per_route"].keys(), key=int):
    v1_0_mae = v1_0_metrics["per_route"][route_id]["mae"]
    v1_1_mae = v1_1_metrics["per_route"][route_id]["reconstructed_mae"]
    delta = v1_0_mae - v1_1_mae
    pct = delta / v1_0_mae * 100
```

### Pattern 5: Residual Diagnostics with scipy.stats
**What:** Compute skewness and kurtosis of the residual distribution using scipy.stats.
**When to use:** For the residual diagnostics section.
**Example:**
```python
from scipy.stats import skew, kurtosis

residuals = y_pred - y_actual  # or predicted_residual values
stats = {
    "mean": float(np.mean(residuals)),
    "std": float(np.std(residuals)),
    "skew": float(skew(residuals, nan_policy="omit")),
    "kurtosis": float(kurtosis(residuals, fisher=True, nan_policy="omit")),
}
```

### Anti-Patterns to Avoid
- **Re-computing v1.0 predictions:** The tuned_v1.ubj model was trained on a different version of the feature pipeline. The saved metrics in tuned_metrics.json are authoritative.
- **Using seaborn:** Not installed, don't add it. matplotlib handles everything needed.
- **Saving separate image files:** Embed everything in HTML as base64. The `reports/` directory should contain only the HTML file.
- **Ignoring the data sync issue:** Don't present live-computed v1.1 MAE (103.4s) as the official number. Use the 94.6s from the metrics JSON.

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SHAP values | Custom feature importance | `bst.predict(dm, pred_contribs=True)` | Native XGBoost SHAP, fast and exact |
| Skewness/kurtosis | Manual moment calculations | `scipy.stats.skew()`, `scipy.stats.kurtosis()` | Handles NaN, bias correction, well-tested |
| HTML templating | Manual string concatenation | f-strings with a template string | Simple enough for one file; jinja2 available if needed |
| Image embedding | Saving PNGs + linking | base64 encoding in BytesIO | Self-contained HTML, no external file dependencies |
| Per-route metrics | Re-running model predictions | Loading from saved JSON files | Metrics already computed and saved during training |

**Key insight:** Nearly all evaluation data already exists in saved JSON files. The new script primarily needs to: (1) format existing data into HTML, (2) generate new visualizations, and (3) run SHAP on both models.

## Common Pitfalls

### Pitfall 1: Data Sync Between Model and Baselines
**What goes wrong:** The v1.1 model was trained on progress-decile baselines, but `build_baselines.py` was subsequently rewritten with a 4D tiered approach. The featured_v2 parquets now contain baselines that don't match what the model was trained on, causing reconstruction MAE to be 103.4s instead of 94.6s.
**Why it happens:** build_baselines.py was re-run after training without retraining the model.
**How to avoid:** For headline metrics, use the saved v1_1_metrics.json (94.6s). For SHAP analysis, use live pred_contribs (SHAP explains model behavior, which is still valid). Document the data sync issue in the report.
**Warning signs:** Live-computed MAE doesn't match saved metrics JSON.

### Pitfall 2: v1.0 Feature Set Mismatch
**What goes wrong:** v1.0 (tuned_v1.ubj) expects 43 features including `lateness_now`. The current `FEATURE_COLS_V2` has 45 features without `lateness_now`. Feeding 45 features to the v1.0 model will crash.
**Why it happens:** Feature list was updated for v1.1 (dropped lateness_now, added 3 baselines).
**How to avoid:** Explicitly define `V1_0_FEATURES` list with `lateness_now` included. Add `df["lateness_now"] = 0.0` before building the v1.0 DMatrix.
**Warning signs:** XGBoost error about feature count mismatch.

### Pitfall 3: v1.0 iteration_range
**What goes wrong:** v1.0 model has 2175 boosted rounds but best_iteration was 2158. Using all rounds gives slightly different results than the saved metrics.
**Why it happens:** The model was saved with all rounds, but evaluation used `iteration_range=(0, 2159)`.
**How to avoid:** Always use `iteration_range=(0, best_iteration + 1)` when predicting with v1.0. `best_iteration=2158` from tuned_metrics.json.
**Warning signs:** v1.0 MAE slightly different from 123.08s.

### Pitfall 4: Matplotlib Backend in Script Mode
**What goes wrong:** matplotlib tries to open a display window and crashes in headless environments.
**Why it happens:** Default backend tries to create GUI windows.
**How to avoid:** Set `matplotlib.use("Agg")` BEFORE importing pyplot. This is already done in the existing evaluate.py and should be replicated.
**Warning signs:** `_tkinter.TclError: no display name and no $DISPLAY environment variable`.

### Pitfall 5: Route 27 Sparse Data
**What goes wrong:** Route 27 has only 96 test samples. Small sample sizes make metrics unstable and visual comparisons misleading.
**Why it happens:** Infrequent route with limited data.
**How to avoid:** Flag Route 27 (and any route with <200 samples) with an asterisk/note in the table and narrative. Include in aggregates but call out in highlights.
**Warning signs:** Extremely high or low per-route metrics.

### Pitfall 6: SHAP Feature Name Mismatch
**What goes wrong:** pred_contribs returns raw arrays without feature names. If feature order doesn't match the column list, SHAP importance is attributed to wrong features.
**Why it happens:** DMatrix columns must match exactly what the model was trained with.
**How to avoid:** Always construct DMatrix with columns in the exact feature list order. Verify `contribs.shape[1] == len(features) + 1`.
**Warning signs:** Feature importance ranking looks nonsensical.

## Code Examples

### Complete Chart Embedding Pattern
```python
import io
import base64
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

def fig_to_base64(fig, dpi=150):
    """Convert matplotlib figure to base64 PNG for HTML embedding."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    buf.seek(0)
    b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
    plt.close(fig)
    return b64

def make_grouped_bar_chart(routes, v1_0_maes, v1_1_maes, title):
    """Grouped bar chart: v1.0 vs v1.1 MAE per route."""
    x = np.arange(len(routes))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    bars1 = ax.bar(x - width/2, v1_0_maes, width, label="v1.0", color="#5B8DB8")
    bars2 = ax.bar(x + width/2, v1_1_maes, width, label="v1.1", color="#2D6A4F")

    ax.set_xlabel("Route")
    ax.set_ylabel("MAE (seconds)")
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(routes, rotation=45, ha="right")
    ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    return fig_to_base64(fig)
```

### SHAP Side-by-Side Horizontal Bar Charts
```python
def make_shap_comparison(v1_0_features, v1_0_importance, v1_1_features, v1_1_importance):
    """Side-by-side SHAP importance: v1.0 top 15 vs v1.1 top 15."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))

    # v1.0 (left)
    y_pos = np.arange(len(v1_0_features))
    ax1.barh(y_pos, v1_0_importance, color="#5B8DB8")
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(v1_0_features)
    ax1.invert_yaxis()
    ax1.set_xlabel("Mean |SHAP|")
    ax1.set_title("v1.0 Top 15 Features")

    # v1.1 (right)
    y_pos = np.arange(len(v1_1_features))
    ax2.barh(y_pos, v1_1_importance, color="#2D6A4F")
    ax2.set_yticks(y_pos)
    ax2.set_yticklabels(v1_1_features)
    ax2.invert_yaxis()
    ax2.set_xlabel("Mean |SHAP|")
    ax2.set_title("v1.1 Top 15 Features")

    fig.tight_layout()
    return fig_to_base64(fig)
```

### Residual Histogram with Overlay
```python
from scipy.stats import skew, kurtosis

def make_residual_histogram(predicted_residuals, actual_residuals):
    """Histogram of predicted vs actual residuals with summary stats."""
    fig, ax = plt.subplots(figsize=(12, 6))

    bins = np.linspace(
        min(predicted_residuals.min(), actual_residuals.min()),
        max(predicted_residuals.max(), actual_residuals.max()),
        80
    )

    ax.hist(actual_residuals, bins=bins, alpha=0.5, label="Actual Residuals", color="#5B8DB8")
    ax.hist(predicted_residuals, bins=bins, alpha=0.5, label="Predicted Residuals", color="#2D6A4F")

    ax.axvline(0, color="red", linestyle="--", alpha=0.5, label="Zero")
    ax.set_xlabel("Residual (seconds)")
    ax.set_ylabel("Count")
    ax.set_title("Residual Distribution (v1.1)")
    ax.legend()

    # Summary stats text box
    stats_text = (
        f"Predicted residuals:\n"
        f"  Mean: {predicted_residuals.mean():.1f}s\n"
        f"  Std: {predicted_residuals.std():.1f}s\n"
        f"  Skew: {skew(predicted_residuals):.2f}\n"
        f"  Kurtosis: {kurtosis(predicted_residuals, fisher=True):.2f}"
    )
    ax.text(0.98, 0.95, stats_text, transform=ax.transAxes, fontsize=9,
            verticalalignment="top", horizontalalignment="right",
            bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))

    fig.tight_layout()
    return fig_to_base64(fig)
```

### HTML Report Template Pattern
```python
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>Tiger Transit v1.1 Evaluation Report</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               max-width: 1200px; margin: 0 auto; padding: 20px; color: #333; }}
        h1 {{ color: #1a1a2e; border-bottom: 3px solid #2D6A4F; padding-bottom: 10px; }}
        h2 {{ color: #2D6A4F; margin-top: 40px; }}
        h3 {{ color: #555; }}
        table {{ border-collapse: collapse; width: 100%; margin: 15px 0; }}
        th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: right; }}
        th {{ background-color: #f8f9fa; font-weight: 600; }}
        tr:nth-child(even) {{ background-color: #f8f9fa; }}
        .highlight {{ background-color: #d4edda; font-weight: bold; }}
        .warning {{ background-color: #fff3cd; }}
        .metric-card {{ display: inline-block; padding: 15px 25px; margin: 8px;
                        background: #f8f9fa; border-radius: 8px; border-left: 4px solid #2D6A4F; }}
        .metric-card .value {{ font-size: 28px; font-weight: bold; color: #2D6A4F; }}
        .metric-card .label {{ font-size: 14px; color: #666; }}
        img {{ max-width: 100%; height: auto; margin: 15px 0; }}
        .note {{ background: #e8f4f8; padding: 10px 15px; border-radius: 4px;
                 border-left: 4px solid #5B8DB8; margin: 10px 0; }}
    </style>
</head>
<body>
    <h1>Tiger Transit: v1.1 vs v1.0 Evaluation Report</h1>
    <!-- Content sections inserted here -->
</body>
</html>"""
```

### MAE vs stops_away Line Chart
```python
def make_mae_vs_stops_away(stops_away, abs_errors):
    """Line chart: MAE vs stops_away (individual stops, not bucketed)."""
    import pandas as pd

    df = pd.DataFrame({"stops_away": stops_away, "abs_error": abs_errors})
    grouped = df.groupby("stops_away")["abs_error"].agg(["mean", "count"]).reset_index()
    # Filter to stops_away with enough samples
    grouped = grouped[grouped["count"] >= 50]

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(grouped["stops_away"], grouped["mean"], marker="o", color="#2D6A4F", linewidth=2)
    ax1.set_xlabel("Stops Away")
    ax1.set_ylabel("MAE (seconds)")
    ax1.set_title("v1.1 MAE by Stops Away")
    ax1.grid(alpha=0.3)

    # Secondary axis for sample count
    ax2 = ax1.twinx()
    ax2.bar(grouped["stops_away"], grouped["count"], alpha=0.15, color="gray", label="Sample count")
    ax2.set_ylabel("Sample Count")

    fig.tight_layout()
    return fig_to_base64(fig)
```

### MAE vs Hour Line Chart
```python
def make_mae_vs_hour(hours, abs_errors):
    """Line chart: MAE vs hour of day."""
    import pandas as pd

    df = pd.DataFrame({"hour": hours, "abs_error": abs_errors})
    grouped = df.groupby("hour")["abs_error"].agg(["mean", "count"]).reset_index()
    grouped = grouped[grouped["count"] >= 50]

    fig, ax1 = plt.subplots(figsize=(12, 5))
    ax1.plot(grouped["hour"], grouped["mean"], marker="o", color="#2D6A4F", linewidth=2)
    ax1.set_xlabel("Hour of Day (Central Time)")
    ax1.set_ylabel("MAE (seconds)")
    ax1.set_title("v1.1 MAE by Hour of Day")
    ax1.set_xticks(range(0, 24))
    ax1.grid(alpha=0.3)

    ax2 = ax1.twinx()
    ax2.bar(grouped["hour"], grouped["count"], alpha=0.15, color="gray")
    ax2.set_ylabel("Sample Count")

    fig.tight_layout()
    return fig_to_base64(fig)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| v1.0 raw time_to_arrival_seconds target | v1.1 residual target (actual - baseline_eta) | Phase 8 | Model learns correction, not absolute ETA |
| 43 features (with lateness_now) | 45 features (no lateness_now, +3 baselines) | Phase 8 | lateness_now was zero-variance; baselines now explicit features |
| Squared error loss | Pseudo-Huber loss (slope=78.8) | Phase 8 | More robust to outliers |
| 2158 boosting rounds | 274 boosting rounds | Phase 8 | Smaller model, faster predictions |
| Markdown/JSON evaluation output | HTML with embedded charts | Phase 9 | Self-contained, visual report |

**Deprecated/outdated:**
- `scripts/evaluate.py`: Phase 6 evaluation for v1.0 only. Still works but uses wrong feature list for current featured_v2 data. Not directly reusable for Phase 9.
- `FEATURE_COLS_V2` importing from evaluate.py: The existing evaluate.py imports from build_differentiator_features.py which now has 45 features, but v1.0 needs 43.

## Key Data Available for the Report

### Pre-computed Metrics (from JSON files, authoritative)
| Data Point | Source | Value |
|------------|--------|-------|
| v1.0 overall MAE | tuned_metrics.json | 123.08s |
| v1.0 overall RMSE | tuned_metrics.json | 202.81s |
| v1.0 per-route MAE/RMSE | tuned_metrics.json | 23 routes |
| v1.0 per-route MAE/RMSE/MAPE | eval_metrics_sliced.json | 23 routes |
| v1.0 SHAP top 10 | eval_shap_meta.json | 10 features with mean |SHAP| |
| v1.1 overall MAE | v1_1_metrics.json | 94.58s |
| v1.1 overall RMSE | v1_1_metrics.json | 204.57s |
| v1.1 per-route MAE/RMSE | v1_1_metrics.json | 23 routes |
| v1.1 baseline-only MAE | v1_1_metrics.json comparison | 111.1s (70/30 blend) |
| v1.0 progressive chain | eval_comparison.json | Naive->Baseline->Diff->Tuned |

### Live Computation Needed
| Data Point | Why Live | Notes |
|------------|----------|-------|
| v1.0 SHAP (top 15) | Need mean |SHAP| values, not just ranking | Subsample 2000 rows, pred_contribs |
| v1.1 SHAP (top 15) | Same | Subsample 2000 rows, pred_contribs |
| v1.1 predicted residuals | Residual diagnostics | Live predict on test set |
| v1.1 tail analysis | % of predictions >5min, >10min off | From live predictions |
| v1.1 MAE vs stops_away | Line chart needs per-stop granularity | From live predictions |
| v1.1 MAE vs hour | Line chart needs per-hour granularity | From live predictions |

### Model Loading Details
| Model | File | Features | Rounds | iteration_range |
|-------|------|----------|--------|-----------------|
| v1.0 | models/tuned_v1.ubj | 43 (V1_0_FEATURES) | 2175 (best=2158) | (0, 2159) |
| v1.1 | models/v1_1_residual.ubj | 45 (FEATURE_COLS_V2) | 274 | (0, 274) or default |

## Open Questions

Things that couldn't be fully resolved:

1. **Data sync: Should Phase 9 retrain the model first?**
   - What we know: The model was trained on progress-decile baselines. The current baselines use a 4D tiered approach. Live predictions yield 103.4s instead of 94.6s.
   - What's unclear: Whether the user wants to retrain before evaluating, or use saved metrics.
   - Recommendation: Use saved metrics for headline numbers. Live predictions for SHAP and residual diagnostics. Document the discrepancy in the report. If the user wants true live metrics, a retrain (or baseline rebuild to match the old approach) is needed first, but that's outside Phase 9 scope.

2. **v1.0 SHAP: Recompute or reuse saved data?**
   - What we know: eval_shap_meta.json has the top 10 features with mean |SHAP| values from v1.0. But Phase 9 asks for top 15.
   - What's unclear: Whether to recompute with 15 features or just use the saved 10.
   - Recommendation: Recompute v1.0 SHAP with top 15 for consistency. The model and data are available; it takes ~30 seconds on a 2000-row subsample.

3. **Baseline-only MAE: Which baseline version?**
   - What we know: v1_1_metrics.json reports 111.1s for baseline-only. This was the progress-decile baseline, not the current 4D baseline.
   - What's unclear: Which baseline MAE to report.
   - Recommendation: Use 111.1s from the saved metrics (matches what the model was trained on). Alternatively, compute the current baseline MAE from the parquet data for context.

## Sources

### Primary (HIGH confidence)
- Local codebase inspection: `scripts/evaluate.py`, `scripts/train_advanced.py`, `scripts/build_baselines.py`, `scripts/build_differentiator_features.py`
- Local data verification: `models/tuned_metrics.json`, `models/v1_1_metrics.json`, `models/evaluation/eval_metrics_sliced.json`, `models/evaluation/eval_shap_meta.json`
- Live Python verification: xgboost 3.1.3 `pred_contribs` confirmed working for both models, matplotlib base64 embedding confirmed

### Secondary (MEDIUM confidence)
- [XGBoost Prediction Documentation](https://xgboost.readthedocs.io/en/stable/prediction.html) - pred_contribs API
- [SciPy stats.skew](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.skew.html) - v1.17.0 docs
- [SciPy stats.kurtosis](https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.kurtosis.html) - v1.17.0 docs
- [matplotlib base64 embedding](https://saturncloud.io/blog/converting-matplotlib-png-to-base64-for-viewing-in-html-template/) - community pattern guide

### Tertiary (LOW confidence)
- None needed -- all research based on verified local data and official documentation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All packages verified installed with exact versions
- Architecture: HIGH - Patterns extracted from working codebase (evaluate.py, train_advanced.py)
- Data availability: HIGH - All JSON metrics files verified, per-route data confirmed matching between v1.0 and v1.1
- Data sync issue: HIGH - Verified through live computation (103.4s vs 94.6s), git history confirms timeline
- Pitfalls: HIGH - Each pitfall discovered through direct investigation

**Research date:** 2026-02-17
**Valid until:** 2026-03-17 (stable -- no fast-moving dependencies)
