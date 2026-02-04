"""
build_differentiator_features.py - Differentiator feature engineering for Tiger Transit.

Computes GPS-derived rolling speed features and historical aggregate features
that go beyond the baseline feature set (build_features.py).

Features computed:
  Rolling speed: gps_speed_mps, speed_mean_{30,60,120,180}s, speed_std_{30,60,120,180}s
  Dynamics:      acceleration, is_idle_gps, seconds_idle
  Historical:    segment travel time medians, dwell time medians (saved as parquets)

Usage:
    python scripts/build_differentiator_features.py

Input:
    data/processed/train.parquet

Output:
    data/processed/historical_segments.parquet
    data/processed/historical_dwells.parquet
    (Rolling features are computed in-memory for merge-back; not saved standalone)
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DATA_DIR = Path("data/processed")

# Speed thresholds
GPS_SPEED_CAP_MPS = 29.06        # 65 mph in m/s
IDLE_SPEED_THRESHOLD = 0.894     # 2 mph in m/s
MIN_DELTA_SECONDS = 5            # Jitter filter
GAP_THRESHOLD_SECONDS = 300      # 5-minute gap resets

ROLLING_WINDOWS = [30, 60, 120, 180]  # seconds

MIN_OBS = 10  # Minimum observations for valid historical aggregate


# ---------------------------------------------------------------------------
# Haversine distance (vectorized)
# ---------------------------------------------------------------------------


def haversine_meters(lat1, lon1, lat2, lon2):
    """Vectorized haversine distance in meters between two coordinate arrays."""
    R = 6_371_000  # Earth radius in meters
    lat1_r, lat2_r = np.radians(lat1), np.radians(lat2)
    dlat = np.radians(lat2 - lat1)
    dlon = np.radians(lon2 - lon1)

    a = np.sin(dlat / 2) ** 2 + np.cos(lat1_r) * np.cos(lat2_r) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c


# ---------------------------------------------------------------------------
# Unique ping extraction
# ---------------------------------------------------------------------------


def extract_unique_pings(df: pd.DataFrame) -> pd.DataFrame:
    """Extract unique pings from exploded data.

    The exploded DataFrame has ~4.4x duplication (each ping appears once per
    target stop). Rolling features must be computed on unique pings only.
    """
    pings = df.drop_duplicates(subset=["vehicle_id", "timestamp"]).copy()
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).reset_index(drop=True)
    return pings


# ---------------------------------------------------------------------------
# GPS speed computation
# ---------------------------------------------------------------------------


def compute_gps_speed(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute GPS-derived speed from haversine distance / time delta.

    Groups by (vehicle_id, route_id), computes distance between consecutive
    pings, divides by time delta. Filters jitter (delta < 5s), caps at 65 mph,
    and sets NaN for gaps > 5 minutes.
    """
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).copy()

    # Shift within groups
    grp = pings.groupby(["vehicle_id", "route_id"], observed=True)
    pings["prev_lat"] = grp["lat"].shift(1)
    pings["prev_lon"] = grp["lon"].shift(1)
    pings["prev_ts"] = grp["timestamp"].shift(1)

    # Time delta in seconds
    pings["delta_s"] = (pings["timestamp"] - pings["prev_ts"]).dt.total_seconds()

    # Haversine distance
    dist = haversine_meters(
        pings["prev_lat"].values, pings["prev_lon"].values,
        pings["lat"].values, pings["lon"].values,
    )

    # Speed = distance / time
    pings["gps_speed_mps"] = dist / pings["delta_s"]

    # Filter: NaN where delta < MIN_DELTA_SECONDS (GPS jitter)
    pings.loc[pings["delta_s"] < MIN_DELTA_SECONDS, "gps_speed_mps"] = np.nan

    # Filter: NaN for first ping in group (prev is NaN)
    pings.loc[pings["prev_ts"].isna(), "gps_speed_mps"] = np.nan

    # Filter: NaN for gap > 5 minutes
    pings.loc[pings["delta_s"] > GAP_THRESHOLD_SECONDS, "gps_speed_mps"] = np.nan

    # Cap at 65 mph
    pings["gps_speed_mps"] = pings["gps_speed_mps"].clip(upper=GPS_SPEED_CAP_MPS)

    # Clean up temp columns
    pings.drop(columns=["prev_lat", "prev_lon", "prev_ts"], inplace=True)

    return pings


# ---------------------------------------------------------------------------
# Rolling speed features
# ---------------------------------------------------------------------------


