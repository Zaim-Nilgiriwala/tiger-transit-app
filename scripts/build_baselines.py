"""
build_baselines.py - Baseline ETA computation pipeline for Tiger Transit v1.1.

Computes historical baseline ETAs using a tiered fallback hierarchy, segment-
median-sum baselines, a 50/50 blend, and residual labels. Augments the existing
train/val/test parquets with baseline_eta and residual columns.

Baselines computed:
  BASE-01: Stop-to-stop average lookup (3-tier fallback hierarchy)
  BASE-02: Segment-median-sum baseline (stop-distance median with tiered fallback)
  BASE-03: 50/50 blend of BASE-01 and BASE-02
  BASE-04: Residual labels (time_to_arrival_seconds - baseline_eta)
  BASE-05: Diagnostic report (MAE, per-route breakdown, error distribution)

Usage:
    python scripts/build_baselines.py

Input:
    data/processed/{train,val,test}.parquet
    data/processed/stop_sequences.parquet

Output:
    data/processed/{train,val,test}.parquet  (augmented with baseline_eta, residual)
    models/diagnostics/baseline_error_dist.png
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/processed")
DIAG_DIR = Path("models/diagnostics")

MIN_OBS = 5
SPLITS = ["train", "val", "test"]

TOD_BUCKETS = {
    "morning":   (6, 10),   # 6am-10am CT
    "midday":    (10, 14),  # 10am-2pm CT
    "afternoon": (14, 18),  # 2pm-6pm CT
    "evening":   (18, 23),  # 6pm-11pm CT
}


# ---------------------------------------------------------------------------
# Helper: Central Time hour extraction
# ---------------------------------------------------------------------------


def add_ct_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour_ct column: UTC timestamp shifted to US Central (UTC-6)."""
    df["hour_ct"] = (df["timestamp"] - pd.Timedelta(hours=6)).dt.hour
    return df


# ---------------------------------------------------------------------------
# Helper: Load stop sequences
# ---------------------------------------------------------------------------


def load_stop_sequences() -> pd.DataFrame:
    """Load stop_sequences.parquet with clean dtypes."""
    ss = pd.read_parquet(DATA_DIR / "stop_sequences.parquet")
    # Ensure route_id is plain int64 (not nullable Int64)
    ss["route_id"] = ss["route_id"].astype("int64")
    return ss


# ---------------------------------------------------------------------------
# BASE-01: Stop-to-Stop Average Lookup (3-Tier Fallback)
# ---------------------------------------------------------------------------


