"""
train_advanced.py - Optuna hyperparameter tuning for Tiger Transit ETA model.

Uses Optuna with TimeSeriesSplit cross-validation and MedianPruner to find
optimal XGBoost hyperparameters. Retrains the best configuration on full
training data and evaluates on held-out test set.

Purpose: The Phase 4 model used all 3000 rounds with hand-tuned hyperparameters
(175.7s MAE). Optuna will find optimal learning_rate, max_depth, regularization,
and num_boost_round for significant MAE improvement.

Strategy: Two-stage tuning for practical runtime.
  Stage 1: 150 Optuna trials using train/val holdout (fast -- 1 model per trial)
  Stage 2: Verify best params with 4-fold TimeSeriesSplit CV on train+val
  Final:   Retrain best config on full train, evaluate on held-out test

Usage:
    python scripts/train_advanced.py

Input:
    data/processed/{train,val,test}_featured_v2.parquet

Output:
    models/tuned_v1.ubj           - XGBoost model retrained with best hyperparameters
    models/tuned_metrics.json     - Tuned model metrics with Optuna study summary
"""

import argparse
import json
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import optuna
from sklearn.model_selection import TimeSeriesSplit
import xgboost as xgb

# Suppress noisy Optuna internal warnings
warnings.filterwarnings("ignore", message=".*step.*already reported.*")

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
SEED = 42
N_TRIALS = 50
N_CV_SPLITS = 4
EARLY_STOPPING_ROUNDS_CV = 15
EARLY_STOPPING_ROUNDS_FINAL = 100

FIXED_PARAMS = {
    "objective": "reg:squarederror",
    "eval_metric": "mae",
    "tree_method": "hist",
    "max_cat_to_onehot": 10,
    "seed": SEED,
}


# ---------------------------------------------------------------------------
# Helpers (reused from train_differentiator.py)
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


def distance_bucket(dist):
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


def parse_args():
    parser = argparse.ArgumentParser(description="Optuna hyperparameter tuning for Tiger Transit ETA model")
    parser.add_argument("--batch", type=int, default=0,
                        help="Run N trials per invocation (0=all). Uses SQLite storage for persistence.")
    parser.add_argument("--skip-tuning", action="store_true",
                        help="Skip Optuna, load best_params from tuned_metrics.json, retrain+eval only")
    parser.add_argument("--tuning-only", action="store_true",
                        help="Run Optuna trials only, skip retrain/eval (use with --batch)")
    return parser.parse_args()


# SQLite storage path for persistent Optuna study
STUDY_DB = "sqlite:///models/optuna_study.db"