def compute_rolling_speed_features(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute rolling mean and std of gps_speed_mps over multiple windows.

    Uses time-based rolling windows (30s, 60s, 120s, 180s) with min_periods=1.
    Groups by (vehicle_id, route_id) to prevent cross-trip contamination.
    """
    pings = pings.set_index("timestamp")

    rolling_results = {}
    for window in ROLLING_WINDOWS:
        win_str = f"{window}s"
        grp = pings.groupby(["vehicle_id", "route_id"], observed=True)["gps_speed_mps"]
        rolling_results[f"speed_mean_{window}s"] = grp.transform(
            lambda x: x.rolling(win_str, min_periods=1).mean()
        )
        rolling_results[f"speed_std_{window}s"] = grp.transform(
            lambda x: x.rolling(win_str, min_periods=1).std()
        )

    for col, values in rolling_results.items():
        pings[col] = values

    pings = pings.reset_index()
    return pings


# ---------------------------------------------------------------------------
# Acceleration
# ---------------------------------------------------------------------------


def compute_acceleration(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute acceleration as change in GPS speed over time delta."""
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).copy()

    grp = pings.groupby(["vehicle_id", "route_id"], observed=True)
    prev_speed = grp["gps_speed_mps"].shift(1)
    prev_ts = grp["timestamp"].shift(1)
    delta_s = (pings["timestamp"] - prev_ts).dt.total_seconds()

    pings["acceleration"] = (pings["gps_speed_mps"] - prev_speed) / delta_s

    # NaN for jitter and gaps
    pings.loc[delta_s < MIN_DELTA_SECONDS, "acceleration"] = np.nan
    pings.loc[prev_ts.isna(), "acceleration"] = np.nan
    pings.loc[delta_s > GAP_THRESHOLD_SECONDS, "acceleration"] = np.nan

    return pings


# ---------------------------------------------------------------------------
# Idle detection
# ---------------------------------------------------------------------------


