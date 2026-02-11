"""
diagnose_features.py - Feature Distribution Diagnostic Script.

Compares feature distributions for ALL test predictions vs the TOP 10%
highest-error predictions to surface data quality issues, feature computation
bugs, or missing-data patterns that correlate with model failure.

Usage:
    python scripts/diagnose_features.py                  # Full diagnostics
    python scripts/diagnose_features.py --top-pct 0.05   # Top 5% instead of 10%
    python scripts/diagnose_features.py --skip-individual # Skip 43 individual PNGs

Input:
    data/processed/test_featured_v2.parquet
    models/tuned_v1.ubj
    models/tuned_metrics.json

Output (models/diagnostics/):
    diag_summary.md              - Markdown report with rankings, NaN tables, flags
    diag_feature_stats.json      - Full per-feature stats (overall + high-error)
    diag_ranking.json            - Features ranked by distribution shift score
    feat_<name>.png (x43)        - Per-feature distribution comparison plot
    diag_grid_<group>.png (x6)   - Feature group mini-histogram grids
    diag_nan_comparison.png      - NaN rate overall vs high-error
    diag_top6_scatter.png        - Error vs feature value for top-6 shifted features
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Headless rendering -- must be set BEFORE any matplotlib imports
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import numpy as np
import pandas as pd
import xgboost as xgb
from scipy import stats

# ---------------------------------------------------------------------------
# Add scripts/ to path so we can import from build_differentiator_features
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_differentiator_features import (
    FEATURE_COLS_V2,
    CATEGORICAL_COLS_V2,
    TARGET_COL,
    load_featured_v2,
    PHASE3_FEATURE_COLS,
    PHASE4_FEATURE_COLS,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODELS_DIR = Path("models")
DIAG_DIR = MODELS_DIR / "diagnostics"
DPI = 150
TOP_ERROR_PCT = 0.10

# Feature groups for organized reporting
FEATURE_GROUPS = {
    "phase_3_baseline": PHASE3_FEATURE_COLS,
    "phase_4_rolling_gps": [
        "gps_speed_mps",
        "speed_mean_30s", "speed_mean_60s", "speed_mean_120s", "speed_mean_180s",
        "speed_std_30s", "speed_std_60s", "speed_std_120s", "speed_std_180s",
        "acceleration", "is_idle_gps", "seconds_idle",
    ],
    "phase_4_timepoint": [
        "is_timepoint", "scheduled_departure_seconds", "timepoints_remaining",
        "time_until_next_timepoint_departure", "timepoint_adherence",
    ],
    "phase_4_historical": [
        "segment_travel_median", "segment_travel_p25", "segment_travel_p75",
    ],
    "phase_4_dwell": [
        "dwell_median", "dwell_p25", "dwell_p75",
        "target_dwell_median", "target_dwell_p25", "target_dwell_p75",
    ],
    "phase_4_speed_temporal": [
        "speed_ratio", "is_rush_hour",
    ],
}

# Binary/low-cardinality features rendered as bar charts
BINARY_FEATURES = {"is_idle", "is_rush_hour", "is_timepoint", "is_idle_gps"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def _safe_float(x):
    """Convert numpy types to Python float for JSON serialization."""
    if isinstance(x, (np.floating, np.integer)):
        return float(x)
    if isinstance(x, float) and (np.isnan(x) or np.isinf(x)):
        return None
    return x


def _sanitize_for_json(obj):
    """Recursively sanitize an object for JSON serialization."""
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        v = float(obj)
        if np.isnan(v) or np.isinf(v):
            return None
        return v
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float):
        if np.isnan(obj) or np.isinf(obj):
            return None
    return obj


# ---------------------------------------------------------------------------
# 1. load_data
# ---------------------------------------------------------------------------


def load_data(top_pct: float = TOP_ERROR_PCT):
    """Load test data, model, compute predictions and error masks.

    Returns:
        dict with df_test, abs_error, high_error_mask, threshold, y_test, y_pred
    """
    print("Loading v2 featured test data...")
    df_test = load_featured_v2("test")
    print(f"  test: {df_test.shape}")

    X_test = df_test[FEATURE_COLS_V2].copy()
    y_test = df_test[TARGET_COL].values

    # Load tuned model
    print("Loading tuned model...")
    bst = xgb.Booster()
    bst.load_model(str(MODELS_DIR / "tuned_v1.ubj"))

    with open(MODELS_DIR / "tuned_metrics.json") as f:
        tuned_metrics = json.load(f)
    best_iter = tuned_metrics["best_iteration"]
    print(f"  best_iteration: {best_iter}")

    # Create DMatrix and predict
    dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)
    y_pred = bst.predict(dtest, iteration_range=(0, best_iter + 1))

    abs_error = np.abs(y_pred - y_test)
    threshold = np.percentile(abs_error, (1 - top_pct) * 100)
    high_error_mask = abs_error >= threshold

    # Bottom 2% mask (top 2% highest error)
    threshold_2pct = np.percentile(abs_error, 98)
    bottom_2pct_mask = abs_error >= threshold_2pct

    overall_mae = mae(y_test, y_pred)
    high_error_mae = mae(y_test[high_error_mask], y_pred[high_error_mask])
    bottom_2pct_mae = mae(y_test[bottom_2pct_mask], y_pred[bottom_2pct_mask])

    print(f"  Predictions: {len(y_pred)}")
    print(f"  Overall MAE: {overall_mae:.1f}s")
    print(f"  Top {top_pct*100:.0f}% error threshold: {threshold:.1f}s")
    print(f"  High-error samples: {high_error_mask.sum()} "
          f"({high_error_mask.mean()*100:.1f}%)")
    print(f"  High-error MAE: {high_error_mae:.1f}s")
    print(f"  Top 2% error threshold: {threshold_2pct:.1f}s")
    print(f"  Bottom-2% samples: {bottom_2pct_mask.sum()} "
          f"({bottom_2pct_mask.mean()*100:.1f}%)")
    print(f"  Bottom-2% MAE: {bottom_2pct_mae:.1f}s")

    return {
        "df_test": df_test,
        "abs_error": abs_error,
        "high_error_mask": high_error_mask,
        "bottom_2pct_mask": bottom_2pct_mask,
        "threshold": threshold,
        "threshold_2pct": threshold_2pct,
        "y_test": y_test,
        "y_pred": y_pred,
        "overall_mae": overall_mae,
        "high_error_mae": high_error_mae,
        "bottom_2pct_mae": bottom_2pct_mae,
        "top_pct": top_pct,
    }


# ---------------------------------------------------------------------------
# 2. compute_feature_stats
# ---------------------------------------------------------------------------


def compute_feature_stats(series: pd.Series, is_categorical: bool = False) -> dict:
    """Compute descriptive stats for a single feature column.

    Args:
        series: Feature values (may contain NaN).
        is_categorical: If True, also compute value_counts.

    Returns:
        dict of stats.
    """
    n = len(series)
    nan_count = int(series.isna().sum())
    nan_pct = nan_count / n * 100 if n > 0 else 0.0
    valid = series.dropna()

    result = {
        "count": n,
        "nan_count": nan_count,
        "nan_pct": round(nan_pct, 2),
    }

    if len(valid) == 0:
        result.update({
            "mean": None, "median": None, "std": None,
            "min": None, "max": None,
            "p5": None, "p25": None, "p75": None, "p95": None,
        })
    else:
        vals = valid.astype(float).values
        result.update({
            "mean": round(float(np.mean(vals)), 4),
            "median": round(float(np.median(vals)), 4),
            "std": round(float(np.std(vals)), 4),
            "min": round(float(np.min(vals)), 4),
            "max": round(float(np.max(vals)), 4),
            "p5": round(float(np.percentile(vals, 5)), 4),
            "p25": round(float(np.percentile(vals, 25)), 4),
            "p75": round(float(np.percentile(vals, 75)), 4),
            "p95": round(float(np.percentile(vals, 95)), 4),
        })

    if is_categorical:
        vc = series.value_counts(dropna=False).head(20)
        result["value_counts"] = {str(k): int(v) for k, v in vc.items()}

    return result


# ---------------------------------------------------------------------------
# 3. compute_shift_metric
# ---------------------------------------------------------------------------


def compute_shift_metric(
    overall: pd.Series,
    high_error: pd.Series,
    is_categorical: bool = False,
) -> dict:
    """Quantify distribution shift between overall and high-error groups.

    Args:
        overall: Feature values for all test samples.
        high_error: Feature values for high-error samples.
        is_categorical: Whether this is a categorical feature.

    Returns:
        dict with ks_stat, ks_pvalue, mean_diff_norm, nan_diff, shift_score, flags.
    """
    result = {
        "ks_stat": None,
        "ks_pvalue": None,
        "mean_diff_norm": None,
        "nan_diff": None,
        "chi2_stat": None,
        "chi2_pvalue": None,
        "js_divergence": None,
        "shift_score": 0.0,
    }

    # NaN rate difference (percentage points)
    nan_overall = overall.isna().mean() * 100
    nan_high = high_error.isna().mean() * 100
    nan_diff = nan_high - nan_overall
    result["nan_diff"] = round(float(nan_diff), 2)

    overall_valid = overall.dropna()
    high_valid = high_error.dropna()

    if is_categorical:
        # Chi-squared test on category frequencies
        try:
            all_cats = set(overall_valid.unique()) | set(high_valid.unique())
            if len(all_cats) > 1:
                vc_o = overall_valid.value_counts()
                vc_h = high_valid.value_counts()
                # Align categories
                all_cats_sorted = sorted(all_cats, key=str)
                freq_o = np.array([vc_o.get(c, 0) for c in all_cats_sorted],
                                  dtype=float)
                freq_h = np.array([vc_h.get(c, 0) for c in all_cats_sorted],
                                  dtype=float)
                # Normalize to proportions
                p_o = freq_o / freq_o.sum() if freq_o.sum() > 0 else freq_o
                p_h = freq_h / freq_h.sum() if freq_h.sum() > 0 else freq_h
                # Jensen-Shannon divergence
                m = 0.5 * (p_o + p_h)
                # Avoid log(0) by adding epsilon
                eps = 1e-10
                js = 0.5 * np.sum(p_o * np.log((p_o + eps) / (m + eps))) + \
                     0.5 * np.sum(p_h * np.log((p_h + eps) / (m + eps)))
                result["js_divergence"] = round(float(js), 6)
                # Chi-squared
                if len(freq_o) > 0 and freq_h.sum() > 0:
                    expected = freq_o * (freq_h.sum() / freq_o.sum())
                    mask = expected > 0
                    if mask.sum() > 1:
                        chi2, pval = stats.chisquare(freq_h[mask], expected[mask])
                        result["chi2_stat"] = round(float(chi2), 4)
                        result["chi2_pvalue"] = float(pval)
                result["shift_score"] = round(
                    float(result["js_divergence"] or 0) * 5.0
                    + abs(nan_diff) * 0.02, 4
                )
        except Exception:
            pass
        return result

    # Numeric features
    if len(overall_valid) < 2 or len(high_valid) < 2:
        return result

    overall_vals = overall_valid.astype(float).values
    high_vals = high_valid.astype(float).values

    # KS statistic
    try:
        ks_stat, ks_pval = stats.ks_2samp(overall_vals, high_vals)
        result["ks_stat"] = round(float(ks_stat), 6)
        result["ks_pvalue"] = float(ks_pval)
    except Exception:
        ks_stat = 0.0

    # Normalized mean difference
    std_overall = float(np.std(overall_vals))
    if std_overall > 1e-10:
        mean_diff_norm = (float(np.mean(high_vals)) - float(np.mean(overall_vals))) \
                         / std_overall
    else:
        mean_diff_norm = 0.0
    result["mean_diff_norm"] = round(float(mean_diff_norm), 4)

    # Composite shift score
    ks = result["ks_stat"] or 0.0
    result["shift_score"] = round(
        ks * 0.5
        + abs(mean_diff_norm) * 0.3
        + abs(nan_diff / 100) * 0.2,
        4,
    )

    return result


# ---------------------------------------------------------------------------
# 4. analyze_all_features
# ---------------------------------------------------------------------------


def analyze_all_features(df_test: pd.DataFrame, high_error_mask: np.ndarray):
    """Analyze all 43 features for distribution shift.

    Returns:
        results: list of dicts (one per feature)
        summary_df: DataFrame sorted by shift_score descending
    """
    results = []

    for feat in FEATURE_COLS_V2:
        is_cat = feat in CATEGORICAL_COLS_V2

        overall = df_test[feat]
        high_error = df_test.loc[high_error_mask, feat]

        stats_overall = compute_feature_stats(overall, is_categorical=is_cat)
        stats_high = compute_feature_stats(high_error, is_categorical=is_cat)
        shift = compute_shift_metric(overall, high_error, is_categorical=is_cat)

        # Generate flags
        flags = []
        if stats_overall["nan_pct"] > 50:
            flags.append("HIGH_NAN_OVERALL")
        if (stats_high["nan_pct"] - stats_overall["nan_pct"]) > 5:
            flags.append("NAN_RATE_SPIKE")
        if shift["mean_diff_norm"] is not None and abs(shift["mean_diff_norm"]) > 0.5:
            flags.append("MEAN_SHIFT")
        if shift["ks_stat"] is not None and shift["ks_stat"] > 0.15:
            flags.append("STRONG_KS")
        if stats_overall["std"] is not None and stats_overall["std"] == 0:
            flags.append("ZERO_VARIANCE")
        if stats_high["std"] is not None and stats_high["std"] == 0:
            flags.append("ZERO_VARIANCE")

        # Deduplicate flags
        flags = sorted(set(flags))

        entry = {
            "feature": feat,
            "is_categorical": is_cat,
            "stats_overall": stats_overall,
            "stats_high_error": stats_high,
            "shift": shift,
            "flags": flags,
        }
        results.append(entry)

    # Build summary DataFrame
    rows = []
    for r in results:
        rows.append({
            "feature": r["feature"],
            "shift_score": r["shift"]["shift_score"],
            "ks_stat": r["shift"]["ks_stat"],
            "mean_diff_norm": r["shift"]["mean_diff_norm"],
            "nan_pct_overall": r["stats_overall"]["nan_pct"],
            "nan_pct_high": r["stats_high_error"]["nan_pct"],
            "nan_diff": r["shift"]["nan_diff"],
            "js_divergence": r["shift"]["js_divergence"],
            "n_flags": len(r["flags"]),
            "flags": ", ".join(r["flags"]) if r["flags"] else "",
        })

    summary_df = pd.DataFrame(rows).sort_values("shift_score", ascending=False)
    summary_df = summary_df.reset_index(drop=True)

    n_flagged = sum(1 for r in results if r["flags"])
    print(f"\n  Features analyzed: {len(results)}")
    print(f"  Features with flags: {n_flagged}")
    print(f"  Top 5 by shift_score:")
    for _, row in summary_df.head(5).iterrows():
        print(f"    {row['feature']}: {row['shift_score']:.4f} "
              f"[{row['flags']}]")

    return results, summary_df


# ---------------------------------------------------------------------------
# 5. plot_feature_distribution
# ---------------------------------------------------------------------------


def plot_feature_distribution(
    overall: pd.Series,
    high_error: pd.Series,
    bottom_2pct: pd.Series,
    feat_name: str,
    stats_overall: dict,
    stats_high: dict,
    stats_bottom_2pct: dict,
    shift: dict,
    flags: list,
    is_categorical: bool = False,
    save_path: Path = None,
):
    """Plot single feature: 3 side-by-side distributions (shared x-axis) + stats table."""
    is_binary = feat_name in BINARY_FEATURES or overall.dropna().nunique() <= 5

    fig = plt.figure(figsize=(20, 5.5))
    gs = gridspec.GridSpec(1, 4, width_ratios=[1, 1, 1, 1], wspace=0.25)
    ax_all = fig.add_subplot(gs[0, 0])
    ax_b10 = fig.add_subplot(gs[0, 1])
    ax_b2 = fig.add_subplot(gs[0, 2])
    ax_table = fig.add_subplot(gs[0, 3])

    datasets = [
        (overall, "All Data", "steelblue", ax_all),
        (high_error, "Bottom 10%", "orange", ax_b10),
        (bottom_2pct, "Bottom 2%", "indianred", ax_b2),
    ]

    if is_categorical or is_binary:
        # Compute union of all categories for shared x-axis
        all_cats = sorted(
            set(overall.dropna().unique())
            | set(high_error.dropna().unique())
            | set(bottom_2pct.dropna().unique()),
            key=str,
        )
        x = np.arange(len(all_cats))

        # Find max proportion across all 3 for shared y-axis
        max_prop = 0.0
        for series, label, color, ax in datasets:
            vc = series.dropna().value_counts().sort_index()
            prop = np.array([vc.get(c, 0) for c in all_cats], dtype=float)
            if prop.sum() > 0:
                prop = prop / prop.sum()
            max_prop = max(max_prop, prop.max() if len(prop) > 0 else 0)
            ax.bar(x, prop, alpha=0.7, color=color)
            ax.set_xticks(x)
            ax.set_xticklabels([str(c) for c in all_cats], rotation=45,
                                ha="right", fontsize=7)
            ax.set_title(label, fontsize=10, fontweight="bold", color=color)

        # Shared y-axis limits
        for _, _, _, ax in datasets:
            ax.set_ylim(0, max_prop * 1.1 if max_prop > 0 else 1)
        ax_all.set_ylabel("Proportion")
    else:
        # Compute shared bins from overall P1-P99
        o_valid = overall.dropna().astype(float).values
        h_valid = high_error.dropna().astype(float).values
        b_valid = bottom_2pct.dropna().astype(float).values

        if len(o_valid) > 0:
            lo = np.percentile(o_valid, 1)
            hi = np.percentile(o_valid, 99)
            if lo == hi:
                lo = lo - 1
                hi = hi + 1
            bins = np.linspace(lo, hi, 51)

            # Compute all histograms first to find shared y-axis max
            max_density = 0.0
            for vals, label, color, ax in [
                (o_valid, "All Data", "steelblue", ax_all),
                (h_valid, "Bottom 10%", "orange", ax_b10),
                (b_valid, "Bottom 2%", "indianred", ax_b2),
            ]:
                if len(vals) > 0:
                    counts, _, _ = ax.hist(vals, bins=bins, alpha=0.7,
                                            color=color, density=True)
                    max_density = max(max_density, counts.max())
                ax.set_title(label, fontsize=10, fontweight="bold", color=color)

            # Apply shared axis limits
            for _, _, _, ax in datasets:
                ax.set_xlim(lo, hi)
                ax.set_ylim(0, max_density * 1.1 if max_density > 0 else 1)
        else:
            for _, label, color, ax in datasets:
                ax.set_title(label, fontsize=10, fontweight="bold", color=color)

        ax_all.set_ylabel("Density")

    fig.suptitle(feat_name, fontsize=13, fontweight="bold", y=1.02)

    # Stats comparison table on right panel (3 data columns)
    ax_table.axis("off")
    table_rows = []
    stat_keys = ["count", "nan_pct", "mean", "median", "std", "min", "max",
                 "p5", "p25", "p75", "p95"]
    for key in stat_keys:
        v_o = stats_overall.get(key)
        v_h = stats_high.get(key)
        v_b = stats_bottom_2pct.get(key)
        v_o_str = f"{v_o}" if v_o is not None else "N/A"
        v_h_str = f"{v_h}" if v_h is not None else "N/A"
        v_b_str = f"{v_b}" if v_b is not None else "N/A"
        table_rows.append([key, v_o_str, v_h_str, v_b_str])

    # Add shift metrics
    table_rows.append(["---", "---", "---", "---"])
    table_rows.append(["KS stat", f"{shift.get('ks_stat', 'N/A')}", "", ""])
    table_rows.append(["Mean diff (norm)", f"{shift.get('mean_diff_norm', 'N/A')}", "", ""])
    table_rows.append(["NaN diff (pp)", f"{shift.get('nan_diff', 'N/A')}", "", ""])
    table_rows.append(["Shift score", f"{shift.get('shift_score', 'N/A')}", "", ""])
    if flags:
        table_rows.append(["FLAGS", ", ".join(flags), "", ""])

    tbl = ax_table.table(
        cellText=table_rows,
        colLabels=["Stat", "All Data", "Bot 10%", "Bot 2%"],
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.scale(1, 1.2)

    # Highlight flagged rows
    if flags:
        last_row = len(table_rows)
        for j in range(4):
            tbl[last_row, j].set_facecolor("#ffe0e0")

    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        fig.tight_layout()
    if save_path:
        fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
    plt.close("all")


# ---------------------------------------------------------------------------
# 6. plot_feature_grid
# ---------------------------------------------------------------------------


def plot_feature_grid(
    group_name: str,
    features: list,
    df_test: pd.DataFrame,
    high_error_mask: np.ndarray,
    results_lookup: dict,
    save_path: Path,
):
    """Summary grid of mini histograms for a feature group."""
    n = len(features)
    ncols = 4
    nrows = max(1, int(np.ceil(n / ncols)))

    fig, axes = plt.subplots(nrows, ncols, figsize=(4 * ncols, 3 * nrows))
    if nrows == 1 and ncols == 1:
        axes = np.array([[axes]])
    elif nrows == 1:
        axes = axes.reshape(1, -1)
    elif ncols == 1:
        axes = axes.reshape(-1, 1)

    for idx, feat in enumerate(features):
        row, col = divmod(idx, ncols)
        ax = axes[row, col]

        is_binary = feat in BINARY_FEATURES or df_test[feat].dropna().nunique() <= 5
        is_cat = feat in CATEGORICAL_COLS_V2

        overall = df_test[feat]
        high_error = df_test.loc[high_error_mask, feat]

        r = results_lookup.get(feat, {})
        ks = r.get("shift", {}).get("ks_stat")
        score = r.get("shift", {}).get("shift_score", 0)

        if is_cat or is_binary:
            vc_o = overall.dropna().value_counts().sort_index()
            vc_h = high_error.dropna().value_counts().sort_index()
            all_cats = sorted(set(vc_o.index) | set(vc_h.index), key=str)
            prop_o = np.array([vc_o.get(c, 0) for c in all_cats], dtype=float)
            prop_h = np.array([vc_h.get(c, 0) for c in all_cats], dtype=float)
            if prop_o.sum() > 0:
                prop_o /= prop_o.sum()
            if prop_h.sum() > 0:
                prop_h /= prop_h.sum()
            x = np.arange(len(all_cats))
            w = 0.35
            ax.bar(x - w / 2, prop_o, w, alpha=0.7, color="steelblue")
            ax.bar(x + w / 2, prop_h, w, alpha=0.7, color="indianred")
            if len(all_cats) <= 8:
                ax.set_xticks(x)
                ax.set_xticklabels([str(c) for c in all_cats], fontsize=6,
                                    rotation=45, ha="right")
            else:
                ax.set_xticks([])
        else:
            o_valid = overall.dropna().astype(float).values
            h_valid = high_error.dropna().astype(float).values
            if len(o_valid) > 0:
                lo = np.percentile(o_valid, 1)
                hi_bound = np.percentile(o_valid, 99)
                if lo == hi_bound:
                    lo -= 1
                    hi_bound += 1
                bins = np.linspace(lo, hi_bound, 31)
                ax.hist(o_valid, bins=bins, alpha=0.6, color="steelblue",
                         density=True)
                if len(h_valid) > 0:
                    ax.hist(h_valid, bins=bins, alpha=0.6, color="indianred",
                             density=True)

        # Annotate with KS stat
        label = feat
        if len(label) > 25:
            label = label[:22] + "..."
        ks_str = f"KS={ks:.3f}" if ks is not None else f"JS={r.get('shift', {}).get('js_divergence', 0):.4f}"
        ax.set_title(f"{label}\n{ks_str} (s={score:.3f})", fontsize=7,
                      fontweight="bold")
        ax.tick_params(labelsize=6)

    # Hide unused axes
    for idx in range(n, nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row, col].set_visible(False)

    fig.suptitle(f"Feature Group: {group_name}", fontsize=13, fontweight="bold",
                  y=1.02)
    fig.tight_layout()
    fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
    plt.close("all")


# ---------------------------------------------------------------------------
# 7. plot_nan_comparison
# ---------------------------------------------------------------------------


def plot_nan_comparison(feature_results: list, save_path: Path):
    """Horizontal grouped bar chart of NaN rates (overall vs high-error)."""
    # Filter to features with NaN% > 1% in either group
    entries = []
    for r in feature_results:
        nan_o = r["stats_overall"]["nan_pct"]
        nan_h = r["stats_high_error"]["nan_pct"]
        if nan_o > 1.0 or nan_h > 1.0:
            entries.append({
                "feature": r["feature"],
                "nan_overall": nan_o,
                "nan_high": nan_h,
                "nan_diff": nan_h - nan_o,
            })

    if not entries:
        print("  No features with NaN > 1% -- skipping NaN comparison plot.")
        return

    # Sort by NaN rate difference
    entries.sort(key=lambda x: x["nan_diff"], reverse=True)

    n = len(entries)
    fig, ax = plt.subplots(figsize=(10, max(4, n * 0.4)))

    y = np.arange(n)
    h = 0.35

    ax.barh(y - h / 2, [e["nan_overall"] for e in entries], h,
            color="steelblue", alpha=0.7, label="Overall")
    ax.barh(y + h / 2, [e["nan_high"] for e in entries], h,
            color="indianred", alpha=0.7, label="High Error")

    ax.set_yticks(y)
    ax.set_yticklabels([e["feature"] for e in entries], fontsize=8)
    ax.set_xlabel("NaN %")
    ax.set_title("NaN Rate Comparison: Overall vs High-Error", fontweight="bold")
    ax.legend()
    ax.invert_yaxis()

    fig.tight_layout()
    fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
    plt.close("all")


# ---------------------------------------------------------------------------
# 8. plot_error_scatter
# ---------------------------------------------------------------------------


def plot_error_scatter(
    df_test: pd.DataFrame,
    abs_error: np.ndarray,
    top_features: list,
    save_path: Path,
):
    """2x3 grid of binned mean-error-vs-feature-value for top shifted features."""
    n_feats = min(6, len(top_features))
    if n_feats == 0:
        return

    nrows = 2
    ncols = 3
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 4 * nrows))

    for idx in range(n_feats):
        row, col = divmod(idx, ncols)
        ax = axes[row, col]
        feat = top_features[idx]

        vals = df_test[feat].values
        is_cat = feat in CATEGORICAL_COLS_V2
        is_binary = feat in BINARY_FEATURES or df_test[feat].dropna().nunique() <= 5

        if is_cat or is_binary:
            # Group by category value
            mask = ~pd.isna(vals)
            if hasattr(vals, 'categories'):
                cat_vals = vals[mask]
            else:
                cat_vals = pd.Series(vals[mask])
            err_vals = abs_error[mask]
            group_df = pd.DataFrame({"cat": cat_vals, "err": err_vals})
            agg = group_df.groupby("cat")["err"].mean().sort_index()
            ax.bar(range(len(agg)), agg.values, color="steelblue", alpha=0.7)
            ax.set_xticks(range(len(agg)))
            ax.set_xticklabels([str(c) for c in agg.index], fontsize=7,
                                rotation=45, ha="right")
        else:
            # Bin numeric values into 20 bins
            float_vals = pd.to_numeric(vals, errors="coerce")
            mask = ~np.isnan(float_vals)
            fv = float_vals[mask]
            ev = abs_error[mask]
            if len(fv) > 0:
                try:
                    bins = pd.qcut(fv, q=20, duplicates="drop")
                    bin_df = pd.DataFrame({"bin": bins, "err": ev})
                    agg = bin_df.groupby("bin", observed=True)["err"].mean()
                    midpoints = [interval.mid for interval in agg.index]
                    ax.plot(midpoints, agg.values, "o-", color="steelblue",
                            markersize=4, alpha=0.8)
                except Exception:
                    ax.scatter(fv[::max(1, len(fv)//500)],
                               ev[::max(1, len(ev)//500)],
                               s=2, alpha=0.3, color="steelblue")

        ax.set_title(feat, fontsize=10, fontweight="bold")
        ax.set_xlabel("Feature Value", fontsize=8)
        ax.set_ylabel("Mean |Error| (s)", fontsize=8)
        ax.tick_params(labelsize=7)

    # Hide unused axes
    for idx in range(n_feats, nrows * ncols):
        row, col = divmod(idx, ncols)
        axes[row, col].set_visible(False)

    fig.suptitle("Mean Absolute Error by Feature Value (Top 6 Shifted Features)",
                  fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(save_path, dpi=DPI, bbox_inches="tight")
    plt.close("all")


# ---------------------------------------------------------------------------
# 9. generate_report
# ---------------------------------------------------------------------------


def generate_report(
    feature_results: list,
    summary_df: pd.DataFrame,
    data_info: dict,
    save_path: Path,
):
    """Write markdown diagnostic report."""
    top_pct = data_info["top_pct"]
    threshold = data_info["threshold"]
    n_total = len(data_info["y_test"])
    n_high = int(data_info["high_error_mask"].sum())
    n_flagged = sum(1 for r in feature_results if r["flags"])

    lines = []
    lines.append("# Feature Distribution Diagnostic Report\n")
    lines.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Executive summary
    lines.append("## Executive Summary\n")
    lines.append(f"- **Test set size**: {n_total:,} samples")
    lines.append(f"- **Overall MAE**: {data_info['overall_mae']:.1f}s")
    lines.append(f"- **High-error threshold**: top {top_pct*100:.0f}% "
                 f"(|error| >= {threshold:.1f}s)")
    lines.append(f"- **High-error samples**: {n_high:,} "
                 f"({n_high/n_total*100:.1f}%)")
    lines.append(f"- **High-error MAE**: {data_info['high_error_mae']:.1f}s")
    lines.append(f"- **Features analyzed**: {len(feature_results)}")
    lines.append(f"- **Features with flags**: {n_flagged}\n")

    # Flag legend
    lines.append("### Flag Definitions\n")
    lines.append("| Flag | Meaning |")
    lines.append("|------|---------|")
    lines.append("| HIGH_NAN_OVERALL | NaN% > 50% in overall test set |")
    lines.append("| NAN_RATE_SPIKE | High-error NaN% exceeds overall by >5pp |")
    lines.append("| MEAN_SHIFT | \\|normalized mean diff\\| > 0.5 |")
    lines.append("| STRONG_KS | KS statistic > 0.15 |")
    lines.append("| ZERO_VARIANCE | std = 0 in overall or high-error group |")
    lines.append("")

    # Distribution shift ranking
    lines.append("## Distribution Shift Ranking (All Features)\n")
    lines.append("| Rank | Feature | Shift Score | KS Stat | Mean Diff (norm) "
                 "| NaN% Overall | NaN% High | NaN Diff (pp) | Flags |")
    lines.append("|------|---------|-------------|---------|------------------|"
                 "--------------|-----------|---------------|-------|")
    for i, (_, row) in enumerate(summary_df.iterrows(), 1):
        ks = f"{row['ks_stat']:.4f}" if pd.notna(row['ks_stat']) else "N/A"
        md = f"{row['mean_diff_norm']:.4f}" if pd.notna(row['mean_diff_norm']) else "N/A"
        js = row.get('js_divergence')
        if pd.isna(row['ks_stat']) and js is not None and not pd.isna(js):
            ks = f"JS={js:.4f}"
        lines.append(
            f"| {i} | {row['feature']} | {row['shift_score']:.4f} "
            f"| {ks} | {md} "
            f"| {row['nan_pct_overall']:.1f} | {row['nan_pct_high']:.1f} "
            f"| {row['nan_diff']:.1f} | {row['flags']} |"
        )
    lines.append("")

    # NaN rate comparison
    nan_entries = [r for r in feature_results
                   if r["stats_overall"]["nan_pct"] > 0.1
                   or r["stats_high_error"]["nan_pct"] > 0.1]
    if nan_entries:
        nan_entries.sort(
            key=lambda x: x["stats_high_error"]["nan_pct"]
            - x["stats_overall"]["nan_pct"],
            reverse=True,
        )
        lines.append("## NaN Rate Comparison\n")
        lines.append("| Feature | NaN% Overall | NaN% High Error | Diff (pp) |")
        lines.append("|---------|--------------|-----------------|-----------|")
        for r in nan_entries:
            o = r["stats_overall"]["nan_pct"]
            h = r["stats_high_error"]["nan_pct"]
            lines.append(f"| {r['feature']} | {o:.1f} | {h:.1f} | {h-o:+.1f} |")
        lines.append("")

    # Flagged features detail
    flagged = [r for r in feature_results if r["flags"]]
    if flagged:
        flagged.sort(key=lambda x: x["shift"]["shift_score"], reverse=True)
        lines.append("## Flagged Features Detail\n")
        for r in flagged:
            lines.append(f"### {r['feature']}\n")
            lines.append(f"- **Flags**: {', '.join(r['flags'])}")
            lines.append(f"- **Shift score**: {r['shift']['shift_score']:.4f}")
            so = r["stats_overall"]
            sh = r["stats_high_error"]
            lines.append(f"- **Overall**: mean={so['mean']}, std={so['std']}, "
                         f"NaN%={so['nan_pct']}")
            lines.append(f"- **High-error**: mean={sh['mean']}, std={sh['std']}, "
                         f"NaN%={sh['nan_pct']}")
            if r["shift"]["ks_stat"] is not None:
                lines.append(f"- **KS stat**: {r['shift']['ks_stat']:.4f} "
                             f"(p={r['shift']['ks_pvalue']:.2e})")
            if r["shift"]["mean_diff_norm"] is not None:
                lines.append(f"- **Mean diff (norm)**: "
                             f"{r['shift']['mean_diff_norm']:.4f}")
            lines.append("")

    # Per-group summaries
    lines.append("## Per-Group Summaries\n")
    results_lookup = {r["feature"]: r for r in feature_results}
    for group_name, feats in FEATURE_GROUPS.items():
        lines.append(f"### {group_name}\n")
        group_results = [results_lookup[f] for f in feats if f in results_lookup]
        if not group_results:
            lines.append("No features found.\n")
            continue
        avg_score = np.mean([r["shift"]["shift_score"] for r in group_results])
        max_score = max(r["shift"]["shift_score"] for r in group_results)
        n_flags = sum(1 for r in group_results if r["flags"])
        lines.append(f"- Features: {len(group_results)}")
        lines.append(f"- Avg shift score: {avg_score:.4f}")
        lines.append(f"- Max shift score: {max_score:.4f}")
        lines.append(f"- Flagged: {n_flags}")
        top_feat = max(group_results,
                       key=lambda x: x["shift"]["shift_score"])
        lines.append(f"- Most shifted: {top_feat['feature']} "
                     f"({top_feat['shift']['shift_score']:.4f})")
        lines.append("")

    report = "\n".join(lines)
    save_path.write_text(report, encoding="utf-8")
    print(f"  Report written: {save_path}")


# ---------------------------------------------------------------------------
# 10. main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Feature distribution diagnostics for Tiger Transit ETA model"
    )
    parser.add_argument(
        "--top-pct", type=float, default=TOP_ERROR_PCT,
        help=f"Fraction of highest-error samples to analyze (default: {TOP_ERROR_PCT})"
    )
    parser.add_argument(
        "--skip-individual", action="store_true",
        help="Skip generating 43 individual feature PNGs"
    )
    args = parser.parse_args()

    t0 = time.time()
    print("=" * 60)
    print("Feature Distribution Diagnostics")
    print("=" * 60)

    # Create output directory
    DIAG_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Load data
    print("\n[1/6] Loading data and computing predictions...")
    data = load_data(top_pct=args.top_pct)
    df_test = data["df_test"]
    abs_error = data["abs_error"]
    high_error_mask = data["high_error_mask"]
    bottom_2pct_mask = data["bottom_2pct_mask"]

    # Step 2: Analyze all features
    print("\n[2/6] Analyzing feature distributions...")
    feature_results, summary_df = analyze_all_features(df_test, high_error_mask)
    results_lookup = {r["feature"]: r for r in feature_results}

    # Pre-compute bottom 2% stats for each feature (used by individual plots)
    bottom_2pct_stats = {}
    for feat in FEATURE_COLS_V2:
        is_cat = feat in CATEGORICAL_COLS_V2
        bottom_2pct_stats[feat] = compute_feature_stats(
            df_test.loc[bottom_2pct_mask, feat], is_categorical=is_cat
        )

    # Step 3: Individual feature plots
    if not args.skip_individual:
        print(f"\n[3/6] Generating {len(FEATURE_COLS_V2)} individual feature plots...")
        for i, feat in enumerate(FEATURE_COLS_V2):
            r = results_lookup[feat]
            save_path = DIAG_DIR / f"feat_{feat}.png"
            plot_feature_distribution(
                overall=df_test[feat],
                high_error=df_test.loc[high_error_mask, feat],
                bottom_2pct=df_test.loc[bottom_2pct_mask, feat],
                feat_name=feat,
                stats_overall=r["stats_overall"],
                stats_high=r["stats_high_error"],
                stats_bottom_2pct=bottom_2pct_stats[feat],
                shift=r["shift"],
                flags=r["flags"],
                is_categorical=(feat in CATEGORICAL_COLS_V2),
                save_path=save_path,
            )
            if (i + 1) % 10 == 0:
                print(f"    {i + 1}/{len(FEATURE_COLS_V2)} done")
        print(f"    {len(FEATURE_COLS_V2)}/{len(FEATURE_COLS_V2)} done")
    else:
        print("\n[3/6] Skipping individual feature plots (--skip-individual)")

    # Step 4: Feature group grids
    print(f"\n[4/6] Generating {len(FEATURE_GROUPS)} feature group grids...")
    for group_name, feats in FEATURE_GROUPS.items():
        save_path = DIAG_DIR / f"diag_grid_{group_name}.png"
        plot_feature_grid(
            group_name=group_name,
            features=feats,
            df_test=df_test,
            high_error_mask=high_error_mask,
            results_lookup=results_lookup,
            save_path=save_path,
        )
        print(f"    {group_name}: {len(feats)} features")

    # Step 5: NaN comparison + error scatter
    print("\n[5/6] Generating NaN comparison and error scatter plots...")
    plot_nan_comparison(feature_results, DIAG_DIR / "diag_nan_comparison.png")

    # Top 6 most-shifted numeric features for scatter plot
    numeric_results = [r for r in feature_results if not r["is_categorical"]]
    numeric_results.sort(key=lambda x: x["shift"]["shift_score"], reverse=True)
    top6_feats = [r["feature"] for r in numeric_results[:6]]
    plot_error_scatter(df_test, abs_error, top6_feats,
                       DIAG_DIR / "diag_top6_scatter.png")

    # Step 6: Write JSON + report
    print("\n[6/6] Writing JSON outputs and markdown report...")

    # diag_feature_stats.json
    stats_json = _sanitize_for_json(feature_results)
    with open(DIAG_DIR / "diag_feature_stats.json", "w") as f:
        json.dump(stats_json, f, indent=2, default=str)

    # diag_ranking.json
    ranking = []
    for _, row in summary_df.iterrows():
        ranking.append(_sanitize_for_json(row.to_dict()))
    with open(DIAG_DIR / "diag_ranking.json", "w") as f:
        json.dump(ranking, f, indent=2, default=str)

    # Markdown report
    generate_report(feature_results, summary_df, data, DIAG_DIR / "diag_summary.md")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s")
    print(f"Output directory: {DIAG_DIR.resolve()}")
    print(f"Files generated: check {DIAG_DIR}/diag_summary.md for full report")


if __name__ == "__main__":
    main()
