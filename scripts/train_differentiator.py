"""
train_differentiator.py - Train XGBoost with Phase 4 differentiator features.

Retrains the XGBoost regressor using the expanded v2 feature set (43 features)
and measures improvement over the Phase 3 baseline (394.7s MAE). Uses identical
hyperparameters to the baseline to isolate the impact of new features, with
num_boost_round increased to 3000 (baseline was under-trained at 2000).

Usage:
    python scripts/train_differentiator.py

Input:
    data/processed/{train,val,test}_featured_v2.parquet

Output:
    models/differentiator_v1.ubj          - Trained XGBoost model
    models/differentiator_metrics.json    - Full metrics report + baseline comparison
    models/differentiator_shap.png        - SHAP feature importance bar chart
"""

import json
import sys
from pathlib import Path

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
    PHASE3_FEATURE_COLS,
    PHASE4_FEATURE_COLS,
    TARGET_COL,
    load_featured_v2,
)

# ---------------------------------------------------------------------------
# Config -- same hyperparameters as baseline to isolate feature impact
# ---------------------------------------------------------------------------

MODELS_DIR = Path("models")
PARAMS = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "tree_method": "hist",
    "max_depth": 5,
    "learning_rate": 0.05,
    "min_child_weight": 30,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_alpha": 1.0,
    "reg_lambda": 5.0,
    "max_cat_to_onehot": 10,
    "seed": 42,
}
NUM_BOOST_ROUND = 3000  # up from 2000 (baseline was under-trained)
EARLY_STOPPING_ROUNDS = 100


# ---------------------------------------------------------------------------
# Helpers
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
    """Assign stops_away value to a bucket label."""
    if s == 1:
        return "1"
    elif s <= 3:
        return "2-3"
    elif s <= 6:
        return "4-6"
    else:
        return "7+"


def tod_bucket(hour_ct):
    """Assign Central Time hour to a time-of-day bucket."""
    if 6 <= hour_ct < 11:
        return "morning"
    elif 11 <= hour_ct < 14:
        return "midday"
    elif 14 <= hour_ct < 18:
        return "afternoon"
    else:
        return "evening"


