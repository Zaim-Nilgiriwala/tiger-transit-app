"""Baseline configuration sweep for Tiger Transit ETA.

Tests ~15 SegSum baseline configurations systematically, reporting overall MAE,
per-time-bucket, per-stops-away, and tier coverage for each config.

Usage:
    python scripts/eval_baseline_sweep.py
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path("data/processed")


# ---------------------------------------------------------------------------
# Preprocessing: compute all derived columns once
# ---------------------------------------------------------------------------


def preprocess(df: pd.DataFrame, elapsed_bin_edges: np.ndarray,
               ss: pd.DataFrame) -> pd.DataFrame:
    """Add all derived columns needed by any config."""
    # hour_ct and day_type
    df["hour_ct"] = (df["timestamp"] - pd.Timedelta(hours=6)).dt.hour
    df["day_type"] = df["is_weekday"].astype(int)

    # last_stop_progress (join from stop_sequences)
    if "last_stop_progress" not in df.columns:
        lookup = ss[["route_id", "stop_id", "stop_progress"]].rename(
            columns={"stop_id": "last_stop_id", "stop_progress": "last_stop_progress"}
        )
        n = len(df)
        df = df.merge(lookup, on=["route_id", "last_stop_id"], how="left")
        assert len(df) == n

    # segment_decile
    remaining = df["target_stop_progress"].values - df["progress"].values
    span = df["target_stop_progress"].values - df["last_stop_progress"].values
    remaining = np.where(remaining < 0, remaining + 1.0, remaining)
    span = np.where(span <= 0, span + 1.0, span)
    normalized = remaining / span
    decile = np.floor(normalized * 10).clip(0, 9)
    nan_mask = df["last_stop_progress"].isna().values
    if nan_mask.any():
        fb = df["target_stop_progress"].values[nan_mask] - df["progress"].values[nan_mask]
        decile[nan_mask] = np.floor(fb * 10).clip(0, 9)
    df["segment_decile"] = decile.astype(int)

    # elapsed_decile
    secs = (df["timestamp_ms"] - df["last_stop_time_ms"]) / 1000
    n_bins = len(elapsed_bin_edges) - 1
    ed = np.digitize(secs, elapsed_bin_edges, right=True).clip(1, n_bins) - 1
    invalid = secs.isna() | (secs < 0)
    ed[invalid] = -1
    df["elapsed_decile"] = ed.astype(int)

    # is_stopped
    df["is_stopped"] = (df["speed"] == 0).astype(int)

    # on_time bins
    ot = df["last_stop_on_time"].values.copy().astype(float)
    # NaN sentinel
    nan_ot = np.isnan(ot)

    # 3-bin: negative=0, 0-4=1, 5+=2
    ot3 = np.where(ot < 0, 0, np.where(ot <= 4, 1, 2))
    ot3[nan_ot] = -1
    df["on_time_3bin"] = ot3.astype(int)

    # 4-bin: negative=0, 0-1=1, 2-5=2, 6+=3
    ot4 = np.where(ot < 0, 0, np.where(ot <= 1, 1, np.where(ot <= 5, 2, 3)))
    ot4[nan_ot] = -1
    df["on_time_4bin"] = ot4.astype(int)

    return df


def compute_elapsed_bins(train: pd.DataFrame, n_bins: int = 10) -> np.ndarray:
    """Compute elapsed-time quantile bin edges from training data."""
    secs = (train["timestamp_ms"] - train["last_stop_time_ms"]) / 1000
    valid = secs[secs.notna() & (secs >= 0)]
    _, bin_edges = pd.qcut(valid, n_bins, retbins=True, duplicates="drop")
    bin_edges[0] = 0.0
    bin_edges[-1] = np.inf
    return bin_edges


def compute_custom_elapsed_bins(train: pd.DataFrame, edges: list) -> np.ndarray:
    """Compute elapsed bins with custom edges instead of quantiles."""
    return np.array(edges, dtype=float)


# ---------------------------------------------------------------------------
# Generic tier builder & applier
# ---------------------------------------------------------------------------


def build_tier_lookup(df: pd.DataFrame, group_keys: list, min_obs: int,
                      agg_fn: str = "median") -> pd.DataFrame:
    """Build a lookup table by grouping on group_keys and aggregating."""
    agg = df.groupby(group_keys).agg(
        _value=("time_to_arrival_seconds", agg_fn),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    return agg[agg["_count"] >= min_obs].drop(columns=["_count"])


def apply_tiered_fallback(df: pd.DataFrame, tiers: list,
                          s2s_col: str = "baseline_s2s") -> np.ndarray:
    """Apply tiered merge cascade, returning predicted values.

    tiers: list of (lookup_df, merge_keys) tuples, ordered most-specific first.
    Final fallback uses s2s_col if available.
    """
    result = np.full(len(df), np.nan)

    for lookup, keys in tiers:
        mask = np.isnan(result)
        if not mask.any():
            break
        subset = df.loc[mask, keys].reset_index()
        merged = subset.merge(lookup, on=keys, how="left")
        vals = merged.set_index("index")["_value"]
        filled = vals.dropna()
        if len(filled) > 0:
            result[filled.index] = filled.values

    # S2S final fallback
    still_nan = np.isnan(result)
    if still_nan.any() and s2s_col in df.columns:
        result[still_nan] = df.loc[still_nan, s2s_col].values

    return result


# ---------------------------------------------------------------------------
# Configuration definitions
# ---------------------------------------------------------------------------


def define_configs():
    """Return list of config dicts to sweep."""
    base_keys = ["route_id", "last_stop_id", "target_stop_id"]

    configs = []

    # --- Group A: Dimension experiments ---

    # 1. Control: current baseline (elapsed10 + segment10, day_type, min_obs=5)
    configs.append({
        "name": "control",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "day_type"],
            base_keys + ["elapsed_decile", "day_type"],
            base_keys + ["segment_decile", "day_type"],
            base_keys + ["day_type"],
        ],
        "min_obs": 5, "agg_fn": "median",
        "require_valid_elapsed": [True, True, False, False],
    })

    # 2. No day_type
    configs.append({
        "name": "no-daytype",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 5, "agg_fn": "median",
        "require_valid_elapsed": [True, True, False, False],
    })

    # 3. +stopped (with day_type)
    configs.append({
        "name": "+stopped",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "day_type"],
            base_keys + ["elapsed_decile", "segment_decile", "day_type"],
            base_keys + ["elapsed_decile", "day_type"],
            base_keys + ["segment_decile", "day_type"],
            base_keys + ["day_type"],
        ],
        "min_obs": 5, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, False, False],
    })

    # 4. +stopped, no day_type, min_obs=3
    configs.append({
        "name": "+stopped-nodt",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 3, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, False, False],
    })

    # 5. Replace segment with is_stopped
    configs.append({
        "name": "replace-seg",
        "tiers": [
            base_keys + ["elapsed_decile", "is_stopped", "day_type"],
            base_keys + ["elapsed_decile", "day_type"],
            base_keys + ["is_stopped", "day_type"],
            base_keys + ["day_type"],
        ],
        "min_obs": 5, "agg_fn": "median",
        "require_valid_elapsed": [True, True, False, False],
    })

    # 6. 4D with on_time_3bin
    configs.append({
        "name": "4D-ot3",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "on_time_3bin"],
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 3, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, True, False, False],
    })

    # 7. 4D with on_time_4bin (expected winner)
    configs.append({
        "name": "4D-ot4",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "on_time_4bin"],
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 2, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, True, False, False],
    })

    # 8. 4D-ot4 with min_obs=3
    configs.append({
        "name": "4D-ot4-mo3",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "on_time_4bin"],
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 3, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, True, False, False],
    })

    # --- Group B: Elapsed bin experiments (on 4D-ot4 config) ---
    # These use custom elapsed bins; handled separately

    # --- Group C: Aggregation experiments ---

    # 12. Mean instead of median
    configs.append({
        "name": "4D-mean",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "on_time_4bin"],
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 2, "agg_fn": "mean",
        "require_valid_elapsed": [True, True, True, True, False, False],
    })

    # 13. MIN_OBS=1
    configs.append({
        "name": "4D-mo1",
        "tiers": [
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped", "on_time_4bin"],
            base_keys + ["elapsed_decile", "segment_decile", "is_stopped"],
            base_keys + ["elapsed_decile", "segment_decile"],
            base_keys + ["elapsed_decile"],
            base_keys + ["segment_decile"],
            base_keys,
        ],
        "min_obs": 1, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, True, False, False],
    })

    return configs


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------


def evaluate(actual: np.ndarray, predicted: np.ndarray, df: pd.DataFrame,
             config_name: str) -> dict:
    """Compute MAE overall and per-bucket."""
    valid = np.isfinite(predicted) & np.isfinite(actual)
    errors = np.abs(actual[valid] - predicted[valid])
    overall_mae = errors.mean()

    # Time buckets (in seconds of actual time)
    buckets = [
        ("0-1min", 0, 60),
        ("1-2min", 60, 120),
        ("2-5min", 120, 300),
        ("5-10min", 300, 600),
        ("10-20min", 600, 1200),
        ("20min+", 1200, 1e9),
    ]
    bucket_maes = {}
    for name, lo, hi in buckets:
        mask = valid & (actual >= lo) & (actual < hi)
        if mask.sum() > 0:
            bucket_maes[name] = np.abs(actual[mask] - predicted[mask]).mean()
        else:
            bucket_maes[name] = float("nan")

    # Per stops_away
    sa_maes = {}
    for sa in sorted(df["stops_away"].unique()):
        mask = valid & (df["stops_away"].values == sa)
        if mask.sum() >= 10:
            sa_maes[sa] = np.abs(actual[mask] - predicted[mask]).mean()

    # Tier coverage
    coverage = valid.sum() / len(actual) * 100

    return {
        "name": config_name,
        "overall_mae": overall_mae,
        "bucket_maes": bucket_maes,
        "sa_maes": sa_maes,
        "coverage": coverage,
        "n_valid": valid.sum(),
    }


def run_config(train: pd.DataFrame, test: pd.DataFrame, val: pd.DataFrame,
               config: dict, elapsed_col: str = "elapsed_decile") -> dict:
    """Run a single config and return results for test and val."""
    name = config["name"]
    min_obs = config["min_obs"]
    agg_fn = config["agg_fn"]
    tier_keys_list = config["tiers"]
    require_elapsed = config.get("require_valid_elapsed", [False] * len(tier_keys_list))

    # Build lookups from train
    lookups = []
    for keys, need_elapsed in zip(tier_keys_list, require_elapsed):
        # Replace elapsed_decile placeholder if using custom bins
        actual_keys = [elapsed_col if k == "elapsed_decile" else k for k in keys]
        if need_elapsed:
            mask = train[elapsed_col] >= 0
            lk = build_tier_lookup(train[mask], actual_keys, min_obs, agg_fn)
        else:
            lk = build_tier_lookup(train, actual_keys, min_obs, agg_fn)
        lookups.append((lk, actual_keys))

    # Apply to test and val
    actual_test = test["time_to_arrival_seconds"].values
    actual_val = val["time_to_arrival_seconds"].values

    pred_test = apply_tiered_fallback(test, lookups)
    pred_val = apply_tiered_fallback(val, lookups)

    test_result = evaluate(actual_test, pred_test, test, name)
    val_result = evaluate(actual_val, pred_val, val, name)

    # Tier coverage breakdown
    tier_counts = []
    running = np.zeros(len(test), dtype=bool)
    for lookup, keys in lookups:
        mask = np.isnan(apply_tiered_fallback(test, [(lookup, keys)], s2s_col="_nonexistent_"))
        new_filled = ~mask & ~running
        tier_counts.append(new_filled.sum())
        running = running | ~mask
    # S2S fallback
    s2s_count = (~np.isnan(pred_test) & ~running).sum()
    tier_counts.append(s2s_count)

    return {
        "test": test_result,
        "val": val_result,
        "tier_counts": tier_counts,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("=" * 70)
    print("Baseline Configuration Sweep")
    print("=" * 70)

    # Load stop sequences
    ss = pd.read_parquet(DATA_DIR / "stop_sequences.parquet")
    ss["route_id"] = ss["route_id"].astype("int64")

    # Load data
    print("\nLoading data...")
    train = pd.read_parquet(DATA_DIR / "train.parquet")
    val = pd.read_parquet(DATA_DIR / "val.parquet")
    test = pd.read_parquet(DATA_DIR / "test.parquet")
    print(f"  Train: {len(train):,}, Val: {len(val):,}, Test: {len(test):,}")

    # Compute standard elapsed bins
    elapsed_bin_edges = compute_elapsed_bins(train)
    print(f"  Standard elapsed bin edges: {np.round(elapsed_bin_edges, 1)}")

    # Preprocess all splits
    print("\nPreprocessing...")
    train = preprocess(train, elapsed_bin_edges, ss)
    val = preprocess(val, elapsed_bin_edges, ss)
    test = preprocess(test, elapsed_bin_edges, ss)

    # Run standard configs
    configs = define_configs()
    results = []

    print(f"\nRunning {len(configs)} standard configs...")
    for i, cfg in enumerate(configs):
        print(f"  [{i+1}/{len(configs)}] {cfg['name']}...", end=" ", flush=True)
        r = run_config(train, test, val, cfg)
        results.append(r)
        print(f"test={r['test']['overall_mae']:.1f}s, val={r['val']['overall_mae']:.1f}s")

    # --- Group B: Custom elapsed bins on 4D-ot4 ---
    print("\nRunning Group B (elapsed bin experiments)...")

    base_4d_config = {
        "tiers": [
            ["route_id", "last_stop_id", "target_stop_id", "elapsed_decile", "segment_decile", "is_stopped", "on_time_4bin"],
            ["route_id", "last_stop_id", "target_stop_id", "elapsed_decile", "segment_decile", "is_stopped"],
            ["route_id", "last_stop_id", "target_stop_id", "elapsed_decile", "segment_decile"],
            ["route_id", "last_stop_id", "target_stop_id", "elapsed_decile"],
            ["route_id", "last_stop_id", "target_stop_id", "segment_decile"],
            ["route_id", "last_stop_id", "target_stop_id"],
        ],
        "min_obs": 2, "agg_fn": "median",
        "require_valid_elapsed": [True, True, True, True, False, False],
    }

    elapsed_experiments = [
        ("4D-e15", 15, None),
        ("4D-e20", 20, None),
        ("4D-custom", None, [0, 10, 20, 30, 45, 60, 80, 100, 120, 160, 220, 300, 400, float("inf")]),
    ]

    for exp_name, n_bins, custom_edges in elapsed_experiments:
        print(f"  {exp_name}...", end=" ", flush=True)

        if custom_edges is not None:
            edges = np.array(custom_edges, dtype=float)
        else:
            edges = compute_elapsed_bins(train, n_bins=n_bins)

        # Recompute elapsed_decile with new bins
        alt_col = "_elapsed_alt"
        for split in [train, val, test]:
            secs = (split["timestamp_ms"] - split["last_stop_time_ms"]) / 1000
            nb = len(edges) - 1
            ed = np.digitize(secs, edges, right=True).clip(1, nb) - 1
            inv = secs.isna() | (secs < 0)
            ed[inv] = -1
            split[alt_col] = ed.astype(int)

        cfg = dict(base_4d_config)
        cfg["name"] = exp_name
        # Replace elapsed_decile with alt column in tier keys
        cfg["tiers"] = [
            [alt_col if k == "elapsed_decile" else k for k in tier]
            for tier in base_4d_config["tiers"]
        ]
        r = run_config(train, test, val, cfg, elapsed_col=alt_col)
        results.append(r)
        print(f"test={r['test']['overall_mae']:.1f}s, val={r['val']['overall_mae']:.1f}s")

        # Clean up
        for split in [train, val, test]:
            split.drop(columns=[alt_col], inplace=True)

    # --- Group D: Post-hoc corrections ---
    print("\nRunning Group D (post-hoc corrections)...")

    # 14. Linear on_time correction on best config
    print("  4D+linear-ot...", end=" ", flush=True)
    cfg_linear = dict(base_4d_config)
    cfg_linear["name"] = "4D+linear-ot"

    # Build lookups and get base predictions
    lookups_base = []
    for keys, need_elapsed in zip(base_4d_config["tiers"], base_4d_config["require_valid_elapsed"]):
        if need_elapsed:
            mask = train["elapsed_decile"] >= 0
            lk = build_tier_lookup(train[mask], keys, 2, "median")
        else:
            lk = build_tier_lookup(train, keys, 2, "median")
        lookups_base.append((lk, keys))

    pred_test_base = apply_tiered_fallback(test, lookups_base)
    pred_val_base = apply_tiered_fallback(val, lookups_base)

    # Apply linear correction: +1.0 * last_stop_on_time
    pred_test_linear = pred_test_base + 1.0 * test["last_stop_on_time"].values
    pred_val_linear = pred_val_base + 1.0 * val["last_stop_on_time"].values

    actual_test = test["time_to_arrival_seconds"].values
    actual_val = val["time_to_arrival_seconds"].values

    test_r14 = evaluate(actual_test, pred_test_linear, test, "4D+linear-ot")
    val_r14 = evaluate(actual_val, pred_val_linear, val, "4D+linear-ot")
    results.append({"test": test_r14, "val": val_r14, "tier_counts": []})
    print(f"test={test_r14['overall_mae']:.1f}s, val={val_r14['overall_mae']:.1f}s")

    # 15. Per-route best-of (SegSum vs S2S)
    print("  4D+per-route...", end=" ", flush=True)
    s2s_test = test["baseline_s2s"].values
    pred_test_perroute = pred_test_base.copy()
    pred_val_perroute = pred_val_base.copy()

    for rid in train["route_id"].unique():
        # Evaluate which is better on train
        rmask_train = train["route_id"] == rid
        train_actual = train.loc[rmask_train, "time_to_arrival_seconds"].values

        # Build SegSum for this route on train
        pred_train_seg = apply_tiered_fallback(train[rmask_train].reset_index(drop=True), lookups_base)
        s2s_train = train.loc[rmask_train, "baseline_s2s"].values

        seg_valid = np.isfinite(pred_train_seg) & np.isfinite(train_actual)
        s2s_valid = np.isfinite(s2s_train) & np.isfinite(train_actual)

        seg_mae = np.abs(train_actual[seg_valid] - pred_train_seg[seg_valid]).mean() if seg_valid.any() else 1e9
        s2s_mae = np.abs(train_actual[s2s_valid] - s2s_train[s2s_valid]).mean() if s2s_valid.any() else 1e9

        if s2s_mae < seg_mae:
            # Use S2S for this route
            rmask_test = test["route_id"].values == rid
            rmask_val = val["route_id"].values == rid
            pred_test_perroute[rmask_test] = test.loc[rmask_test, "baseline_s2s"].values
            pred_val_perroute[rmask_val] = val.loc[rmask_val, "baseline_s2s"].values

    test_r15 = evaluate(actual_test, pred_test_perroute, test, "4D+per-route")
    val_r15 = evaluate(actual_val, pred_val_perroute, val, "4D+per-route")
    results.append({"test": test_r15, "val": val_r15, "tier_counts": []})
    print(f"test={test_r15['overall_mae']:.1f}s, val={val_r15['overall_mae']:.1f}s")

    # ---------------------------------------------------------------------------
    # Summary report
    # ---------------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY: All Configurations")
    print("=" * 70)

    print(f"\n{'#':>3} {'Config':<20} {'Test MAE':>10} {'Val MAE':>10} {'Coverage':>10}")
    print(f"{'---':>3} {'--------------------':<20} {'--------':>10} {'--------':>10} {'--------':>10}")

    for i, r in enumerate(results, 1):
        t = r["test"]
        v = r["val"]
        print(f"{i:3d} {t['name']:<20} {t['overall_mae']:10.1f} {v['overall_mae']:10.1f} {t['coverage']:9.1f}%")

    # Best config
    best = min(results, key=lambda r: r["test"]["overall_mae"])
    print(f"\nBest config: {best['test']['name']} (test={best['test']['overall_mae']:.1f}s)")

    # Per-time-bucket breakdown for top 5
    print("\n" + "=" * 70)
    print("Per-Time-Bucket MAE (Top 5 Configs)")
    print("=" * 70)

    sorted_results = sorted(results, key=lambda r: r["test"]["overall_mae"])[:5]
    bucket_names = ["0-1min", "1-2min", "2-5min", "5-10min", "10-20min", "20min+"]

    header = f"{'Config':<20}" + "".join(f"{b:>10}" for b in bucket_names)
    print(header)
    print("-" * len(header))

    for r in sorted_results:
        t = r["test"]
        vals = "".join(f"{t['bucket_maes'].get(b, float('nan')):10.1f}" for b in bucket_names)
        print(f"{t['name']:<20}{vals}")

    # Per-stops-away for best config
    print(f"\n--- Per-stops-away for {best['test']['name']} ---")
    print(f"  {'SA':>4} {'Test MAE':>10} {'Val MAE':>10}")
    for sa in sorted(best["test"]["sa_maes"].keys()):
        t_mae = best["test"]["sa_maes"].get(sa, float("nan"))
        v_mae = best["val"]["sa_maes"].get(sa, float("nan"))
        print(f"  {sa:4d} {t_mae:10.1f} {v_mae:10.1f}")


if __name__ == "__main__":
    main()