def compute_idle_features(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute idle flag and cumulative idle duration.

    is_idle_gps: 1 if gps_speed_mps < 0.894 m/s (2 mph), 0 otherwise
    seconds_idle: cumulative seconds in current idle streak per vehicle-route
    """
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).copy()

    # Idle flag (treat NaN speed as not idle for safety)
    pings["is_idle_gps"] = (pings["gps_speed_mps"] < IDLE_SPEED_THRESHOLD).astype(int)
    pings.loc[pings["gps_speed_mps"].isna(), "is_idle_gps"] = 0

    # Detect idle streak boundaries within each vehicle-route group
    grp_cols = ["vehicle_id", "route_id"]
    grp = pings.groupby(grp_cols, observed=True)

    # Detect gap resets: if delta > GAP_THRESHOLD, break streak
    prev_ts = grp["timestamp"].shift(1)
    delta_s = (pings["timestamp"] - prev_ts).dt.total_seconds()
    gap_break = (delta_s > GAP_THRESHOLD_SECONDS) | prev_ts.isna()

    # Streak ID: increments when idle status changes OR gap occurs
    streak_change = (pings["is_idle_gps"] != grp["is_idle_gps"].shift(1)) | gap_break
    pings["_streak_id"] = streak_change.cumsum()

    # Cumulative idle seconds within each idle streak
    pings["seconds_idle"] = 0.0
    idle_mask = pings["is_idle_gps"] == 1

    if idle_mask.any():
        idle_groups = pings.loc[idle_mask].groupby("_streak_id")
        pings.loc[idle_mask, "seconds_idle"] = idle_groups["timestamp"].transform(
            lambda x: (x - x.iloc[0]).dt.total_seconds()
        )

    pings.drop(columns=["_streak_id"], inplace=True)
    return pings


# ---------------------------------------------------------------------------
# Central Time hour extraction
# ---------------------------------------------------------------------------


def add_ct_hour(df: pd.DataFrame) -> pd.DataFrame:
    """Add hour_ct column: UTC timestamp shifted to US Central (UTC-6)."""
    df["hour_ct"] = (df["timestamp"] - pd.Timedelta(hours=6)).dt.hour
    return df


# ---------------------------------------------------------------------------
# Historical segment travel time aggregates
# ---------------------------------------------------------------------------


def compute_historical_segments(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute median segment travel times from training data.

    Segment = (route_id, last_stop_id). Travel time = time between
    consecutive stop transitions within a vehicle-route trajectory.

    Groups by (route_id, last_stop_id, hour_ct, day_type) and computes
    median, p25, p75. Sets to NaN where count < MIN_OBS.
    """
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).copy()
    pings = add_ct_hour(pings)

    # Detect stop transitions: when last_stop_id changes within vehicle-route
    grp = pings.groupby(["vehicle_id", "route_id"], observed=True)
    prev_stop = grp["last_stop_id"].shift(1)
    stop_changed = (pings["last_stop_id"] != prev_stop) & prev_stop.notna()

    # Mark transition timestamps
    pings["_stop_changed"] = stop_changed

    # Get timestamps of transitions
    transitions = pings[stop_changed].copy()
    transitions["_prev_ts"] = grp["timestamp"].shift(1).loc[stop_changed]

    # Also need the previous transition time -- use the time of the last ping
    # before the stop changed
    # Better approach: for each vehicle-route, compute time at each stop transition
    # Segment travel time = time between consecutive transitions

    # Group transitions by vehicle-route and compute consecutive differences
    if len(transitions) == 0:
        print("  WARNING: No stop transitions found")
        return pd.DataFrame()

    transitions = transitions.sort_values(["vehicle_id", "route_id", "timestamp"])
    trans_grp = transitions.groupby(["vehicle_id", "route_id"], observed=True)
    transitions["prev_transition_ts"] = trans_grp["timestamp"].shift(1)
    transitions["segment_travel_s"] = (
        transitions["timestamp"] - transitions["prev_transition_ts"]
    ).dt.total_seconds()

    # Filter out first transition per group and gap-spanning transitions
    transitions = transitions[transitions["prev_transition_ts"].notna()].copy()
    transitions = transitions[transitions["segment_travel_s"] <= GAP_THRESHOLD_SECONDS].copy()
    transitions = transitions[transitions["segment_travel_s"] > 0].copy()

    # day_type from is_weekday
    transitions["day_type"] = transitions["is_weekday"].astype(int)

    # Aggregate
    agg_cols = ["route_id", "last_stop_id", "hour_ct", "day_type"]
    agg = transitions.groupby(agg_cols, observed=True)["segment_travel_s"].agg(
        segment_travel_median="median",
        segment_travel_p25=lambda x: x.quantile(0.25),
        segment_travel_p75=lambda x: x.quantile(0.75),
        count="count",
    ).reset_index()

    total_combos = len(agg)
    valid = agg["count"] >= MIN_OBS
    sparse = ~valid

    print(f"\n  Segment aggregates: {total_combos} total combos")
    print(f"    Valid (count >= {MIN_OBS}): {valid.sum()} ({valid.sum()/total_combos*100:.1f}%)")
    print(f"    Sparse (count < {MIN_OBS}): {sparse.sum()} ({sparse.sum()/total_combos*100:.1f}%)")

    # Set sparse combos to NaN
    for col in ["segment_travel_median", "segment_travel_p25", "segment_travel_p75"]:
        agg.loc[sparse, col] = np.nan

    # Print distribution of valid medians
    valid_medians = agg.loc[valid, "segment_travel_median"]
    if len(valid_medians) > 0:
        print(f"\n  Valid segment median distribution:")
        print(f"    min={valid_medians.min():.1f}s, p25={valid_medians.quantile(0.25):.1f}s, "
              f"median={valid_medians.median():.1f}s, p75={valid_medians.quantile(0.75):.1f}s, "
              f"max={valid_medians.max():.1f}s")

    return agg.drop(columns=["count"])


# ---------------------------------------------------------------------------
# Historical dwell time aggregates
# ---------------------------------------------------------------------------