def distance_bucket(dist):
    """Assign distance_to_target to a bucket label."""
    if dist < 1000:
        return "<1km"
    elif dist < 3000:
        return "1-3km"
    elif dist < 5000:
        return "3-5km"
    else:
        return "5km+"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    MODELS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load data and create DMatrix objects
    # ------------------------------------------------------------------
    print("Loading v2 featured data...")
    df_train = load_featured_v2("train")
    df_val = load_featured_v2("val")
    df_test = load_featured_v2("test")

    print(f"  train: {df_train.shape}")
    print(f"  val:   {df_val.shape}")
    print(f"  test:  {df_test.shape}")
    print(f"  Features: {len(FEATURE_COLS_V2)} (Phase 3: {len(PHASE3_FEATURE_COLS)}, Phase 4: {len(PHASE4_FEATURE_COLS)})")

    # Verify feature count
    available_features = [c for c in FEATURE_COLS_V2 if c in df_test.columns]
    missing_features = [c for c in FEATURE_COLS_V2 if c not in df_test.columns]
    if missing_features:
        print(f"  WARNING: Missing features: {missing_features}")
    assert len(available_features) == len(FEATURE_COLS_V2), (
        f"Feature count mismatch! Expected {len(FEATURE_COLS_V2)}, got {len(available_features)}"
    )

    # Keep test metadata columns for sliced evaluation
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_away = df_test["stops_away"].values
    test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)
    test_distances = df_test["distance_to_target"].values.astype(float)
    # Central Time hour for time-of-day slicing
    test_minutes = df_test["minutes_since_midnight"].values
    test_hour_ct = (test_minutes // 60).astype(int)

    y_train = df_train[TARGET_COL].values
    y_val = df_val[TARGET_COL].values
    y_test = df_test[TARGET_COL].values

    dtrain = xgb.DMatrix(
        df_train[FEATURE_COLS_V2], label=y_train, enable_categorical=True
    )
    dval = xgb.DMatrix(
        df_val[FEATURE_COLS_V2], label=y_val, enable_categorical=True
    )
    dtest = xgb.DMatrix(
        df_test[FEATURE_COLS_V2], label=y_test, enable_categorical=True
    )

    print(f"  DMatrix sizes: train={dtrain.num_row()}, val={dval.num_row()}, test={dtest.num_row()}")

    # ------------------------------------------------------------------
    # 2. Naive baseline: predict scheduled_time_to_target
    # ------------------------------------------------------------------
    naive_mae = mae(y_test, test_scheduled)
    naive_rmse = rmse(y_test, test_scheduled)
    print(f"\nNaive baseline (scheduled_time_to_target):")
    print(f"  MAE:  {naive_mae:.1f}s")
    print(f"  RMSE: {naive_rmse:.1f}s")

    # ------------------------------------------------------------------
    # 3. Train XGBoost
    # ------------------------------------------------------------------
    print(f"\nTraining XGBoost (max {NUM_BOOST_ROUND} rounds, early stop {EARLY_STOPPING_ROUNDS})...")
    evals = [(dtrain, "train"), (dval, "val")]
    bst = xgb.train(
        PARAMS,
        dtrain,
        num_boost_round=NUM_BOOST_ROUND,
        evals=evals,
        early_stopping_rounds=EARLY_STOPPING_ROUNDS,
        verbose_eval=100,
    )
    print(f"\nBest iteration: {bst.best_iteration}")
    print(f"Best validation MAE: {bst.best_score:.2f}s")

    # ------------------------------------------------------------------
    # 4. Predict on test set
    # ------------------------------------------------------------------
    y_pred = bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))
    xgb_mae = mae(y_test, y_pred)
    xgb_rmse = rmse(y_test, y_pred)
    xgb_mape = mape(y_test, y_pred)
    improvement_vs_naive = (naive_mae - xgb_mae) / naive_mae * 100

    print(f"\nTest set results:")
    print(f"  XGBoost MAE:  {xgb_mae:.1f}s")
    print(f"  XGBoost RMSE: {xgb_rmse:.1f}s")
    print(f"  XGBoost MAPE: {xgb_mape:.1f}%")
    print(f"  Naive MAE:    {naive_mae:.1f}s")
    print(f"  vs Naive:     {improvement_vs_naive:.1f}%")

    # ------------------------------------------------------------------
    # 5. Sliced metrics
    # ------------------------------------------------------------------

    # Per-route
    print(f"\n{'='*60}")
    print("Per-route metrics:")
    print(f"{'='*60}")
    unique_routes = sorted(set(test_route_ids))
    per_route = {}
    print(f"  {'Route':>8s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for rid in unique_routes:
        mask = test_route_ids == rid
        n = int(mask.sum())
        r_mae = mae(y_test[mask], y_pred[mask])
        r_rmse = rmse(y_test[mask], y_pred[mask])
        per_route[str(rid)] = {"mae": round(r_mae, 2), "rmse": round(r_rmse, 2), "n": n}
        print(f"  {rid:>8d}  {n:>8d}  {r_mae:>8.1f}  {r_rmse:>8.1f}")

    # Per stops_away bucket
    print(f"\n{'='*60}")
    print("Per stops_away bucket:")
    print(f"{'='*60}")
    buckets_order = ["1", "2-3", "4-6", "7+"]
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_away])
    per_stops_bucket = {}
    print(f"  {'Bucket':>8s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*8}  {'-'*8}")
    for b in buckets_order:
        mask = bucket_labels == b
        n = int(mask.sum())
        if n == 0:
            continue
        b_mae = mae(y_test[mask], y_pred[mask])
        b_rmse = rmse(y_test[mask], y_pred[mask])
        per_stops_bucket[b] = {"mae": round(b_mae, 2), "rmse": round(b_rmse, 2), "n": n}
        print(f"  {b:>8s}  {n:>8d}  {b_mae:>8.1f}  {b_rmse:>8.1f}")

    # Per time-of-day bucket
    print(f"\n{'='*60}")
    print("Per time-of-day bucket (Central Time):")
    print(f"{'='*60}")
    tod_order = ["morning", "midday", "afternoon", "evening"]
    tod_labels = np.array([tod_bucket(h) for h in test_hour_ct])
    per_tod = {}
    print(f"  {'TOD':>12s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*8}  {'-'*8}")
    for t in tod_order:
        mask = tod_labels == t
        n = int(mask.sum())
        if n == 0:
            continue
        t_mae = mae(y_test[mask], y_pred[mask])
        t_rmse = rmse(y_test[mask], y_pred[mask])
        per_tod[t] = {"mae": round(t_mae, 2), "rmse": round(t_rmse, 2), "n": n}
        print(f"  {t:>12s}  {n:>8d}  {t_mae:>8.1f}  {t_rmse:>8.1f}")

    # Per distance bucket
    print(f"\n{'='*60}")
    print("Per distance bucket:")
    print(f"{'='*60}")
    dist_order = ["<1km", "1-3km", "3-5km", "5km+"]
    dist_labels = np.array([distance_bucket(d) for d in test_distances])
    per_distance = {}
    print(f"  {'Distance':>10s}  {'N':>8s}  {'MAE':>8s}  {'RMSE':>8s}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*8}  {'-'*8}")
    for d in dist_order:
        mask = dist_labels == d
        n = int(mask.sum())
        if n == 0:
            continue
        d_mae = mae(y_test[mask], y_pred[mask])
        d_rmse = rmse(y_test[mask], y_pred[mask])
        per_distance[d] = {"mae": round(d_mae, 2), "rmse": round(d_rmse, 2), "n": n}
        print(f"  {d:>10s}  {n:>8d}  {d_mae:>8.1f}  {d_rmse:>8.1f}")

    # ------------------------------------------------------------------
    # 6. SHAP feature importance via pred_contribs
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("SHAP Feature Importance (pred_contribs)")
    print(f"{'='*60}")
    shap_values = bst.predict(dtest, pred_contribs=True,
                              iteration_range=(0, bst.best_iteration + 1))
    # Shape: (n_samples, n_features + 1), last col is bias
    feature_shap = shap_values[:, :-1]
    mean_abs_shap = np.mean(np.abs(feature_shap), axis=0)

    # Map to feature names
    feature_importance = list(zip(FEATURE_COLS_V2, mean_abs_shap.tolist()))
    feature_importance.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  {'Rank':>4s}  {'Feature':>40s}  {'mean|SHAP|':>12s}")
    print(f"  {'-'*4}  {'-'*40}  {'-'*12}")
    for i, (fname, fval) in enumerate(feature_importance, 1):
        marker = " *NEW*" if fname in PHASE4_FEATURE_COLS else ""
        print(f"  {i:>4d}  {fname:>40s}  {fval:>12.2f}{marker}")

    # Identify Phase 4 features in top 10
    top10 = feature_importance[:10]
    top10_names = [f[0] for f in top10]
    new_in_top10 = [(f, v, i + 1) for i, (f, v) in enumerate(top10) if f in PHASE4_FEATURE_COLS]

    # SHAP bar chart
    fig, ax = plt.subplots(figsize=(12, 10))
    names = [f[0] for f in feature_importance]
    values = [f[1] for f in feature_importance]
    colors = ["#E74C3C" if f in PHASE4_FEATURE_COLS else "#4C72B0" for f in names]
    y_pos = np.arange(len(names))
    ax.barh(y_pos, values, align="center", color=colors)
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names, fontsize=8)
    ax.invert_yaxis()
    ax.set_xlabel("mean |SHAP value|")
    ax.set_title("Differentiator Model - Feature Importance (mean |SHAP|)\nRed = Phase 4 new features, Blue = Phase 3 features")
    plt.tight_layout()
    shap_path = MODELS_DIR / "differentiator_shap.png"
    fig.savefig(shap_path, dpi=150)
    plt.close(fig)
    print(f"\nSaved SHAP plot: {shap_path}")

    # ------------------------------------------------------------------
    # 7. Baseline comparison
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("Baseline Comparison")
    print(f"{'='*60}")

    baseline_metrics_path = MODELS_DIR / "baseline_metrics.json"
    with open(baseline_metrics_path) as f:
        baseline = json.load(f)

    baseline_mae = baseline["xgboost"]["mae"]
    baseline_rmse = baseline["xgboost"]["rmse"]
    baseline_naive_mae = baseline["naive_baseline"]["mae"]

    improvement_vs_baseline = (baseline_mae - xgb_mae) / baseline_mae * 100
    mae_reduction = baseline_mae - xgb_mae

    print(f"\n  {'Metric':<30s}  {'Baseline':>10s}  {'Differ.':>10s}  {'Change':>10s}")
    print(f"  {'-'*30}  {'-'*10}  {'-'*10}  {'-'*10}")
    print(f"  {'Overall MAE':<30s}  {baseline_mae:>10.1f}  {xgb_mae:>10.1f}  {-mae_reduction:>+10.1f}")
    print(f"  {'Overall RMSE':<30s}  {baseline_rmse:>10.1f}  {xgb_rmse:>10.1f}  {xgb_rmse - baseline_rmse:>+10.1f}")

    # Per-route comparison
    print(f"\n  Per-route MAE comparison:")
    print(f"  {'Route':>8s}  {'Baseline':>10s}  {'Differ.':>10s}  {'Change':>10s}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*10}")
    per_route_comparison = {}
    for rid in sorted(per_route.keys(), key=lambda x: int(x)):
        new_mae = per_route[rid]["mae"]
        if rid in baseline["per_route"]:
            old_mae = baseline["per_route"][rid]["mae"]
            change = new_mae - old_mae
            per_route_comparison[rid] = {
                "baseline_mae": old_mae,
                "differentiator_mae": new_mae,
                "change": round(change, 2),
            }
            print(f"  {rid:>8s}  {old_mae:>10.1f}  {new_mae:>10.1f}  {change:>+10.1f}")
        else:
            per_route_comparison[rid] = {
                "baseline_mae": None,
                "differentiator_mae": new_mae,
                "change": None,
            }
            print(f"  {rid:>8s}  {'N/A':>10s}  {new_mae:>10.1f}  {'N/A':>10s}")

    # Per-bucket comparison
    print(f"\n  Per stops_away bucket MAE comparison:")
    print(f"  {'Bucket':>8s}  {'Baseline':>10s}  {'Differ.':>10s}  {'Change':>10s}")
    print(f"  {'-'*8}  {'-'*10}  {'-'*10}  {'-'*10}")
    per_bucket_comparison = {}
    for b in buckets_order:
        if b in per_stops_bucket and b in baseline["per_stops_bucket"]:
            new_mae_b = per_stops_bucket[b]["mae"]
            old_mae_b = baseline["per_stops_bucket"][b]["mae"]
            change = new_mae_b - old_mae_b
            per_bucket_comparison[b] = {
                "baseline_mae": old_mae_b,
                "differentiator_mae": new_mae_b,
                "change": round(change, 2),
            }
            print(f"  {b:>8s}  {old_mae_b:>10.1f}  {new_mae_b:>10.1f}  {change:>+10.1f}")

    # ------------------------------------------------------------------
    # 8. Save artifacts
    # ------------------------------------------------------------------

    # Model
    model_path = MODELS_DIR / "differentiator_v1.ubj"
    bst.save_model(str(model_path))
    print(f"\nSaved model: {model_path}")

    # Metrics JSON
    metrics = {
        "model": "differentiator_v1",
        "best_iteration": int(bst.best_iteration),
        "num_features": len(FEATURE_COLS_V2),
        "hyperparameters": {k: v for k, v in PARAMS.items()},
        "naive_baseline": {"mae": round(naive_mae, 2), "rmse": round(naive_rmse, 2)},
        "xgboost": {
            "mae": round(xgb_mae, 2),
            "rmse": round(xgb_rmse, 2),
            "mape": round(xgb_mape, 2),
        },
        "improvement_vs_naive_pct": round(improvement_vs_naive, 2),
        "per_route": per_route,
        "per_stops_bucket": per_stops_bucket,
        "per_time_of_day": per_tod,
        "per_distance": per_distance,
        "top_features_shap": [[f, round(v, 4)] for f, v in feature_importance],
        "new_phase4_features_in_top10": [
            {"feature": f, "shap": round(v, 4), "rank": r}
            for f, v, r in new_in_top10
        ],
        "comparison": {
            "baseline_mae": baseline_mae,
            "baseline_rmse": baseline_rmse,
            "differentiator_mae": round(xgb_mae, 2),
            "differentiator_rmse": round(xgb_rmse, 2),
            "mae_reduction": round(mae_reduction, 2),
            "improvement_pct": round(improvement_vs_baseline, 2),
            "per_route": per_route_comparison,
            "per_stops_bucket": per_bucket_comparison,
        },
    }
    metrics_path = MODELS_DIR / "differentiator_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics: {metrics_path}")

    # ------------------------------------------------------------------
    # 9. Print clear summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("=== PHASE 4 RESULTS ===")
    print(f"{'='*60}")
    print(f"  Baseline MAE:        {baseline_mae:.1f}s")
    print(f"  Differentiator MAE:  {xgb_mae:.1f}s")
    print(f"  Improvement:         {improvement_vs_baseline:.1f}% ({mae_reduction:.1f}s reduction)")
    print(f"  Naive MAE:           {naive_mae:.1f}s")
    print(f"  vs Naive:            {improvement_vs_naive:.1f}% improvement")
    print(f"  Best iteration:      {bst.best_iteration} / {NUM_BOOST_ROUND}")

    print(f"\n  Top 5 features (SHAP):")
    for i, (fname, fval) in enumerate(feature_importance[:5], 1):
        marker = " *NEW*" if fname in PHASE4_FEATURE_COLS else ""
        print(f"    {i}. {fname} - {fval:.2f}{marker}")

    if new_in_top10:
        print(f"\n  New Phase 4 features in top 10:")
        for fname, fval, rank in new_in_top10:
            print(f"    - {fname} (rank {rank}, SHAP={fval:.2f})")
    else:
        print(f"\n  No new Phase 4 features in top 10 (all top features are Phase 3)")

    print(f"\n  Progressive improvement chain:")
    print(f"    Naive:          {naive_mae:.1f}s")
    print(f"    Baseline (P3):  {baseline_mae:.1f}s ({(naive_mae - baseline_mae) / naive_mae * 100:.1f}% vs naive)")
    print(f"    Differ. (P4):   {xgb_mae:.1f}s ({improvement_vs_naive:.1f}% vs naive)")

    # Gate check
    if xgb_mae < baseline_mae:
        print(f"\n  PASS: Differentiator MAE ({xgb_mae:.1f}s) < Baseline MAE ({baseline_mae:.1f}s)")
    else:
        print(f"\n  FAIL: Differentiator MAE ({xgb_mae:.1f}s) >= Baseline MAE ({baseline_mae:.1f}s)")

    print(f"\n{'='*60}")
    print("TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  Model:       {model_path}")
    print(f"  Metrics:     {metrics_path}")
    print(f"  SHAP plot:   {shap_path}")


if __name__ == "__main__":
    main()
