"""
build_differentiator_features.py - Differentiator feature engineering for Tiger Transit.

Computes GPS-derived rolling speed features, historical aggregate features,
timepoint features, and speed ratio -- going beyond the baseline feature set.

Features computed:
  Rolling speed: gps_speed_mps, speed_mean_{30,60,120,180}s, speed_std_{30,60,120,180}s
  Dynamics:      acceleration, is_idle_gps, seconds_idle
  Historical:    segment travel time medians, dwell time medians (saved as parquets)
  Timepoint:     is_timepoint, scheduled_departure_seconds, timepoints_remaining,
                 time_until_next_timepoint_departure, timepoint_adherence
  Speed ratio:   speed_ratio (current / historical median)
  Temporal:      is_rush_hour

Usage:
    python scripts/build_differentiator_features.py

Input:
    data/processed/{train,val,test}.parquet
    data/processed/timepoints.parquet
    data/processed/stop_sequences.parquet
    data/processed/weather.parquet

Output:
    data/processed/historical_segments.parquet
    data/processed/historical_dwells.parquet
    data/processed/{train,val,test}_featured_v2.parquet
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
# Timepoint feature helpers
# ---------------------------------------------------------------------------


def load_timepoint_data():
    """Load timepoint schedule and stop sequence data.

    Returns:
        tp_set: set of (route_id, stop_id) tuples that are timepoints
        tp_schedule: DataFrame with (route_id, stop_id, scheduled_time_seconds)
                     - one row per scheduled departure
        stop_seq: DataFrame with (route_id, stop_id, stop_sequence)
        tp_seq_by_route: dict mapping route_id -> sorted list of timepoint stop_sequences
    """
    tp = pd.read_parquet(DATA_DIR / "timepoints.parquet")
    ss = pd.read_parquet(DATA_DIR / "stop_sequences.parquet")

    # Convert scheduled_time to seconds since midnight
    tp["scheduled_time_seconds"] = pd.to_timedelta(tp["scheduled_time"]).dt.total_seconds()

    # Unique timepoint (route_id, stop_id) set
    tp_unique = tp.drop_duplicates(subset=["route_id", "stop_id"])[["route_id", "stop_id"]]
    tp_set = set(zip(tp_unique["route_id"], tp_unique["stop_id"]))

    # Merge stop_sequence onto timepoint stops
    tp_with_seq = tp_unique.merge(
        ss[["route_id", "stop_id", "stop_sequence"]],
        on=["route_id", "stop_id"],
        how="left",
    )

    # Build per-route sorted timepoint stop_sequences
    tp_seq_by_route = {}
    for rid, grp in tp_with_seq.groupby("route_id"):
        seqs = sorted(grp["stop_sequence"].dropna().astype(int).tolist())
        tp_seq_by_route[rid] = seqs

    return tp_set, tp, ss, tp_seq_by_route


def compute_timepoint_features(df: pd.DataFrame, tp_set, tp_schedule,
                                stop_seq, tp_seq_by_route) -> pd.DataFrame:
    """Compute all timepoint features (vectorized).

    Features:
      - is_timepoint: 1 if target_stop_id is a timepoint for this route
      - scheduled_departure_seconds: scheduled time for target stop (if timepoint)
      - timepoints_remaining: count of timepoint stops between current and target
      - time_until_next_timepoint_departure: seconds until next timepoint departure
      - timepoint_adherence: seconds ahead/behind schedule at last passed timepoint

    Routes 27, 235 get all NaN (no timepoint data).
    """
    n_before = len(df)

    # --- is_timepoint ---
    # Build MultiIndex from (route_id, target_stop_id) pairs in tp_set
    tp_index = pd.MultiIndex.from_tuples(list(tp_set), names=["route_id", "stop_id"])
    obs_index = pd.MultiIndex.from_frame(
        df[["route_id", "target_stop_id"]].rename(columns={"target_stop_id": "stop_id"})
    )
    df["is_timepoint"] = obs_index.isin(tp_index).astype(int)

    # --- scheduled_departure_seconds ---
    # For target stops that are timepoints, get the FIRST scheduled departure
    # (we use median scheduled time per route-stop as representative)
    tp_first = tp_schedule.groupby(["route_id", "stop_id"])["scheduled_time_seconds"].median().reset_index()
    tp_first = tp_first.rename(columns={"stop_id": "target_stop_id",
                                         "scheduled_time_seconds": "scheduled_departure_seconds"})
    df = df.merge(tp_first, on=["route_id", "target_stop_id"], how="left")
    # Non-timepoint target stops already get NaN from left merge

    # --- Get last_stop_sequence via merge ---
    seq_lookup = stop_seq[["route_id", "stop_id", "stop_sequence"]].copy()
    seq_lookup = seq_lookup.rename(columns={"stop_id": "last_stop_id",
                                             "stop_sequence": "last_stop_sequence"})
    df = df.merge(seq_lookup, on=["route_id", "last_stop_id"], how="left")

    assert len(df) == n_before, (
        f"Row count changed after stop_sequence merge! Before={n_before}, After={len(df)}"
    )

    # --- timepoints_remaining ---
    # For each row: count timepoint stop_sequences > last_stop_sequence AND <= target_stop_sequence
    # Vectorize by building a mapping per route
    tp_remaining = np.full(len(df), np.nan)
    for rid, tp_seqs in tp_seq_by_route.items():
        if not tp_seqs:
            continue
        mask = df["route_id"] == rid
        if not mask.any():
            continue
        last_seq = df.loc[mask, "last_stop_sequence"].values
        target_seq = df.loc[mask, "target_stop_sequence"].values
        tp_arr = np.array(tp_seqs)
        # For each obs: count tp_seqs > last_seq AND <= target_seq
        counts = np.zeros(mask.sum(), dtype=float)
        for ts in tp_arr:
            counts += ((ts > last_seq) & (ts <= target_seq)).astype(float)
        tp_remaining[mask.values] = counts

    df["timepoints_remaining"] = tp_remaining

    # --- time_until_next_timepoint_departure ---
    # Current time in CT seconds since midnight
    ct_ts = df["timestamp"] - pd.Timedelta(hours=6)
    minutes_ct = ct_ts.dt.hour * 60 + ct_ts.dt.minute
    seconds_ct = minutes_ct * 60 + ct_ts.dt.second

    # For each row, find the next timepoint stop ahead on the route
    # and look up its scheduled departure
    # Build lookup: for each route, for each timepoint stop_seq, get the median scheduled time
    tp_with_seq_sched = tp_schedule.drop_duplicates(subset=["route_id", "stop_id"]).copy()
    tp_with_seq_sched = tp_with_seq_sched.merge(
        stop_seq[["route_id", "stop_id", "stop_sequence"]],
        on=["route_id", "stop_id"],
        how="left",
    )
    # Median scheduled time per (route_id, stop_id)
    tp_sched_lookup = tp_schedule.groupby(["route_id", "stop_id"])["scheduled_time_seconds"].median().reset_index()
    tp_sched_lookup = tp_sched_lookup.merge(
        stop_seq[["route_id", "stop_id", "stop_sequence"]],
        on=["route_id", "stop_id"],
        how="left",
    )

    time_until_next = np.full(len(df), np.nan)
    adherence = np.full(len(df), np.nan)

    for rid, tp_seqs in tp_seq_by_route.items():
        if not tp_seqs:
            continue
        mask = df["route_id"] == rid
        if not mask.any():
            continue

        # Get (stop_sequence, scheduled_time) for this route's timepoints
        route_tp = tp_sched_lookup[tp_sched_lookup["route_id"] == rid].copy()
        route_tp = route_tp.dropna(subset=["stop_sequence"])
        route_tp = route_tp.sort_values("stop_sequence")

        if len(route_tp) == 0:
            continue

        tp_seqs_arr = route_tp["stop_sequence"].values.astype(float)
        tp_times_arr = route_tp["scheduled_time_seconds"].values.astype(float)

        mask_indices = mask.values.nonzero()[0]
        last_seq = df.loc[mask, "last_stop_sequence"].values.astype(float)
        curr_secs = seconds_ct[mask].values.astype(float)

        # Vectorized: use searchsorted to find next TP ahead and last TP behind
        # searchsorted(tp_seqs_arr, last_seq, side='right') gives index of first tp > last_seq
        valid = ~np.isnan(last_seq)
        if not valid.any():
            continue

        next_idx = np.searchsorted(tp_seqs_arr, last_seq[valid], side="right")
        prev_idx = next_idx - 1  # index of last tp <= last_seq

        # Next TP ahead
        has_next = next_idx < len(tp_seqs_arr)
        next_times = np.where(has_next, tp_times_arr[np.clip(next_idx, 0, len(tp_seqs_arr) - 1)], np.nan)
        time_until_next[mask_indices[valid]] = np.where(has_next, next_times - curr_secs[valid], np.nan)

        # Previous TP (most recent passed)
        has_prev = prev_idx >= 0
        prev_times = np.where(has_prev, tp_times_arr[np.clip(prev_idx, 0, len(tp_seqs_arr) - 1)], np.nan)
        adherence[mask_indices[valid]] = np.where(has_prev, curr_secs[valid] - prev_times, np.nan)

    df["time_until_next_timepoint_departure"] = time_until_next
    df["timepoint_adherence"] = adherence

    # --- Routes 27, 235: verify all NaN ---
    no_tp_routes = {27, 235}
    for rid in no_tp_routes:
        rmask = df["route_id"] == rid
        if rmask.any():
            for col in ["is_timepoint", "scheduled_departure_seconds",
                        "timepoints_remaining", "time_until_next_timepoint_departure",
                        "timepoint_adherence"]:
                if col == "is_timepoint":
                    # Should be 0 (not a timepoint), set to NaN for consistency
                    df.loc[rmask, col] = np.nan
                # Others should already be NaN from merges

    # Drop temp column
    if "last_stop_sequence" in df.columns:
        df.drop(columns=["last_stop_sequence"], inplace=True)

    return df


def compute_speed_ratio(df: pd.DataFrame, hist_segments: pd.DataFrame) -> pd.DataFrame:
    """Compute speed ratio: current GPS speed / historical median speed for segment.

    Uses the historical_segments aggregates to get median segment speed, then
    computes a simpler ratio based on the gps_speed_mps already on the dataframe.

    NaN where historical median is NaN or zero.
    """
    # Compute historical median GPS speed per (route_id, last_stop_id, hour_ct, day_type)
    # from the segment data. We use segment_travel_median as a proxy -- but we need
    # actual speed. Since we don't have distance per segment, use a different approach:
    # compute speed ratio = gps_speed_mps / route-hour-daytype median gps_speed_mps
    # from a precomputed lookup.
    #
    # Actually, the plan says: "compute historical median GPS speed per
    # (route_id, last_stop_id, hour_ct, day_type) from training pings directly"
    # This should already be saved or computed. For simplicity, use the
    # segment_travel columns from historical_segments as a proxy for segment context,
    # and build the speed lookup from the training data inline.

    # We'll just do: speed_ratio = gps_speed_mps / median_speed_for_segment
    # where median_speed_for_segment is grouped from all gps_speed_mps values
    # in training pings by (route_id, last_stop_id, hour_ct, day_type).
    # This lookup is built and stored during the pipeline.

    if "_hist_speed_median" in df.columns:
        # Already merged
        df["speed_ratio"] = df["gps_speed_mps"] / df["_hist_speed_median"]
        df.loc[df["_hist_speed_median"] <= 0, "speed_ratio"] = np.nan
        df.drop(columns=["_hist_speed_median"], inplace=True)
    else:
        df["speed_ratio"] = np.nan

    return df


def build_historical_speed_lookup(pings: pd.DataFrame) -> pd.DataFrame:
    """Build historical median GPS speed per (route_id, last_stop_id, hour_ct, day_type).

    Used for speed_ratio computation. Built from training pings only.
    """
    pings = add_ct_hour(pings) if "hour_ct" not in pings.columns else pings
    pings["day_type"] = pings["is_weekday"].astype(int) if "day_type" not in pings.columns else pings["day_type"]

    valid = pings[pings["gps_speed_mps"].notna()].copy()
    agg_cols = ["route_id", "last_stop_id", "hour_ct", "day_type"]
    lookup = valid.groupby(agg_cols, observed=True)["gps_speed_mps"].agg(
        _hist_speed_median="median",
        _count="count",
    ).reset_index()

    # Filter sparse combos
    lookup.loc[lookup["_count"] < MIN_OBS, "_hist_speed_median"] = np.nan
    lookup.drop(columns=["_count"], inplace=True)

    return lookup


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


ROLLING_FEATURE_COLS = (
    ["gps_speed_mps"]
    + [f"speed_mean_{w}s" for w in ROLLING_WINDOWS]
    + [f"speed_std_{w}s" for w in ROLLING_WINDOWS]
    + ["acceleration", "is_idle_gps", "seconds_idle"]
)

# Phase 3 baseline features (from build_features.py)
PHASE3_FEATURE_COLS = [
    "distance_to_target", "scheduled_time_to_target", "current_speed",
    "route_progress", "stops_remaining", "stop_index", "lateness_now",
    "minutes_since_midnight", "day_of_week", "route_id", "pattern_id",
    "precipitation_mm", "temperature_c", "passenger_load", "is_idle",
]

# Phase 4 new features
PHASE4_FEATURE_COLS = (
    ROLLING_FEATURE_COLS
    + [
        "is_timepoint", "scheduled_departure_seconds", "timepoints_remaining",
        "time_until_next_timepoint_departure", "timepoint_adherence",
        "segment_travel_median", "segment_travel_p25", "segment_travel_p75",
        "dwell_median", "dwell_p25", "dwell_p75",
        "target_dwell_median", "target_dwell_p25", "target_dwell_p75",
        "speed_ratio",
        "is_rush_hour",
    ]
)

# Combined v2 feature set
FEATURE_COLS_V2 = PHASE3_FEATURE_COLS + PHASE4_FEATURE_COLS

CATEGORICAL_COLS_V2 = ["day_of_week", "route_id", "pattern_id"]

TARGET_COL = "time_to_arrival_seconds"

KEEP_EXTRA = ["stops_away", "route_id"]

SPLITS = ["train", "val", "test"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_featured_v2(split: str) -> pd.DataFrame:
    """Load a v2 featured parquet split with correct dtypes.

    Args:
        split: One of "train", "val", "test"

    Returns:
        DataFrame with all Phase 3 + Phase 4 features, target, and eval columns.
    """
    path = DATA_DIR / f"{split}_featured_v2.parquet"
    df = pd.read_parquet(path)
    for col in CATEGORICAL_COLS_V2:
        if col in df.columns:
            df[col] = df[col].astype("category")
    return df


# ---------------------------------------------------------------------------
# Phase 3 feature computation (inlined from build_features.py)
# ---------------------------------------------------------------------------


def _load_max_shape_dist() -> pd.Series:
    """Load max_shape_dist per route_id from stop_sequences."""
    ss = pd.read_parquet(DATA_DIR / "stop_sequences.parquet")
    return ss.groupby("route_id")["max_shape_dist"].first()


def _load_weather() -> pd.DataFrame:
    """Load hourly weather data for merge."""
    w = pd.read_parquet(DATA_DIR / "weather.parquet")
    w = w[["hour", "precipitation_mm", "temperature_c"]].copy()
    if w["hour"].dt.tz is None:
        w["hour"] = w["hour"].dt.tz_localize("UTC")
    # Deduplicate
    w = w.drop_duplicates(subset=["hour"], keep="first")
    return w


def compute_phase3_features(df: pd.DataFrame, max_shape_dist: pd.Series,
                             weather: pd.DataFrame, split_name: str) -> pd.DataFrame:
    """Compute Phase 3 baseline features (15 columns). Inlined from build_features.py."""
    n_before = len(df)

    # FEAT-01: distance_to_target
    route_max_sd = df["route_id"].map(max_shape_dist)
    df["distance_to_target"] = (
        (df["target_stop_progress"] - df["progress"]) * route_max_sd
    ).clip(lower=0)

    # FEAT-02: scheduled_time_to_target
    df["scheduled_time_to_target"] = df["scheduled_eta_seconds"].clip(lower=0)

    # FEAT-03: current_speed, route_progress, stops_remaining, stop_index
    df["current_speed"] = df["speed"]
    df["route_progress"] = df["progress"]
    df["stops_remaining"] = df["stops_away"]
    df["stop_index"] = df["target_stop_sequence"]

    # FEAT-04: lateness_now
    df["lateness_now"] = df["scheduled_eta_seconds"] - df["eta_seconds"]

    # FEAT-05: minutes_since_midnight, day_of_week
    ts = df["timestamp"]
    df["minutes_since_midnight"] = ts.dt.hour * 60 + ts.dt.minute
    df["day_of_week"] = ts.dt.dayofweek.astype("category")

    # FEAT-06: pattern_id, route_id as categorical
    df["pattern_id"] = df["pattern_id"].astype("category")
    df["route_id"] = df["route_id"].astype("category")

    # FEAT-07: precipitation_mm, temperature_c
    df["_merge_hour"] = ts.dt.floor("h")
    df = df.merge(weather, left_on="_merge_hour", right_on="hour", how="left",
                  suffixes=("", "_weather"))
    df.drop(columns=["_merge_hour", "hour"], inplace=True, errors="ignore")
    df["precipitation_mm"] = df["precipitation_mm"].fillna(0)
    df["temperature_c"] = df["temperature_c"].fillna(df["temperature_c"].median())

    # FEAT-08: passenger_load, is_idle
    df["passenger_load"] = df["load"]
    df["is_idle"] = (df["speed"] <= 2).astype(int)

    assert len(df) == n_before, (
        f"Row count changed during Phase 3 features! Before={n_before}, After={len(df)}"
    )
    return df


# ---------------------------------------------------------------------------
# v2 Parquet save
# ---------------------------------------------------------------------------


def save_v2_parquet(df: pd.DataFrame, split_name: str) -> None:
    """Save v2 featured parquet with pyarrow dictionary encoding for categoricals."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    out_cols = list(FEATURE_COLS_V2) + [TARGET_COL]
    for c in KEEP_EXTRA:
        if c not in out_cols:
            out_cols.append(c)

    # Only keep columns that exist
    available = [c for c in out_cols if c in df.columns]
    missing = [c for c in out_cols if c not in df.columns]
    if missing:
        print(f"  WARNING: Missing columns: {missing}")

    out = df[available].copy()

    # Ensure categoricals
    for col in CATEGORICAL_COLS_V2:
        if col in out.columns:
            out[col] = out[col].astype("category")

    table = pa.Table.from_pandas(out, preserve_index=False)
    for col in CATEGORICAL_COLS_V2:
        idx = table.schema.get_field_index(col)
        if idx >= 0:
            arr = table.column(col)
            if not pa.types.is_dictionary(arr.type):
                arr = arr.dictionary_encode()
            table = table.set_column(idx, col, arr)

    path = DATA_DIR / f"{split_name}_featured_v2.parquet"
    pq.write_table(table, path)
    print(f"  Saved {path} ({len(out):,} rows, {len(available)} columns)")


