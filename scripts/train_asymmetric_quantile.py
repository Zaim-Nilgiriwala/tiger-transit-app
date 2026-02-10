"""
train_asymmetric_quantile.py - Asymmetric loss retraining and quantile models.

Phase 5 Plan 02: Takes Optuna-best hyperparameters from Plan 01, retrains with
custom 3:1 asymmetric objective (8-minute proximity scaling), trains P20/P50/P75
quantile models, and generates the full Phase 5 comparison table.

Usage:
    python scripts/train_asymmetric_quantile.py                    # Run all sections
    python scripts/train_asymmetric_quantile.py --section quantile # Quantile + comparison only
    python scripts/train_asymmetric_quantile.py --section comparison # Comparison table only
    python scripts/train_asymmetric_quantile.py --subsample-frac 0.25 # Use 25% subsample

Input:
    data/processed/{train,val,test}_featured_v2.parquet
    models/tuned_metrics.json (best_params from Plan 01)

Output:
    models/asymmetric_v1.ubj           - Asymmetric loss model
    models/asymmetric_metrics.json     - Asymmetric model metrics
    models/quantile_p{20,50,75}_v1.ubj - Quantile models
    models/quantile_metrics.json       - Quantile evaluation metrics
    models/phase5_comparison.json      - Full progressive comparison
"""

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import xgboost as xgb

# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_differentiator_features import (
    FEATURE_COLS_V2,
    TARGET_COL,
    load_featured_v2,
)

MODELS_DIR = Path("models")
SEED = 42
EARLY_STOPPING_ROUNDS = 100

FIXED_PARAMS = {
    "tree_method": "hist",
    "device": "cuda",
    "max_cat_to_onehot": 10,
    "seed": SEED,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def mae(y_true, y_pred):
    return float(np.mean(np.abs(y_true - y_pred)))


def rmse(y_true, y_pred):
    return float(np.sqrt(np.mean((y_true - y_pred) ** 2)))


def mape(y_true, y_pred):
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


def distance_bucket(dist):
    if dist < 1000:
        return "<1km"
    elif dist < 3000:
        return "1-3km"
    elif dist < 5000:
        return "3-5km"
    else:
        return "5km+"


def compute_sliced_metrics(y_true, y_pred, test_route_ids, test_stops_away, test_hour_ct, test_distances):
    """Compute per-route, per-stops, per-tod, per-distance metrics."""
    # Per-route
    per_route = {}
    for rid in sorted(set(test_route_ids)):
        mask = test_route_ids == rid
        n = int(mask.sum())
        per_route[str(rid)] = {"mae": round(mae(y_true[mask], y_pred[mask]), 2),
                               "rmse": round(rmse(y_true[mask], y_pred[mask]), 2), "n": n}

    # Per stops_away bucket
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_away])
    per_stops = {}
    for b in ["1", "2-3", "4-6", "7+"]:
        mask = bucket_labels == b
        n = int(mask.sum())
        if n > 0:
            per_stops[b] = {"mae": round(mae(y_true[mask], y_pred[mask]), 2),
                            "rmse": round(rmse(y_true[mask], y_pred[mask]), 2), "n": n}

    # Per time-of-day
    tod_labels = np.array([tod_bucket(h) for h in test_hour_ct])
    per_tod = {}
    for t in ["morning", "midday", "afternoon", "evening"]:
        mask = tod_labels == t
        n = int(mask.sum())
        if n > 0:
            per_tod[t] = {"mae": round(mae(y_true[mask], y_pred[mask]), 2),
                          "rmse": round(rmse(y_true[mask], y_pred[mask]), 2), "n": n}

    # Per distance
    dist_labels = np.array([distance_bucket(d) for d in test_distances])
    per_distance = {}
    for d in ["<1km", "1-3km", "3-5km", "5km+"]:
        mask = dist_labels == d
        n = int(mask.sum())
        if n > 0:
            per_distance[d] = {"mae": round(mae(y_true[mask], y_pred[mask]), 2),
                               "rmse": round(rmse(y_true[mask], y_pred[mask]), 2), "n": n}

    return per_route, per_stops, per_tod, per_distance


