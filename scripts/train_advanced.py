"""
train_advanced.py - Phase 8 v1.1 Residual Training Pipeline.

Trains XGBoost to predict residuals (actual - baseline_eta) with fresh Optuna
hyperparameter tuning, z-score outlier trimming, GPU auto-detection, Huber vs
squared error comparison, and deterministic final model training.

Strategy: Two-stage tuning for practical runtime.
  Stage 1: 100 Optuna trials using subsampled train/val holdout
           (9 hyperparameters + conditional huber_slope, 2 loss functions)
  Stage 2: Verify best params with 4-fold TimeSeriesSplit CV on train+val
  Final:   Retrain best config deterministically on full trimmed train,
           evaluate on held-out test with reconstructed MAE

Pipeline:
  1. Load v1.1 featured parquets (45 features, residual target)
  2. Apply z-score 2.5 outlier trimming to training data only
  3. Run 100 Optuna trials comparing reg:squarederror vs reg:pseudohubererror
  4. Verify best params with 4-fold TimeSeriesSplit CV
  5. Retrain final model deterministically (exact round count, no early stopping)
  6. Evaluate with reconstructed MAE (baseline_eta + predicted_residual)
  7. Save model and metrics

Usage:
    python scripts/train_advanced.py                      # Full pipeline
    python scripts/train_advanced.py --skip-tuning        # Skip Optuna, retrain only
    python scripts/train_advanced.py --batch 25           # Run 25 Optuna trials
    python scripts/train_advanced.py --tuning-only        # Optuna only, no retrain

Input:
    data/processed/{train,val,test}_featured_v2.parquet

Output:
    models/v1_1_residual.ubj       - XGBoost model trained on residuals
    models/v1_1_metrics.json       - Metrics with reconstructed MAE, Optuna summary
"""

import argparse
import gc
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
# GPU Auto-Detection
# ---------------------------------------------------------------------------


def detect_xgb_device():
    """Auto-detect GPU availability for XGBoost. Returns 'cuda' or 'cpu'."""
    try:
        dm = xgb.DMatrix(np.zeros((2, 1)), label=[0, 1])
        bst = xgb.train({"device": "cuda", "tree_method": "hist"},
                         dm, num_boost_round=1, verbose_eval=False)
        del bst, dm
        return "cuda"
    except Exception:
        return "cpu"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

MODELS_DIR = Path("models")
SEED = 42
N_TRIALS = 100
N_CV_SPLITS = 4
STUDY_NAME = "v1_1_residual_tuning"
STUDY_DB = "sqlite:///models/optuna_study.db"
Z_SCORE_THRESHOLD = 2.5

DEVICE = detect_xgb_device()
print(f"XGBoost device: {DEVICE}")

FIXED_PARAMS = {
    "eval_metric": "mae",
    "tree_method": "hist",
    "device": DEVICE,
    "max_cat_to_onehot": 10,
    "seed": SEED,
}


# ---------------------------------------------------------------------------
# Outlier Trimming
# ---------------------------------------------------------------------------


def trim_outliers(y, z_threshold=Z_SCORE_THRESHOLD):
    """Remove outliers by z-score on target values. Returns boolean mask of rows to keep."""
    mean = y.mean()
    std = y.std()
    z_scores = np.abs((y - mean) / std)
    mask = z_scores <= z_threshold
    n_removed = (~mask).sum()
    pct_removed = n_removed / len(y) * 100
    print(f"  Outlier trimming (z <= {z_threshold}): removed {n_removed:,} of {len(y):,} samples ({pct_removed:.1f}%)")
    return mask


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
    parser = argparse.ArgumentParser(description="v1.1 Optuna hyperparameter tuning for Tiger Transit residual ETA model")
    parser.add_argument("--batch", type=int, default=0,
                        help="Run N trials per invocation (0=all). Uses SQLite storage for persistence.")
    parser.add_argument("--skip-tuning", action="store_true",
                        help="Skip Optuna, load best_params from v1_1_metrics.json, retrain+eval only")
    parser.add_argument("--tuning-only", action="store_true",
                        help="Run Optuna trials only, skip retrain/eval (use with --batch)")
    return parser.parse_args()