# ---------------------------------------------------------------------------
# Full assembly pipeline
# ---------------------------------------------------------------------------


def process_split(df: pd.DataFrame, split_name: str,
                  max_shape_dist, weather,
                  pings_featured, hist_segments, hist_dwells,
                  speed_lookup, tp_set, tp_schedule, stop_seq,
                  tp_seq_by_route) -> pd.DataFrame:
    """Process a single split: compute all Phase 3 + Phase 4 features."""
    n_original = len(df)
    print(f"\n{'='*60}")
    print(f"Processing {split_name} split ({n_original:,} rows)")
    print(f"{'='*60}")

    # Step A: Phase 3 features
    print("\n  [A] Phase 3 features...")
    # Need route_id as numeric for merges
    df["route_id"] = df["route_id"].astype(int)
    df = compute_phase3_features(df, max_shape_dist, weather, split_name)
    # Restore route_id to int for merges (compute_phase3 makes it categorical)
    df["route_id"] = df["route_id"].astype(int)

    # Step B+C: Rolling features from unique pings
    print("  [B] Extracting unique pings and computing rolling features...")
    pings = extract_unique_pings(df)
    print(f"      Unique pings: {len(pings):,}")
    pings = compute_gps_speed(pings)
    pings = compute_rolling_speed_features(pings)
    pings = compute_acceleration(pings)
    pings = compute_idle_features(pings)

    print("  [C] Merging rolling features back to exploded data...")
    df = merge_rolling_to_exploded(df, pings, ROLLING_FEATURE_COLS)
    assert len(df) == n_original, (
        f"Row count changed after rolling merge! Before={n_original}, After={len(df)}"
    )

    # Step D: Historical aggregates
    print("  [D] Merging historical aggregates...")

    # Add hour_ct and day_type for merge keys
    df = add_ct_hour(df)
    df["day_type"] = df["is_weekday"].astype(int)

    # Segments: merge on (route_id, last_stop_id, hour_ct, day_type)
    n_pre = len(df)
    df = df.merge(hist_segments, on=["route_id", "last_stop_id", "hour_ct", "day_type"], how="left")
    assert len(df) == n_pre, f"Row explosion on segment merge! {n_pre} -> {len(df)}"

    # Dwells for current stop: merge on (route_id, stop_id=last_stop_id, hour_ct, day_type)
    dwell_current = hist_dwells.rename(columns={"stop_id": "last_stop_id"})
    df = df.merge(dwell_current, on=["route_id", "last_stop_id", "hour_ct", "day_type"], how="left")
    assert len(df) == n_pre, f"Row explosion on dwell merge! {n_pre} -> {len(df)}"

    # Dwells for target stop: merge on (route_id, stop_id=target_stop_id, hour_ct, day_type)
    dwell_target = hist_dwells.rename(columns={
        "stop_id": "target_stop_id",
        "dwell_median": "target_dwell_median",
        "dwell_p25": "target_dwell_p25",
        "dwell_p75": "target_dwell_p75",
    })
    df = df.merge(dwell_target, on=["route_id", "target_stop_id", "hour_ct", "day_type"], how="left")
    assert len(df) == n_pre, f"Row explosion on target dwell merge! {n_pre} -> {len(df)}"

    # Speed lookup merge
    df = df.merge(speed_lookup, on=["route_id", "last_stop_id", "hour_ct", "day_type"], how="left")
    assert len(df) == n_pre, f"Row explosion on speed lookup merge! {n_pre} -> {len(df)}"

    # Step E: Timepoint features
    print("  [E] Computing timepoint features...")
    df = compute_timepoint_features(df, tp_set, tp_schedule, stop_seq, tp_seq_by_route)
    assert len(df) == n_original, (
        f"Row count changed after timepoint features! Before={n_original}, After={len(df)}"
    )

    # Step F: Speed ratio
    print("  [F] Computing speed ratio...")
    df = compute_speed_ratio(df, hist_segments)

    # Step G: is_rush_hour
    print("  [G] Computing is_rush_hour...")
    df["is_rush_hour"] = df["hour_ct"].isin([7, 8, 9, 16, 17, 18]).astype(int)

    # Restore categoricals for save
    df["route_id"] = df["route_id"].astype("category")

    assert len(df) == n_original, (
        f"Final row count mismatch! Expected={n_original}, Got={len(df)}"
    )

    return df


