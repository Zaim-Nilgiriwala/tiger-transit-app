"""
build_baselines.py - Baseline ETA computation pipeline for Tiger Transit v1.1.

Computes historical baseline ETAs using a 4D tiered fallback hierarchy
(elapsed + segment + is_stopped + on_time_bin), stop-to-stop averages,
and residual labels. Augments the existing train/val/test parquets with
baseline_eta and residual columns.

Baselines computed:
  BASE-01: Stop-to-stop average lookup (3-tier fallback hierarchy)
  BASE-02: 4D destination-specific baseline (6-tier fallback, no day_type)
          Tier A: (route, last, target, elapsed, segment, is_stopped, on_time_bin)
          Tier B: (route, last, target, elapsed, segment, is_stopped)
          Tier C: (route, last, target, elapsed, segment)
          Tier D: (route, last, target, elapsed)
          Tier E: (route, last, target, segment)
          Tier F: (route, last, target)
  BASE-03: SegSum-only (no S2S blend — SegSum dominates at every stops_away)
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

MIN_OBS = 2
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


def derive_last_stop_progress(df: pd.DataFrame, ss: pd.DataFrame) -> pd.DataFrame:
    """Join last_stop_id against stop_sequences to get last_stop_progress.

    last_stop_id is the next stop the bus is approaching.  When last_stop_id=0
    (no stop assigned), last_stop_progress is set to NaN.
    """
    lookup = ss[["route_id", "stop_id", "stop_progress"]].rename(
        columns={"stop_id": "last_stop_id", "stop_progress": "last_stop_progress"}
    )
    n_before = len(df)
    df = df.merge(lookup, on=["route_id", "last_stop_id"], how="left")
    assert len(df) == n_before, (
        f"Row explosion on last_stop_progress merge: {n_before} -> {len(df)}"
    )
    # last_stop_id == 0 won't match anything → already NaN
    return df


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
# BASE-02: 4D Destination-Specific Baseline
#
# Four binning dimensions:
#   - elapsed_decile: quantile bins of seconds since last stop event
#   - segment_decile: normalised remaining progress within last_stop→target span
#   - is_stopped: binary (speed == 0) — +22s systematic bias when stopped
#   - on_time_bin: 4-bin schedule deviation (<0, 0-1, 2-5, 6+)
#
# No day_type (99% weekday — halves cell counts for no benefit).
# MIN_OBS=2 for maximum specificity.
#
# Tiered fallback (6 tiers + S2S final):
#   Tier A: (route, last, target, elapsed, segment, is_stopped, on_time_bin)
#   Tier B: (route, last, target, elapsed, segment, is_stopped)
#   Tier C: (route, last, target, elapsed, segment)
#   Tier D: (route, last, target, elapsed)
#   Tier E: (route, last, target, segment)
#   Tier F: (route, last, target)
#   Final:  Fill remaining NaN from baseline_s2s
# ---------------------------------------------------------------------------


def _add_segment_decile(df: pd.DataFrame) -> pd.DataFrame:
    """Add segment_decile column using last_stop_progress for fine-grained binning.

    Normalises remaining progress by the last_stop-to-target_stop span so that
    even 1-stop-away observations get full 0-9 decile resolution.

    Fallback: rows with NaN last_stop_progress use the old route-level formula.
    """
    remaining = df["target_stop_progress"].values - df["progress"].values
    span = df["target_stop_progress"].values - df["last_stop_progress"].values

    # Handle circular route wrap-around
    remaining = np.where(remaining < 0, remaining + 1.0, remaining)
    span = np.where(span <= 0, span + 1.0, span)

    # Normalize: 0 = at target, 1 = at last_stop, >1 = before last_stop
    normalized = remaining / span

    # Bin: full 0-9 resolution for buses between last_stop and target
    # Buses before last_stop (normalized > 1) clip to decile 9
    decile = np.floor(normalized * 10).clip(0, 9)

    # Fallback for NaN last_stop_progress: use old prog_decile
    nan_mask = df["last_stop_progress"].isna().values
    if nan_mask.any():
        fallback_remaining = (
            df["target_stop_progress"].values[nan_mask]
            - df["progress"].values[nan_mask]
        )
        fallback = np.floor(fallback_remaining * 10).clip(0, 9)
        decile[nan_mask] = fallback

    df["segment_decile"] = decile.astype(int)
    return df


def _add_is_stopped(df: pd.DataFrame) -> pd.DataFrame:
    """Add is_stopped column: 1 if speed == 0, else 0."""
    df["is_stopped"] = (df["speed"] == 0).astype(int)
    return df


def _add_on_time_bin(df: pd.DataFrame) -> pd.DataFrame:
    """Add on_time_bin column: 4-bin encoding of last_stop_on_time.

    Bins: <0 -> 0, 0-1 -> 1, 2-5 -> 2, 6+ -> 3.
    NaN last_stop_on_time -> -1 (sentinel).
    """
    ot = df["last_stop_on_time"].values.copy().astype(float)
    nan_mask = np.isnan(ot)
    result = np.where(ot < 0, 0, np.where(ot <= 1, 1, np.where(ot <= 5, 2, 3)))
    result[nan_mask] = -1
    df["on_time_bin"] = result.astype(int)
    return df


def _compute_elapsed_bins(train: pd.DataFrame, n_bins: int = 10) -> np.ndarray:
    """Compute elapsed-time quantile bin edges from training data.

    Returns bin_edges array of length n_bins+1 for use with np.digitize.
    """
    secs = (train["timestamp_ms"] - train["last_stop_time_ms"]) / 1000
    valid = secs[secs.notna() & (secs >= 0)]
    _, bin_edges = pd.qcut(valid, n_bins, retbins=True, duplicates="drop")
    # Extend edges to cover all possible values
    bin_edges[0] = 0.0
    bin_edges[-1] = np.inf
    return bin_edges


def _add_elapsed_decile(df: pd.DataFrame, bin_edges: np.ndarray) -> pd.DataFrame:
    """Add elapsed_decile column using pre-computed quantile bin edges.

    elapsed_decile = quantile bin (0 to n_bins-1) of seconds since last stop.
    Rows with missing last_stop_time_ms get elapsed_decile = -1 (sentinel).
    """
    secs = (df["timestamp_ms"] - df["last_stop_time_ms"]) / 1000
    # np.digitize returns 1..n_bins; subtract 1 for 0-indexed, clip to valid range
    n_bins = len(bin_edges) - 1
    decile = np.digitize(secs, bin_edges, right=True).clip(1, n_bins) - 1
    # Mark NaN / negative as -1 sentinel
    invalid = secs.isna() | (secs < 0)
    decile[invalid] = -1
    df["elapsed_decile"] = decile.astype(int)
    return df


def build_seg_sum_lookups(train: pd.DataFrame, elapsed_bin_edges: np.ndarray) -> tuple:
    """Build tiered elapsed+segment destination-specific lookups from training data.

    4D tier hierarchy (no day_type — 99% weekday makes it useless):
      Tier A: (route, last, target, elapsed, segment, is_stopped, on_time_bin)
      Tier B: (route, last, target, elapsed, segment, is_stopped)
      Tier C: (route, last, target, elapsed, segment)
      Tier D: (route, last, target, elapsed)
      Tier E: (route, last, target, segment)
      Tier F: (route, last, target)

    Returns (tier_a, tier_b, tier_c, tier_d, tier_e, tier_f) DataFrames.
    """
    train = _add_segment_decile(train)
    train = _add_elapsed_decile(train, elapsed_bin_edges)
    train = _add_is_stopped(train)
    train = _add_on_time_bin(train)

    # Only use rows with valid elapsed_decile for tiers A-D
    valid_elapsed = train["elapsed_decile"] >= 0

    # Tier A: most specific — all 4 dimensions
    agg_a = train[valid_elapsed].groupby(
        ["route_id", "last_stop_id", "target_stop_id",
         "elapsed_decile", "segment_decile", "is_stopped", "on_time_bin"]
    ).agg(
        baseline_seg_sum=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_a = agg_a[agg_a["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier A (route, last, target, elapsed, segment, stopped, ot): {len(tier_a):,} combos")

    # Tier B: drop on_time_bin
    agg_b = train[valid_elapsed].groupby(
        ["route_id", "last_stop_id", "target_stop_id",
         "elapsed_decile", "segment_decile", "is_stopped"]
    ).agg(
        _seg_b=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_b = agg_b[agg_b["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier B (route, last, target, elapsed, segment, stopped):     {len(tier_b):,} combos")

    # Tier C: drop is_stopped
    agg_c = train[valid_elapsed].groupby(
        ["route_id", "last_stop_id", "target_stop_id",
         "elapsed_decile", "segment_decile"]
    ).agg(
        _seg_c=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_c = agg_c[agg_c["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier C (route, last, target, elapsed, segment):              {len(tier_c):,} combos")

    # Tier D: elapsed only
    agg_d = train[valid_elapsed].groupby(
        ["route_id", "last_stop_id", "target_stop_id", "elapsed_decile"]
    ).agg(
        _seg_d=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_d = agg_d[agg_d["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier D (route, last, target, elapsed):                       {len(tier_d):,} combos")

    # Tier E: segment only (fallback for missing elapsed)
    agg_e = train.groupby(
        ["route_id", "last_stop_id", "target_stop_id", "segment_decile"]
    ).agg(
        _seg_e=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_e = agg_e[agg_e["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier E (route, last, target, segment):                       {len(tier_e):,} combos")

    # Tier F: broadest — just route + stops
    agg_f = train.groupby(
        ["route_id", "last_stop_id", "target_stop_id"]
    ).agg(
        _seg_f=("time_to_arrival_seconds", "median"),
        _count=("time_to_arrival_seconds", "count"),
    ).reset_index()
    tier_f = agg_f[agg_f["_count"] >= MIN_OBS].drop(columns=["_count"])
    print(f"  Tier F (route, last, target):                                {len(tier_f):,} combos")

    return tier_a, tier_b, tier_c, tier_d, tier_e, tier_f


def apply_seg_sum_fallback(df: pd.DataFrame, tier_a: pd.DataFrame,
                           tier_b: pd.DataFrame, tier_c: pd.DataFrame,
                           tier_d: pd.DataFrame, tier_e: pd.DataFrame,
                           tier_f: pd.DataFrame,
                           elapsed_bin_edges: np.ndarray,
                           split_name: str) -> pd.DataFrame:
    """Apply 6-tier 4D fallback to produce baseline_seg_sum column."""
    n_before = len(df)

    # Add all required columns
    df = _add_segment_decile(df)
    df = _add_elapsed_decile(df, elapsed_bin_edges)
    df = _add_is_stopped(df)
    df = _add_on_time_bin(df)

    # --- Tier A: (route, last, target, elapsed, segment, is_stopped, on_time_bin) ---
    df = df.merge(
        tier_a,
        on=["route_id", "last_stop_id", "target_stop_id",
            "elapsed_decile", "segment_decile", "is_stopped", "on_time_bin"],
        how="left",
    )
    assert len(df) == n_before, f"Seg Tier A merge explosion: {n_before} -> {len(df)}"
    ta_filled = df["baseline_seg_sum"].notna().sum()

    # --- Tier B: drop on_time_bin ---
    mask_b = df["baseline_seg_sum"].isna()
    if mask_b.any():
        b_merge = df.loc[mask_b, ["route_id", "last_stop_id", "target_stop_id",
                                   "elapsed_decile", "segment_decile", "is_stopped"]].merge(
            tier_b, on=["route_id", "last_stop_id", "target_stop_id",
                        "elapsed_decile", "segment_decile", "is_stopped"], how="left"
        )
        df.loc[mask_b, "baseline_seg_sum"] = b_merge["_seg_b"].values
    tb_filled = df["baseline_seg_sum"].notna().sum() - ta_filled

    # --- Tier C: drop is_stopped ---
    mask_c = df["baseline_seg_sum"].isna()
    if mask_c.any():
        c_merge = df.loc[mask_c, ["route_id", "last_stop_id", "target_stop_id",
                                   "elapsed_decile", "segment_decile"]].merge(
            tier_c, on=["route_id", "last_stop_id", "target_stop_id",
                        "elapsed_decile", "segment_decile"], how="left"
        )
        df.loc[mask_c, "baseline_seg_sum"] = c_merge["_seg_c"].values
    tc_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled

    # --- Tier D: elapsed only ---
    mask_d = df["baseline_seg_sum"].isna()
    if mask_d.any():
        d_merge = df.loc[mask_d, ["route_id", "last_stop_id", "target_stop_id",
                                   "elapsed_decile"]].merge(
            tier_d, on=["route_id", "last_stop_id", "target_stop_id",
                        "elapsed_decile"], how="left"
        )
        df.loc[mask_d, "baseline_seg_sum"] = d_merge["_seg_d"].values
    td_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled - tc_filled

    # --- Tier E: segment only ---
    mask_e = df["baseline_seg_sum"].isna()
    if mask_e.any():
        e_merge = df.loc[mask_e, ["route_id", "last_stop_id", "target_stop_id",
                                   "segment_decile"]].merge(
            tier_e, on=["route_id", "last_stop_id", "target_stop_id",
                        "segment_decile"], how="left"
        )
        df.loc[mask_e, "baseline_seg_sum"] = e_merge["_seg_e"].values
    te_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled - tc_filled - td_filled

    # --- Tier F: broadest (route + stops only) ---
    mask_f = df["baseline_seg_sum"].isna()
    if mask_f.any():
        f_merge = df.loc[mask_f, ["route_id", "last_stop_id", "target_stop_id"]].merge(
            tier_f, on=["route_id", "last_stop_id", "target_stop_id"], how="left"
        )
        df.loc[mask_f, "baseline_seg_sum"] = f_merge["_seg_f"].values
    tf_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled - tc_filled - td_filled - te_filled

    # --- Final fallback: fill from baseline_s2s ---
    mask_final = df["baseline_seg_sum"].isna()
    if mask_final.any() and "baseline_s2s" in df.columns:
        df.loc[mask_final, "baseline_seg_sum"] = df.loc[mask_final, "baseline_s2s"]
    ts2s_filled = df["baseline_seg_sum"].notna().sum() - ta_filled - tb_filled - tc_filled - td_filled - te_filled - tf_filled

    still_nan = df["baseline_seg_sum"].isna().sum()
    total = len(df)

    print(f"  {split_name} segment-sum tier coverage:")
    print(f"    Tier A: {ta_filled:,} ({ta_filled/total*100:.1f}%)")
    print(f"    Tier B: {tb_filled:,} ({tb_filled/total*100:.1f}%)")
    print(f"    Tier C: {tc_filled:,} ({tc_filled/total*100:.1f}%)")
    print(f"    Tier D: {td_filled:,} ({td_filled/total*100:.1f}%)")
    print(f"    Tier E: {te_filled:,} ({te_filled/total*100:.1f}%)")
    print(f"    Tier F: {tf_filled:,} ({tf_filled/total*100:.1f}%)")
    print(f"    S2S fallback: {ts2s_filled:,} ({ts2s_filled/total*100:.2f}%)")
    print(f"    Still NaN: {still_nan:,} ({still_nan/total*100:.2f}%)")

    # Drop temp columns
    df.drop(columns=["segment_decile", "elapsed_decile", "is_stopped", "on_time_bin"],
            inplace=True)

    return df


# ---------------------------------------------------------------------------
# BASE-03: Blend Baselines
# ---------------------------------------------------------------------------


def blend_baselines(df: pd.DataFrame) -> pd.DataFrame:
    """Set baseline_eta to SegSum only (no S2S blend).

    Blending with S2S always hurts — SegSum dominates at every stops_away value.
    baseline_s2s is kept as a separate column for the model to use as a feature.
    """
    df["baseline_eta"] = df["baseline_seg_sum"].copy()
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
                        ("SegSum-4D", "baseline_seg_sum"),
                        ("baseline_eta (=SegSum)", "baseline_eta")]:
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

    # Drop old baseline columns from previous runs (if present)
    old_cols = ["baseline_s2s", "baseline_seg_sum", "baseline_eta",
                "residual", "last_stop_progress"]
    existing_old = [c for c in old_cols if c in train.columns]
    if existing_old:
        train.drop(columns=existing_old, inplace=True)
        print(f"  Dropped old columns: {existing_old}")

    # Add derived columns
    train = add_ct_hour(train)
    train["day_type"] = train["is_weekday"].astype(int)
    train = derive_last_stop_progress(train, ss)
    lsp_nan = train["last_stop_progress"].isna().sum()
    print(f"  last_stop_progress NaN: {lsp_nan:,} ({lsp_nan/len(train)*100:.1f}%)")

    # --- BASE-01: S2S Lookup Tables ---
    print("\n--- BASE-01: Building S2S Lookup Tables ---")
    tier1 = build_tier1_lookup(train)
    print(f"  Tier 1 combos (>={MIN_OBS} obs): {len(tier1):,}")
    tier2 = build_tier2_lookup(train)
    print(f"  Tier 2 combos (>={MIN_OBS} obs): {len(tier2):,}")
    tier3 = build_tier3_lookup(train, ss)
    print(f"  Tier 3 combos (>={MIN_OBS} obs): {len(tier3):,}")

    # --- Elapsed-time decile bins ---
    print("\n--- Computing elapsed-time decile bins ---")
    elapsed_bin_edges = _compute_elapsed_bins(train)
    print(f"  Bin edges: {np.round(elapsed_bin_edges, 1)}")

    # --- BASE-02: 4D Destination-Specific Lookup Tables ---
    print("\n--- BASE-02: Building 4D Lookups ---")
    seg_a, seg_b, seg_c, seg_d, seg_e, seg_f = build_seg_sum_lookups(train, elapsed_bin_edges)

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

        # Drop old baseline columns from previous runs (if present)
        old_cols = ["baseline_s2s", "baseline_seg_sum", "baseline_eta",
                    "residual", "last_stop_progress"]
        existing_old = [c for c in old_cols if c in df.columns]
        if existing_old:
            df.drop(columns=existing_old, inplace=True)
            print(f"  Dropped old columns: {existing_old}")

        # Add derived columns
        df = add_ct_hour(df)
        df["day_type"] = df["is_weekday"].astype(int)
        df = derive_last_stop_progress(df, ss)

        # Apply S2S fallback
        print("\n  Applying S2S fallback hierarchy...")
        df = apply_s2s_fallback(df, tier1, tier2, tier3, ss, split_name)
        assert len(df) == n_original, (
            f"Row count changed after S2S: {n_original} -> {len(df)}"
        )

        # Apply segment-sum fallback (4D, 6-tier)
        print("\n  Applying 4D fallback hierarchy...")
        df = apply_seg_sum_fallback(df, seg_a, seg_b, seg_c, seg_d, seg_e, seg_f, elapsed_bin_edges, split_name)
        assert len(df) == n_original, (
            f"Row count changed after seg-sum: {n_original} -> {len(df)}"
        )

        # Blend (SegSum-only, no S2S blend)
        print("\n  Setting baseline_eta = SegSum...")
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

        # Also store intermediate baselines and last_stop_progress
        original["baseline_s2s"] = df["baseline_s2s"].values
        original["baseline_seg_sum"] = df["baseline_seg_sum"].values
        original["last_stop_progress"] = df["last_stop_progress"].values

        assert len(original) == n_original, (
            f"Row count changed during write: {n_original} -> {len(original)}"
        )

        original.to_parquet(path)
        print(
            f"  Wrote {path} ({n_original:,} rows, "
            f"new cols: baseline_eta, residual, baseline_s2s, baseline_seg_sum, last_stop_progress)"
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