def compute_historical_dwells(pings: pd.DataFrame) -> pd.DataFrame:
    """Compute median dwell times at stops from training data.

    Dwell = time bus spends at a stop after arriving (low speed pings after
    a stop transition). Duration from stop change to when speed exceeds
    idle threshold.

    Groups by (route_id, stop_id, hour_ct, day_type).
    """
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).copy()
    if "hour_ct" not in pings.columns:
        pings = add_ct_hour(pings)

    grp = pings.groupby(["vehicle_id", "route_id"], observed=True)
    prev_stop = grp["last_stop_id"].shift(1)
    stop_changed = (pings["last_stop_id"] != prev_stop) & prev_stop.notna()

    # For each stop transition, find how long the bus stays idle
    # Mark each ping with its "arrival event" -- the most recent stop transition
    pings["_stop_changed"] = stop_changed
    pings["_arrival_group"] = stop_changed.cumsum()

    # Arrival time = first timestamp of each arrival group
    arrival_times = pings.groupby("_arrival_group")["timestamp"].transform("first")
    pings["_since_arrival"] = (pings["timestamp"] - arrival_times).dt.total_seconds()

    # Mark non-idle pings within each arrival group
    is_moving = pings["gps_speed_mps"].fillna(0) >= IDLE_SPEED_THRESHOLD

    # For each arrival group that starts with a stop transition,
    # find the first moving ping to determine dwell end
    # Vectorized: get first row per arrival group (arrival info)
    arrival_info = pings[stop_changed][
        ["_arrival_group", "route_id", "last_stop_id", "hour_ct", "is_weekday", "timestamp"]
    ].copy()
    arrival_info = arrival_info.rename(columns={"timestamp": "arrival_ts"})

    # Get first moving ping per arrival group (departure time)
    moving_pings = pings[is_moving].groupby("_arrival_group")["timestamp"].first()
    moving_pings.name = "departure_ts"

    # Get last ping per arrival group (fallback if bus stays idle)
    last_pings = pings.groupby("_arrival_group")["timestamp"].last()
    last_pings.name = "last_ts"

    # Merge
    arrival_info = arrival_info.merge(moving_pings, left_on="_arrival_group",
                                       right_index=True, how="left")
    arrival_info = arrival_info.merge(last_pings, left_on="_arrival_group",
                                       right_index=True, how="left")

    # Dwell = departure - arrival (or last ping if no departure)
    departure = arrival_info["departure_ts"].fillna(arrival_info["last_ts"])
    arrival_info["dwell_s"] = (departure - arrival_info["arrival_ts"]).dt.total_seconds()

    # Filter valid dwells
    valid_dwell = (arrival_info["dwell_s"] > 0) & (arrival_info["dwell_s"] <= GAP_THRESHOLD_SECONDS)
    dwells = arrival_info.loc[valid_dwell, ["route_id", "last_stop_id", "hour_ct",
                                             "is_weekday", "dwell_s"]].copy()
    dwells = dwells.rename(columns={"last_stop_id": "stop_id"})
    dwells["day_type"] = dwells["is_weekday"].astype(int)
    dwells.drop(columns=["is_weekday"], inplace=True)

    pings.drop(columns=["_stop_changed", "_arrival_group", "_since_arrival"], inplace=True)

    if len(dwells) == 0:
        print("  WARNING: No dwell records found")
        return pd.DataFrame()

    # Aggregate
    agg_cols = ["route_id", "stop_id", "hour_ct", "day_type"]
    agg = dwells.groupby(agg_cols)["dwell_s"].agg(
        dwell_median="median",
        dwell_p25=lambda x: x.quantile(0.25),
        dwell_p75=lambda x: x.quantile(0.75),
        count="count",
    ).reset_index()

    total_combos = len(agg)
    valid = agg["count"] >= MIN_OBS
    sparse = ~valid

    print(f"\n  Dwell aggregates: {total_combos} total combos")
    print(f"    Valid (count >= {MIN_OBS}): {valid.sum()} ({valid.sum()/total_combos*100:.1f}%)")
    print(f"    Sparse (count < {MIN_OBS}): {sparse.sum()} ({sparse.sum()/total_combos*100:.1f}%)")

    # Set sparse combos to NaN
    for col in ["dwell_median", "dwell_p25", "dwell_p75"]:
        agg.loc[sparse, col] = np.nan

    # Print distribution
    valid_medians = agg.loc[valid, "dwell_median"]
    if len(valid_medians) > 0:
        print(f"\n  Valid dwell median distribution:")
        print(f"    min={valid_medians.min():.1f}s, p25={valid_medians.quantile(0.25):.1f}s, "
              f"median={valid_medians.median():.1f}s, p75={valid_medians.quantile(0.75):.1f}s, "
              f"max={valid_medians.max():.1f}s")

    return agg.drop(columns=["count"])


# ---------------------------------------------------------------------------
# Merge-back helper
# ---------------------------------------------------------------------------