def main():
    args = parse_args()
    MODELS_DIR.mkdir(exist_ok=True)
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("Loading v2 featured data...")
    df_train = load_featured_v2("train")
    df_val = load_featured_v2("val")
    df_test = load_featured_v2("test")

    print(f"  train: {df_train.shape}")
    print(f"  val:   {df_val.shape}")
    print(f"  test:  {df_test.shape}")
    print(f"  Features: {len(FEATURE_COLS_V2)}")

    # Test set -- never touched during tuning
    X_test = df_test[FEATURE_COLS_V2].copy()
    y_test = df_test[TARGET_COL].values

    # Test metadata for sliced evaluation
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_away = df_test["stops_away"].values
    test_scheduled = df_test["scheduled_time_to_target"].values.astype(float)
    test_distances = df_test["distance_to_target"].values.astype(float)
    test_minutes = df_test["minutes_since_midnight"].values
    test_hour_ct = (test_minutes // 60).astype(int)

    # Training arrays
    X_train = df_train[FEATURE_COLS_V2].copy()
    y_train = df_train[TARGET_COL].values
    X_val = df_val[FEATURE_COLS_V2].copy()
    y_val = df_val[TARGET_COL].values

    # ------------------------------------------------------------------
    # 2. Stage 1: Optuna search using subsampled train/val holdout
    #    Uses SQLite storage for persistence across batch runs
    # ------------------------------------------------------------------
    if not args.skip_tuning:
        # 10% subsample for fast Optuna search, verify on full data later
        SEARCH_FRAC = 0.10
        rng = np.random.RandomState(SEED)
        search_train_idx = rng.choice(len(y_train), size=int(len(y_train) * SEARCH_FRAC), replace=False)
        search_train_idx.sort()
        search_val_idx = rng.choice(len(y_val), size=int(len(y_val) * SEARCH_FRAC), replace=False)
        search_val_idx.sort()

        print(f"\nPre-building DMatrix objects for Optuna search ({SEARCH_FRAC:.0%} subsample)...")
        dtrain_search = xgb.DMatrix(
            X_train.iloc[search_train_idx], label=y_train[search_train_idx], enable_categorical=True
        )
        dval_search = xgb.DMatrix(
            X_val.iloc[search_val_idx], label=y_val[search_val_idx], enable_categorical=True
        )
        y_val_search = y_val[search_val_idx]
        print(f"  Search DMatrix: train={dtrain_search.num_row()}, val={dval_search.num_row()}")

        def objective(trial):
            from optuna_integration import XGBoostPruningCallback

            params = {
                **FIXED_PARAMS,
                "max_depth": trial.suggest_int("max_depth", 3, 8),
                "learning_rate": trial.suggest_float("learning_rate", 0.03, 0.3, log=True),
                "min_child_weight": trial.suggest_int("min_child_weight", 5, 100),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-3, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-3, 10.0, log=True),
            }
            num_boost_round = trial.suggest_int("num_boost_round", 200, 600)

            pruning_callback = XGBoostPruningCallback(trial, "val-mae")

            bst = xgb.train(
                params,
                dtrain_search,
                num_boost_round=num_boost_round,
                evals=[(dval_search, "val")],
                early_stopping_rounds=EARLY_STOPPING_ROUNDS_CV,
                verbose_eval=False,
                callbacks=[pruning_callback],
            )

            preds = bst.predict(dval_search, iteration_range=(0, bst.best_iteration + 1))
            return float(np.mean(np.abs(y_val_search - preds)))

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        # Use SQLite storage for persistence across batch runs
        storage = optuna.storages.RDBStorage(url=STUDY_DB)
        study = optuna.create_study(
            direction="minimize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10),
            study_name="tiger_transit_tuning",
            storage=storage,
            load_if_exists=True,
        )

        existing_trials = len(study.trials)
        remaining = max(0, N_TRIALS - existing_trials)

        if args.batch > 0 and remaining > 0:
            batch_size = min(args.batch, remaining)
            print(f"\nStage 1: Optuna batch ({batch_size} trials, {existing_trials} already done, {N_TRIALS} target)...")
            study.optimize(objective, n_trials=batch_size, timeout=None, show_progress_bar=True)
        elif remaining > 0:
            # Full run with 90 minute timeout as safety net
            print(f"\nStage 1: Optuna search ({remaining} trials remaining of {N_TRIALS}, {existing_trials} done)...")
            study.optimize(objective, n_trials=remaining, timeout=5400, show_progress_bar=True)
        else:
            print(f"\nStage 1: Optuna study already has {existing_trials} trials (target: {N_TRIALS}). Skipping.")

        total_trials = len(study.trials)
        n_pruned = len([t for t in study.trials if t.state == optuna.trial.TrialState.PRUNED])
        n_complete = len([t for t in study.trials if t.state == optuna.trial.TrialState.COMPLETE])

        stage1_time = time.time() - start_time
        print(f"\nStage 1 status ({stage1_time/60:.1f} min)")
        print(f"  Total trials: {total_trials}")
        print(f"  Pruned trials: {n_pruned}")
        print(f"  Complete trials: {n_complete}")
        print(f"  Best trial: #{study.best_trial.number}")
        print(f"  Best val MAE: {study.best_trial.value:.2f}s")
        print(f"  Best params:")
        for k, v in study.best_trial.params.items():
            print(f"    {k}: {v}")

        # If batch mode and more trials remain, exit early
        if args.tuning_only or (args.batch > 0 and total_trials < N_TRIALS):
            remaining_after = N_TRIALS - total_trials
            print(f"\n  {remaining_after} trials remaining. Run again with --batch to continue.")
            return

        best_trial = study.best_trial
    else:
        # Load best params from existing metrics
        print("\nSkipping tuning, loading best_params from tuned_metrics.json...")
        with open(MODELS_DIR / "tuned_metrics.json") as f:
            existing = json.load(f)
        best_trial = None
        n_pruned = existing.get("study_summary", {}).get("n_pruned", 0)
        n_complete = existing.get("study_summary", {}).get("n_complete", 0)

    # ------------------------------------------------------------------
    # 3. Stage 2: Verify best params with TimeSeriesSplit CV
    # ------------------------------------------------------------------
    if best_trial is not None:
        best_params_full = {
            **FIXED_PARAMS,
            "max_depth": best_trial.params["max_depth"],
            "learning_rate": best_trial.params["learning_rate"],
            "min_child_weight": best_trial.params["min_child_weight"],
            "subsample": best_trial.params["subsample"],
            "colsample_bytree": best_trial.params["colsample_bytree"],
            "reg_alpha": best_trial.params["reg_alpha"],
            "reg_lambda": best_trial.params["reg_lambda"],
        }
        best_num_boost_round = best_trial.params["num_boost_round"]
    else:
        bp = existing["best_params"]
        best_params_full = {**FIXED_PARAMS, **bp}
        best_num_boost_round = existing["best_num_boost_round"]

    print(f"\nStage 2: Verifying best params with {N_CV_SPLITS}-fold TimeSeriesSplit CV...")

    import pandas as pd
    df_cv = pd.concat([df_train, df_val], ignore_index=True)
    X_cv_df = df_cv[FEATURE_COLS_V2]
    y_cv = df_cv[TARGET_COL].values

    tscv = TimeSeriesSplit(n_splits=N_CV_SPLITS)
    cv_maes = []
    for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X_cv_df)):
        dtrain_fold = xgb.DMatrix(
            X_cv_df.iloc[train_idx], label=y_cv[train_idx], enable_categorical=True
        )
        dval_fold = xgb.DMatrix(
            X_cv_df.iloc[val_idx], label=y_cv[val_idx], enable_categorical=True
        )

        bst_cv = xgb.train(
            best_params_full,
            dtrain_fold,
            num_boost_round=best_num_boost_round,
            evals=[(dval_fold, "val")],
            early_stopping_rounds=EARLY_STOPPING_ROUNDS_CV,
            verbose_eval=False,
        )

        preds = bst_cv.predict(dval_fold, iteration_range=(0, bst_cv.best_iteration + 1))
        fold_mae = float(np.mean(np.abs(y_cv[val_idx] - preds)))
        cv_maes.append(fold_mae)
        print(f"  Fold {fold_idx}: MAE={fold_mae:.2f}s (best_iter={bst_cv.best_iteration})")

    cv_mean_mae = float(np.mean(cv_maes))
    cv_std_mae = float(np.std(cv_maes))
    print(f"  CV Mean MAE: {cv_mean_mae:.2f}s (+/- {cv_std_mae:.2f}s)")

    # ------------------------------------------------------------------
    # 4. Retrain best config on full train set
    # ------------------------------------------------------------------
    print(f"\nRetraining best config on train split (val for early stopping)...")

    dtrain = xgb.DMatrix(X_train, label=y_train, enable_categorical=True)
    dval = xgb.DMatrix(X_val, label=y_val, enable_categorical=True)
    dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)

    # Use 5x the Optuna-found rounds for final retrain, letting early stopping find optimal
    final_num_rounds = min(best_num_boost_round * 5, 3000)
    bst = xgb.train(
        best_params_full,
        dtrain,
        num_boost_round=final_num_rounds,
        evals=[(dtrain, "train"), (dval, "val")],
        early_stopping_rounds=EARLY_STOPPING_ROUNDS_FINAL,
        verbose_eval=100,
    )

    print(f"\nBest iteration: {bst.best_iteration}")
    print(f"Best validation MAE: {bst.best_score:.2f}s")

    # ------------------------------------------------------------------
    # 5. Evaluate on test set
    # ------------------------------------------------------------------
    y_pred = bst.predict(dtest, iteration_range=(0, bst.best_iteration + 1))
    xgb_mae = mae(y_test, y_pred)
    xgb_rmse = rmse(y_test, y_pred)
    xgb_mape = mape(y_test, y_pred)

    naive_mae = mae(y_test, test_scheduled)
    naive_rmse = rmse(y_test, test_scheduled)
    improvement_vs_naive = (naive_mae - xgb_mae) / naive_mae * 100

    print(f"\nTest set results:")
    print(f"  Tuned MAE:  {xgb_mae:.1f}s")
    print(f"  Tuned RMSE: {xgb_rmse:.1f}s")
    print(f"  Tuned MAPE: {xgb_mape:.1f}%")
    print(f"  Naive MAE:  {naive_mae:.1f}s")
    print(f"  vs Naive:   {improvement_vs_naive:.1f}%")

    # ------------------------------------------------------------------
    # 6. Sliced metrics
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
    # 7. Load Phase 4 differentiator metrics for comparison
    # ------------------------------------------------------------------
    diff_metrics_path = MODELS_DIR / "differentiator_metrics.json"
    with open(diff_metrics_path) as f:
        diff_metrics = json.load(f)

    diff_mae = diff_metrics["xgboost"]["mae"]
    diff_rmse = diff_metrics["xgboost"]["rmse"]
    baseline_mae = diff_metrics["comparison"]["baseline_mae"]

    improvement_vs_diff = (diff_mae - xgb_mae) / diff_mae * 100
    improvement_vs_baseline = (baseline_mae - xgb_mae) / baseline_mae * 100

    # ------------------------------------------------------------------
    # 8. Save artifacts
    # ------------------------------------------------------------------

    # Model
    model_path = MODELS_DIR / "tuned_v1.ubj"
    bst.save_model(str(model_path))
    print(f"\nSaved model: {model_path}")

    # Extract best params dict for JSON serialization
    bp_for_json = {k: v for k, v in best_params_full.items() if k not in FIXED_PARAMS}

    # Metrics JSON
    metrics = {
        "model": "tuned_v1",
        "best_iteration": int(bst.best_iteration),
        "num_features": len(FEATURE_COLS_V2),
        "best_params": bp_for_json,
        "best_num_boost_round": best_num_boost_round,
        "best_cv_mae": round(cv_mean_mae, 2),
        "cv_std_mae": round(cv_std_mae, 2),
        "cv_fold_maes": [round(m, 2) for m in cv_maes],
        "best_holdout_mae": round(best_trial.value, 2) if best_trial else None,
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
        "study_summary": {
            "n_trials": n_complete + n_pruned,
            "n_pruned": n_pruned,
            "n_complete": n_complete,
            "best_trial_number": best_trial.number if best_trial else None,
        },
        "comparison": {
            "baseline_mae": baseline_mae,
            "differentiator_mae": diff_mae,
            "differentiator_rmse": diff_rmse,
            "tuned_mae": round(xgb_mae, 2),
            "tuned_rmse": round(xgb_rmse, 2),
            "improvement_vs_differentiator_pct": round(improvement_vs_diff, 2),
            "improvement_vs_baseline_pct": round(improvement_vs_baseline, 2),
        },
    }
    metrics_path = MODELS_DIR / "tuned_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics: {metrics_path}")

    # ------------------------------------------------------------------
    # 9. Print summary
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print("=== PHASE 5 PLAN 01 RESULTS: OPTUNA TUNING ===")
    print(f"{'='*60}")
    total_trials = n_complete + n_pruned
    print(f"  Optuna trials:       {total_trials} ({n_pruned} pruned, {n_complete} complete)")
    if best_trial:
        print(f"  Best holdout MAE:    {best_trial.value:.2f}s")
        print(f"  Best trial:          #{best_trial.number}")
    print(f"  CV Mean MAE:         {cv_mean_mae:.2f}s (+/- {cv_std_mae:.2f}s)")
    print(f"  Elapsed time:        {elapsed/60:.1f} minutes")

    print(f"\n  Comparison:")
    print(f"  Differentiator MAE:  {diff_mae:.1f}s")
    print(f"  Tuned MAE:           {xgb_mae:.1f}s")
    print(f"  Improvement:         {improvement_vs_diff:.1f}% ({diff_mae - xgb_mae:.1f}s reduction)")

    print(f"\n  Progressive improvement chain:")
    print(f"    Naive:              {naive_mae:.1f}s")
    print(f"    Baseline (P3):     {baseline_mae:.1f}s ({(naive_mae - baseline_mae) / naive_mae * 100:.1f}% vs naive)")
    print(f"    Differentiator(P4):{diff_mae:.1f}s ({(naive_mae - diff_mae) / naive_mae * 100:.1f}% vs naive)")
    print(f"    Tuned (P5):        {xgb_mae:.1f}s ({improvement_vs_naive:.1f}% vs naive)")

    # Gate check
    if xgb_mae < diff_mae:
        print(f"\n  PASS: Tuned MAE ({xgb_mae:.1f}s) < Differentiator MAE ({diff_mae:.1f}s)")
    else:
        print(f"\n  WARN: Tuned MAE ({xgb_mae:.1f}s) >= Differentiator MAE ({diff_mae:.1f}s)")

    print(f"\n{'='*60}")
    print("TUNING COMPLETE")
    print(f"{'='*60}")
    print(f"  Model:       {model_path}")
    print(f"  Metrics:     {metrics_path}")


if __name__ == "__main__":
    main()