def main():
    print("=" * 60)
    print("Differentiator Feature Engineering v2 Pipeline")
    print("=" * 60)

    # --- Load supplementary data ---
    print("\nLoading supplementary data...")
    max_shape_dist = _load_max_shape_dist()
    print(f"  max_shape_dist: {len(max_shape_dist)} routes")
    weather = _load_weather()
    print(f"  weather: {len(weather)} hourly records")

    # --- Load timepoint data ---
    print("\nLoading timepoint data...")
    tp_set, tp_schedule, stop_seq, tp_seq_by_route = load_timepoint_data()
    print(f"  Timepoint (route, stop) pairs: {len(tp_set)}")
    print(f"  Routes with timepoints: {len(tp_seq_by_route)}")

    # --- Step 1: Train pings for historical aggregates and speed lookup ---
    print("\n" + "=" * 60)
    print("Step 1: Historical aggregates from training data")
    print("=" * 60)

    train_path = DATA_DIR / "train.parquet"
    print(f"\nLoading {train_path}...")
    train_raw = pd.read_parquet(train_path)
    print(f"  Loaded {len(train_raw):,} rows")

    pings = extract_unique_pings(train_raw)
    print(f"  Unique pings: {len(pings):,}")
    pings = compute_gps_speed(pings)

    # Historical segments
    print("\n--- Historical segment travel times ---")
    hist_segments = compute_historical_segments(pings)
    if len(hist_segments) > 0:
        seg_path = DATA_DIR / "historical_segments.parquet"
        hist_segments.to_parquet(seg_path, index=False)
        print(f"  Saved {seg_path} ({len(hist_segments)} rows)")

    # Historical dwells
    print("\n--- Historical dwell times ---")
    hist_dwells = compute_historical_dwells(pings)
    if len(hist_dwells) > 0:
        dwell_path = DATA_DIR / "historical_dwells.parquet"
        hist_dwells.to_parquet(dwell_path, index=False)
        print(f"  Saved {dwell_path} ({len(hist_dwells)} rows)")

    # Speed lookup (for speed_ratio)
    print("\n--- Historical speed lookup ---")
    pings = add_ct_hour(pings)
    speed_lookup = build_historical_speed_lookup(pings)
    print(f"  Speed lookup: {len(speed_lookup)} combos, "
          f"{speed_lookup['_hist_speed_median'].notna().sum()} valid")

    del pings  # Free memory

    # --- Step 2: Process all splits ---
    print("\n" + "=" * 60)
    print("Step 2: Assemble v2 featured parquets")
    print("=" * 60)

    expected_rows = {}
    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}.parquet"
        print(f"\nLoading {path}...")
        df = pd.read_parquet(path)
        expected_rows[split_name] = len(df)

        df = process_split(
            df, split_name,
            max_shape_dist, weather,
            None, hist_segments, hist_dwells,
            speed_lookup, tp_set, tp_schedule, stop_seq,
            tp_seq_by_route,
        )

        # Print feature NaN rates
        print(f"\n  --- {split_name} Phase 4 Feature NaN Rates ---")
        for col in PHASE4_FEATURE_COLS:
            if col in df.columns:
                nan_pct = df[col].isna().mean() * 100
                print(f"    {col:45s}: NaN={nan_pct:.1f}%")
            else:
                print(f"    {col:45s}: MISSING")

        save_v2_parquet(df, split_name)
        del df  # Free memory

    # --- Step 3: Summary ---
    print("\n" + "=" * 60)
    print("v2 Feature Assembly Summary")
    print("=" * 60)

    print(f"\n  Phase 3 features: {len(PHASE3_FEATURE_COLS)}")
    print(f"  Phase 4 features: {len(PHASE4_FEATURE_COLS)}")
    print(f"  Total v2 features: {len(FEATURE_COLS_V2)}")

    print(f"\n  {'Split':<8} {'Expected':>10} {'Saved':>10}")
    print(f"  {'-'*30}")
    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}_featured_v2.parquet"
        saved = pd.read_parquet(path, columns=[TARGET_COL])
        print(f"  {split_name:<8} {expected_rows[split_name]:>10,} {len(saved):>10,}")
        assert len(saved) == expected_rows[split_name], (
            f"Row count mismatch for {split_name}! "
            f"Expected={expected_rows[split_name]}, Got={len(saved)}"
        )

    # Verify routes 27 and 235 have NaN timepoint features
    print("\n  Verifying routes 27/235 timepoint features are NaN...")
    for split_name in SPLITS:
        path = DATA_DIR / f"{split_name}_featured_v2.parquet"
        check = pd.read_parquet(path, columns=["is_timepoint", "timepoints_remaining",
                                                 "route_id"])
        # route_id may be dictionary-encoded
        if hasattr(check["route_id"], "cat"):
            rid = check["route_id"].astype(int)
        else:
            rid = check["route_id"]
        for r in [27, 235]:
            rmask = rid == r
            if rmask.any():
                tp_nans = check.loc[rmask, "is_timepoint"].isna().all()
                print(f"    {split_name} route {r}: is_timepoint all NaN = {tp_nans} ({rmask.sum()} rows)")

    print(f"\n{'='*60}")
    print("Differentiator feature engineering v2 complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