def merge_rolling_to_exploded(exploded: pd.DataFrame, pings_featured: pd.DataFrame,
                               feature_cols: list[str]) -> pd.DataFrame:
    """Merge rolling features from unique pings back to exploded DataFrame.

    Joins on (vehicle_id, timestamp) since each unique ping maps to multiple
    rows in the exploded data (one per target stop).
    """
    merge_cols = ["vehicle_id", "timestamp"] + feature_cols
    return exploded.merge(
        pings_featured[merge_cols],
        on=["vehicle_id", "timestamp"],
        how="left",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


ROLLING_FEATURE_COLS = (
    ["gps_speed_mps"]
    + [f"speed_mean_{w}s" for w in ROLLING_WINDOWS]
    + [f"speed_std_{w}s" for w in ROLLING_WINDOWS]
    + ["acceleration", "is_idle_gps", "seconds_idle"]
)


def main():
    print("=" * 60)
    print("Differentiator Feature Engineering")
    print("=" * 60)

    # Load training data
    train_path = DATA_DIR / "train.parquet"
    print(f"\nLoading {train_path}...")
    train = pd.read_parquet(train_path)
    print(f"  Loaded {len(train):,} rows")

    # --- Step 1: Extract unique pings ---
    print("\n--- Extracting unique pings ---")
    pings = extract_unique_pings(train)
    print(f"  Unique pings: {len(pings):,} (from {len(train):,} exploded rows)")
    print(f"  Duplication ratio: {len(train)/len(pings):.2f}x")

    # --- Step 2: GPS speed ---
    print("\n--- Computing GPS speed ---")
    pings = compute_gps_speed(pings)
    speed = pings["gps_speed_mps"]
    print(f"  NaN rate: {speed.isna().mean()*100:.1f}%")
    valid_speed = speed.dropna()
    if len(valid_speed) > 0:
        print(f"  Distribution (valid only):")
        print(f"    min={valid_speed.min():.2f}, p25={valid_speed.quantile(0.25):.2f}, "
              f"median={valid_speed.median():.2f}, p75={valid_speed.quantile(0.75):.2f}, "
              f"max={valid_speed.max():.2f} m/s")

    # --- Step 3: Rolling speed features ---
    print("\n--- Computing rolling speed features ---")
    pings = compute_rolling_speed_features(pings)
    for w in ROLLING_WINDOWS:
        mean_col = f"speed_mean_{w}s"
        std_col = f"speed_std_{w}s"
        nan_mean = pings[mean_col].isna().mean() * 100
        nan_std = pings[std_col].isna().mean() * 100
        print(f"  {mean_col}: NaN={nan_mean:.1f}%, median={pings[mean_col].median():.2f}")
        print(f"  {std_col}: NaN={nan_std:.1f}%, median={pings[std_col].dropna().median():.2f}")

    # --- Step 4: Acceleration ---
    print("\n--- Computing acceleration ---")
    pings = compute_acceleration(pings)
    accel = pings["acceleration"].dropna()
    print(f"  NaN rate: {pings['acceleration'].isna().mean()*100:.1f}%")
    if len(accel) > 0:
        print(f"  Distribution: min={accel.min():.3f}, median={accel.median():.3f}, "
              f"max={accel.max():.3f} m/s^2")
        print(f"  p5={accel.quantile(0.05):.3f}, p95={accel.quantile(0.95):.3f}")

    # --- Step 5: Idle features ---
    print("\n--- Computing idle features ---")
    pings = compute_idle_features(pings)
    idle_rate = pings["is_idle_gps"].mean() * 100
    print(f"  Idle rate: {idle_rate:.1f}% of pings")
    idle_duration = pings.loc[pings["is_idle_gps"] == 1, "seconds_idle"]
    if len(idle_duration) > 0:
        print(f"  seconds_idle (idle pings): median={idle_duration.median():.0f}s, "
              f"max={idle_duration.max():.0f}s")

    # --- Step 6: Feature summary ---
    print(f"\n--- Feature Summary ({len(pings):,} unique pings) ---")
    for col in ROLLING_FEATURE_COLS:
        nan_pct = pings[col].isna().mean() * 100
        print(f"  {col:25s}: NaN={nan_pct:.1f}%")

    # --- Step 7: Historical aggregates ---
    print("\n" + "=" * 60)
    print("Computing historical aggregates (training data only)")
    print("=" * 60)

    print("\n--- Historical segment travel times ---")
    hist_segments = compute_historical_segments(pings)
    if len(hist_segments) > 0:
        seg_path = DATA_DIR / "historical_segments.parquet"
        hist_segments.to_parquet(seg_path, index=False)
        print(f"  Saved {seg_path} ({len(hist_segments)} rows)")

    print("\n--- Historical dwell times ---")
    hist_dwells = compute_historical_dwells(pings)
    if len(hist_dwells) > 0:
        dwell_path = DATA_DIR / "historical_dwells.parquet"
        hist_dwells.to_parquet(dwell_path, index=False)
        print(f"  Saved {dwell_path} ({len(hist_dwells)} rows)")

    print(f"\n{'='*60}")
    print("Differentiator feature engineering complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
