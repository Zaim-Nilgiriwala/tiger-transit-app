"""Evaluate existing v1.1 model on new baselines (no retrain).

Loads the existing model, predicts residuals on the updated test_featured_v2,
reconstructs final ETAs using the new baseline_eta, and prints MAE comparison.

Usage:
    python scripts/eval_baseline.py
"""

from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb

DATA_DIR = Path("data/processed")
MODEL_PATH = Path("models/v1_1_residual.ubj")

# Feature list must match training (from train_advanced.py)
FEATURES = [
    "distance_to_target", "scheduled_time_to_target", "current_speed",
    "route_progress", "stops_remaining", "stop_index",
    "minutes_since_midnight", "day_of_week", "route_id", "pattern_id",
    "precipitation_mm", "temperature_c", "passenger_load", "is_idle",
    "gps_speed_mps", "speed_mean_30s", "speed_mean_60s", "speed_mean_120s",
    "speed_mean_180s", "speed_std_30s", "speed_std_60s", "speed_std_120s",
    "speed_std_180s", "acceleration", "is_idle_gps", "seconds_idle",
    "is_timepoint", "scheduled_departure_seconds", "timepoints_remaining",
    "time_until_next_timepoint_departure", "timepoint_adherence",
    "segment_travel_median", "segment_travel_p25", "segment_travel_p75",
    "dwell_median", "dwell_p25", "dwell_p75",
    "target_dwell_median", "target_dwell_p25", "target_dwell_p75",
    "speed_ratio", "is_rush_hour",
    "baseline_s2s", "baseline_seg_sum", "baseline_eta",
]


def main():
    print("Loading model...")
    model = xgb.Booster()
    model.load_model(str(MODEL_PATH))

    print("Loading test data...")
    test = pd.read_parquet(DATA_DIR / "test_featured_v2.parquet")
    actual = test["time_to_arrival_seconds"].values

    # Predict residuals
    X = test[FEATURES].values
    dmat = xgb.DMatrix(X, feature_names=FEATURES)
    pred_residual = model.predict(dmat)

    # Reconstruct final ETA
    baseline_eta = test["baseline_eta"].values
    pred_eta = baseline_eta + pred_residual

    # MAE
    model_mae = np.nanmean(np.abs(actual - pred_eta))
    baseline_mae = np.nanmean(np.abs(actual - baseline_eta))
    s2s_mae = np.nanmean(np.abs(actual - test["baseline_s2s"].values))
    seg_mae = np.nanmean(np.abs(actual - test["baseline_seg_sum"].values))

    print("\n" + "=" * 60)
    print("Results on test set (new segment-decile baselines)")
    print("=" * 60)
    print(f"  S2S-only baseline MAE:      {s2s_mae:7.1f}s")
    print(f"  SegSum baseline MAE:        {seg_mae:7.1f}s")
    print(f"  Blended baseline MAE:       {baseline_mae:7.1f}s")
    print(f"  Model (baseline + residual): {model_mae:7.1f}s")
    print(f"  Previous model MAE:          94.6s (for comparison)")

    # Per-stops-away breakdown
    print("\n--- MAE by stops_away ---")
    print(f"  {'stops':>6} | {'N':>8} | {'Baseline':>9} | {'Model':>9} | {'Improvement':>12}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*9}-+-{'-'*9}-+-{'-'*12}")

    test["_pred_eta"] = pred_eta
    test["_baseline_err"] = np.abs(actual - baseline_eta)
    test["_model_err"] = np.abs(actual - pred_eta)

    for sa in sorted(test["stops_away"].unique()):
        mask = test["stops_away"] == sa
        n = mask.sum()
        if n < 10:
            continue
        bl_mae = test.loc[mask, "_baseline_err"].mean()
        ml_mae = test.loc[mask, "_model_err"].mean()
        impr = bl_mae - ml_mae
        print(f"  {sa:6d} | {n:8,} | {bl_mae:9.1f} | {ml_mae:9.1f} | {impr:+12.1f}")

    # Per-route breakdown
    print("\n--- MAE by route_id ---")
    print(f"  {'Route':>6} | {'N':>8} | {'Baseline':>9} | {'Model':>9}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*9}-+-{'-'*9}")

    for rid in sorted(test["route_id"].unique()):
        mask = test["route_id"] == rid
        n = mask.sum()
        if n < 50:
            continue
        bl_mae = test.loc[mask, "_baseline_err"].mean()
        ml_mae = test.loc[mask, "_model_err"].mean()
        print(f"  {rid:6d} | {n:8,} | {bl_mae:9.1f} | {ml_mae:9.1f}")

    # Short-trip analysis (0-2 min actual)
    print("\n--- Short-trip analysis (actual < 120s) ---")
    short_mask = actual < 120
    if short_mask.any():
        n_short = short_mask.sum()
        bl_short = test.loc[short_mask, "_baseline_err"].mean()
        ml_short = test.loc[short_mask, "_model_err"].mean()
        bl_bias = (baseline_eta[short_mask] - actual[short_mask]).mean()
        ml_bias = (pred_eta[short_mask] - actual[short_mask]).mean()
        print(f"  N={n_short:,}")
        print(f"  Baseline MAE: {bl_short:.1f}s  (mean bias: {bl_bias:+.1f}s)")
        print(f"  Model MAE:    {ml_short:.1f}s  (mean bias: {ml_bias:+.1f}s)")

    test.drop(columns=["_pred_eta", "_baseline_err", "_model_err"], inplace=True)


if __name__ == "__main__":
    main()
