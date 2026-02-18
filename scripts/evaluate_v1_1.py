"""
evaluate_v1_1.py - Phase 9 v1.1 vs v1.0 Evaluation Report.

Produces a self-contained HTML evaluation report comparing v1.1 (residual-target,
4D tiered baselines, 85.6s MAE) against v1.0 (direct prediction, 123.1s MAE) and
baseline-only (~91.9s MAE).

ALL metrics are computed LIVE from models + test data. No saved metrics JSON files
are used for v1.1 numbers.

Sections:
  1. Headline Comparison -- three-way: baseline-only, v1.0, v1.1
  2. Per-Route Comparison Table -- all 23 routes with delta and % improvement
  3. SHAP Analysis -- side-by-side top 15 features for v1.0 and v1.1
  4. Residual Diagnostics -- histogram, tail analysis, MAE vs stops_away, MAE vs hour

Usage:
    python scripts/evaluate_v1_1.py

Input:
    data/processed/test_featured_v2.parquet
    models/tuned_v1.ubj          (v1.0 model, 43 features)
    models/v1_1_residual.ubj     (v1.1 model, 45 features)
    models/tuned_metrics.json    (v1.0 best_iteration)

Output:
    reports/v1_1_evaluation.html  (self-contained HTML with embedded charts)
"""

import base64
import io
import json
import sys
import time
from pathlib import Path

# Headless rendering -- must be set BEFORE importing pyplot
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch

import numpy as np
from scipy import stats
import xgboost as xgb

