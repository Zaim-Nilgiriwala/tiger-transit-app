"""
train_baseline.py - Train XGBoost baseline ETA model for Tiger Transit.

Trains an XGBoost regressor on featured data, evaluates against a naive
schedule baseline, computes SHAP feature importance via pred_contribs,
and saves all artifacts (model, metrics, SHAP plot).

Usage:
    python scripts/train_baseline.py

Input:
    data/processed/{train,val,test}_featured.parquet

Output:
    models/baseline_v1.ubj          - Trained XGBoost model
    models/baseline_metrics.json    - Full metrics report (overall + sliced)
    models/shap_summary.png         - SHAP feature importance bar chart
"""

import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend for saving plots
import matplotlib.pyplot as plt
import numpy as np
import xgboost as xgb

# ---------------------------------------------------------------------------
# Add scripts/ to path so we can import from build_features
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_features import CATEGORICAL_COLS, FEATURE_COLS, TARGET_COL, load_featured

# ---------------------------------------------------------------------------
# Config
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
NUM_BOOST_ROUND = 2000
EARLY_STOPPING_ROUNDS = 100


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def stops_bucket(s):
    """Assign stops_remaining value to a bucket label."""
    if s == 1:
        return "1"
    elif s <= 3:
        return "2-3"
    elif s <= 6:
        return "4-6"
    else:
        return "7+"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    MODELS_DIR.mkdir(exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load data and create DMatrix objects
    # ------------------------------------------------------------------
    print("Loading featured data...")
    df_train = load_featured("train")
    df_val = load_featured("val")
    df_test = load_featured("test")

    print(f"  train: {df_train.shape}")
    print(f"  val:   {df_val.shape}")
    print(f"  test:  {df_test.shape}")

    # Keep test metadata columns for sliced evaluation
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_remaining = df_test["stops_remaining"].values
    test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)

    y_train = df_train[TARGET_COL].values
    y_val = df_val[TARGET_COL].values
    y_test = df_test[TARGET_COL].values

    dtrain = xgb.DMatrix(
        df_train[FEATURE_COLS], label=y_train, enable_categorical=True
    )
    dval = xgb.DMatrix(
        df_val[FEATURE_COLS], label=y_val, enable_categorical=True
    )
    dtest = xgb.DMatrix(
        df_test[FEATURE_COLS], label=y_test, enable_categorical=True
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
        verbose_eval=50,
    )
    print(f"\nBest iteration: {bst.best_iteration}")
    print(f"Best validation MAE: {bst.best_score:.2f}s")

    # ------------------------------------------------------------------
    # 4. Predict on test set
    # ------------------------------------------------------------------
    y_pred = bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))
    xgb_mae = mae(y_test, y_pred)
    xgb_rmse = rmse(y_test, y_pred)
    improvement_pct = (naive_mae - xgb_mae) / naive_mae * 100

    print(f"\nTest set results:")
    print(f"  XGBoost MAE:  {xgb_mae:.1f}s")
    print(f"  XGBoost RMSE: {xgb_rmse:.1f}s")
    print(f"  Naive MAE:    {naive_mae:.1f}s")
    print(f"  Improvement:  {improvement_pct:.1f}%")

    # ------------------------------------------------------------------
    # 5. Sliced metrics
    # ------------------------------------------------------------------
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

    print(f"\n{'='*60}")
    print("Per stops_remaining bucket:")
    print(f"{'='*60}")
    buckets_order = ["1", "2-3", "4-6", "7+"]
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_remaining])
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
    feature_importance = list(zip(FEATURE_COLS, mean_abs_shap.tolist()))
    feature_importance.sort(key=lambda x: x[1], reverse=True)

    print(f"\n  {'Rank':>4s}  {'Feature':>30s}  {'mean|SHAP|':>12s}")
    print(f"  {'-'*4}  {'-'*30}  {'-'*12}")
    for i, (fname, fval) in enumerate(feature_importance, 1):
        print(f"  {i:>4d}  {fname:>30s}  {fval:>12.2f}")

    # Verify distance_to_target and scheduled_time_to_target are among top features
    top5_names = [f[0] for f in feature_importance[:5]]
    for expected in ["distance_to_target", "scheduled_time_to_target"]:
        if expected in top5_names:
            rank = top5_names.index(expected) + 1
            print(f"\n  OK: {expected} is rank #{rank}")
        else:
            print(f"\n  WARNING: {expected} not in top 5 features! Top 5: {top5_names}")

    # SHAP bar chart
    fig, ax = plt.subplots(figsize=(10, 6))
    names = [f[0] for f in feature_importance]
    values = [f[1] for f in feature_importance]
    y_pos = np.arange(len(names))
    ax.barh(y_pos, values, align="center", color="#4C72B0")
    ax.set_yticks(y_pos)
    ax.set_yticklabels(names)
    ax.invert_yaxis()
    ax.set_xlabel("mean |SHAP value|")
    ax.set_title("Baseline Model - Feature Importance (mean |SHAP|)")
    plt.tight_layout()
    shap_path = MODELS_DIR / "shap_summary.png"
    fig.savefig(shap_path, dpi=150)
    plt.close(fig)
    print(f"\nSaved SHAP plot: {shap_path}")

    # ------------------------------------------------------------------
    # 7. Save artifacts
    # ------------------------------------------------------------------
    # Model
    model_path = MODELS_DIR / "baseline_v1.ubj"
    bst.save_model(str(model_path))
    print(f"Saved model: {model_path}")

    # Metrics JSON
    metrics = {
        "model": "baseline_v1",
        "best_iteration": int(bst.best_iteration),
        "hyperparameters": {k: v for k, v in PARAMS.items()},
        "naive_baseline": {"mae": round(naive_mae, 2), "rmse": round(naive_rmse, 2)},
        "xgboost": {"mae": round(xgb_mae, 2), "rmse": round(xgb_rmse, 2)},
        "improvement_pct": round(improvement_pct, 2),
        "per_route": per_route,
        "per_stops_bucket": per_stops_bucket,
        "top_features_shap": [[f, round(v, 4)] for f, v in feature_importance],
    }
    metrics_path = MODELS_DIR / "baseline_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics: {metrics_path}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    print(f"\n{'='*60}")
    print("TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  Model:       {model_path}")
    print(f"  Metrics:     {metrics_path}")
    print(f"  SHAP plot:   {shap_path}")
    print(f"  XGBoost MAE: {xgb_mae:.1f}s (vs naive {naive_mae:.1f}s, {improvement_pct:.1f}% better)")


if __name__ == "__main__":
    main()