def main():
    args = parse_args()
    MODELS_DIR.mkdir(exist_ok=True)
    start_time = time.time()

    # ------------------------------------------------------------------
    # 1. Load data
    # ------------------------------------------------------------------
    print("Loading v1.1 featured data (45 features, residual target)...")
    df_train = load_featured_v2("train")
    df_val = load_featured_v2("val")
    df_test = load_featured_v2("test")

    print(f"  train: {df_train.shape}")
    print(f"  val:   {df_val.shape}")
    print(f"  test:  {df_test.shape}")
    print(f"  Features: {len(FEATURE_COLS_V2)}")
    print(f"  Target: {TARGET_COL}")

    # Test set -- never touched during tuning
    X_test = df_test[FEATURE_COLS_V2].copy()
    y_test = df_test[TARGET_COL].values

    # Test metadata for sliced evaluation
    test_route_ids = df_test["route_id"].astype(int).values
    test_stops_away = df_test["stops_away"].values
    test_distances = df_test["distance_to_target"].values.astype(float)
    test_minutes = df_test["minutes_since_midnight"].values
    test_hour_ct = (test_minutes // 60).astype(int)

    # Reconstruction columns for test set
    test_baseline_eta = df_test["baseline_eta"].values
    test_actual_seconds = df_test["time_to_arrival_seconds"].values

    # Training arrays
    X_train = df_train[FEATURE_COLS_V2].copy()
    y_train = df_train[TARGET_COL].values
    X_val = df_val[FEATURE_COLS_V2].copy()
    y_val = df_val[TARGET_COL].values

    # ------------------------------------------------------------------
    # 2. Outlier trimming on training data only
    # ------------------------------------------------------------------
    print("\nApplying outlier trimming to training data...")
    trim_mask = trim_outliers(y_train, Z_SCORE_THRESHOLD)
    X_train_trimmed = X_train[trim_mask].reset_index(drop=True)
    y_train_trimmed = y_train[trim_mask]

    # Store trimming stats for metrics
    n_trimmed = int((~trim_mask).sum())
    pct_trimmed = n_trimmed / len(y_train) * 100

    print(f"  Training data: {len(y_train):,} -> {len(y_train_trimmed):,} after trimming")

    # ------------------------------------------------------------------
    # 3. Stage 1: Optuna search using subsampled trimmed train / val holdout
    # ------------------------------------------------------------------
    if not args.skip_tuning:
        # 10% subsample for fast Optuna search, verify on full data later
        SEARCH_FRAC = 0.10
        rng = np.random.RandomState(SEED)
        search_train_idx = rng.choice(len(y_train_trimmed), size=int(len(y_train_trimmed) * SEARCH_FRAC), replace=False)
        search_train_idx.sort()
        # Validation subsample from untrimmed validation data
        search_val_idx = rng.choice(len(y_val), size=int(len(y_val) * SEARCH_FRAC), replace=False)
        search_val_idx.sort()

        print(f"\nPre-building DMatrix objects for Optuna search ({SEARCH_FRAC:.0%} subsample)...")
        dtrain_search = xgb.DMatrix(
            X_train_trimmed.iloc[search_train_idx], label=y_train_trimmed[search_train_idx], enable_categorical=True
        )
        dval_search = xgb.DMatrix(
            X_val.iloc[search_val_idx], label=y_val[search_val_idx], enable_categorical=True
        )
        y_val_search = y_val[search_val_idx]
        print(f"  Search DMatrix: train={dtrain_search.num_row()}, val={dval_search.num_row()}")

        def objective(trial):
            from optuna_integration import XGBoostPruningCallback

            objective_name = trial.suggest_categorical(
                "objective", ["reg:squarederror", "reg:pseudohubererror"]
            )
            params = {
                **FIXED_PARAMS,
                "objective": objective_name,
                "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
                "max_depth": trial.suggest_int("max_depth", 3, 10),
                "subsample": trial.suggest_float("subsample", 0.5, 1.0),
                "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
                "min_child_weight": trial.suggest_int("min_child_weight", 1, 100),
                "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10.0, log=True),
                "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10.0, log=True),
                "gamma": trial.suggest_float("gamma", 0.0, 5.0),
            }
            if objective_name == "reg:pseudohubererror":
                params["huber_slope"] = trial.suggest_float("huber_slope", 1.0, 100.0, log=True)

            num_boost_round = trial.suggest_int("num_boost_round", 200, 2000)

            pruning_callback = XGBoostPruningCallback(trial, "val-mae")
            bst = xgb.train(
                params,
                dtrain_search,
                num_boost_round=num_boost_round,
                evals=[(dval_search, "val")],
                early_stopping_rounds=15,
                verbose_eval=False,
                callbacks=[pruning_callback],
            )

            trial.set_user_attr("best_iteration", int(bst.best_iteration))
            trial.set_user_attr("objective_type", objective_name)
            preds = bst.predict(dval_search, iteration_range=(0, bst.best_iteration + 1))
            val_mae = float(np.mean(np.abs(y_val_search - preds)))

            del bst  # Free GPU memory between trials (XGBoost issue #3045)
            gc.collect()

            return val_mae

        optuna.logging.set_verbosity(optuna.logging.WARNING)

        # Use SQLite storage for persistence across batch runs
        storage = optuna.storages.RDBStorage(url=STUDY_DB)
        study = optuna.create_study(
            direction="minimize",
            pruner=optuna.pruners.MedianPruner(n_startup_trials=10, n_warmup_steps=50),
            study_name=STUDY_NAME,
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

        # Count how many trials used each objective
        n_squared = 0
        n_huber = 0
        for t in study.trials:
            if t.state in (optuna.trial.TrialState.COMPLETE, optuna.trial.TrialState.PRUNED):
                obj_type = t.params.get("objective", "unknown")
                if obj_type == "reg:squarederror":
                    n_squared += 1
                elif obj_type == "reg:pseudohubererror":
                    n_huber += 1

        stage1_time = time.time() - start_time
        print(f"\nStage 1 status ({stage1_time/60:.1f} min)")
        print(f"  Total trials: {total_trials}")
        print(f"  Pruned trials: {n_pruned}")
        print(f"  Complete trials: {n_complete}")
        print(f"  Objective split: {n_squared} squarederror, {n_huber} pseudohubererror")
        print(f"  Best trial: #{study.best_trial.number}")
        print(f"  Best val MAE: {study.best_trial.value:.2f}s")
        print(f"  Best objective: {study.best_trial.user_attrs.get('objective_type', study.best_trial.params.get('objective', 'unknown'))}")
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
        print("\nSkipping tuning, loading best_params from v1_1_metrics.json...")
        with open(MODELS_DIR / "v1_1_metrics.json") as f:
            existing = json.load(f)
        best_trial = None
        n_pruned = existing.get("study_summary", {}).get("n_pruned", 0)
        n_complete = existing.get("study_summary", {}).get("n_complete", 0)
        n_squared = existing.get("study_summary", {}).get("n_squarederror", 0)
        n_huber = existing.get("study_summary", {}).get("n_pseudohubererror", 0)

    # ------------------------------------------------------------------
    # 4. Stage 2: Verify best params with TimeSeriesSplit CV
    # ------------------------------------------------------------------
    if best_trial is not None:
        best_objective = best_trial.user_attrs.get("objective_type", best_trial.params.get("objective", "reg:squarederror"))
        best_params_full = {
            **FIXED_PARAMS,
            "objective": best_objective,
            "max_depth": best_trial.params["max_depth"],
            "learning_rate": best_trial.params["learning_rate"],
            "min_child_weight": best_trial.params["min_child_weight"],
            "subsample": best_trial.params["subsample"],
            "colsample_bytree": best_trial.params["colsample_bytree"],
            "reg_alpha": best_trial.params["reg_alpha"],
            "reg_lambda": best_trial.params["reg_lambda"],
            "gamma": best_trial.params["gamma"],
        }
        if best_objective == "reg:pseudohubererror":
            best_params_full["huber_slope"] = best_trial.params["huber_slope"]

        # Use best_iteration from Optuna trial for deterministic training
        best_n_rounds = best_trial.user_attrs.get("best_iteration", best_trial.params["num_boost_round"]) + 1
    else:
        bp = existing["best_params"]
        best_objective = existing.get("best_objective", "reg:squarederror")
        best_params_full = {**FIXED_PARAMS, "objective": best_objective, **bp}
        best_n_rounds = existing["best_n_rounds"]

    print(f"\nStage 2: Verifying best params with {N_CV_SPLITS}-fold TimeSeriesSplit CV...")
    print(f"  Objective: {best_objective}")
    print(f"  Rounds: {best_n_rounds}")

    import pandas as pd
    df_cv = pd.concat([df_train, df_val], ignore_index=True)
    X_cv_df = df_cv[FEATURE_COLS_V2]
    y_cv = df_cv[TARGET_COL].values

    tscv = TimeSeriesSplit(n_splits=N_CV_SPLITS)
    cv_maes = []
    for fold_idx, (train_idx, val_idx) in enumerate(tscv.split(X_cv_df)):
        # Apply outlier trimming to each fold's training portion independently
        fold_y_train = y_cv[train_idx]
        fold_trim_mask = trim_outliers(fold_y_train, Z_SCORE_THRESHOLD)
        fold_train_trimmed_idx = train_idx[fold_trim_mask]

        dtrain_fold = xgb.DMatrix(
            X_cv_df.iloc[fold_train_trimmed_idx], label=y_cv[fold_train_trimmed_idx], enable_categorical=True
        )
        dval_fold = xgb.DMatrix(
            X_cv_df.iloc[val_idx], label=y_cv[val_idx], enable_categorical=True
        )

        bst_cv = xgb.train(
            best_params_full,
            dtrain_fold,
            num_boost_round=best_n_rounds,
            evals=[(dval_fold, "val")],
            verbose_eval=False,
        )

        preds = bst_cv.predict(dval_fold)
        fold_mae = float(np.mean(np.abs(y_cv[val_idx] - preds)))
        cv_maes.append(fold_mae)
        print(f"  Fold {fold_idx}: MAE={fold_mae:.2f}s")
        del bst_cv
        gc.collect()

    cv_mean_mae = float(np.mean(cv_maes))
    cv_std_mae = float(np.std(cv_maes))
    print(f"  CV Mean MAE: {cv_mean_mae:.2f}s (+/- {cv_std_mae:.2f}s)")

    # ------------------------------------------------------------------
    # 5. Retrain best config on full trimmed train set (deterministic)
    # ------------------------------------------------------------------
    print(f"\nDeterministic final retrain: {best_n_rounds} rounds, no early stopping...")
    print(f"  Training on {len(y_train_trimmed):,} trimmed samples")

    dtrain = xgb.DMatrix(X_train_trimmed, label=y_train_trimmed, enable_categorical=True)
    dval = xgb.DMatrix(X_val, label=y_val, enable_categorical=True)
    dtest = xgb.DMatrix(X_test, label=y_test, enable_categorical=True)

    bst = xgb.train(
        best_params_full,
        dtrain,
        num_boost_round=best_n_rounds,
        evals=[(dtrain, "train"), (dval, "val")],
        # NO early_stopping_rounds -- deterministic
        verbose_eval=100,
    )

    print(f"\nFinal model trained: {best_n_rounds} rounds (deterministic)")

    # ------------------------------------------------------------------
    # 6. Evaluate on test set -- both residual and reconstructed
    # ------------------------------------------------------------------
    y_pred_residual = bst.predict(dtest)

    # Residual metrics (on residual target)
    residual_mae_val = mae(y_test, y_pred_residual)
    residual_rmse_val = rmse(y_test, y_pred_residual)

    # Reconstructed metrics: final ETA = baseline_eta + predicted_residual
    y_pred_eta = test_baseline_eta + y_pred_residual
    reconstructed_mae_val = mae(test_actual_seconds, y_pred_eta)
    reconstructed_rmse_val = rmse(test_actual_seconds, y_pred_eta)
    reconstructed_mape_val = mape(test_actual_seconds, y_pred_eta)

    print(f"\nTest set results:")
    print(f"  Residual MAE (on residual target):     {residual_mae_val:.1f}s")
    print(f"  Residual RMSE (on residual target):    {residual_rmse_val:.1f}s")
    print(f"  Reconstructed MAE (vs actual seconds): {reconstructed_mae_val:.1f}s")
    print(f"  Reconstructed RMSE (vs actual seconds):{reconstructed_rmse_val:.1f}s")
    print(f"  Reconstructed MAPE:                    {reconstructed_mape_val:.1f}%")
    print(f"  v1.0 MAE: 123.1s")
    print(f"  v1.1 vs v1.0: {'BETTER' if reconstructed_mae_val < 123.1 else 'WORSE'} ({abs(reconstructed_mae_val - 123.1):.1f}s {'improvement' if reconstructed_mae_val < 123.1 else 'regression'})")

    # ------------------------------------------------------------------
    # 7. Sliced metrics (reconstructed)
    # ------------------------------------------------------------------

    # Per-route (reconstructed)
    print(f"\n{'='*60}")
    print("Per-route metrics (reconstructed):")
    print(f"{'='*60}")
    unique_routes = sorted(set(test_route_ids))
    per_route = {}
    print(f"  {'Route':>8s}  {'N':>8s}  {'Recon MAE':>10s}  {'Recon RMSE':>11s}  {'Resid MAE':>10s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*11}  {'-'*10}")
    for rid in unique_routes:
        mask = test_route_ids == rid
        n = int(mask.sum())
        r_recon_mae = mae(test_actual_seconds[mask], y_pred_eta[mask])
        r_recon_rmse = rmse(test_actual_seconds[mask], y_pred_eta[mask])
        r_resid_mae = mae(y_test[mask], y_pred_residual[mask])
        per_route[str(rid)] = {
            "reconstructed_mae": round(r_recon_mae, 2),
            "reconstructed_rmse": round(r_recon_rmse, 2),
            "residual_mae": round(r_resid_mae, 2),
            "n": n,
        }
        print(f"  {rid:>8d}  {n:>8d}  {r_recon_mae:>10.1f}  {r_recon_rmse:>11.1f}  {r_resid_mae:>10.1f}")

    # Per stops_away bucket
    print(f"\n{'='*60}")
    print("Per stops_away bucket (reconstructed):")
    print(f"{'='*60}")
    buckets_order = ["1", "2-3", "4-6", "7+"]
    bucket_labels = np.array([stops_bucket(s) for s in test_stops_away])
    per_stops_bucket = {}
    print(f"  {'Bucket':>8s}  {'N':>8s}  {'Recon MAE':>10s}  {'Recon RMSE':>11s}")
    print(f"  {'-'*8}  {'-'*8}  {'-'*10}  {'-'*11}")
    for b in buckets_order:
        mask = bucket_labels == b
        n = int(mask.sum())
        if n == 0:
            continue
        b_recon_mae = mae(test_actual_seconds[mask], y_pred_eta[mask])
        b_recon_rmse = rmse(test_actual_seconds[mask], y_pred_eta[mask])
        per_stops_bucket[b] = {"reconstructed_mae": round(b_recon_mae, 2), "reconstructed_rmse": round(b_recon_rmse, 2), "n": n}
        print(f"  {b:>8s}  {n:>8d}  {b_recon_mae:>10.1f}  {b_recon_rmse:>11.1f}")

    # Per time-of-day bucket
    print(f"\n{'='*60}")
    print("Per time-of-day bucket (reconstructed, Central Time):")
    print(f"{'='*60}")
    tod_order = ["morning", "midday", "afternoon", "evening"]
    tod_labels = np.array([tod_bucket(h) for h in test_hour_ct])
    per_tod = {}
    print(f"  {'TOD':>12s}  {'N':>8s}  {'Recon MAE':>10s}  {'Recon RMSE':>11s}")
    print(f"  {'-'*12}  {'-'*8}  {'-'*10}  {'-'*11}")
    for t in tod_order:
        mask = tod_labels == t
        n = int(mask.sum())
        if n == 0:
            continue
        t_recon_mae = mae(test_actual_seconds[mask], y_pred_eta[mask])
        t_recon_rmse = rmse(test_actual_seconds[mask], y_pred_eta[mask])
        per_tod[t] = {"reconstructed_mae": round(t_recon_mae, 2), "reconstructed_rmse": round(t_recon_rmse, 2), "n": n}
        print(f"  {t:>12s}  {n:>8d}  {t_recon_mae:>10.1f}  {t_recon_rmse:>11.1f}")

    # Per distance bucket
    print(f"\n{'='*60}")
    print("Per distance bucket (reconstructed):")
    print(f"{'='*60}")
    dist_order = ["<1km", "1-3km", "3-5km", "5km+"]
    dist_labels = np.array([distance_bucket(d) for d in test_distances])
    per_distance = {}
    print(f"  {'Distance':>10s}  {'N':>8s}  {'Recon MAE':>10s}  {'Recon RMSE':>11s}")
    print(f"  {'-'*10}  {'-'*8}  {'-'*10}  {'-'*11}")
    for d in dist_order:
        mask = dist_labels == d
        n = int(mask.sum())
        if n == 0:
            continue
        d_recon_mae = mae(test_actual_seconds[mask], y_pred_eta[mask])
        d_recon_rmse = rmse(test_actual_seconds[mask], y_pred_eta[mask])
        per_distance[d] = {"reconstructed_mae": round(d_recon_mae, 2), "reconstructed_rmse": round(d_recon_rmse, 2), "n": n}
        print(f"  {d:>10s}  {n:>8d}  {d_recon_mae:>10.1f}  {d_recon_rmse:>11.1f}")

    # ------------------------------------------------------------------
    # 8. Save artifacts
    # ------------------------------------------------------------------

    # Model
    model_path = MODELS_DIR / "v1_1_residual.ubj"
    bst.save_model(str(model_path))
    print(f"\nSaved model: {model_path}")

    # Extract best params dict for JSON serialization
    bp_for_json = {k: v for k, v in best_params_full.items() if k not in FIXED_PARAMS}

    # Metrics JSON
    metrics = {
        "model": "v1_1_residual",
        "version": "1.1",
        "target": TARGET_COL,
        "num_features": len(FEATURE_COLS_V2),
        "num_boost_rounds": best_n_rounds,
        "device": DEVICE,
        "best_objective": best_objective,
        "best_params": bp_for_json,
        "best_n_rounds": best_n_rounds,
        "best_cv_mae": round(cv_mean_mae, 2),
        "cv_std_mae": round(cv_std_mae, 2),
        "cv_fold_maes": [round(m, 2) for m in cv_maes],
        "best_holdout_mae": round(best_trial.value, 2) if best_trial else None,
        "reconstructed_mae": round(reconstructed_mae_val, 2),
        "reconstructed_rmse": round(reconstructed_rmse_val, 2),
        "reconstructed_mape": round(reconstructed_mape_val, 2),
        "residual_mae": round(residual_mae_val, 2),
        "residual_rmse": round(residual_rmse_val, 2),
        "outlier_trimming": {
            "z_threshold": Z_SCORE_THRESHOLD,
            "n_removed": n_trimmed,
            "pct_removed": round(pct_trimmed, 2),
            "train_size_before": len(y_train),
            "train_size_after": len(y_train_trimmed),
        },
        "study_summary": {
            "study_name": STUDY_NAME,
            "n_trials": n_complete + n_pruned,
            "n_pruned": n_pruned,
            "n_complete": n_complete,
            "n_squarederror": n_squared,
            "n_pseudohubererror": n_huber,
            "best_trial_number": best_trial.number if best_trial else None,
        },
        "comparison_v1_0": {
            "v1_0_mae": 123.1,
            "v1_1_reconstructed_mae": round(reconstructed_mae_val, 2),
            "improvement_seconds": round(123.1 - reconstructed_mae_val, 2),
            "improvement_pct": round((123.1 - reconstructed_mae_val) / 123.1 * 100, 2),
        },
        "per_route": per_route,
        "per_stops_bucket": per_stops_bucket,
        "per_time_of_day": per_tod,
        "per_distance": per_distance,
    }
    metrics_path = MODELS_DIR / "v1_1_metrics.json"
    with open(metrics_path, "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"Saved metrics: {metrics_path}")

    # ------------------------------------------------------------------
    # 9. Print summary
    # ------------------------------------------------------------------
    elapsed = time.time() - start_time

    print(f"\n{'='*60}")
    print("=== PHASE 8 PLAN 02 RESULTS: v1.1 RESIDUAL TRAINING ===")
    print(f"{'='*60}")
    total_trials = n_complete + n_pruned
    print(f"  Optuna trials:       {total_trials} ({n_pruned} pruned, {n_complete} complete)")
    print(f"  Objective split:     {n_squared} squarederror, {n_huber} pseudohubererror")
    print(f"  Best objective:      {best_objective}")
    if best_trial:
        print(f"  Best holdout MAE:    {best_trial.value:.2f}s")
        print(f"  Best trial:          #{best_trial.number}")
    print(f"  CV Mean MAE:         {cv_mean_mae:.2f}s (+/- {cv_std_mae:.2f}s)")
    print(f"  Final rounds:        {best_n_rounds} (deterministic)")
    print(f"  Device:              {DEVICE}")
    print(f"  Elapsed time:        {elapsed/60:.1f} minutes")

    print(f"\n  Outlier trimming:")
    print(f"    Z-score threshold: {Z_SCORE_THRESHOLD}")
    print(f"    Samples removed:   {n_trimmed:,} ({pct_trimmed:.1f}%)")

    print(f"\n  Key metrics:")
    print(f"    Residual MAE:      {residual_mae_val:.1f}s")
    print(f"    Reconstructed MAE: {reconstructed_mae_val:.1f}s")
    print(f"    v1.0 MAE:          123.1s")
    print(f"    v1.1 vs v1.0:      {'BETTER' if reconstructed_mae_val < 123.1 else 'WORSE'} ({abs(reconstructed_mae_val - 123.1):.1f}s)")

    print(f"\n  Progressive improvement chain:")
    print(f"    Naive (schedule):  708.9s")
    print(f"    Baseline (P3):     394.7s")
    print(f"    Differentiator(P4):175.7s")
    print(f"    Tuned (P5/v1.0):   123.1s")
    print(f"    v1.1 Residual:     {reconstructed_mae_val:.1f}s")

    print(f"\n{'='*60}")
    print("v1.1 TRAINING COMPLETE")
    print(f"{'='*60}")
    print(f"  Model:       {model_path}")
    print(f"  Metrics:     {metrics_path}")


if __name__ == "__main__":
    main()
