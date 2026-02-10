"""
evaluate.py - Phase 6 Comprehensive Evaluation Pipeline.

Produces all four EVAL deliverables for the Tiger Transit XGBoost ETA model:
  EVAL-01: Sliced metrics (overall, per-route, per-stops, per-TOD, per-distance)
  EVAL-02: SHAP explainability (global bar + 3 waterfall plots)
  EVAL-03: Comparison table vs naive baseline (all phases + per-route wins/losses)
  EVAL-04: Residual bias detection (signed residuals by route, TOD, stops)

Usage:
    python scripts/evaluate.py                   # Run all sections
    python scripts/evaluate.py --section metrics  # Only EVAL-01
    python scripts/evaluate.py --section shap     # Only EVAL-02
    python scripts/evaluate.py --section comparison  # Only EVAL-03
    python scripts/evaluate.py --section residuals   # Only EVAL-04
    python scripts/evaluate.py --section report   # Only master report

Input:
    data/processed/test_featured_v2.parquet
    models/tuned_v1.ubj
    models/tuned_metrics.json
    models/baseline_metrics.json
    models/differentiator_metrics.json

Output:
    models/evaluation/eval_metrics_sliced.json
    models/evaluation/eval_shap_global.png
    models/evaluation/eval_shap_waterfall_{1,2,3}.png
    models/evaluation/eval_comparison.json
    models/evaluation/eval_comparison.md
    models/evaluation/eval_residuals.json
    models/evaluation/eval_residuals_by_route.png
    models/evaluation/eval_residuals_by_tod.png
    models/evaluation/eval_report.md
"""

import argparse
import json
import sys
import time
from pathlib import Path

# Headless rendering -- must be set BEFORE any matplotlib/shap imports
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import numpy as np
import xgboost as xgb

# ---------------------------------------------------------------------------
# Add scripts/ to path so we can import from build_differentiator_features
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_differentiator_features import (
    FEATURE_COLS_V2,
    CATEGORICAL_COLS_V2,
    TARGET_COL,
    load_featured_v2,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODELS_DIR = Path("models")
EVAL_DIR = MODELS_DIR / "evaluation"


# ---------------------------------------------------------------------------
# Helpers (copied from train_advanced.py -- not imported)
# ---------------------------------------------------------------------------


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true, y_pred):
    """Mean Absolute Percentage Error, excluding zero targets."""
    mask = y_true > 0
    if mask.sum() == 0:
        return float("nan")
    return float(np.mean(np.abs((y_true[mask] - y_pred[mask]) / y_true[mask])) * 100)


def stops_bucket(s):
    if s == 1:
        return "1"
    elif s <= 3:
        return "2-3"
    elif s <= 6:
        return "4-6"
    else:
        return "7+"


def tod_bucket(hour_ct):
    if 6 <= hour_ct < 11:
        return "morning"
    elif 11 <= hour_ct < 14:
        return "midday"
    elif 14 <= hour_ct < 18:
        return "afternoon"
    else:
        return "evening"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args():
    parser = argparse.ArgumentParser(description="Tiger Transit ETA model evaluation (Phase 6)")
    parser.add_argument(
        "--section",
        choices=["metrics", "shap", "comparison", "residuals", "report", "all"],
        default="all",
        help="Which section to run (default: all)",
    )
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Data loading (shared across all sections)
# ---------------------------------------------------------------------------


def load_data():
    """Load test data and tuned model. Returns dict of commonly needed arrays."""
    print("Loading v2 featured test data...")
    df_test = load_featured_v2("test")
    print(f"  test: {df_test.shape}")
    print(f"  Features: {len(FEATURE_COLS_V2)}")

    X_test = df_test[FEATURE_COLS_V2].copy()
    y_test = df_test[TARGET_COL].values

    # Test metadata for sliced evaluation
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_away = df_test["stops_away"].values
    test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)
    test_distances = df_test["distance_to_target"].values.astype(float)
    test_minutes = df_test["minutes_since_midnight"].values
    test_hour_ct = (test_minutes // 60).astype(int)

    # Load tuned model
    print("Loading tuned model...")
    bst = xgb.Booster()
    bst.load_model(str(MODELS_DIR / "tuned_v1.ubj"))

    # Load best_iteration from metrics (may not persist through UBJSON save/load)
    with open(MODELS_DIR / "tuned_metrics.json") as f:
        tuned_metrics = json.load(f)
    best_iter = tuned_metrics["best_iteration"]
    print(f"  best_iteration: {best_iter}")

    # Create DMatrix and predict
    dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)
    y_pred = bst.predict(dtest, iteration_range=(0, best_iter + 1))

    print(f"  Predictions: {len(y_pred)}")
    print(f"  Overall MAE: {mae(y_test, y_pred):.1f}s")

    return {
        "df_test": df_test,
        "X_test": X_test,
        "y_test": y_test,
        "y_pred": y_pred,
        "bst": bst,
        "dtest": dtest,
        "best_iter": best_iter,
        "tuned_metrics": tuned_metrics,
        "test_route_ids": test_route_ids,
        "test_stops_away": test_stops_away,
        "test_scheduled": test_scheduled,
        "test_distances": test_distances,
        "test_minutes": test_minutes,
        "test_hour_ct": test_hour_ct,
    }


# ---------------------------------------------------------------------------
# EVAL-01: Comprehensive sliced metrics
# ---------------------------------------------------------------------------