def build_tier1_lookup(train: pd.DataFrame) -> pd.DataFrame:
    """Tier 1: (route_id, last_stop_id, target_stop_id, hour_ct, day_type) mean."""
    agg = train.groupby(
        ["route_id", "last_stop_id", "target_stop_id", "hour_ct", "day_type"],
    ).agg(
        baseline_s2s=("time_to_arrival_seconds", "mean"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    valid = agg[agg["_count"] >= MIN_OBS].drop(columns=["_count"])
    return valid


def build_tier2_lookup(train: pd.DataFrame) -> pd.DataFrame:
    """Tier 2: (route_id, last_stop_id, target_stop_id, day_type) mean."""
    agg = train.groupby(
        ["route_id", "last_stop_id", "target_stop_id", "day_type"],
    ).agg(
        _t2_val=("time_to_arrival_seconds", "mean"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    valid = agg[agg["_count"] >= MIN_OBS].drop(columns=["_count"])
    return valid


def build_tier3_lookup(train: pd.DataFrame, ss: pd.DataFrame) -> pd.DataFrame:
    """Tier 3: Per-(route_id, day_type) median seconds_per_shape_dist_unit.

    For rows where last_stop_id is in stop_sequences, use shape_dist_traveled.
    For rows where last_stop_id=0 or not in stop_sequences, use progress columns.
    """
    # Merge shape_dist for last_stop_id and target_stop_id
    ss_last = ss[["route_id", "stop_id", "shape_dist_traveled"]].rename(
        columns={"stop_id": "last_stop_id", "shape_dist_traveled": "last_shape_dist"}
    )
    ss_target = ss[["route_id", "stop_id", "shape_dist_traveled"]].rename(
        columns={"stop_id": "target_stop_id", "shape_dist_traveled": "target_shape_dist"}
    )

    # Also get max_shape_dist per route for progress-based distance fallback
    max_dist = ss.groupby("route_id")["max_shape_dist"].first().reset_index()

    t = train[["route_id", "last_stop_id", "target_stop_id", "day_type",
               "time_to_arrival_seconds", "progress", "target_stop_progress"]].copy()

    n_pre = len(t)
    t = t.merge(ss_last, on=["route_id", "last_stop_id"], how="left")
    assert len(t) == n_pre, f"Row explosion on ss_last merge: {n_pre} -> {len(t)}"
    t = t.merge(ss_target, on=["route_id", "target_stop_id"], how="left")
    assert len(t) == n_pre, f"Row explosion on ss_target merge: {n_pre} -> {len(t)}"
    t = t.merge(max_dist, on="route_id", how="left")
    assert len(t) == n_pre, f"Row explosion on max_dist merge: {n_pre} -> {len(t)}"

    # Compute distance: prefer shape_dist, fallback to progress-based
    shape_dist = t["target_shape_dist"] - t["last_shape_dist"]
    progress_dist = (t["target_stop_progress"] - t["progress"]) * t["max_shape_dist"]

    t["_dist"] = np.where(
        shape_dist.notna() & (shape_dist > 0),
        shape_dist,
        np.where(progress_dist > 0, progress_dist, np.nan)
    )

    # seconds per dist unit
    t["_sec_per_unit"] = t["time_to_arrival_seconds"] / t["_dist"]

    # Filter valid rows
    valid = t["_dist"].notna() & (t["_dist"] > 0) & t["_sec_per_unit"].notna()
    t = t[valid].copy()

    # Aggregate median per (route_id, day_type)
    tier3 = t.groupby(["route_id", "day_type"]).agg(
        _sec_per_unit=("_sec_per_unit", "median"),
        _count=("_sec_per_unit", "count"),
    ).reset_index()
    tier3 = tier3[tier3["_count"] >= MIN_OBS].drop(columns=["_count"])

    return tier3


def apply_s2s_fallback(df: pd.DataFrame, tier1: pd.DataFrame,
                       tier2: pd.DataFrame, tier3: pd.DataFrame,
                       ss: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """Apply 3-tier fallback hierarchy to produce baseline_s2s column."""
    n_before = len(df)

    # --- Tier 1 merge ---
    df = df.merge(
        tier1,
        on=["route_id", "last_stop_id", "target_stop_id", "hour_ct", "day_type"],
        how="left",
    )
    assert len(df) == n_before, f"Tier 1 merge explosion: {n_before} -> {len(df)}"
    t1_filled = df["baseline_s2s"].notna().sum()

    # --- Tier 2 fill ---
    mask_t2 = df["baseline_s2s"].isna()
    if mask_t2.any():
        t2_merge = df.loc[mask_t2, ["route_id", "last_stop_id", "target_stop_id", "day_type"]].merge(
            tier2, on=["route_id", "last_stop_id", "target_stop_id", "day_type"], how="left"
        )
        df.loc[mask_t2, "baseline_s2s"] = t2_merge["_t2_val"].values
    t2_filled = df["baseline_s2s"].notna().sum() - t1_filled

    # --- Tier 3 fill ---
    mask_t3 = df["baseline_s2s"].isna()
    if mask_t3.any():
        # Need distance for each row, then multiply by sec_per_unit
        ss_last = ss[["route_id", "stop_id", "shape_dist_traveled"]].rename(
            columns={"stop_id": "last_stop_id", "shape_dist_traveled": "last_shape_dist"}
        )
        ss_target = ss[["route_id", "stop_id", "shape_dist_traveled"]].rename(
            columns={"stop_id": "target_stop_id", "shape_dist_traveled": "target_shape_dist"}
        )
        max_dist = ss.groupby("route_id")["max_shape_dist"].first().reset_index()

        t3_rows = df.loc[mask_t3].copy()
        n_t3 = len(t3_rows)
        t3_rows = t3_rows.merge(ss_last, on=["route_id", "last_stop_id"], how="left")
        if len(t3_rows) > n_t3:
            t3_rows = t3_rows.drop_duplicates(
                subset=t3_rows.columns.difference(
                    ["last_shape_dist", "target_shape_dist"]
                ),
                keep="first",
            )
        t3_rows = t3_rows.merge(ss_target, on=["route_id", "target_stop_id"], how="left")
        if len(t3_rows) > n_t3:
            t3_rows = t3_rows.drop_duplicates(
                subset=t3_rows.columns.difference(
                    ["last_shape_dist", "target_shape_dist"]
                ),
                keep="first",
            )
        t3_rows = t3_rows.merge(max_dist, on="route_id", how="left")
        if len(t3_rows) > n_t3:
            t3_rows = t3_rows.drop_duplicates(
                subset=t3_rows.columns.difference(
                    ["last_shape_dist", "target_shape_dist", "max_shape_dist"]
                ),
                keep="first",
            )

        # Compute distance
        shape_dist = t3_rows["target_shape_dist"] - t3_rows["last_shape_dist"]
        progress_dist = (
            (t3_rows["target_stop_progress"] - t3_rows["progress"])
            * t3_rows["max_shape_dist"]
        )
        t3_rows["_dist"] = np.where(
            shape_dist.notna() & (shape_dist > 0),
            shape_dist,
            np.where(progress_dist > 0, progress_dist, np.nan),
        )

        # Merge tier3 lookup
        t3_rows = t3_rows.merge(tier3, on=["route_id", "day_type"], how="left")

        # Compute estimate
        t3_vals = t3_rows["_dist"].values * t3_rows["_sec_per_unit"].values
        df.loc[mask_t3, "baseline_s2s"] = t3_vals

    t3_filled = df["baseline_s2s"].notna().sum() - t1_filled - t2_filled
    still_nan = df["baseline_s2s"].isna().sum()

    total = len(df)
    print(f"  {split_name} S2S tier coverage:")
    print(f"    Tier 1: {t1_filled:,} ({t1_filled/total*100:.1f}%)")
    print(f"    Tier 2: {t2_filled:,} ({t2_filled/total*100:.1f}%)")
    print(f"    Tier 3: {t3_filled:,} ({t3_filled/total*100:.1f}%)")
    print(f"    Still NaN: {still_nan:,} ({still_nan/total*100:.2f}%)")

    return df


# ---------------------------------------------------------------------------
# BASE-02: Segment-Median-Sum Baseline
#
# Uses (route_id, last_stop_id, stops_away, hour_ct, day_type) as the lookup
# key. This captures a DIFFERENT aggregation axis than S2S (which uses
# target_stop_id instead of stops_away). The median-based estimate provides
# a complementary signal to the mean-based S2S baseline.
#
# Tiered fallback:
#   Tier A: (route_id, last_stop_id, stops_away, hour_ct, day_type) median
#   Tier B: (route_id, last_stop_id, stops_away, day_type) median
#   Tier C: (route_id, stops_away, hour_ct, day_type) median
# ---------------------------------------------------------------------------


def build_seg_sum_lookups(train: pd.DataFrame) -> tuple:
    """Build tiered segment-sum lookups from training data.

    Returns (tier_a, tier_b, tier_c) DataFrames.
    """
    # Tier A: (route_id, last_stop_id, stops_away, hour_ct, day_type) median
    agg_a = train.groupby(
        ["route_id", "last_stop_id", "stops_away", "hour_ct", "day_type"]
    ).agg(
        baseline_seg_sum=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_a = agg_a[agg_a["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier A (route, last_stop, stops_away, hour, day): {len(tier_a):,} combos")

    # Tier B: (route_id, last_stop_id, stops_away, day_type) median
    agg_b = train.groupby(
        ["route_id", "last_stop_id", "stops_away", "day_type"]
    ).agg(
        _seg_b=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_b = agg_b[agg_b["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier B (route, last_stop, stops_away, day):      {len(tier_b):,} combos")

    # Tier C: (route_id, stops_away, hour_ct, day_type) median
    agg_c = train.groupby(
        ["route_id", "stops_away", "hour_ct", "day_type"]
    ).agg(
        _seg_c=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_c = agg_c[agg_c["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier C (route, stops_away, hour, day):           {len(tier_c):,} combos")

    return tier_a, tier_b, tier_c


def apply_seg_sum_fallback(df: pd.DataFrame, tier_a: pd.DataFrame,
                           tier_b: pd.DataFrame, tier_c: pd.DataFrame,
                           split_name: str) -> pd.DataFrame:
    """Apply segment-sum tiered fallback to produce baseline_seg_sum column."""
    n_before = len(df)

    # --- Tier A merge ---
    df = df.merge(
        tier_a,
        on=["route_id", "last_stop_id", "stops_away", "hour_ct", "day_type"],
        how="left",
    )
    assert len(df) == n_before, f"Seg Tier A merge explosion: {n_before} -> {len(df)}"
    ta_filled = df["baseline_seg_sum"].notna().sum()

    # --- Tier B fill ---
    mask_b = df["baseline_seg_sum"].isna()
    if mask_b.any():
        b_merge = df.loc[mask_b, ["route_id", "last_stop_id", "stops_away", "day_type"]].merge(
            tier_b, on=["route_id", "last_stop_id", "stops_away", "day_type"], how="left"
        )
        df.loc[mask_b, "baseline_seg_sum"] = b_merge["_seg_b"].values
    tb_filled = df["baseline_seg_sum"].notna().sum() - ta_filled

    # --- Tier C fill ---
    mask_c = df["baseline_seg_sum"].isna()
    if mask_c.any():
        c_merge = df.loc[mask_c, ["route_id", "stops_away", "hour_ct", "day_type"]].merge(
            tier_c, on=["route_id", "stops_away", "hour_ct", "day_type"], how="left"
        )
        df.loc[mask_c, "baseline_seg_sum"] = c_merge["_seg_c"].values
    tc_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled

    still_nan = df["baseline_seg_sum"].isna().sum()
    total = len(df)

    print(f"  {split_name} segment-sum tier coverage:")
    print(f"    Tier A: {ta_filled:,} ({ta_filled/total*100:.1f}%)")
    print(f"    Tier B: {tb_filled:,} ({tb_filled/total*100:.1f}%)")
    print(f"    Tier C: {tc_filled:,} ({tc_filled/total*100:.1f}%)")
    print(f"    Still NaN: {still_nan:,} ({still_nan/total*100:.2f}%)")

    return df


# ---------------------------------------------------------------------------
# BASE-03: Blend Baselines
# ---------------------------------------------------------------------------


def blend_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """50/50 blend of s2s and segment-sum baselines.

    Where one is NaN and other is not: use the non-NaN one.
    """
    s2s = df["baseline_s2s"].values
    seg = df["baseline_seg_sum"].values

    both_valid = np.isfinite(s2s) & np.isfinite(seg)
    s2s_only = np.isfinite(s2s) & ~np.isfinite(seg)
    seg_only = ~np.isfinite(s2s) & np.isfinite(seg)

    blend = np.full(len(df), np.nan)
    blend[both_valid] = (s2s[both_valid] + seg[both_valid]) / 2.0
    blend[s2s_only] = s2s[s2s_only]
    blend[seg_only] = seg[seg_only]

    df["baseline_eta"] = blend
    return df


# ---------------------------------------------------------------------------
# BASE-04: Residual Labels
# ---------------------------------------------------------------------------


def compute_residuals(df: pd.DataFrame) -> pd.DataFrame:
    """Compute residual = time_to_arrival_seconds - baseline_eta."""
    df["residual"] = df["time_to_arrival_seconds"] - df["baseline_eta"]
    return df


# ---------------------------------------------------------------------------
# BASE-05: Diagnostic Report
# ---------------------------------------------------------------------------


def print_diagnostics(splits_data: dict, ss: pd.DataFrame):
    """Print comprehensive diagnostic report."""
    print("\n" + "=" * 60)
    print("BASE-05: Diagnostic Report")
    print("=" * 60)

    test = splits_data["test"]
    train = splits_data["train"]

    # a. Overall MAE for all three methods
    print("\n--- Overall MAE on Test Set ---")
    for method, col in [("S2S-only", "baseline_s2s"),
                        ("Segment-sum", "baseline_seg_sum"),
                        ("Blended (50/50)", "baseline_eta")]:
        valid = test[col].notna() & test["time_to_arrival_seconds"].notna()
        if valid.sum() > 0:
            mae = (test.loc[valid, "time_to_arrival_seconds"] - test.loc[valid, col]).abs().mean()
            coverage = valid.sum() / len(test) * 100
            print(f"  {method:20s}: MAE = {mae:7.1f}s  (coverage: {coverage:.1f}%)")
        else:
            print(f"  {method:20s}: No valid predictions")

    # b. Per-route breakdown table
    print("\n--- Per-Route MAE Breakdown (Test Set) ---")
    print(f"  {'Route':>6} | {'N':>8} | {'S2S MAE':>9} | {'SegSum MAE':>11} | {'Blend MAE':>10}")
    print(f"  {'-'*6}-+-{'-'*8}-+-{'-'*9}-+-{'-'*11}-+-{'-'*10}")

    for route_id in sorted(test["route_id"].unique()):
        rmask = test["route_id"] == route_id
        rdf = test[rmask]
        n = len(rdf)

        s2s_valid = rdf["baseline_s2s"].notna()
        seg_valid = rdf["baseline_seg_sum"].notna()
        blend_valid = rdf["baseline_eta"].notna()

        s2s_mae = (
            (rdf.loc[s2s_valid, "time_to_arrival_seconds"]
             - rdf.loc[s2s_valid, "baseline_s2s"]).abs().mean()
            if s2s_valid.any() else float("nan")
        )
        seg_mae = (
            (rdf.loc[seg_valid, "time_to_arrival_seconds"]
             - rdf.loc[seg_valid, "baseline_seg_sum"]).abs().mean()
            if seg_valid.any() else float("nan")
        )
        blend_mae = (
            (rdf.loc[blend_valid, "time_to_arrival_seconds"]
             - rdf.loc[blend_valid, "baseline_eta"]).abs().mean()
            if blend_valid.any() else float("nan")
        )

        print(f"  {route_id:6d} | {n:8,} | {s2s_mae:9.1f} | {seg_mae:11.1f} | {blend_mae:10.1f}")

    # c. Error distribution histogram
    print("\n--- Saving Error Distribution Histogram ---")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        valid = test["baseline_eta"].notna()
        errors = test.loc[valid, "time_to_arrival_seconds"] - test.loc[valid, "baseline_eta"]

        fig, ax = plt.subplots(figsize=(10, 5))
        bins = np.arange(-2000, 2000, 20)
        ax.hist(errors, bins=bins, edgecolor="none", alpha=0.7, color="steelblue")
        ax.set_xlabel("Residual (actual - baseline_eta) [seconds]")
        ax.set_ylabel("Count")
        ax.set_title("Baseline Error Distribution (Test Set)")
        ax.axvline(0, color="red", linestyle="--", alpha=0.5, label="zero")
        ax.axvline(errors.mean(), color="orange", linestyle="--", alpha=0.7,
                   label=f"mean={errors.mean():.1f}s")
        ax.legend()
        ax.set_xlim(-2000, 2000)
        fig.tight_layout()
        out_path = DIAG_DIR / "baseline_error_dist.png"
        fig.savefig(out_path, dpi=150)
        plt.close(fig)
        print(f"  Saved {out_path}")
    except ImportError:
        print("  WARNING: matplotlib not available, skipping histogram")

    # d. Time-of-day breakdown
    print("\n--- Time-of-Day MAE Breakdown (Test Set) ---")
    print(f"  {'TOD Bucket':>12} | {'N':>8} | {'Blend MAE':>10}")
    print(f"  {'-'*12}-+-{'-'*8}-+-{'-'*10}")

    for bucket, (h_start, h_end) in TOD_BUCKETS.items():
        tod_mask = (
            test["hour_ct"].between(h_start, h_end - 1) & test["baseline_eta"].notna()
        )
        if tod_mask.any():
            mae = (
                test.loc[tod_mask, "time_to_arrival_seconds"]
                - test.loc[tod_mask, "baseline_eta"]
            ).abs().mean()
            print(f"  {bucket:>12} | {tod_mask.sum():8,} | {mae:10.1f}")
        else:
            print(f"  {bucket:>12} | {0:8,} |        N/A")

    # e. Residual statistics
    print("\n--- Residual Statistics ---")
    for split_name, sdf in splits_data.items():
        valid = sdf["residual"].notna()
        if valid.any():
            r = sdf.loc[valid, "residual"]
            print(
                f"  {split_name:>6}: mean={r.mean():+8.1f}s, std={r.std():8.1f}s, "
                f"median={r.median():+8.1f}s, min={r.min():+9.1f}s, max={r.max():+9.1f}s"
            )

    train_resid_mean = train.loc[train["residual"].notna(), "residual"].mean()
    if abs(train_resid_mean) < 30:
        print(
            f"  PASS: Train residual mean ({train_resid_mean:+.1f}s) "
            f"is within +/-30s of zero"
        )
    else:
        print(
            f"  FAIL: Train residual mean ({train_resid_mean:+.1f}s) "
            f"exceeds +/-30s threshold!"
        )

    # f. Baseline NaN summary
    print("\n--- Baseline NaN Summary ---")
    for split_name, sdf in splits_data.items():
        be_nan = sdf["baseline_eta"].isna().sum()
        r_nan = sdf["residual"].isna().sum()
        print(f"  {split_name:>6}: baseline_eta NaN={be_nan:,}, residual NaN={r_nan:,}")


# ---------------------------------------------------------------------------
# Main Pipeline
# ---------------------------------------------------------------------------


def main():
    print("=" * 60)
    print("Baseline Computation Pipeline (v1.1)")
    print("=" * 60)

    # --- Load stop sequences ---
    print("\nLoading stop_sequences...")
    ss = load_stop_sequences()
    print(f"  {len(ss)} rows, {ss['route_id'].nunique()} routes")

    # --- Load training data ---
    print("\n" + "=" * 60)
    print("Step 1: Build lookup tables from training data ONLY")
    print("=" * 60)

    train_path = DATA_DIR / "train.parquet"
    print(f"\nLoading {train_path}...")
    train = pd.read_parquet(train_path)
    print(f"  {len(train):,} rows")

    # Add derived columns
    train = add_ct_hour(train)
    train["day_type"] = train["is_weekday"].astype(int)

    # --- BASE-01: S2S Lookup Tables ---
    print("\n--- BASE-01: Building S2S Lookup Tables ---")
    tier1 = build_tier1_lookup(train)
    print(f"  Tier 1 combos (>=5 obs): {len(tier1):,}")
    tier2 = build_tier2_lookup(train)
    print(f"  Tier 2 combos (>=5 obs): {len(tier2):,}")
    tier3 = build_tier3_lookup(train, ss)
    print(f"  Tier 3 combos (>=5 obs): {len(tier3):,}")

    # --- BASE-02: Segment-Sum Lookup Tables ---
    print("\n--- BASE-02: Building Segment-Sum Lookups ---")
    seg_a, seg_b, seg_c = build_seg_sum_lookups(train)

    # --- Process all splits ---
    print("\n" + "=" * 60)
    print("Step 2: Apply baselines to all splits")
    print("=" * 60)

    splits_data = {}

    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}.parquet"
        print(f"\n{'='*60}")
        print(f"Processing {split_name} ({path})")
        print(f"{'='*60}")

        df = pd.read_parquet(path)
        n_original = len(df)
        print(f"  Loaded {n_original:,} rows")

        # Add derived columns
        df = add_ct_hour(df)
        df["day_type"] = df["is_weekday"].astype(int)

        # Apply S2S fallback
        print("\n  Applying S2S fallback hierarchy...")
        df = apply_s2s_fallback(df, tier1, tier2, tier3, ss, split_name)
        assert len(df) == n_original, (
            f"Row count changed after S2S: {n_original} -> {len(df)}"
        )

        # Apply segment-sum fallback
        print("\n  Applying segment-sum fallback hierarchy...")
        df = apply_seg_sum_fallback(df, seg_a, seg_b, seg_c, split_name)
        assert len(df) == n_original, (
            f"Row count changed after seg-sum: {n_original} -> {len(df)}"
        )

        # Blend
        print("\n  Blending baselines (50/50)...")
        df = blend_baselines(df)
        be_nan = df["baseline_eta"].isna().sum()
        print(
            f"  baseline_eta NaN after blend: "
            f"{be_nan:,} ({be_nan/n_original*100:.3f}%)"
        )

        # Residuals
        df = compute_residuals(df)

        splits_data[split_name] = df
        print(
            f"  {split_name} complete: {n_original:,} rows, "
            f"baseline_eta NaN={be_nan:,}, "
            f"residual mean={df['residual'].mean():+.1f}s"
        )

    # --- Diagnostics ---
    print_diagnostics(splits_data, ss)

    # --- Write augmented parquets ---
    print("\n" + "=" * 60)
    print("Step 3: Write augmented parquets")
    print("=" * 60)

    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}.parquet"
        df = splits_data[split_name]

        # Read original to verify columns, then write with new columns
        original = pd.read_parquet(path)
        n_original = len(original)

        # Add new columns to original
        original["baseline_eta"] = df["baseline_eta"].values
        original["residual"] = df["residual"].values

        # Also store intermediate baselines for diagnostic reference
        original["baseline_s2s"] = df["baseline_s2s"].values
        original["baseline_seg_sum"] = df["baseline_seg_sum"].values

        assert len(original) == n_original, (
            f"Row count changed during write: {n_original} -> {len(original)}"
        )

        original.to_parquet(path)
        print(
            f"  Wrote {path} ({n_original:,} rows, "
            f"new cols: baseline_eta, residual, baseline_s2s, baseline_seg_sum)"
        )

    # --- Final verification ---
    print("\n" + "=" * 60)
    print("Step 4: Final Verification")
    print("=" * 60)

    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}.parquet"
        df = pd.read_parquet(path)
        assert "baseline_eta" in df.columns, f"Missing baseline_eta in {split_name}"
        assert "residual" in df.columns, f"Missing residual in {split_name}"
        be_nan = df["baseline_eta"].isna().sum()
        r_nan = df["residual"].isna().sum()
        print(
            f"  {split_name}: {len(df):,} rows, "
            f"baseline_eta NaN={be_nan:,}, "
            f"residual NaN={r_nan:,}, "
            f"baseline_eta mean={df['baseline_eta'].mean():.1f}s, "
            f"residual mean={df['residual'].mean():+.1f}s"
        )

    train_df = pd.read_parquet(DATA_DIR / "train.parquet")
    train_resid_mean = train_df["residual"].mean()
    assert abs(train_resid_mean) < 30, (
        f"Train residual mean ({train_resid_mean:+.1f}s) "
        f"exceeds +/-30s threshold!"
    )

    print(f"\n{'='*60}")
    print("Baseline computation pipeline complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