# ---------------------------------------------------------------------------
# Add scripts/ to path so we can import from build_differentiator_features
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_differentiator_features import (
    FEATURE_COLS_V2,
    PHASE3_FEATURE_COLS,
    PHASE4_FEATURE_COLS,
    CATEGORICAL_COLS_V2,
    TARGET_COL,
    KEEP_EXTRA,
    load_featured_v2,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODELS_DIR = Path("models")
REPORTS_DIR = Path("reports")

# v1.0 used 43 features: the original 15 Phase3 features (with lateness_now)
# plus 28 Phase4 features. Current PHASE3_FEATURE_COLS has 14 (lateness_now
# removed), so we reconstruct the v1.0 feature list.
V1_0_FEATURES = (
    PHASE3_FEATURE_COLS[:6]
    + ["lateness_now"]
    + PHASE3_FEATURE_COLS[6:]
    + list(PHASE4_FEATURE_COLS)
)

# Chart colors
COLOR_V1_0 = "#5B8DB8"  # blue
COLOR_V1_1 = "#2D6A4F"  # green
COLOR_BASELINE = "#D4A574"  # warm tan
COLOR_BG = "#F8F9FA"
COLOR_TEXT = "#1A1A2E"
LOW_SAMPLE_THRESHOLD = 200  # Flag routes with fewer samples


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def fig_to_base64(fig, dpi=150):
    """Save matplotlib figure to base64-encoded PNG string, then close figure."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    buf.close()
    plt.close(fig)
    return b64


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


# ---------------------------------------------------------------------------
# Data loading and prediction
# ---------------------------------------------------------------------------

def load_and_predict():
    """Load test data, both models, compute all predictions.

    Returns dict with all arrays needed for report sections.
    """
    print("Loading test data...")
    df = load_featured_v2("test")
    print(f"  Test set: {len(df):,} rows, {df.shape[1]} columns")

    # Load v1.0 metrics for best_iteration
    with open(MODELS_DIR / "tuned_metrics.json") as f:
        v1_0_metrics = json.load(f)
    best_iter_v1_0 = v1_0_metrics["best_iteration"]
    print(f"  v1.0 best_iteration: {best_iter_v1_0}")

    # Load models
    print("Loading models...")
    bst_v1_0 = xgb.Booster()
    bst_v1_0.load_model(str(MODELS_DIR / "tuned_v1.ubj"))
    print(f"  v1.0: {bst_v1_0.num_features()} features")

    bst_v1_1 = xgb.Booster()
    bst_v1_1.load_model(str(MODELS_DIR / "v1_1_residual.ubj"))
    print(f"  v1.1: {bst_v1_1.num_features()} features")

    # --- Build v1.0 DMatrix ---
    # v1.0 needs lateness_now (always 0.0 -- zero variance feature retained for compatibility)
    df["lateness_now"] = 0.0
    X_v1_0 = df[V1_0_FEATURES].copy()
    for col in CATEGORICAL_COLS_V2:
        if col in X_v1_0.columns:
            X_v1_0[col] = X_v1_0[col].astype("category")
    dtest_v1_0 = xgb.DMatrix(X_v1_0, enable_categorical=True)

    # --- Build v1.1 DMatrix ---
    X_v1_1 = df[FEATURE_COLS_V2].copy()
    for col in CATEGORICAL_COLS_V2:
        if col in X_v1_1.columns:
            X_v1_1[col] = X_v1_1[col].astype("category")
    dtest_v1_1 = xgb.DMatrix(X_v1_1, enable_categorical=True)

    # --- Predictions ---
    print("Computing predictions...")

    # v1.0 predicts time_to_arrival_seconds directly
    pred_v1_0 = bst_v1_0.predict(dtest_v1_0, iteration_range=(0, best_iter_v1_0 + 1))

    # v1.1 predicts residual (deviation from baseline_eta)
    pred_residual_v1_1 = bst_v1_1.predict(dtest_v1_1)

    # Reconstruct v1.1 absolute prediction
    baseline_eta = df["baseline_eta"].values.astype(float)
    pred_v1_1 = baseline_eta + pred_residual_v1_1

    # Ground truth
    y_true = df["time_to_arrival_seconds"].values.astype(float)
    actual_residual = df[TARGET_COL].values.astype(float)

    # Metadata columns
    route_ids = df["route_id"].astype(int).values
    stops_away = df["stops_away"].values.astype(int)
    minutes_since_midnight = df["minutes_since_midnight"].values.astype(float)

    # Quick sanity check
    mae_v1_0 = mae(y_true, pred_v1_0)
    mae_v1_1 = mae(y_true, pred_v1_1)
    mae_baseline = mae(y_true, baseline_eta)
    print(f"  Baseline-only MAE: {mae_baseline:.1f}s")
    print(f"  v1.0 MAE: {mae_v1_0:.1f}s")
    print(f"  v1.1 MAE: {mae_v1_1:.1f}s")

    return {
        "df": df,
        "y_true": y_true,
        "baseline_eta": baseline_eta,
        "pred_v1_0": pred_v1_0,
        "pred_v1_1": pred_v1_1,
        "pred_residual_v1_1": pred_residual_v1_1,
        "actual_residual": actual_residual,
        "route_ids": route_ids,
        "stops_away": stops_away,
        "minutes_since_midnight": minutes_since_midnight,
        "bst_v1_0": bst_v1_0,
        "bst_v1_1": bst_v1_1,
        "dtest_v1_0": dtest_v1_0,
        "dtest_v1_1": dtest_v1_1,
        "best_iter_v1_0": best_iter_v1_0,
        "mae_v1_0": mae_v1_0,
        "mae_v1_1": mae_v1_1,
        "mae_baseline": mae_baseline,
    }


# ---------------------------------------------------------------------------
# Section 1: Headline Comparison
# ---------------------------------------------------------------------------

def section_headline(data):
    """Three-way headline comparison: baseline-only, v1.0, v1.1."""
    y_true = data["y_true"]
    mae_b = data["mae_baseline"]
    mae_v0 = data["mae_v1_0"]
    mae_v1 = data["mae_v1_1"]

    rmse_b = rmse(y_true, data["baseline_eta"])
    rmse_v0 = rmse(y_true, data["pred_v1_0"])
    rmse_v1 = rmse(y_true, data["pred_v1_1"])

    improv_vs_v0 = (mae_v0 - mae_v1) / mae_v0 * 100
    improv_vs_baseline = (mae_b - mae_v1) / mae_b * 100

    # Console output
    print(f"\n{'='*60}")
    print("Section 1: Headline Comparison")
    print(f"{'='*60}")
    print(f"  Baseline-only MAE:  {mae_b:.1f}s  (RMSE: {rmse_b:.1f}s)")
    print(f"  v1.0 MAE:           {mae_v0:.1f}s  (RMSE: {rmse_v0:.1f}s)")
    print(f"  v1.1 MAE:           {mae_v1:.1f}s  (RMSE: {rmse_v1:.1f}s)")
    print(f"  v1.1 vs v1.0:       {improv_vs_v0:.1f}% improvement")
    print(f"  v1.1 vs baseline:   {improv_vs_baseline:.1f}% improvement")
    print(f"  Test samples:       {len(y_true):,}")

    # HTML metric cards
    html = f"""
    <div class="metric-cards">
        <div class="metric-card baseline">
            <div class="metric-label">Baseline-Only</div>
            <div class="metric-value">{mae_b:.1f}s</div>
            <div class="metric-detail">RMSE: {rmse_b:.1f}s</div>
            <div class="metric-detail">SegSum 4D tiered lookup</div>
        </div>
        <div class="metric-card v10">
            <div class="metric-label">v1.0 (Direct)</div>
            <div class="metric-value">{mae_v0:.1f}s</div>
            <div class="metric-detail">RMSE: {rmse_v0:.1f}s</div>
            <div class="metric-detail">43 features, squared error</div>
        </div>
        <div class="metric-card v11">
            <div class="metric-label">v1.1 (Residual)</div>
            <div class="metric-value">{mae_v1:.1f}s</div>
            <div class="metric-detail">RMSE: {rmse_v1:.1f}s</div>
            <div class="metric-detail">45 features, Huber loss</div>
        </div>
    </div>
    <div class="improvement-banner">
        v1.1 improves over v1.0 by <strong>{improv_vs_v0:.1f}%</strong>
        ({mae_v0:.1f}s &rarr; {mae_v1:.1f}s MAE)
        &nbsp;|&nbsp;
        Over baseline by <strong>{improv_vs_baseline:.1f}%</strong>
        ({mae_b:.1f}s &rarr; {mae_v1:.1f}s MAE)
        &nbsp;|&nbsp;
        Test samples: <strong>{len(y_true):,}</strong>
    </div>
    """

    return {
        "html": html,
        "mae_baseline": mae_b,
        "mae_v1_0": mae_v0,
        "mae_v1_1": mae_v1,
        "rmse_baseline": rmse_b,
        "rmse_v1_0": rmse_v0,
        "rmse_v1_1": rmse_v1,
        "improv_vs_v0": improv_vs_v0,
        "improv_vs_baseline": improv_vs_baseline,
    }


# ---------------------------------------------------------------------------
# Section 2: Per-Route Comparison Table
# ---------------------------------------------------------------------------

def section_per_route(data):
    """Per-route comparison table and grouped bar chart."""
    y_true = data["y_true"]
    pred_v0 = data["pred_v1_0"]
    pred_v1 = data["pred_v1_1"]
    route_ids = data["route_ids"]

    unique_routes = sorted(set(route_ids))

    print(f"\n{'='*60}")
    print("Section 2: Per-Route Comparison")
    print(f"{'='*60}")

    rows = []
    for rid in unique_routes:
        mask = route_ids == rid
        n = int(mask.sum())
        m0 = mae(y_true[mask], pred_v0[mask])
        m1 = mae(y_true[mask], pred_v1[mask])
        r0 = rmse(y_true[mask], pred_v0[mask])
        r1 = rmse(y_true[mask], pred_v1[mask])
        delta = m0 - m1
        pct = (delta / m0 * 100) if m0 > 0 else 0.0
        flag = "*" if n < LOW_SAMPLE_THRESHOLD else ""
        rows.append({
            "route": rid, "n": n, "flag": flag,
            "v0_mae": m0, "v1_mae": m1, "v0_rmse": r0, "v1_rmse": r1,
            "delta": delta, "pct": pct,
        })

    # Sort by % improvement (best first) for table display
    rows_by_pct = sorted(rows, key=lambda r: r["pct"], reverse=True)

    # Win/loss/tie counts (1% tolerance)
    wins = sum(1 for r in rows if r["v1_mae"] < r["v0_mae"] * 0.99)
    losses = sum(1 for r in rows if r["v1_mae"] > r["v0_mae"] * 1.01)
    ties = len(rows) - wins - losses

    # Console output
    print(f"\n  {'Route':>6}{'*':>2} {'N':>7}  {'v1.0 MAE':>9} {'v1.1 MAE':>9} {'Delta':>8} {'%Improv':>8}")
    print(f"  {'-'*6} {'-'*2} {'-'*7}  {'-'*9} {'-'*9} {'-'*8} {'-'*8}")
    for r in rows_by_pct:
        print(f"  {r['route']:>6}{r['flag']:>2} {r['n']:>7}  {r['v0_mae']:>9.1f} {r['v1_mae']:>9.1f} {r['delta']:>+8.1f} {r['pct']:>+7.1f}%")
    print(f"\n  Summary: {wins} wins, {losses} losses, {ties} ties out of {len(rows)} routes")

    # Identify highlights
    best_route = rows_by_pct[0]
    worst_route = rows_by_pct[-1]
    route_27 = next((r for r in rows if r["route"] == 27), None)

    # --- HTML Table ---
    table_html = """
    <table class="data-table">
        <thead>
            <tr>
                <th>Route</th><th>N</th>
                <th>v1.0 MAE</th><th>v1.1 MAE</th>
                <th>v1.0 RMSE</th><th>v1.1 RMSE</th>
                <th>Delta MAE</th><th>% Improvement</th>
            </tr>
        </thead>
        <tbody>
    """
    for r in rows_by_pct:
        css_class = ""
        if r["pct"] > 1:
            css_class = ' class="row-win"'
        elif r["pct"] < -1:
            css_class = ' class="row-loss"'
        flag_html = f' <span class="flag" title="Low sample count ({r["n"]} samples)">*</span>' if r["flag"] else ""
        table_html += f"""
            <tr{css_class}>
                <td>{r['route']}{flag_html}</td><td>{r['n']:,}</td>
                <td>{r['v0_mae']:.1f}s</td><td>{r['v1_mae']:.1f}s</td>
                <td>{r['v0_rmse']:.1f}s</td><td>{r['v1_rmse']:.1f}s</td>
                <td>{r['delta']:+.1f}s</td><td>{r['pct']:+.1f}%</td>
            </tr>
        """
    table_html += "</tbody></table>"

    # Win/loss summary
    summary_html = f"""
    <div class="summary-box">
        <span class="win-count">{wins} wins</span> &middot;
        <span class="loss-count">{losses} losses</span> &middot;
        <span class="tie-count">{ties} ties</span>
        out of {len(rows)} routes (1% tolerance)
    </div>
    """

    # Narrative highlights
    highlights_html = '<div class="highlights">'
    highlights_html += f'<p><strong>Biggest winner:</strong> Route {best_route["route"]} improved by {best_route["pct"]:.1f}% ({best_route["v0_mae"]:.1f}s &rarr; {best_route["v1_mae"]:.1f}s MAE, N={best_route["n"]:,})</p>'
    highlights_html += f'<p><strong>Biggest loser:</strong> Route {worst_route["route"]} regressed by {abs(worst_route["pct"]):.1f}% ({worst_route["v0_mae"]:.1f}s &rarr; {worst_route["v1_mae"]:.1f}s MAE, N={worst_route["n"]:,})</p>'
    if route_27:
        highlights_html += f'<p><strong>Route 27 <span class="flag">*</span>:</strong> Only {route_27["n"]} test samples -- metrics unreliable. v1.0 MAE: {route_27["v0_mae"]:.1f}s, v1.1 MAE: {route_27["v1_mae"]:.1f}s</p>'
    highlights_html += '<p class="note">* Routes with fewer than 200 test samples are flagged -- metrics may be unreliable.</p>'
    highlights_html += '</div>'

    # --- Grouped Bar Chart ---
    # Sort by route ID for the chart
    rows_by_id = sorted(rows, key=lambda r: r["route"])
    route_labels = [str(r["route"]) for r in rows_by_id]
    v0_maes = [r["v0_mae"] for r in rows_by_id]
    v1_maes = [r["v1_mae"] for r in rows_by_id]

    x = np.arange(len(route_labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    bars_v0 = ax.bar(x - width / 2, v0_maes, width, label="v1.0", color=COLOR_V1_0, alpha=0.85)
    bars_v1 = ax.bar(x + width / 2, v1_maes, width, label="v1.1", color=COLOR_V1_1, alpha=0.85)
    ax.set_xlabel("Route ID", fontsize=11)
    ax.set_ylabel("MAE (seconds)", fontsize=11)
    ax.set_title("Per-Route MAE: v1.0 vs v1.1", fontsize=13, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels(route_labels, rotation=45, ha="right")
    ax.legend(fontsize=10)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    chart_b64 = fig_to_base64(fig)

    chart_html = f'<img src="data:image/png;base64,{chart_b64}" alt="Per-route MAE comparison" class="chart-img">'

    html = summary_html + table_html + highlights_html + chart_html

    return {
        "html": html,
        "rows": rows,
        "wins": wins,
        "losses": losses,
        "ties": ties,
    }


# ---------------------------------------------------------------------------
# Section 3: SHAP Analysis
# ---------------------------------------------------------------------------

def section_shap(data):
    """SHAP feature importance comparison: v1.0 vs v1.1 side-by-side."""
    print(f"\n{'='*60}")
    print("Section 3: SHAP Feature Importance Analysis")
    print(f"{'='*60}")

    bst_v1_0 = data["bst_v1_0"]
    bst_v1_1 = data["bst_v1_1"]
    df = data["df"]
    best_iter = data["best_iter_v1_0"]

    # Subsample 2000 rows
    rng = np.random.RandomState(42)
    n_total = len(df)
    n_sample = min(2000, n_total)
    sample_idx = rng.choice(n_total, size=n_sample, replace=False)
    sample_idx.sort()
    df_sample = df.iloc[sample_idx].copy()
    print(f"  Subsampled {n_sample} rows for SHAP")

    # --- v1.0 SHAP ---
    print("  Computing v1.0 SHAP values...")
    df_sample["lateness_now"] = 0.0
    X_sample_v0 = df_sample[V1_0_FEATURES].copy()
    for col in CATEGORICAL_COLS_V2:
        if col in X_sample_v0.columns:
            X_sample_v0[col] = X_sample_v0[col].astype("category")
    dsample_v0 = xgb.DMatrix(X_sample_v0, enable_categorical=True)
    contribs_v0 = bst_v1_0.predict(dsample_v0, pred_contribs=True, iteration_range=(0, best_iter + 1))
    assert contribs_v0.shape[1] == len(V1_0_FEATURES) + 1, (
        f"v1.0 contribs shape {contribs_v0.shape[1]} != {len(V1_0_FEATURES) + 1} expected"
    )
    shap_v0 = contribs_v0[:, :-1]  # Drop bias column
    mean_abs_v0 = np.mean(np.abs(shap_v0), axis=0)
    top15_idx_v0 = np.argsort(mean_abs_v0)[::-1][:15]
    top15_names_v0 = [V1_0_FEATURES[i] for i in top15_idx_v0]
    top15_vals_v0 = [float(mean_abs_v0[i]) for i in top15_idx_v0]
    print(f"  v1.0 SHAP computed: {contribs_v0.shape}")

    # --- v1.1 SHAP ---
    print("  Computing v1.1 SHAP values...")
    X_sample_v1 = df_sample[FEATURE_COLS_V2].copy()
    for col in CATEGORICAL_COLS_V2:
        if col in X_sample_v1.columns:
            X_sample_v1[col] = X_sample_v1[col].astype("category")
    dsample_v1 = xgb.DMatrix(X_sample_v1, enable_categorical=True)
    contribs_v1 = bst_v1_1.predict(dsample_v1, pred_contribs=True)
    assert contribs_v1.shape[1] == len(FEATURE_COLS_V2) + 1, (
        f"v1.1 contribs shape {contribs_v1.shape[1]} != {len(FEATURE_COLS_V2) + 1} expected"
    )
    shap_v1 = contribs_v1[:, :-1]  # Drop bias column
    mean_abs_v1 = np.mean(np.abs(shap_v1), axis=0)
    top15_idx_v1 = np.argsort(mean_abs_v1)[::-1][:15]
    top15_names_v1 = [FEATURE_COLS_V2[i] for i in top15_idx_v1]
    top15_vals_v1 = [float(mean_abs_v1[i]) for i in top15_idx_v1]
    print(f"  v1.1 SHAP computed: {contribs_v1.shape}")

    # Console: top 15 for each
    print(f"\n  v1.0 Top 15 Features (mean |SHAP|):")
    for i, (name, val) in enumerate(zip(top15_names_v0, top15_vals_v0), 1):
        print(f"    {i:2d}. {name:42s} {val:.2f}")
    print(f"\n  v1.1 Top 15 Features (mean |SHAP|):")
    for i, (name, val) in enumerate(zip(top15_names_v1, top15_vals_v1), 1):
        print(f"    {i:2d}. {name:42s} {val:.2f}")

    # --- Side-by-side horizontal bar chart ---
    fig, (ax0, ax1) = plt.subplots(1, 2, figsize=(16, 7))

    # v1.0 (left)
    y_pos = np.arange(15)
    ax0.barh(y_pos, top15_vals_v0[::-1], color=COLOR_V1_0, alpha=0.85)
    ax0.set_yticks(y_pos)
    ax0.set_yticklabels(top15_names_v0[::-1], fontsize=9)
    ax0.set_xlabel("Mean |SHAP value|", fontsize=10)
    ax0.set_title("v1.0 Top 15 Features", fontsize=12, fontweight="bold", color=COLOR_V1_0)
    ax0.grid(axis="x", alpha=0.3)

    # v1.1 (right)
    ax1.barh(y_pos, top15_vals_v1[::-1], color=COLOR_V1_1, alpha=0.85)
    ax1.set_yticks(y_pos)
    ax1.set_yticklabels(top15_names_v1[::-1], fontsize=9)
    ax1.set_xlabel("Mean |SHAP value|", fontsize=10)
    ax1.set_title("v1.1 Top 15 Features", fontsize=12, fontweight="bold", color=COLOR_V1_1)
    ax1.grid(axis="x", alpha=0.3)

    fig.suptitle("SHAP Feature Importance Comparison", fontsize=14, fontweight="bold", y=1.02)
    fig.tight_layout()
    chart_b64 = fig_to_base64(fig)

    chart_html = f'<img src="data:image/png;base64,{chart_b64}" alt="SHAP comparison" class="chart-img">'

    # Feature shift narrative
    # Identify features new to v1.1 top 15
    new_in_v1_1 = [f for f in top15_names_v1 if f not in top15_names_v0]
    dropped_from_v1_0 = [f for f in top15_names_v0 if f not in top15_names_v1]

    narrative = '<div class="highlights">'
    narrative += f'<p><strong>Key observation:</strong> v1.1 uses a residual target (deviation from baseline), '
    narrative += f'so SHAP values represent contribution to the residual correction rather than raw ETA prediction.</p>'
    if new_in_v1_1:
        narrative += f'<p><strong>New in v1.1 top 15:</strong> {", ".join(new_in_v1_1)}</p>'
    if dropped_from_v1_0:
        narrative += f'<p><strong>Dropped from v1.0 top 15:</strong> {", ".join(dropped_from_v1_0)}</p>'
    narrative += '</div>'

    html = chart_html + narrative

    return {
        "html": html,
        "top15_v0": list(zip(top15_names_v0, top15_vals_v0)),
        "top15_v1": list(zip(top15_names_v1, top15_vals_v1)),
    }


# ---------------------------------------------------------------------------
# Section 4: Residual Diagnostics
# ---------------------------------------------------------------------------

def section_residuals(data):
    """Residual diagnostics: histogram, tail analysis, MAE vs stops_away, MAE vs hour."""
    print(f"\n{'='*60}")
    print("Section 4: Residual Diagnostics")
    print(f"{'='*60}")

    y_true = data["y_true"]
    pred_v1_1 = data["pred_v1_1"]
    pred_residual = data["pred_residual_v1_1"]
    actual_residual = data["actual_residual"]
    route_ids = data["route_ids"]
    stops_away = data["stops_away"]
    minutes_since_midnight = data["minutes_since_midnight"]

    # Reconstruction errors for each row
    recon_errors = np.abs(pred_v1_1 - y_true)

    # --- 4a. Residual Histogram ---
    print("\n  [4a] Residual distribution...")

    # Stats for predicted and actual residuals
    pred_stats = {
        "mean": float(np.mean(pred_residual)),
        "std": float(np.std(pred_residual)),
        "skew": float(stats.skew(pred_residual)),
        "kurtosis": float(stats.kurtosis(pred_residual)),
    }
    actual_stats = {
        "mean": float(np.mean(actual_residual)),
        "std": float(np.std(actual_residual)),
        "skew": float(stats.skew(actual_residual)),
        "kurtosis": float(stats.kurtosis(actual_residual)),
    }

    print(f"    Predicted residuals -- mean: {pred_stats['mean']:.1f}, std: {pred_stats['std']:.1f}, "
          f"skew: {pred_stats['skew']:.2f}, kurtosis: {pred_stats['kurtosis']:.2f}")
    print(f"    Actual residuals    -- mean: {actual_stats['mean']:.1f}, std: {actual_stats['std']:.1f}, "
          f"skew: {actual_stats['skew']:.2f}, kurtosis: {actual_stats['kurtosis']:.2f}")

    fig, ax = plt.subplots(figsize=(10, 5))
    # Clip to reasonable range for display
    clip_low, clip_high = np.percentile(actual_residual, [1, 99])
    bins = np.linspace(clip_low, clip_high, 80)
    ax.hist(actual_residual, bins=bins, alpha=0.5, label="Actual residuals", color="#E07A5F", density=True)
    ax.hist(pred_residual, bins=bins, alpha=0.5, label="Predicted residuals", color=COLOR_V1_1, density=True)
    ax.axvline(x=0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax.set_xlabel("Residual (seconds)", fontsize=11)
    ax.set_ylabel("Density", fontsize=11)
    ax.set_title("Predicted vs Actual Residual Distribution", fontsize=13, fontweight="bold")
    ax.legend(fontsize=10)

    # Stats text box
    stats_text = (
        f"Predicted: mean={pred_stats['mean']:.1f}, std={pred_stats['std']:.1f}, "
        f"skew={pred_stats['skew']:.2f}, kurt={pred_stats['kurtosis']:.2f}\n"
        f"Actual:    mean={actual_stats['mean']:.1f}, std={actual_stats['std']:.1f}, "
        f"skew={actual_stats['skew']:.2f}, kurt={actual_stats['kurtosis']:.2f}"
    )
    ax.text(0.02, 0.95, stats_text, transform=ax.transAxes, fontsize=8,
            verticalalignment="top", bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8))
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    hist_b64 = fig_to_base64(fig)

    # --- 4b. Tail Analysis ---
    print("\n  [4b] Tail analysis...")

    thresholds = [(300, "5 min"), (600, "10 min"), (900, "15 min")]
    tail_results = []
    for thresh, label in thresholds:
        count = int(np.sum(recon_errors > thresh))
        pct = float(count / len(recon_errors) * 100)
        tail_results.append({"threshold_s": thresh, "label": label, "count": count, "pct": pct})
        print(f"    |error| > {thresh}s ({label}): {count:,} ({pct:.2f}%)")

    # --- 4c. MAE vs stops_away ---
    print("\n  [4c] MAE vs stops_away...")

    unique_stops = sorted(set(stops_away))
    stops_data = []
    for s in unique_stops:
        mask = stops_away == s
        n = int(mask.sum())
        if n >= 50:
            s_mae = mae(y_true[mask], pred_v1_1[mask])
            stops_data.append({"stops_away": s, "mae": s_mae, "n": n})

    print(f"    {len(stops_data)} groups with >= 50 samples (out of {len(unique_stops)} unique stops_away)")

    fig, ax1 = plt.subplots(figsize=(10, 5))
    stops_x = [d["stops_away"] for d in stops_data]
    stops_mae = [d["mae"] for d in stops_data]
    stops_n = [d["n"] for d in stops_data]

    ax2 = ax1.twinx()
    ax2.bar(stops_x, stops_n, alpha=0.2, color="#AAAAAA", label="Sample count", width=0.6)
    ax2.set_ylabel("Sample count", fontsize=10, color="#888888")
    ax2.tick_params(axis="y", labelcolor="#888888")

    ax1.plot(stops_x, stops_mae, "o-", color=COLOR_V1_1, linewidth=2, markersize=5, label="v1.1 MAE", zorder=5)
    ax1.set_xlabel("Stops Away", fontsize=11)
    ax1.set_ylabel("MAE (seconds)", fontsize=11)
    ax1.set_title("MAE vs Stops Away", fontsize=13, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)

    # Combine legends
    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
    fig.tight_layout()
    stops_b64 = fig_to_base64(fig)

    # --- 4d. MAE vs hour ---
    print("\n  [4d] MAE vs hour...")

    hours = (minutes_since_midnight // 60).astype(int)
    unique_hours = sorted(set(hours))
    hour_data = []
    for h in unique_hours:
        mask = hours == h
        n = int(mask.sum())
        if n >= 50:
            h_mae = mae(y_true[mask], pred_v1_1[mask])
            hour_data.append({"hour": h, "mae": h_mae, "n": n})

    print(f"    {len(hour_data)} hours with >= 50 samples")

    fig, ax1 = plt.subplots(figsize=(10, 5))
    hour_x = [d["hour"] for d in hour_data]
    hour_mae = [d["mae"] for d in hour_data]
    hour_n = [d["n"] for d in hour_data]

    ax2 = ax1.twinx()
    ax2.bar(hour_x, hour_n, alpha=0.2, color="#AAAAAA", label="Sample count", width=0.6)
    ax2.set_ylabel("Sample count", fontsize=10, color="#888888")
    ax2.tick_params(axis="y", labelcolor="#888888")

    ax1.plot(hour_x, hour_mae, "o-", color=COLOR_V1_1, linewidth=2, markersize=5, label="v1.1 MAE", zorder=5)
    ax1.set_xlabel("Hour (UTC)", fontsize=11)
    ax1.set_ylabel("MAE (seconds)", fontsize=11)
    ax1.set_title("MAE vs Hour of Day", fontsize=13, fontweight="bold")
    ax1.grid(axis="y", alpha=0.3)

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, fontsize=9, loc="upper left")
    fig.tight_layout()
    hour_b64 = fig_to_base64(fig)

    # --- Build HTML ---
    html = f"""
    <h3>Residual Distribution</h3>
    <img src="data:image/png;base64,{hist_b64}" alt="Residual histogram" class="chart-img">

    <h3>Tail Analysis</h3>
    <p>Percentage of predictions with absolute error exceeding thresholds:</p>
    <table class="data-table compact">
        <thead>
            <tr><th>Threshold</th><th>Count</th><th>% of Total</th></tr>
        </thead>
        <tbody>
    """
    for t in tail_results:
        html += f'<tr><td>|error| &gt; {t["threshold_s"]}s ({t["label"]})</td><td>{t["count"]:,}</td><td>{t["pct"]:.2f}%</td></tr>'
    html += """
        </tbody>
    </table>

    <h3>MAE vs Stops Away</h3>
    """
    html += f'<img src="data:image/png;base64,{stops_b64}" alt="MAE vs stops away" class="chart-img">'

    html += """
    <h3>MAE vs Hour of Day</h3>
    """
    html += f'<img src="data:image/png;base64,{hour_b64}" alt="MAE vs hour" class="chart-img">'

    return {
        "html": html,
        "pred_stats": pred_stats,
        "actual_stats": actual_stats,
        "tail_results": tail_results,
    }


# ---------------------------------------------------------------------------
# HTML Report Template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tiger Transit v1.1 Evaluation Report</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
        background: #F8F9FA;
        color: #1A1A2E;
        line-height: 1.6;
        padding: 20px;
        max-width: 1200px;
        margin: 0 auto;
    }}
    h1 {{
        font-size: 1.8em;
        color: #1A1A2E;
        border-bottom: 3px solid #2D6A4F;
        padding-bottom: 10px;
        margin-bottom: 20px;
    }}
    h2 {{
        font-size: 1.4em;
        color: #2D6A4F;
        margin: 30px 0 15px 0;
        padding-bottom: 5px;
        border-bottom: 1px solid #DEE2E6;
    }}
    h3 {{
        font-size: 1.15em;
        color: #495057;
        margin: 20px 0 10px 0;
    }}
    .metric-cards {{
        display: flex;
        gap: 20px;
        margin: 20px 0;
        flex-wrap: wrap;
    }}
    .metric-card {{
        flex: 1;
        min-width: 200px;
        padding: 20px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
    }}
    .metric-card.baseline {{ background: linear-gradient(135deg, #FFF3E0, #FFE0B2); }}
    .metric-card.v10 {{ background: linear-gradient(135deg, #E3F2FD, #BBDEFB); }}
    .metric-card.v11 {{ background: linear-gradient(135deg, #E8F5E9, #C8E6C9); }}
    .metric-label {{ font-size: 0.85em; color: #666; text-transform: uppercase; letter-spacing: 1px; }}
    .metric-value {{ font-size: 2.2em; font-weight: bold; margin: 5px 0; }}
    .metric-card.baseline .metric-value {{ color: #E65100; }}
    .metric-card.v10 .metric-value {{ color: #5B8DB8; }}
    .metric-card.v11 .metric-value {{ color: #2D6A4F; }}
    .metric-detail {{ font-size: 0.8em; color: #888; }}
    .improvement-banner {{
        background: #2D6A4F;
        color: white;
        padding: 12px 20px;
        border-radius: 8px;
        text-align: center;
        margin: 15px 0 25px 0;
        font-size: 0.95em;
    }}
    .data-table {{
        width: 100%;
        border-collapse: collapse;
        margin: 15px 0;
        font-size: 0.9em;
    }}
    .data-table th {{
        background: #2D6A4F;
        color: white;
        padding: 10px 12px;
        text-align: left;
        font-weight: 600;
    }}
    .data-table td {{
        padding: 8px 12px;
        border-bottom: 1px solid #DEE2E6;
    }}
    .data-table tr:nth-child(even) {{ background: #F8F9FA; }}
    .data-table tr:hover {{ background: #E8F5E9; }}
    .data-table tr.row-win td:last-child {{ color: #2D6A4F; font-weight: bold; }}
    .data-table tr.row-loss td:last-child {{ color: #C62828; font-weight: bold; }}
    .data-table.compact {{ max-width: 500px; }}
    .summary-box {{
        background: #E8F5E9;
        padding: 12px 20px;
        border-radius: 8px;
        margin: 15px 0;
        font-size: 1em;
    }}
    .win-count {{ color: #2D6A4F; font-weight: bold; }}
    .loss-count {{ color: #C62828; font-weight: bold; }}
    .tie-count {{ color: #666; font-weight: bold; }}
    .highlights {{
        background: #FFFDE7;
        border-left: 4px solid #FFD600;
        padding: 12px 16px;
        margin: 15px 0;
        border-radius: 0 6px 6px 0;
    }}
    .highlights p {{ margin: 5px 0; }}
    .highlights .note {{ font-size: 0.85em; color: #888; font-style: italic; }}
    .flag {{
        color: #C62828;
        font-weight: bold;
        cursor: help;
    }}
    .chart-img {{
        max-width: 100%;
        height: auto;
        margin: 10px 0;
        border-radius: 6px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .footer {{
        margin-top: 40px;
        padding-top: 15px;
        border-top: 1px solid #DEE2E6;
        font-size: 0.8em;
        color: #888;
        text-align: center;
    }}
</style>
</head>
<body>

<h1>Tiger Transit v1.1 Evaluation Report</h1>
<p style="color:#666; margin-bottom:20px;">
    XGBoost ETA prediction model comparison: v1.0 (direct) vs v1.1 (residual-target with 4D tiered baselines)
</p>

<h2>1. Headline Comparison</h2>
{section_1}

<h2>2. Per-Route Comparison</h2>
{section_2}

<h2>3. SHAP Feature Importance</h2>
{section_3}

<h2>4. Residual Diagnostics</h2>
{section_4}

<div class="footer">
    Generated by evaluate_v1_1.py | Tiger Transit v1.1 | {timestamp}
</div>

</body>
</html>
"""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    start_time = time.time()

    print("=" * 60)
    print("Tiger Transit v1.1 Evaluation Report")
    print("=" * 60)

    # Load data and compute predictions
    data = load_and_predict()

    # Generate each section
    s1 = section_headline(data)
    s2 = section_per_route(data)
    s3 = section_shap(data)
    s4 = section_residuals(data)

    # Assemble HTML report
    print(f"\n{'='*60}")
    print("Assembling HTML report...")
    print(f"{'='*60}")

    from datetime import datetime
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    html = HTML_TEMPLATE.format(
        section_1=s1["html"],
        section_2=s2["html"],
        section_3=s3["html"],
        section_4=s4["html"],
        timestamp=timestamp,
    )

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS_DIR / "v1_1_evaluation.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    report_size = report_path.stat().st_size
    elapsed = time.time() - start_time

    print(f"\n  Report saved to: {report_path}")
    print(f"  Report size: {report_size:,} bytes ({report_size / 1024:.1f} KB)")

    # Final summary
    print(f"\n{'='*60}")
    print("v1.1 Evaluation Results")
    print(f"{'='*60}")
    print(f"  Baseline-only MAE:  {data['mae_baseline']:.1f}s")
    print(f"  v1.0 MAE:           {data['mae_v1_0']:.1f}s")
    print(f"  v1.1 MAE:           {data['mae_v1_1']:.1f}s")
    print(f"  Improvement vs v1.0: {s1['improv_vs_v0']:.1f}%")
    print(f"  Per-route: {s2['wins']} wins, {s2['losses']} losses, {s2['ties']} ties")
    print(f"  Tail (>5min): {s4['tail_results'][0]['pct']:.2f}%")
    print(f"  Tail (>10min): {s4['tail_results'][1]['pct']:.2f}%")
    print(f"  Elapsed: {elapsed:.1f}s")
    print(f"\n  Report saved to {report_path}")


if __name__ == "__main__":
    main()