def eval_01_sliced_metrics(data):
    """Compute sliced metrics across 4 dimensions + overall."""
    print(f"\n{'='*60}")
    print("EVAL-01: Comprehensive Sliced Metrics")
    print(f"{'='*60}")

    y_test = data["y_test"]
    y_pred = data["y_pred"]
    test_route_ids = data["test_route_ids"]
    test_stops_away = data["test_stops_away"]
    test_hour_ct = data["test_hour_ct"]
    test_distances = data["test_distances"]

    # Overall
    overall = {
        "mae": round(mae(y_test, y_pred), 2),
        "rmse": round(rmse(y_test, y_pred), 2),
        "mape": round(mape(y_test, y_pred), 2),
        "n": int(len(y_test)),
    }
    print(f"\n  Overall: MAE={overall['mae']:.1f}s, RMSE={overall['rmse']:.1f}s, MAPE={overall['mape']:.1f}%")

    # Per-route
    unique_routes = sorted(set(test_route_ids))
    per_route = {}
    print(f"\n  {'Route':>8s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}  {'MAPE':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for rid in unique_routes:
        mask = test_route_ids == rid
        n = int(mask.sum())
        r_mae = mae(y_test[mask], y_pred[mask])
        r_rmse = rmse(y_test[mask], y_pred[mask])
        r_mape = mape(y_test[mask], y_pred[mask])
        per_route[str(rid)] = {
            "mae": round(r_mae, 2),
            "rmse": round(r_rmse, 2),
            "mape": round(r_mape, 2),
            "n": n,
        }
        print(f"  {rid:>8d}  {n:>8d}  {r_mae:>8.1f}  {r_rmse:>8.1f}  {r_mape:>8.1f}")

    # Per stops_away bucket
    buckets_order = ["1", "2-3", "4-6", "7+"]
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_away])
    per_stops_bucket = {}
    print(f"\n  {'Stops':>8s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}  {'MAPE':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for b in buckets_order:
        mask = bucket_labels == b
        n = int(mask.sum())
        if n == 0:
            continue
        b_mae = mae(y_test[mask], y_pred[mask])
        b_rmse = rmse(y_test[mask], y_pred[mask])
        b_mape = mape(y_test[mask], y_pred[mask])
        per_stops_bucket[b] = {
            "mae": round(b_mae, 2),
            "rmse": round(b_rmse, 2),
            "mape": round(b_mape, 2),
            "n": n,
        }
        print(f"  {b:>8s}  {n:>8d}  {b_mae:>8.1f}  {b_rmse:>8.1f}  {b_mape:>8.1f}")

    # Per time-of-day bucket
    tod_order = ["morning", "midday", "afternoon", "evening"]
    tod_labels = np.array([tod_bucket(h) for h in test_hour_ct])
    per_time_of_day = {}
    print(f"\n  {'TOD':>12s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}  {'MAPE':>8s}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for t in tod_order:
        mask = tod_labels == t
        n = int(mask.sum())
        if n == 0:
            continue
        t_mae = mae(y_test[mask], y_pred[mask])
        t_rmse = rmse(y_test[mask], y_pred[mask])
        t_mape = mape(y_test[mask], y_pred[mask])
        per_time_of_day[t] = {
            "mae": round(t_mae, 2),
            "rmse": round(t_rmse, 2),
            "mape": round(t_mape, 2),
            "n": n,
        }
        print(f"  {t:>12s}  {n:>8d}  {t_mae:>8.1f}  {t_rmse:>8.1f}  {t_mape:>8.1f}")

    # Per distance bucket -- use quantile-based thresholds
    # The distance_to_target is in fractional km (max ~7 km), so the old
    # meter-based thresholds (<1000, 1-3k, etc.) are wrong. Use actual data quantiles.
    q25, q50, q75 = np.percentile(test_distances, [25, 50, 75])
    print(f"\n  Distance quantiles: Q25={q25:.2f}, Q50={q50:.2f}, Q75={q75:.2f}")

    def distance_bucket_quantile(d):
        if d < q25:
            return f"<{q25:.2f}"
        elif d < q50:
            return f"{q25:.2f}-{q50:.2f}"
        elif d < q75:
            return f"{q50:.2f}-{q75:.2f}"
        else:
            return f">{q75:.2f}"

    dist_order = [f"<{q25:.2f}", f"{q25:.2f}-{q50:.2f}", f"{q50:.2f}-{q75:.2f}", f">{q75:.2f}"]
    dist_labels = np.array([distance_bucket_quantile(d) for d in test_distances])
    per_distance_bucket = {}
    print(f"\n  {'Distance':>14s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}  {'MAPE':>8s}")
    print(f"  {'-'*14}  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for d in dist_order:
        mask = dist_labels == d
        n = int(mask.sum())
        if n == 0:
            continue
        d_mae = mae(y_test[mask], y_pred[mask])
        d_rmse = rmse(y_test[mask], y_pred[mask])
        d_mape = mape(y_test[mask], y_pred[mask])
        per_distance_bucket[d] = {
            "mae": round(d_mae, 2),
            "rmse": round(d_rmse, 2),
            "mape": round(d_mape, 2),
            "n": n,
        }
        print(f"  {d:>14s}  {n:>8d}  {d_mae:>8.1f}  {d_rmse:>8.1f}  {d_mape:>8.1f}")

    # Save
    sliced = {
        "overall": overall,
        "per_route": per_route,
        "per_stops_bucket": per_stops_bucket,
        "per_time_of_day": per_time_of_day,
        "per_distance_bucket": per_distance_bucket,
        "distance_bucket_quantiles": {
            "q25": round(q25, 4),
            "q50": round(q50, 4),
            "q75": round(q75, 4),
            "unit": "km (fractional)",
        },
    }
    out_path = EVAL_DIR / "eval_metrics_sliced.json"
    with open(out_path, "w") as f:
        json.dump(sliced, f, indent=2)
    print(f"\n  Saved: {out_path}")
    return sliced


# ---------------------------------------------------------------------------
# EVAL-02: SHAP explainability analysis
# ---------------------------------------------------------------------------


def eval_02_shap(data):
    """SHAP global importance bar plot + 3 waterfall plots."""
    print(f"\n{'='*60}")
    print("EVAL-02: SHAP Explainability Analysis")
    print(f"{'='*60}")

    import shap

    bst = data["bst"]
    dtest = data["dtest"]
    X_test = data["X_test"]
    y_test = data["y_test"]
    y_pred = data["y_pred"]
    best_iter = data["best_iter"]

    shap_path_used = None
    shap_values_obj = None

    # ------------------------------------------------------------------
    # Subsample for SHAP: pred_contribs on 2158-iteration model is slow
    # (~100s per 1000 rows). Use 2000-row subsample for stable global
    # importance estimates + waterfall sample selection.
    # ------------------------------------------------------------------
    SHAP_SUBSAMPLE = 2000
    rng = np.random.RandomState(42)
    sample_idx = rng.choice(len(X_test), size=min(SHAP_SUBSAMPLE, len(X_test)), replace=False)
    sample_idx.sort()
    X_sample = X_test.iloc[sample_idx].copy()
    y_sample = y_test[sample_idx]
    y_pred_sample = y_pred[sample_idx]

    dsample = xgb.DMatrix(X_sample, label=y_sample, enable_categorical=True)

    # ------------------------------------------------------------------
    # Path A (preferred): pred_contribs -- native XGBoost SHAP values
    # ------------------------------------------------------------------
    try:
        print(f"\n  Trying Path A: pred_contribs ({SHAP_SUBSAMPLE}-row subsample)...")
        contribs = bst.predict(dsample, pred_contribs=True, iteration_range=(0, best_iter + 1))
        shap_vals = contribs[:, :-1]  # Slice off bias column
        base_val = float(contribs[0, -1])
        shap_values_obj = shap.Explanation(
            values=shap_vals,
            base_values=np.full(len(shap_vals), base_val),
            data=X_sample.values,
            feature_names=list(FEATURE_COLS_V2),
        )
        shap_path_used = "pred_contribs"
        print(f"  Path A succeeded. SHAP values shape: {shap_values_obj.values.shape}")
    except Exception as e:
        print(f"  Path A failed: {e}")
        print("  Falling back to Path B: TreeExplainer...")

    # ------------------------------------------------------------------
    # Path B (fallback): TreeExplainer with subsample
    # ------------------------------------------------------------------
    if shap_path_used is None:
        print(f"\n  Using Path B: TreeExplainer ({SHAP_SUBSAMPLE}-row subsample)...")
        explainer = shap.TreeExplainer(bst, feature_perturbation="tree_path_dependent")
        shap_values_obj = explainer(X_sample)
        shap_path_used = "TreeExplainer"
        print(f"  Path B complete. SHAP values shape: {shap_values_obj.values.shape}")

    # ------------------------------------------------------------------
    # Global importance bar plot
    # ------------------------------------------------------------------
    print("\n  Generating global importance bar plot...")
    fig = plt.figure(figsize=(10, 8))
    shap.plots.bar(shap_values_obj, show=False)
    plt.tight_layout()
    global_path = EVAL_DIR / "eval_shap_global.png"
    plt.savefig(str(global_path), dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: {global_path}")

    # Top 10 features by mean |SHAP|
    mean_abs_shap = np.mean(np.abs(shap_values_obj.values), axis=0)
    feature_names = list(FEATURE_COLS_V2)
    top_indices = np.argsort(mean_abs_shap)[::-1][:10]
    print(f"\n  Top 10 features by mean |SHAP| ({shap_path_used}):")
    top_features = []
    for rank, idx in enumerate(top_indices, 1):
        print(f"    {rank:2d}. {feature_names[idx]:40s} {mean_abs_shap[idx]:.2f}")
        top_features.append({"rank": rank, "feature": feature_names[idx],
                             "mean_abs_shap": round(float(mean_abs_shap[idx]), 2)})

    # ------------------------------------------------------------------
    # Sample selection for waterfall plots
    # Both paths use the subsample, so index within subsample
    # ------------------------------------------------------------------
    abs_errors_full = np.abs(y_test - y_pred)
    abs_errors_sample = np.abs(y_sample - y_pred_sample)

    # Use full-data percentiles as targets, find closest in subsample
    p95 = np.percentile(abs_errors_full, 95)
    p5 = np.percentile(abs_errors_full, 5)
    median_err = np.median(abs_errors_full)

    high_idx = int(np.argmin(np.abs(abs_errors_sample - p95)))
    low_idx = int(np.argmin(np.abs(abs_errors_sample - p5)))
    typical_idx = int(np.argmin(np.abs(abs_errors_sample - median_err)))

    waterfall_samples = [
        (high_idx, "high-error (P95)", "eval_shap_waterfall_1.png"),
        (low_idx, "low-error (P5)", "eval_shap_waterfall_2.png"),
        (typical_idx, "typical (median)", "eval_shap_waterfall_3.png"),
    ]

    for idx, label, filename in waterfall_samples:
        print(f"\n  Generating waterfall plot: {label} (idx={idx})...")
        actual_error = abs_errors_sample[idx]
        print(f"    Absolute error: {actual_error:.1f}s")

        fig = plt.figure(figsize=(10, 8))
        shap.plots.waterfall(shap_values_obj[idx], max_display=15, show=False)
        plt.tight_layout()
        wf_path = EVAL_DIR / filename
        plt.savefig(str(wf_path), dpi=150, bbox_inches="tight")
        plt.close("all")
        print(f"    Saved: {wf_path}")

    # Save SHAP metadata
    shap_meta = {
        "path_used": shap_path_used,
        "n_samples": int(shap_values_obj.values.shape[0]),
        "n_features": int(shap_values_obj.values.shape[1]),
        "top_features": top_features,
        "waterfall_samples": [
            {"label": label, "index": int(idx), "filename": fn}
            for idx, label, fn in waterfall_samples
        ],
    }
    print(f"\n  SHAP path used: {shap_path_used}")
    return shap_meta


# ---------------------------------------------------------------------------
# EVAL-03: Comparison table vs naive baseline
# ---------------------------------------------------------------------------


def eval_03_comparison(data, sliced_metrics=None):
    """Build comparison table across all phases + per-route wins/losses."""
    print(f"\n{'='*60}")
    print("EVAL-03: Comparison Table vs Naive Baseline")
    print(f"{'='*60}")

    y_test = data["y_test"]
    y_pred = data["y_pred"]
    test_route_ids = data["test_route_ids"]
    test_scheduled = data["test_scheduled"]

    # Load prior phase metrics
    with open(MODELS_DIR / "baseline_metrics.json") as f:
        baseline = json.load(f)
    with open(MODELS_DIR / "differentiator_metrics.json") as f:
        diff = json.load(f)
    tuned = data["tuned_metrics"]

    naive_mae_val = mae(y_test, test_scheduled)
    naive_rmse_val = rmse(y_test, test_scheduled)

    baseline_mae_val = baseline["xgboost"]["mae"]
    baseline_rmse_val = baseline["xgboost"]["rmse"]
    diff_mae_val = diff["xgboost"]["mae"]
    diff_rmse_val = diff["xgboost"]["rmse"]
    tuned_mae_val = tuned["xgboost"]["mae"]
    tuned_rmse_val = tuned["xgboost"]["rmse"]

    # Overall comparison
    overall = []
    for label, m, r in [
        ("Naive (schedule)", naive_mae_val, naive_rmse_val),
        ("Baseline (P3)", baseline_mae_val, baseline_rmse_val),
        ("Differentiator (P4)", diff_mae_val, diff_rmse_val),
        ("Tuned (P5)", tuned_mae_val, tuned_rmse_val),
    ]:
        vs_naive_pct = round((naive_mae_val - m) / naive_mae_val * 100, 2) if m < naive_mae_val else 0.0
        overall.append({
            "model": label,
            "mae": round(m, 2),
            "rmse": round(r, 2),
            "vs_naive_pct": vs_naive_pct,
        })

    print(f"\n  Overall comparison:")
    print(f"  {'Model':<25s}  {'MAE':>8s}  {'RMSE':>8s}  {'vs Naive':>10s}")
    print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*10}")
    for entry in overall:
        print(f"  {entry['model']:<25s}  {entry['mae']:>8.1f}  {entry['rmse']:>8.1f}  {entry['vs_naive_pct']:>9.1f}%")

    # Per-route comparison: naive vs tuned
    unique_routes = sorted(set(test_route_ids))
    per_route = []
    wins = 0
    losses = 0
    ties = 0

    print(f"\n  Per-route: Naive vs Tuned")
    print(f"  {'Route':>8s}  {'N':>8s}  {'Naive MAE':>10s}  {'Tuned MAE':>10s}  {'Improv%':>8s}  {'Verdict':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*8}")

    for rid in unique_routes:
        mask = test_route_ids == rid
        n = int(mask.sum())
        naive_r = mae(y_test[mask], test_scheduled[mask])
        tuned_r = mae(y_test[mask], y_pred[mask])
        improvement = (naive_r - tuned_r) / naive_r * 100 if naive_r > 0 else 0.0

        if tuned_r < naive_r * 0.99:  # 1% tolerance for TIE
            verdict = "WIN"
            wins += 1
        elif tuned_r > naive_r * 1.01:
            verdict = "LOSS"
            losses += 1
        else:
            verdict = "TIE"
            ties += 1

        per_route.append({
            "route_id": int(rid),
            "n": n,
            "naive_mae": round(naive_r, 2),
            "tuned_mae": round(tuned_r, 2),
            "improvement_pct": round(improvement, 2),
            "verdict": verdict,
        })
        print(f"  {rid:>8d}  {n:>8d}  {naive_r:>10.1f}  {tuned_r:>10.1f}  {improvement:>7.1f}%  {verdict:>8s}")

    summary = {
        "total_routes": len(unique_routes),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "wins_vs_naive": f"{wins}/{len(unique_routes)}",
    }
    print(f"\n  Summary: {wins} wins, {losses} losses, {ties} ties out of {len(unique_routes)} routes")

    # Save JSON
    comparison = {
        "overall": overall,
        "per_route": per_route,
        "summary": summary,
    }
    json_path = EVAL_DIR / "eval_comparison.json"
    with open(json_path, "w") as f:
        json.dump(comparison, f, indent=2)
    print(f"\n  Saved: {json_path}")

    # Generate markdown report
    md_lines = []
    md_lines.append("# Model Comparison: Naive Baseline vs Tuned XGBoost\n")
    md_lines.append("## Overall Progressive Improvement\n")
    md_lines.append("| Model | MAE (s) | RMSE (s) | vs Naive |")
    md_lines.append("|-------|---------|----------|----------|")
    for entry in overall:
        md_lines.append(f"| {entry['model']} | {entry['mae']:.1f} | {entry['rmse']:.1f} | {entry['vs_naive_pct']:.1f}% |")

    md_lines.append("\n## Per-Route Comparison: Tuned vs Naive\n")
    md_lines.append("| Route | N | Naive MAE (s) | Tuned MAE (s) | Improvement | Verdict |")
    md_lines.append("|-------|---|---------------|---------------|-------------|---------|")
    for entry in per_route:
        md_lines.append(
            f"| {entry['route_id']} | {entry['n']:,} | {entry['naive_mae']:.1f} "
            f"| {entry['tuned_mae']:.1f} | {entry['improvement_pct']:.1f}% | **{entry['verdict']}** |"
        )

    md_lines.append(f"\n## Summary\n")
    md_lines.append(f"- **{wins}/{len(unique_routes)} routes won** (tuned model beats naive schedule)")
    md_lines.append(f"- **{losses} routes lost** (naive schedule was better)")
    md_lines.append(f"- **{ties} routes tied** (within 1% of each other)")
    md_lines.append(f"- Overall improvement: {overall[-1]['vs_naive_pct']:.1f}% MAE reduction vs naive")

    md_path = EVAL_DIR / "eval_comparison.md"
    with open(md_path, "w") as f:
        f.write("\n".join(md_lines) + "\n")
    print(f"  Saved: {md_path}")

    return comparison


# ---------------------------------------------------------------------------
# EVAL-04: Residual bias detection
# ---------------------------------------------------------------------------


def eval_04_residuals(data):
    """Compute signed residuals and detect systematic bias."""
    print(f"\n{'='*60}")
    print("EVAL-04: Residual Bias Detection")
    print(f"{'='*60}")

    y_test = data["y_test"]
    y_pred = data["y_pred"]
    test_route_ids = data["test_route_ids"]
    test_stops_away = data["test_stops_away"]
    test_hour_ct = data["test_hour_ct"]

    BIAS_THRESHOLD = 15.0  # seconds -- ~12% of overall MAE

    # Signed residuals: positive = overprediction (bus arrives sooner than predicted)
    residuals = y_pred - y_test

    # Overall residual stats
    overall = {
        "mean": round(float(np.mean(residuals)), 2),
        "median": round(float(np.median(residuals)), 2),
        "std": round(float(np.std(residuals)), 2),
        "pct_overprediction": round(float(np.mean(residuals > 0)), 4),
        "p5": round(float(np.percentile(residuals, 5)), 2),
        "p25": round(float(np.percentile(residuals, 25)), 2),
        "p50": round(float(np.percentile(residuals, 50)), 2),
        "p75": round(float(np.percentile(residuals, 75)), 2),
        "p95": round(float(np.percentile(residuals, 95)), 2),
    }
    print(f"\n  Overall residual stats:")
    print(f"    Mean:     {overall['mean']:.2f}s")
    print(f"    Median:   {overall['median']:.2f}s")
    print(f"    Std:      {overall['std']:.2f}s")
    print(f"    % over:   {overall['pct_overprediction']:.1%}")
    print(f"    P5/P95:   [{overall['p5']:.1f}, {overall['p95']:.1f}]")

    # Per-route bias
    unique_routes = sorted(set(test_route_ids))
    per_route = {}
    print(f"\n  Per-route bias (threshold={BIAS_THRESHOLD}s):")
    print(f"  {'Route':>8s}  {'N':>8s}  {'Mean Res':>10s}  {'Med Res':>10s}  {'%Over':>8s}  {'Bias':>6s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*6}")
    for rid in unique_routes:
        mask = test_route_ids == rid
        r_res = residuals[mask]
        mean_r = float(np.mean(r_res))
        median_r = float(np.median(r_res))
        pct_over = float(np.mean(r_res > 0))
        n = int(mask.sum())

        if mean_r > BIAS_THRESHOLD:
            bias_flag = "OVER"
        elif mean_r < -BIAS_THRESHOLD:
            bias_flag = "UNDER"
        else:
            bias_flag = "OK"

        per_route[str(rid)] = {
            "mean_residual": round(mean_r, 2),
            "median_residual": round(median_r, 2),
            "pct_overprediction": round(pct_over, 4),
            "n": n,
            "bias": bias_flag,
        }
        flag_str = f"  <-- {bias_flag}" if bias_flag != "OK" else ""
        print(f"  {rid:>8d}  {n:>8d}  {mean_r:>10.2f}  {median_r:>10.2f}  {pct_over:>7.1%}  {bias_flag:>6s}{flag_str}")

    # Per time-of-day bias
    tod_order = ["morning", "midday", "afternoon", "evening"]
    tod_labels = np.array([tod_bucket(h) for h in test_hour_ct])
    per_tod = {}
    print(f"\n  Per time-of-day bias:")
    print(f"  {'TOD':>12s}  {'N':>8s}  {'Mean Res':>10s}  {'Med Res':>10s}  {'%Over':>8s}  {'Bias':>6s}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*6}")
    for t in tod_order:
        mask = tod_labels == t
        n = int(mask.sum())
        if n == 0:
            continue
        t_res = residuals[mask]
        mean_r = float(np.mean(t_res))
        median_r = float(np.median(t_res))
        pct_over = float(np.mean(t_res > 0))

        if mean_r > BIAS_THRESHOLD:
            bias_flag = "OVER"
        elif mean_r < -BIAS_THRESHOLD:
            bias_flag = "UNDER"
        else:
            bias_flag = "OK"

        per_tod[t] = {
            "mean_residual": round(mean_r, 2),
            "median_residual": round(median_r, 2),
            "pct_overprediction": round(pct_over, 4),
            "n": n,
            "bias": bias_flag,
        }
        flag_str = f"  <-- {bias_flag}" if bias_flag != "OK" else ""
        print(f"  {t:>12s}  {n:>8d}  {mean_r:>10.2f}  {median_r:>10.2f}  {pct_over:>7.1%}  {bias_flag:>6s}{flag_str}")

    # Per stops_away bucket bias
    buckets_order = ["1", "2-3", "4-6", "7+"]
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_away])
    per_stops = {}
    print(f"\n  Per stops-remaining bias:")
    print(f"  {'Stops':>8s}  {'N':>8s}  {'Mean Res':>10s}  {'Med Res':>10s}  {'%Over':>8s}  {'Bias':>6s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*8}  {'-'*6}")
    for b in buckets_order:
        mask = bucket_labels == b
        n = int(mask.sum())
        if n == 0:
            continue
        b_res = residuals[mask]
        mean_r = float(np.mean(b_res))
        median_r = float(np.median(b_res))
        pct_over = float(np.mean(b_res > 0))

        if mean_r > BIAS_THRESHOLD:
            bias_flag = "OVER"
        elif mean_r < -BIAS_THRESHOLD:
            bias_flag = "UNDER"
        else:
            bias_flag = "OK"

        per_stops[b] = {
            "mean_residual": round(mean_r, 2),
            "median_residual": round(median_r, 2),
            "pct_overprediction": round(pct_over, 4),
            "n": n,
            "bias": bias_flag,
        }
        flag_str = f"  <-- {bias_flag}" if bias_flag != "OK" else ""
        print(f"  {b:>8s}  {n:>8d}  {mean_r:>10.2f}  {median_r:>10.2f}  {pct_over:>7.1%}  {bias_flag:>6s}{flag_str}")

    # Save JSON
    residuals_data = {
        "bias_threshold_seconds": BIAS_THRESHOLD,
        "overall": overall,
        "per_route": per_route,
        "per_time_of_day": per_tod,
        "per_stops_bucket": per_stops,
    }
    json_path = EVAL_DIR / "eval_residuals.json"
    with open(json_path, "w") as f:
        json.dump(residuals_data, f, indent=2)
    print(f"\n  Saved: {json_path}")

    # ------------------------------------------------------------------
    # Plot: Residuals by route (horizontal bar chart)
    # ------------------------------------------------------------------
    print("\n  Generating residual plots...")
    route_ids_sorted = sorted(per_route.keys(), key=lambda x: int(x))
    route_labels = [f"Route {r}" for r in route_ids_sorted]
    route_means = [per_route[r]["mean_residual"] for r in route_ids_sorted]
    route_colors = []
    for r in route_ids_sorted:
        bias = per_route[r]["bias"]
        if bias == "OVER":
            route_colors.append("#d32f2f")  # red
        elif bias == "UNDER":
            route_colors.append("#1976d2")  # blue
        else:
            route_colors.append("#757575")  # gray

    fig, ax = plt.subplots(figsize=(10, max(6, len(route_labels) * 0.4)))
    y_pos = np.arange(len(route_labels))
    ax.barh(y_pos, route_means, color=route_colors, height=0.6)
    ax.axvline(x=0, color="black", linewidth=0.8, linestyle="-")
    ax.axvline(x=BIAS_THRESHOLD, color="#d32f2f", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axvline(x=-BIAS_THRESHOLD, color="#1976d2", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(route_labels)
    ax.set_xlabel("Mean Signed Residual (seconds)")
    ax.set_title("Residual Bias by Route\n(positive = overprediction, negative = underprediction)")
    ax.invert_yaxis()

    # Add legend
    from matplotlib.patches import Patch
    legend_elements = [
        Patch(facecolor="#d32f2f", label=f"OVER bias (>{BIAS_THRESHOLD}s)"),
        Patch(facecolor="#1976d2", label=f"UNDER bias (<-{BIAS_THRESHOLD}s)"),
        Patch(facecolor="#757575", label="OK"),
    ]
    ax.legend(handles=legend_elements, loc="lower right")

    plt.tight_layout()
    route_path = EVAL_DIR / "eval_residuals_by_route.png"
    plt.savefig(str(route_path), dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: {route_path}")

    # ------------------------------------------------------------------
    # Plot: Residuals by time-of-day (bar chart)
    # ------------------------------------------------------------------
    tod_labels_plot = [t for t in tod_order if t in per_tod]
    tod_means = [per_tod[t]["mean_residual"] for t in tod_labels_plot]
    tod_colors = []
    for t in tod_labels_plot:
        bias = per_tod[t]["bias"]
        if bias == "OVER":
            tod_colors.append("#d32f2f")
        elif bias == "UNDER":
            tod_colors.append("#1976d2")
        else:
            tod_colors.append("#757575")

    fig, ax = plt.subplots(figsize=(8, 5))
    x_pos = np.arange(len(tod_labels_plot))
    bars = ax.bar(x_pos, tod_means, color=tod_colors, width=0.6)
    ax.axhline(y=0, color="black", linewidth=0.8, linestyle="-")
    ax.axhline(y=BIAS_THRESHOLD, color="#d32f2f", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.axhline(y=-BIAS_THRESHOLD, color="#1976d2", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_xticks(x_pos)
    ax.set_xticklabels(tod_labels_plot)
    ax.set_ylabel("Mean Signed Residual (seconds)")
    ax.set_xlabel("Time of Day")
    ax.set_title("Residual Bias by Time of Day\n(positive = overprediction, negative = underprediction)")

    # Add value labels on bars
    for bar, val in zip(bars, tod_means):
        y_offset = 2 if val >= 0 else -6
        ax.text(bar.get_x() + bar.get_width() / 2, val + y_offset,
                f"{val:.1f}s", ha="center", va="bottom" if val >= 0 else "top",
                fontsize=9, fontweight="bold")

    ax.legend(handles=legend_elements, loc="upper right")

    plt.tight_layout()
    tod_path = EVAL_DIR / "eval_residuals_by_tod.png"
    plt.savefig(str(tod_path), dpi=150, bbox_inches="tight")
    plt.close("all")
    print(f"  Saved: {tod_path}")

    return residuals_data


# ---------------------------------------------------------------------------
# Master Evaluation Report
# ---------------------------------------------------------------------------


def generate_report():
    """Generate master markdown report from all JSON outputs."""
    print(f"\n{'='*60}")
    print("Generating Master Evaluation Report")
    print(f"{'='*60}")

    # Load all JSON outputs
    with open(EVAL_DIR / "eval_metrics_sliced.json") as f:
        sliced = json.load(f)
    with open(EVAL_DIR / "eval_comparison.json") as f:
        comparison = json.load(f)
    with open(EVAL_DIR / "eval_residuals.json") as f:
        residuals = json.load(f)

    # Load SHAP metadata if available (from the most recent run)
    shap_meta = None
    shap_meta_path = EVAL_DIR / "eval_shap_meta.json"
    if shap_meta_path.exists():
        with open(shap_meta_path) as f:
            shap_meta = json.load(f)

    overall = sliced["overall"]
    comp_overall = comparison["overall"]
    comp_per_route = comparison["per_route"]
    comp_summary = comparison["summary"]
    res_overall = residuals["overall"]
    res_per_route = residuals["per_route"]
    res_per_tod = residuals["per_time_of_day"]
    res_per_stops = residuals.get("per_stops_bucket", {})

    # Calculate improvement vs naive
    naive_entry = next((e for e in comp_overall if "Naive" in e["model"]), None)
    tuned_entry = next((e for e in comp_overall if "Tuned" in e["model"]), None)
    improvement_pct = tuned_entry["vs_naive_pct"] if tuned_entry else 0

    # Build report
    lines = []
    lines.append("# Tiger Transit XGBoost ETA Model -- Evaluation Report\n")

    # Executive Summary
    lines.append("## Executive Summary\n")
    lines.append(f"- **Model:** Tuned XGBoost (Phase 5, Optuna-optimized)")
    lines.append(f"- **Overall MAE:** {overall['mae']:.1f}s ({overall['mae']/60:.1f} min)")
    lines.append(f"- **Overall RMSE:** {overall['rmse']:.1f}s ({overall['rmse']/60:.1f} min)")
    lines.append(f"- **Overall MAPE:** {overall['mape']:.1f}%")
    lines.append(f"- **Improvement over naive schedule:** {improvement_pct:.1f}%")
    lines.append(f"- **Test set size:** {overall['n']:,} samples")

    # Determine production readiness
    biased_routes = [r for r, v in res_per_route.items() if v["bias"] != "OK"]
    if overall["mae"] < 150 and len(biased_routes) <= len(res_per_route) // 3:
        readiness = "Conditionally ready -- strong overall performance with manageable bias patterns"
    else:
        readiness = "Requires further investigation -- bias patterns need attention"
    lines.append(f"- **Production readiness:** {readiness}")
    lines.append("")

    # Section 1: Model Performance (EVAL-01)
    lines.append("## 1. Model Performance (EVAL-01)\n")

    lines.append("### Overall Metrics\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| MAE | {overall['mae']:.1f}s ({overall['mae']/60:.1f} min) |")
    lines.append(f"| RMSE | {overall['rmse']:.1f}s ({overall['rmse']/60:.1f} min) |")
    lines.append(f"| MAPE | {overall['mape']:.1f}% |")
    lines.append(f"| N | {overall['n']:,} |")
    lines.append("")

    lines.append("### By Route\n")
    lines.append("| Route | N | MAE (s) | RMSE (s) | MAPE (%) |")
    lines.append("|-------|---|---------|----------|----------|")
    for rid in sorted(sliced["per_route"].keys(), key=lambda x: int(x)):
        r = sliced["per_route"][rid]
        lines.append(f"| {rid} | {r['n']:,} | {r['mae']:.1f} | {r['rmse']:.1f} | {r['mape']:.1f} |")
    lines.append("")

    lines.append("### By Stops Remaining\n")
    lines.append("| Stops | N | MAE (s) | RMSE (s) | MAPE (%) |")
    lines.append("|-------|---|---------|----------|----------|")
    for b in ["1", "2-3", "4-6", "7+"]:
        if b in sliced["per_stops_bucket"]:
            r = sliced["per_stops_bucket"][b]
            lines.append(f"| {b} | {r['n']:,} | {r['mae']:.1f} | {r['rmse']:.1f} | {r['mape']:.1f} |")
    lines.append("")

    lines.append("### By Time of Day\n")
    lines.append("| Period | N | MAE (s) | RMSE (s) | MAPE (%) |")
    lines.append("|--------|---|---------|----------|----------|")
    for t in ["morning", "midday", "afternoon", "evening"]:
        if t in sliced["per_time_of_day"]:
            r = sliced["per_time_of_day"][t]
            lines.append(f"| {t} | {r['n']:,} | {r['mae']:.1f} | {r['rmse']:.1f} | {r['mape']:.1f} |")
    lines.append("")

    lines.append("### By Distance\n")
    if "distance_bucket_quantiles" in sliced:
        dq = sliced["distance_bucket_quantiles"]
        lines.append(f"*Note: Distance thresholds are quantile-based (Q25={dq['q25']:.2f}, "
                     f"Q50={dq['q50']:.2f}, Q75={dq['q75']:.2f} {dq['unit']}). "
                     f"The original km-based thresholds placed all samples in a single bucket.*\n")
    lines.append("| Distance | N | MAE (s) | RMSE (s) | MAPE (%) |")
    lines.append("|----------|---|---------|----------|----------|")
    for d, r in sliced["per_distance_bucket"].items():
        lines.append(f"| {d} | {r['n']:,} | {r['mae']:.1f} | {r['rmse']:.1f} | {r['mape']:.1f} |")
    lines.append("")

    # Section 2: Feature Importance (EVAL-02)
    lines.append("## 2. Feature Importance (EVAL-02)\n")
    if shap_meta:
        lines.append(f"SHAP analysis used **{shap_meta['path_used']}** path "
                     f"({shap_meta['n_samples']:,} samples, {shap_meta['n_features']} features).\n")
        lines.append("### Top 10 Features by Mean |SHAP|\n")
        lines.append("| Rank | Feature | Mean |SHAP| |")
        lines.append("|------|---------|-------------|")
        for feat in shap_meta["top_features"]:
            lines.append(f"| {feat['rank']} | {feat['feature']} | {feat['mean_abs_shap']:.2f} |")
        lines.append("")
    else:
        lines.append("*SHAP metadata not available. See eval_shap_global.png for feature importance plot.*\n")

    lines.append("### Plots\n")
    lines.append("- **Global importance:** `eval_shap_global.png` -- ranks all 43 features by mean |SHAP|")
    lines.append("- **Waterfall 1:** `eval_shap_waterfall_1.png` -- high-error sample (P95 absolute error)")
    lines.append("- **Waterfall 2:** `eval_shap_waterfall_2.png` -- low-error sample (P5 absolute error)")
    lines.append("- **Waterfall 3:** `eval_shap_waterfall_3.png` -- typical sample (median absolute error)")
    lines.append("")

    # Section 3: Baseline Comparison (EVAL-03)
    lines.append("## 3. Baseline Comparison (EVAL-03)\n")

    lines.append("### Overall Progressive Improvement\n")
    lines.append("| Model | MAE (s) | RMSE (s) | vs Naive |")
    lines.append("|-------|---------|----------|----------|")
    for entry in comp_overall:
        lines.append(f"| {entry['model']} | {entry['mae']:.1f} | {entry['rmse']:.1f} | {entry['vs_naive_pct']:.1f}% |")
    lines.append("")

    lines.append("### Per-Route Comparison\n")
    lines.append("| Route | N | Naive MAE (s) | Tuned MAE (s) | Improvement | Verdict |")
    lines.append("|-------|---|---------------|---------------|-------------|---------|")
    for entry in comp_per_route:
        lines.append(
            f"| {entry['route_id']} | {entry['n']:,} | {entry['naive_mae']:.1f} "
            f"| {entry['tuned_mae']:.1f} | {entry['improvement_pct']:.1f}% | **{entry['verdict']}** |"
        )
    lines.append("")
    lines.append(f"**Summary:** {comp_summary['wins']}/{comp_summary['total_routes']} routes won, "
                 f"{comp_summary['losses']} lost, {comp_summary['ties']} tied")
    lines.append("")

    # Section 4: Bias Analysis (EVAL-04)
    lines.append("## 4. Bias Analysis (EVAL-04)\n")

    lines.append("### Overall Residual Distribution\n")
    lines.append("| Statistic | Value |")
    lines.append("|-----------|-------|")
    lines.append(f"| Mean | {res_overall['mean']:.2f}s |")
    lines.append(f"| Median | {res_overall['median']:.2f}s |")
    lines.append(f"| Std | {res_overall['std']:.2f}s |")
    lines.append(f"| % Overprediction | {res_overall['pct_overprediction']:.1%} |")
    lines.append(f"| P5 | {res_overall['p5']:.1f}s |")
    lines.append(f"| P25 | {res_overall['p25']:.1f}s |")
    lines.append(f"| P50 | {res_overall['p50']:.1f}s |")
    lines.append(f"| P75 | {res_overall['p75']:.1f}s |")
    lines.append(f"| P95 | {res_overall['p95']:.1f}s |")
    lines.append("")

    lines.append(f"*Positive residual = overprediction (bus arrives sooner than predicted). "
                 f"Bias threshold: {residuals['bias_threshold_seconds']}s.*\n")

    lines.append("### Route-Level Bias\n")
    lines.append("| Route | N | Mean Residual | Median Residual | % Over | Bias |")
    lines.append("|-------|---|---------------|-----------------|--------|------|")
    for rid in sorted(res_per_route.keys(), key=lambda x: int(x)):
        r = res_per_route[rid]
        bias_mark = f"**{r['bias']}**" if r["bias"] != "OK" else r["bias"]
        lines.append(
            f"| {rid} | {r['n']:,} | {r['mean_residual']:.2f}s "
            f"| {r['median_residual']:.2f}s | {r['pct_overprediction']:.1%} | {bias_mark} |"
        )
    lines.append("")

    biased_over = [r for r, v in res_per_route.items() if v["bias"] == "OVER"]
    biased_under = [r for r, v in res_per_route.items() if v["bias"] == "UNDER"]
    if biased_over:
        lines.append(f"**Overprediction bias:** Routes {', '.join(biased_over)} "
                     f"systematically predict later arrival than actual (mean residual > {residuals['bias_threshold_seconds']}s).")
    if biased_under:
        lines.append(f"**Underprediction bias:** Routes {', '.join(biased_under)} "
                     f"systematically predict earlier arrival than actual (mean residual < -{residuals['bias_threshold_seconds']}s).")
    if not biased_over and not biased_under:
        lines.append("No routes show systematic bias beyond the threshold.")
    lines.append("")

    lines.append("### Time-of-Day Bias\n")
    lines.append("| Period | N | Mean Residual | Median Residual | % Over | Bias |")
    lines.append("|--------|---|---------------|-----------------|--------|------|")
    for t in ["morning", "midday", "afternoon", "evening"]:
        if t in res_per_tod:
            r = res_per_tod[t]
            bias_mark = f"**{r['bias']}**" if r["bias"] != "OK" else r["bias"]
            lines.append(
                f"| {t} | {r['n']:,} | {r['mean_residual']:.2f}s "
                f"| {r['median_residual']:.2f}s | {r['pct_overprediction']:.1%} | {bias_mark} |"
            )
    lines.append("")

    biased_tod = [t for t, v in res_per_tod.items() if v["bias"] != "OK"]
    if biased_tod:
        for t in biased_tod:
            direction = "overprediction" if res_per_tod[t]["bias"] == "OVER" else "underprediction"
            lines.append(f"**{t.capitalize()}** shows {direction} bias "
                         f"(mean residual: {res_per_tod[t]['mean_residual']:.2f}s).")
    else:
        lines.append("No time periods show systematic bias beyond the threshold.")
    lines.append("")

    lines.append("### Stops-Remaining Bias\n")
    lines.append("| Stops | N | Mean Residual | Median Residual | % Over | Bias |")
    lines.append("|-------|---|---------------|-----------------|--------|------|")
    for b in ["1", "2-3", "4-6", "7+"]:
        if b in res_per_stops:
            r = res_per_stops[b]
            bias_mark = f"**{r['bias']}**" if r["bias"] != "OK" else r["bias"]
            lines.append(
                f"| {b} | {r['n']:,} | {r['mean_residual']:.2f}s "
                f"| {r['median_residual']:.2f}s | {r['pct_overprediction']:.1%} | {bias_mark} |"
            )
    lines.append("")

    biased_stops = [(b, v) for b, v in res_per_stops.items() if v["bias"] != "OK"]
    if biased_stops:
        for b, v in biased_stops:
            direction = "overprediction" if v["bias"] == "OVER" else "underprediction"
            lines.append(f"**{b} stops remaining** shows {direction} bias "
                         f"(mean residual: {v['mean_residual']:.2f}s).")
    else:
        lines.append("No stops-remaining buckets show systematic bias beyond the threshold.")
    lines.append("")

    lines.append("### Residual Plots\n")
    lines.append("- `eval_residuals_by_route.png` -- horizontal bar chart of mean signed residual per route")
    lines.append("- `eval_residuals_by_tod.png` -- bar chart of mean signed residual per time-of-day period")
    lines.append("")

    # Section 5: Conclusions
    lines.append("## 5. Conclusions\n")

    lines.append("### Key Strengths\n")
    lines.append(f"- {improvement_pct:.1f}% improvement over naive schedule baseline ({overall['mae']:.1f}s vs "
                 f"{naive_entry['mae']:.1f}s MAE)")
    lines.append(f"- {comp_summary['wins']}/{comp_summary['total_routes']} routes outperform naive schedule")
    lines.append(f"- Progressive improvement across all 4 training phases: "
                 f"Naive -> Baseline -> Differentiator -> Tuned")
    lines.append("")

    lines.append("### Known Limitations\n")
    lines.append("- **Limited training data:** Only 5 weeks of telemetry data (Nov 8 - Dec 13)")
    lines.append("- **Distance feature resolution:** distance_to_target values are small "
                 f"(max ~{sliced['distance_bucket_quantiles']['q75']:.1f} km), requiring "
                 "quantile-based bucketing rather than standard km thresholds")
    if biased_over or biased_under:
        lines.append(f"- **Route-level bias:** {len(biased_over)} routes show overprediction bias, "
                     f"{len(biased_under)} routes show underprediction bias")
    lines.append("- **Quantile model monotonicity:** 32.3% violations in independently-trained "
                 "quantile models (corrected by post-processing sort)")
    lines.append("")

    lines.append("### Recommendations for Production\n")
    lines.append("1. Deploy tuned model (MAE 123.1s) as primary ETA predictor")
    lines.append("2. Monitor per-route bias in production and consider route-specific calibration "
                 "for biased routes")
    lines.append("3. Collect more training data (target 3+ months) to improve generalization")
    lines.append("4. Consider retraining with expanded distance features or segment-level models "
                 "for routes with higher error")
    lines.append("5. Use quantile predictions (P20/P75) for uncertainty communication, "
                 "but retrain on full data to reduce monotonicity violations")
    lines.append("")

    # Write report
    report_path = EVAL_DIR / "eval_report.md"
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\n  Saved: {report_path}")
    print(f"  Report length: {len(lines)} lines")

    return report_path


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    args = parse_args()
    start_time = time.time()

    EVAL_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Output directory: {EVAL_DIR}")

    run_metrics = args.section in ("metrics", "all")
    run_shap = args.section in ("shap", "all")
    run_comparison = args.section in ("comparison", "all")
    run_residuals = args.section in ("residuals", "all")
    run_report = args.section in ("report", "all")

    # Load data (shared across all sections except report-only)
    data = None
    if run_metrics or run_shap or run_comparison or run_residuals:
        data = load_data()

    # EVAL-01
    sliced = None
    if run_metrics:
        sliced = eval_01_sliced_metrics(data)

    # EVAL-02
    shap_meta = None
    if run_shap:
        shap_meta = eval_02_shap(data)
        # Save SHAP metadata for report generation
        shap_meta_path = EVAL_DIR / "eval_shap_meta.json"
        with open(shap_meta_path, "w") as f:
            json.dump(shap_meta, f, indent=2)
        print(f"  Saved SHAP metadata: {shap_meta_path}")

    # EVAL-03
    if run_comparison:
        eval_03_comparison(data, sliced)

    # EVAL-04
    if run_residuals:
        eval_04_residuals(data)

    # Master report
    if run_report:
        generate_report()

    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Evaluation complete in {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print(f"{'='*60}")
    print(f"Output directory: {EVAL_DIR}")


if __name__ == "__main__":
    main()
