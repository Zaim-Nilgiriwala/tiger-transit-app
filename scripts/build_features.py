"""
build_features.py - Feature engineering pipeline for Tiger Transit ETA model.

Computes 15 feature columns (FEAT-01 through FEAT-08) from the Phase 2
train/val/test splits, producing feature-enriched parquet files ready for
XGBoost DMatrix creation.

Usage:
    python scripts/build_features.py

Input:
    data/processed/train.parquet, val.parquet, test.parquet
    data/processed/stop_sequences.parquet
    data/processed/weather.parquet

Output:
    data/processed/train_featured.parquet
    data/processed/val_featured.parquet
    data/processed/test_featured.parquet
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/processed")

FEATURE_COLS = [
    "distance_to_target",
    "scheduled_time_to_target",
    "current_speed",
    "route_progress",
    "stops_remaining",
    "stop_index",
    "lateness_now",
    "minutes_since_midnight",
    "day_of_week",
    "route_id",
    "pattern_id",
    "precipitation_mm",
    "temperature_c",
    "passenger_load",
    "is_idle",
]

CATEGORICAL_COLS = ["day_of_week", "route_id", "pattern_id"]

TARGET_COL = "time_to_arrival_seconds"

# Extra columns kept for sliced evaluation later
KEEP_EXTRA = ["stops_away", "route_id"]

SPLITS = ["train", "val", "test"]


# ---------------------------------------------------------------------------
# Public API for downstream consumers
# ---------------------------------------------------------------------------


def load_featured(split: str) -> pd.DataFrame:
    """Load a featured parquet split with correct dtypes.

    Ensures categorical columns are cast to pandas category dtype,
    which may not survive parquet round-trip on all pandas versions.

    Args:
        split: One of "train", "val", "test"

    Returns:
        DataFrame with all features, target, and evaluation columns.
    """
    path = DATA_DIR / f"{split}_featured.parquet"
    df = pd.read_parquet(path)
    for col in CATEGORICAL_COLS:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


# ---------------------------------------------------------------------------
# Supplementary data loaders
# ---------------------------------------------------------------------------


def load_max_shape_dist() -> pd.Series:
    """Load max_shape_dist per route_id from stop_sequences."""
    ss = pd.read_parquet(DATA_DIR / "stop_sequences.parquet")
    # One max_shape_dist per route -- take first (they're identical within route)
    max_sd = ss.groupby("route_id")["max_shape_dist"].first()
    return max_sd


def load_weather() -> pd.DataFrame:
    """Load hourly weather data for merge."""
    w = pd.read_parquet(DATA_DIR / "weather.parquet")
    # Weather already has hour, precipitation_mm, temperature_c
    # Keep only what we need for the merge
    w = w[["hour", "precipitation_mm", "temperature_c"]].copy()
    # Ensure hour is tz-aware UTC
    if w["hour"].dt.tz is None:
        w["hour"] = w["hour"].dt.tz_localize("UTC")
    return w


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------


def compute_features(df: pd.DataFrame, max_shape_dist: pd.Series,
                     weather: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """Compute all 15 features on a single split DataFrame.

    Modifies df in-place for memory efficiency and returns it.
    """
    n_before = len(df)
    print(f"\n{'='*60}")
    print(f"Processing {split_name} split ({n_before:,} rows)")
    print(f"{'='*60}")

    # --- FEAT-01: distance_to_target ---
    # Map route_id -> max_shape_dist
    route_max_sd = df["route_id"].map(max_shape_dist)
    df["distance_to_target"] = (
        (df["target_stop_progress"] - df["progress"]) * route_max_sd
    ).clip(lower=0)

    # --- FEAT-02: scheduled_time_to_target ---
    # Use scheduled_eta_seconds directly as proxy for scheduled time remaining
    df["scheduled_time_to_target"] = df["scheduled_eta_seconds"].clip(lower=0)

    # --- FEAT-03: current_speed, route_progress, stops_remaining, stop_index ---
    df["current_speed"] = df["speed"]
    df["route_progress"] = df["progress"]
    df["stops_remaining"] = df["stops_away"]
    df["stop_index"] = df["target_stop_sequence"]

    # --- FEAT-04: lateness_now ---
    # Positive = running late (scheduled says more time than actual ETA)
    df["lateness_now"] = df["scheduled_eta_seconds"] - df["eta_seconds"]

    stats = df["lateness_now"].describe()
    print(f"\nFEAT-04 lateness_now distribution:")
    print(f"  mean={stats['mean']:.1f}, median={stats['50%']:.1f}, "
          f"std={stats['std']:.1f}, min={stats['min']:.1f}, max={stats['max']:.1f}")

    # --- FEAT-05: minutes_since_midnight, day_of_week ---
    ts = df["timestamp"]
    df["minutes_since_midnight"] = ts.dt.hour * 60 + ts.dt.minute
    df["day_of_week"] = ts.dt.dayofweek.astype("category")

    # --- FEAT-06: pattern_id, route_id as categorical ---
    df["pattern_id"] = df["pattern_id"].astype("category")
    df["route_id"] = df["route_id"].astype("category")

    # --- FEAT-07: precipitation_mm, temperature_c ---
    # Floor timestamp to nearest hour for merge
    df["_merge_hour"] = ts.dt.floor("h")
    df = df.merge(
        weather, left_on="_merge_hour", right_on="hour", how="left",
        suffixes=("", "_weather"),
    )
    df.drop(columns=["_merge_hour", "hour"], inplace=True, errors="ignore")

    # Fill NaN weather: 0 for precipitation, median for temperature
    precip_na = df["precipitation_mm"].isna().sum()
    temp_na = df["temperature_c"].isna().sum()
    if precip_na > 0:
        print(f"  Filling {precip_na:,} NaN precipitation_mm with 0")
        df["precipitation_mm"] = df["precipitation_mm"].fillna(0)
    if temp_na > 0:
        temp_median = df["temperature_c"].median()
        print(f"  Filling {temp_na:,} NaN temperature_c with median ({temp_median:.1f})")
        df["temperature_c"] = df["temperature_c"].fillna(temp_median)

    # --- FEAT-08: passenger_load, is_idle ---
    df["passenger_load"] = df["load"]
    df["is_idle"] = (df["speed"] <= 2).astype(int)

    # --- Verify row count unchanged ---
    assert len(df) == n_before, (
        f"Row count changed during feature engineering! "
        f"Before={n_before:,}, After={len(df):,}. "
        f"Weather merge may have introduced duplicates."
    )

    return df


# ---------------------------------------------------------------------------
# Output and summary
# ---------------------------------------------------------------------------


def select_and_save(df: pd.DataFrame, split_name: str) -> None:
    """Select output columns and save to parquet.

    Uses pyarrow dictionary encoding for categorical columns so that
    pd.read_parquet will restore them as pandas category dtype.
    """
    import pyarrow as pa
    import pyarrow.parquet as pq

    # Build output column set: features + target + extras for evaluation
    out_cols = list(FEATURE_COLS) + [TARGET_COL]
    # Add extras that aren't already in FEATURE_COLS
    for c in KEEP_EXTRA:
        if c not in out_cols:
            out_cols.append(c)

    out = df[out_cols].copy()

    # Ensure categorical columns are category dtype before arrow conversion
    for col in CATEGORICAL_COLS:
        if col in out.columns:
            out[col] = out[col].astype("category")

    # Convert to arrow table, then force dictionary encoding on categoricals
    table = pa.Table.from_pandas(out, preserve_index=False)
    for col in CATEGORICAL_COLS:
        idx = table.schema.get_field_index(col)
        if idx >= 0:
            arr = table.column(col)
            if not pa.types.is_dictionary(arr.type):
                arr = arr.dictionary_encode()
            table = table.set_column(idx, col, arr)

    path = DATA_DIR / f"{split_name}_featured.parquet"
    pq.write_table(table, path)
    print(f"\nSaved {path} ({len(out):,} rows)")


def print_summary(df: pd.DataFrame, split_name: str) -> None:
    """Print feature summary statistics."""
    print(f"\n--- {split_name} Feature Summary ---")
    print(f"Rows: {len(df):,}")

    # NaN counts
    nan_counts = df[FEATURE_COLS].isna().sum()
    nan_nonzero = nan_counts[nan_counts > 0]
    if len(nan_nonzero) == 0:
        print("NaN counts: all zero")
    else:
        print("NaN counts:")
        for col, cnt in nan_nonzero.items():
            print(f"  {col}: {cnt:,}")

    # Numeric feature distributions
    numeric_feats = [c for c in FEATURE_COLS if c not in CATEGORICAL_COLS]
    desc = df[numeric_feats].describe().loc[["min", "50%", "max"]]
    desc.index = ["min", "median", "max"]
    print("\nNumeric features (min / median / max):")
    for col in numeric_feats:
        print(f"  {col:30s}: {desc.loc['min', col]:>10.2f} / "
              f"{desc.loc['median', col]:>10.2f} / {desc.loc['max', col]:>10.2f}")

    # Categorical unique counts
    print("\nCategorical features (unique values):")
    for col in CATEGORICAL_COLS:
        n_unique = df[col].nunique()
        print(f"  {col:30s}: {n_unique}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("Loading supplementary data...")
    max_shape_dist = load_max_shape_dist()
    print(f"  max_shape_dist: {len(max_shape_dist)} routes")

    weather = load_weather()
    print(f"  weather: {len(weather)} hourly records")

    # Check for duplicate hours in weather (would cause row explosion on merge)
    dup_hours = weather["hour"].duplicated().sum()
    if dup_hours > 0:
        print(f"  WARNING: {dup_hours} duplicate hours in weather, deduplicating...")
        weather = weather.drop_duplicates(subset=["hour"], keep="first")

    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}.parquet"
        print(f"\nLoading {path}...")
        df = pd.read_parquet(path)

        df = compute_features(df, max_shape_dist, weather, split_name)
        print_summary(df, split_name)
        select_and_save(df, split_name)

    print(f"\n{'='*60}")
    print("Feature engineering complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