# ---------------------------------------------------------------------------
# Asymmetric loss
# ---------------------------------------------------------------------------

def make_asymmetric_objective(alpha=3.0, threshold_seconds=480):
    """
    Asymmetric loss: penalize overestimation (pred > actual) more heavily.
    Overestimation = predicting bus is further away than it actually is.
    Proximity scaling: penalty increases as predicted time decreases.
    """
    def asymmetric_obj(predt: np.ndarray, dtrain: xgb.DMatrix):
        y = dtrain.get_label()
        residual = predt - y  # positive = overestimation
        is_over = (residual > 0).astype(float)

        # Base weight: 1.0 for underestimation, alpha for overestimation
        weight = 1.0 + (alpha - 1.0) * is_over

        # Proximity scaling: ramp up when predicted time is short
        proximity_scale = np.clip(
            1.0 + (alpha - 1.0) * (1.0 - predt / threshold_seconds), 1.0, alpha
        )
        # Only apply proximity scaling to overestimation
        weight = np.where(is_over > 0, weight * proximity_scale, weight)

        grad = weight * residual
        hess = weight * np.ones_like(y)  # Must be positive
        return grad, hess
    return asymmetric_obj


def mae_eval(predt, dtrain):
    """Custom eval metric for early stopping during asymmetric training."""
    y = dtrain.get_label()
    return "mae", float(np.mean(np.abs(predt - y)))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(description="Asymmetric loss + quantile model training")
    parser.add_argument("--section", choices=["all", "asymmetric", "quantile", "comparison"],
                        default="all", help="Which section(s) to run")
    parser.add_argument("--subsample-frac", type=float, default=0.25,
                        help="Fraction of training data to use (default: 0.25 for speed)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()
    start_time = time.time()

    run_asymmetric = args.section in ("all", "asymmetric")
    run_quantile = args.section in ("all", "quantile")
    run_comparison = args.section in ("all", "quantile", "comparison")

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("Loading v2 featured data...")
    df_train = load_featured_v2("train")
    df_val = load_featured_v2("val")
    df_test = load_featured_v2("test")

    print(f"  train (full): {df_train.shape}")
    print(f"  val (full):   {df_val.shape}")
    print(f"  test:  {df_test.shape}")

    # Subsample training/validation data for speed
    subsample_frac = args.subsample_frac
    if subsample_frac < 1.0:
        rng = np.random.RandomState(SEED)
        train_idx = rng.choice(len(df_train), size=int(len(df_train) * subsample_frac), replace=False)
        train_idx.sort()
        val_idx = rng.choice(len(df_val), size=int(len(df_val) * subsample_frac), replace=False)
        val_idx.sort()
        df_train = df_train.iloc[train_idx].reset_index(drop=True)
        df_val = df_val.iloc[val_idx].reset_index(drop=True)
        print(f"  train (subsampled {subsample_frac:.0%}): {df_train.shape}")
        print(f"  val (subsampled {subsample_frac:.0%}):   {df_val.shape}")

    X_train = df_train[FEATURE_COLS_V2].copy()
    y_train = df_train[TARGET_COL].values
    X_val = df_val[FEATURE_COLS_V2].copy()
    y_val = df_val[TARGET_COL].values
    X_test = df_test[FEATURE_COLS_V2].copy()
    y_test = df_test[TARGET_COL].values

    # Test metadata for sliced evaluation (always use full test set)
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_away = df_test["stops_away"].values
    test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)
    test_distances = df_test["distance_to_target"].values.astype(float)
    test_minutes = df_test["minutes_since_midnight"].values
    test_hour_ct = (test_minutes // 60).astype(int)

    # Build DMatrix objects
    dtrain = xgb.DMatrix(X_train, label=y_train, enable_categorical=True)
    dval = xgb.DMatrix(X_val, label=y_val, enable_categorical=True)
    dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)

    # ------------------------------------------------------------------
    # 2. Load best params from Plan 01
    # ------------------------------------------------------------------
    print("\nLoading best params from tuned_metrics.json...")
    with open(MODELS_DIR / "tuned_metrics.json") as f:
        tuned = json.load(f)

    best_params = tuned["best_params"]
    best_num_boost_round = tuned["best_num_boost_round"]
    print(f"  Best params: {best_params}")
    print(f"  Best num_boost_round: {best_num_boost_round}")

    # ==================================================================
    # SECTION A: ASYMMETRIC LOSS MODEL
    # ==================================================================
    if run_asymmetric:
        print(f"\n{'='*60}")
        print("SECTION A: Asymmetric Loss Retraining")
        print(f"{'='*60}")

        asym_params = {
            **FIXED_PARAMS,
            **best_params,
            "disable_default_eval_metric": True,
        }
        # Remove objective/eval_metric -- we supply custom
        asym_params.pop("objective", None)
        asym_params.pop("eval_metric", None)

        # Use 5x Optuna rounds for final retrain with early stopping
        asym_num_rounds = min(best_num_boost_round * 5, 3000)

        print(f"\nTraining asymmetric model (alpha=3.0, threshold=480s)...")
        print(f"  num_boost_round: {asym_num_rounds}, early_stopping: {EARLY_STOPPING_ROUNDS}")
        print(f"  Training subsample: {subsample_frac:.0%}")

        bst_asym = xgb.train(
            asym_params,
            dtrain,
            num_boost_round=asym_num_rounds,
            obj=make_asymmetric_objective(alpha=3.0, threshold_seconds=480),
            evals=[(dtrain, "train"), (dval, "val")],
            custom_metric=mae_eval,
            early_stopping_rounds=EARLY_STOPPING_ROUNDS,
            verbose_eval=100,
        )

        print(f"\nBest iteration: {bst_asym.best_iteration}")

        # Evaluate asymmetric model on FULL test set
        y_pred_asym = bst_asym.predict(dtest, iteration_range=(0, bst_asym.best_iteration + 1))
        asym_mae = mae(y_test, y_pred_asym)
        asym_rmse_val = rmse(y_test, y_pred_asym)
        asym_mape = mape(y_test, y_pred_asym)

        # Residual analysis
        residuals = y_pred_asym - y_test  # positive = overestimation
        median_residual = float(np.median(residuals))
        overestimation_rate = float(np.mean(residuals > 0))

        residual_distribution = {
            "mean": round(float(np.mean(residuals)), 2),
            "std": round(float(np.std(residuals)), 2),
            "p10": round(float(np.percentile(residuals, 10)), 2),
            "p25": round(float(np.percentile(residuals, 25)), 2),
            "p50": round(float(np.percentile(residuals, 50)), 2),
            "p75": round(float(np.percentile(residuals, 75)), 2),
            "p90": round(float(np.percentile(residuals, 90)), 2),
        }

        print(f"\nAsymmetric model test results:")
        print(f"  MAE:  {asym_mae:.1f}s")
        print(f"  RMSE: {asym_rmse_val:.1f}s")
        print(f"  MAPE: {asym_mape:.1f}%")
        print(f"  Median residual: {median_residual:.2f}s ({'negative (conservative)' if median_residual < 0 else 'positive (risky)'})")
        print(f"  Overestimation rate: {overestimation_rate:.1%}")
        print(f"  Residual distribution: {residual_distribution}")

        # Sliced metrics
        per_route_a, per_stops_a, per_tod_a, per_dist_a = compute_sliced_metrics(
            y_test, y_pred_asym, test_route_ids, test_stops_away, test_hour_ct, test_distances
        )

        # Save asymmetric model
        asym_model_path = MODELS_DIR / "asymmetric_v1.ubj"
        bst_asym.save_model(str(asym_model_path))
        print(f"\nSaved: {asym_model_path}")

        # Save asymmetric metrics
        asym_metrics = {
            "model": "asymmetric_v1",
            "best_iteration": int(bst_asym.best_iteration),
            "alpha": 3.0,
            "threshold_seconds": 480,
            "training_subsample_frac": subsample_frac,
            "xgboost": {
                "mae": round(asym_mae, 2),
                "rmse": round(asym_rmse_val, 2),
                "mape": round(asym_mape, 2),
            },
            "median_residual": round(median_residual, 2),
            "overestimation_rate": round(overestimation_rate, 4),
            "residual_distribution": residual_distribution,
            "per_route": per_route_a,
            "per_stops_bucket": per_stops_a,
            "per_time_of_day": per_tod_a,
            "per_distance": per_dist_a,
            "hyperparameters": best_params,
        }
        asym_metrics_path = MODELS_DIR / "asymmetric_metrics.json"
        with open(asym_metrics_path, "w") as f:
            json.dump(asym_metrics, f, indent=2)
        print(f"Saved: {asym_metrics_path}")
    else:
        print("\nSkipping Section A (asymmetric) -- using existing artifacts")

    # ==================================================================
    # SECTION B: QUANTILE MODELS
    # ==================================================================
    if run_quantile:
        print(f"\n{'='*60}")
        print("SECTION B: Quantile Model Training (P20, P50, P75)")
        print(f"{'='*60}")
        print(f"  Training subsample: {subsample_frac:.0%}")

        quantiles = [0.20, 0.50, 0.75]
        quantile_preds = {}
        quantile_maes = {}

        # Build QuantileDMatrix for train/val
        Xy_train = xgb.QuantileDMatrix(X_train, y_train, enable_categorical=True)
        Xy_val = xgb.QuantileDMatrix(X_val, y_val, ref=Xy_train, enable_categorical=True)

        for q in quantiles:
            label = f"p{int(q * 100)}"
            print(f"\nTraining {label} quantile model (alpha={q})...")

            q_params = {
                **FIXED_PARAMS,
                **best_params,
                "objective": "reg:quantileerror",
                "quantile_alpha": q,
                "eval_metric": "mae",
            }

            q_num_rounds = min(best_num_boost_round * 5, 3000)

            bst_q = xgb.train(
                q_params,
                Xy_train,
                num_boost_round=q_num_rounds,
                evals=[(Xy_val, "val")],
                early_stopping_rounds=EARLY_STOPPING_ROUNDS,
                verbose_eval=100,
            )

            # Predict on test set (regular DMatrix, not QuantileDMatrix)
            preds = bst_q.predict(dtest, iteration_range=(0, bst_q.best_iteration + 1))
            quantile_preds[label] = preds
            q_mae = mae(y_test, preds)
            quantile_maes[label] = round(q_mae, 2)

            print(f"  {label} MAE: {q_mae:.1f}s (best_iter={bst_q.best_iteration})")

            # Save model
            model_path = MODELS_DIR / f"quantile_{label}_v1.ubj"
            bst_q.save_model(str(model_path))
            print(f"  Saved: {model_path}")

        # Quantile evaluation
        p20 = quantile_preds["p20"]
        p50 = quantile_preds["p50"]
        p75 = quantile_preds["p75"]

        # Monotonicity check
        violations_raw = int(np.sum((p20 > p50) | (p50 > p75) | (p20 > p75)))
        print(f"\nMonotonicity violations (raw): {violations_raw} / {len(y_test)}")

        if violations_raw > 0:
            # Post-process by sorting
            stacked = np.stack([p20, p50, p75], axis=1)
            stacked.sort(axis=1)
            p20, p50, p75 = stacked[:, 0], stacked[:, 1], stacked[:, 2]
            print(f"  Post-processed: violations corrected by sorting")

        monotonicity_pass = bool(np.all((p20 <= p50) & (p50 <= p75)))
        print(f"  Monotonicity pass: {monotonicity_pass}")

        # Range stats
        ranges = p75 - p20
        mean_range = float(np.mean(ranges))
        median_range = float(np.median(ranges))
        pct_narrow = float(np.mean(ranges < 60))  # < 1 min range
        pct_wide = float(np.mean(ranges > 300))  # > 5 min range

        print(f"\nRange stats (P75 - P20):")
        print(f"  Mean range:   {mean_range:.1f}s ({mean_range/60:.1f} min)")
        print(f"  Median range: {median_range:.1f}s ({median_range/60:.1f} min)")
        print(f"  Narrow (<60s): {pct_narrow:.1%}")
        print(f"  Wide (>300s):  {pct_wide:.1%}")

        # Calibration: fraction of actuals within [p20, p75]
        in_range = np.mean((y_test >= p20) & (y_test <= p75))
        print(f"\nCalibration (actuals in [P20, P75]): {in_range:.1%} (target ~55%)")

        # Save quantile metrics
        q_metrics = {
            "per_quantile": {
                "p20": {"mae": quantile_maes["p20"]},
                "p50": {"mae": quantile_maes["p50"]},
                "p75": {"mae": quantile_maes["p75"]},
            },
            "monotonicity_pass": monotonicity_pass,
            "monotonicity_violations_raw": violations_raw,
            "range_stats": {
                "mean_range": round(mean_range, 2),
                "median_range": round(median_range, 2),
                "pct_narrow": round(pct_narrow, 4),
                "pct_wide": round(pct_wide, 4),
            },
            "calibration": round(float(in_range), 4),
            "training_subsample_frac": subsample_frac,
            "best_params": best_params,
        }
        q_metrics_path = MODELS_DIR / "quantile_metrics.json"
        with open(q_metrics_path, "w") as f:
            json.dump(q_metrics, f, indent=2)
        print(f"\nSaved: {q_metrics_path}")
    else:
        print("\nSkipping Section B (quantile) -- using existing artifacts")

    # ==================================================================
    # SECTION C: FULL PHASE 5 COMPARISON TABLE
    # ==================================================================
    if run_comparison:
        print(f"\n{'='*60}")
        print("SECTION C: Full Phase 5 Comparison Table")
        print(f"{'='*60}")

        # Load all metrics files
        with open(MODELS_DIR / "baseline_metrics.json") as f:
            baseline = json.load(f)
        with open(MODELS_DIR / "differentiator_metrics.json") as f:
            diff = json.load(f)
        with open(MODELS_DIR / "asymmetric_metrics.json") as f:
            asym_loaded = json.load(f)

        naive_mae_val = 708.9
        naive_rmse_val = 883.4
        baseline_mae_val = baseline["xgboost"]["mae"]
        baseline_rmse_val = baseline["xgboost"]["rmse"]
        diff_mae_val = diff["xgboost"]["mae"]
        diff_rmse_val = diff["xgboost"]["rmse"]
        tuned_mae_val = tuned["xgboost"]["mae"]
        tuned_rmse_val = tuned["xgboost"]["rmse"]
        asym_mae_val = asym_loaded["xgboost"]["mae"]
        asym_rmse_loaded = asym_loaded["xgboost"]["rmse"]
        median_residual_loaded = asym_loaded["median_residual"]

        progressive_chain = [
            {"model": "naive", "mae": naive_mae_val, "rmse": naive_rmse_val},
            {"model": "baseline_p3", "mae": baseline_mae_val, "rmse": baseline_rmse_val},
            {"model": "differentiator_p4", "mae": diff_mae_val, "rmse": diff_rmse_val},
            {"model": "tuned_p5", "mae": tuned_mae_val, "rmse": tuned_rmse_val},
            {"model": "asymmetric_p5", "mae": asym_mae_val, "rmse": asym_rmse_loaded,
             "median_residual": median_residual_loaded},
        ]

        # Per-route comparison across models
        per_route_a_loaded = asym_loaded.get("per_route", {})
        per_route_comparison = {}
        all_route_ids = set(list(per_route_a_loaded.keys()) +
                           list(tuned.get("per_route", {}).keys()) +
                           list(diff.get("per_route", {}).keys()) +
                           list(baseline.get("per_route", {}).keys()))
        for rid_str in sorted(all_route_ids, key=lambda x: int(x)):
            entry = {}
            if rid_str in baseline.get("per_route", {}):
                entry["baseline_mae"] = baseline["per_route"][rid_str]["mae"]
            if rid_str in diff.get("per_route", {}):
                entry["differentiator_mae"] = diff["per_route"][rid_str]["mae"]
            if rid_str in tuned.get("per_route", {}):
                entry["tuned_mae"] = tuned["per_route"][rid_str]["mae"]
            if rid_str in per_route_a_loaded:
                entry["asymmetric_mae"] = per_route_a_loaded[rid_str]["mae"]
            per_route_comparison[rid_str] = entry

        # Per-stops comparison
        per_stops_a_loaded = asym_loaded.get("per_stops_bucket", {})
        per_stops_comparison = {}
        for b in ["1", "2-3", "4-6", "7+"]:
            entry = {}
            if b in baseline.get("per_stops_bucket", {}):
                entry["baseline_mae"] = baseline["per_stops_bucket"][b]["mae"]
            if b in diff.get("per_stops_bucket", {}):
                entry["differentiator_mae"] = diff["per_stops_bucket"][b]["mae"]
            if b in tuned.get("per_stops_bucket", {}):
                entry["tuned_mae"] = tuned["per_stops_bucket"][b]["mae"]
            if b in per_stops_a_loaded:
                entry["asymmetric_mae"] = per_stops_a_loaded[b]["mae"]
            per_stops_comparison[b] = entry

        # Load quantile metrics (from this run or existing file)
        if run_quantile:
            quantile_summary = {
                "p20_mae": quantile_maes["p20"],
                "p50_mae": quantile_maes["p50"],
                "p75_mae": quantile_maes["p75"],
                "calibration": round(float(in_range), 4),
                "mean_range_seconds": round(mean_range, 2),
            }
        else:
            with open(MODELS_DIR / "quantile_metrics.json") as f:
                qm = json.load(f)
            quantile_summary = {
                "p20_mae": qm["per_quantile"]["p20"]["mae"],
                "p50_mae": qm["per_quantile"]["p50"]["mae"],
                "p75_mae": qm["per_quantile"]["p75"]["mae"],
                "calibration": qm["calibration"],
                "mean_range_seconds": qm["range_stats"]["mean_range"],
            }

        comparison = {
            "progressive_chain": progressive_chain,
            "quantile_summary": quantile_summary,
            "per_route_comparison": per_route_comparison,
            "per_stops_bucket_comparison": per_stops_comparison,
        }
        comp_path = MODELS_DIR / "phase5_comparison.json"
        with open(comp_path, "w") as f:
            json.dump(comparison, f, indent=2)
        print(f"Saved: {comp_path}")

        # ------------------------------------------------------------------
        # Print summary
        # ------------------------------------------------------------------
        elapsed = (time.time() - start_time) / 60

        print(f"\n{'='*60}")
        print("=== PHASE 5 COMPLETE: ADVANCED TRAINING ===")
        print(f"{'='*60}")

        print(f"\n  Progressive improvement chain:")
        print(f"  {'Model':<25s}  {'MAE':>8s}  {'RMSE':>8s}  {'vs Naive':>10s}")
        print(f"  {'-'*25}  {'-'*8}  {'-'*8}  {'-'*10}")
        for entry in progressive_chain:
            vs_naive = (naive_mae_val - entry["mae"]) / naive_mae_val * 100
            extra = ""
            if "median_residual" in entry:
                extra = f"  (med_resid={entry['median_residual']:.1f}s)"
            print(f"  {entry['model']:<25s}  {entry['mae']:>8.1f}  {entry['rmse']:>8.1f}  {vs_naive:>9.1f}%{extra}")

        print(f"\n  Quantile models:")
        print(f"    P20 MAE: {quantile_summary['p20_mae']}s")
        print(f"    P50 MAE: {quantile_summary['p50_mae']}s")
        print(f"    P75 MAE: {quantile_summary['p75_mae']}s")
        print(f"    Calibration: {quantile_summary['calibration']:.1%}")
        print(f"    Mean range: {quantile_summary['mean_range_seconds']:.1f}s ({quantile_summary['mean_range_seconds']/60:.1f} min)")

        print(f"\n  Elapsed: {elapsed:.1f} min")
        print(f"\n{'='*60}")
        print("ALL PHASE 5 ARTIFACTS SAVED")
        print(f"{'='*60}")
    else:
        print("\nSkipping Section C (comparison)")


if __name__ == "__main__":
    main()
