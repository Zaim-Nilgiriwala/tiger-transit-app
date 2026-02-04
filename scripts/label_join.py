"""
Join exploded telemetry rows with actual arrival times to create ground truth labels.

Reads:  data/processed/exploded.parquet, data/processed/arrivals.parquet
Writes: data/processed/labeled.parquet

Processing:
1. Load exploded rows and arrivals
2. Prepare columns for merge_asof (rename, sort, type-check)
3. merge_asof(direction='forward', tolerance=2h) on timestamp
4. Compute time_to_arrival_seconds = actual_arrival - timestamp
5. Filter: drop NaT, too-close (<= 10s), too-far (> 7200s), negative, per-route outliers
6. Timezone spike check at 3600s
7. Write labeled.parquet
"""

import sys
import time
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
EXPLODED_PATH = OUTPUT_DIR / "exploded.parquet"
ARRIVALS_PATH = OUTPUT_DIR / "arrivals.parquet"
OUTPUT_PATH = OUTPUT_DIR / "labeled.parquet"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("=" * 60)
    print("Label Join via merge_asof")
    print("=" * 60)

    # ── Step 1: Load data ────────────────────────────────────
    print("\n[1] Loading data...")
    exploded = pd.read_parquet(EXPLODED_PATH)
    arrivals = pd.read_parquet(ARRIVALS_PATH)
    print(f"  Exploded rows: {len(exploded):,}")
    print(f"  Arrivals rows: {len(arrivals):,}")

    total_exploded = len(exploded)

    # ── Step 2: Prepare for merge_asof ───────────────────────
    print("\n[2] Preparing for merge_asof...")

    # Prepare arrivals: rename columns for join
    arrivals_prep = arrivals[["route_id", "stop_id", "vehicle_id", "arrival_timestamp"]].copy()
    arrivals_prep = arrivals_prep.rename(columns={
        "stop_id": "target_stop_id",
        "arrival_timestamp": "actual_arrival",
    })

    # Type checks
    assert exploded["vehicle_id"].dtype == object, f"Exploded vehicle_id is {exploded['vehicle_id'].dtype}, expected string"
    assert arrivals_prep["vehicle_id"].dtype == object, f"Arrivals vehicle_id is {arrivals_prep['vehicle_id'].dtype}, expected string"
    assert exploded["route_id"].dtype == arrivals_prep["route_id"].dtype, "route_id type mismatch"
    assert exploded["target_stop_id"].dtype == arrivals_prep["target_stop_id"].dtype, "target_stop_id type mismatch"
    print("  Type checks passed (vehicle_id=string, route_id=int64, target_stop_id=int64)")

    # Sort both by merge key
    exploded = exploded.sort_values("timestamp").reset_index(drop=True)
    arrivals_prep = arrivals_prep.sort_values("actual_arrival").reset_index(drop=True)

    # Drop arrivals with NaT
    nat_arrivals = arrivals_prep["actual_arrival"].isna().sum()
    if nat_arrivals > 0:
        print(f"  Dropping {nat_arrivals:,} arrivals with NaT timestamps")
        arrivals_prep = arrivals_prep.dropna(subset=["actual_arrival"])

    # Check overlap in keys
    common_routes = set(exploded["route_id"].unique()) & set(arrivals_prep["route_id"].unique())
    common_stops = set(exploded["target_stop_id"].unique()) & set(arrivals_prep["target_stop_id"].unique())
    common_vehicles = set(exploded["vehicle_id"].unique()) & set(arrivals_prep["vehicle_id"].unique())
    print(f"  Common routes: {len(common_routes)}")
    print(f"  Common target_stop_ids: {len(common_stops)}")
    print(f"  Common vehicle_ids: {len(common_vehicles)}")

    if len(common_routes) == 0 or len(common_stops) == 0 or len(common_vehicles) == 0:
        print("ERROR: No overlap in join keys! Check data.")
        sys.exit(1)

    # ── Step 3: Execute merge_asof ───────────────────────────
    print("\n[3] Running merge_asof (direction='forward', tolerance=2h)...")
    sys.stdout.flush()

    df = pd.merge_asof(
        exploded,
        arrivals_prep,
        left_on="timestamp",
        right_on="actual_arrival",
        by=["route_id", "target_stop_id", "vehicle_id"],
        direction="forward",
        tolerance=pd.Timedelta("2h"),
    )
    print(f"  Merged rows: {len(df):,}")

    matched_count = df["actual_arrival"].notna().sum()
    print(f"  Rows with match: {matched_count:,} ({matched_count / len(df) * 100:.1f}%)")

    # ── Step 4: Compute label ────────────────────────────────
    print("\n[4] Computing time_to_arrival_seconds...")
    df["time_to_arrival_seconds"] = (df["actual_arrival"] - df["timestamp"]).dt.total_seconds()

    # ── Step 5: Filter labels ────────────────────────────────
    print("\n[5] Filtering labels...")
    pre_filter = len(df)

    # Drop NaT (no match)
    no_match = df["actual_arrival"].isna().sum()
    df = df[df["actual_arrival"].notna()].copy()
    print(f"  Dropped no-match (NaT): {no_match:,}")

    # Drop negative (should not happen with forward)
    negative = (df["time_to_arrival_seconds"] <= 0).sum()
    df = df[df["time_to_arrival_seconds"] > 0].copy()
    print(f"  Dropped negative/zero: {negative:,}")

    # Drop too close (<= 10s)
    too_close = (df["time_to_arrival_seconds"] <= 10).sum()
    df = df[df["time_to_arrival_seconds"] > 10].copy()
    print(f"  Dropped too-close (<= 10s): {too_close:,}")

    # Drop too far (> 7200s)
    too_far = (df["time_to_arrival_seconds"] > 7200).sum()
    df = df[df["time_to_arrival_seconds"] <= 7200].copy()
    print(f"  Dropped too-far (> 7200s): {too_far:,}")

    # Per-route outlier removal (above 99.5th percentile per route)
    pre_outlier = len(df)
    route_thresholds = df.groupby("route_id")["time_to_arrival_seconds"].quantile(0.995)
    df = df.merge(
        route_thresholds.rename("_route_p995"),
        left_on="route_id",
        right_index=True,
        how="left",
    )
    outlier_count = (df["time_to_arrival_seconds"] > df["_route_p995"]).sum()
    df = df[df["time_to_arrival_seconds"] <= df["_route_p995"]].copy()
    df = df.drop(columns=["_route_p995"])
    print(f"  Dropped per-route outliers (> 99.5th pctile): {outlier_count:,}")

    post_filter = len(df)
    print(f"  Total removed by filters: {pre_filter - post_filter:,}")

    # ── Step 6: Timezone bug check ───────────────────────────
    print("\n[6] Timezone spike check (3540-3660s range)...")
    spike_count = ((df["time_to_arrival_seconds"] >= 3540) & (df["time_to_arrival_seconds"] <= 3660)).sum()
    spike_pct = spike_count / len(df) * 100 if len(df) > 0 else 0
    print(f"  Rows in 3540-3660s range: {spike_count:,} ({spike_pct:.2f}%)")
    if spike_pct > 5:
        print("  WARNING: >5% of labels in 3540-3660s range -- possible timezone mismatch!")
    else:
        print("  OK: No timezone spike detected.")

    # ── Step 7: Write output ─────────────────────────────────
    print(f"\n[7] Writing to {OUTPUT_PATH}...")
    sys.stdout.flush()
    df.to_parquet(OUTPUT_PATH, index=False)
    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print(f"  File size: {size_mb:.1f} MB")

    # ── Step 8: Comprehensive summary ────────────────────────
    elapsed = time.time() - t0
    label_col = df["time_to_arrival_seconds"]
    success_rate = len(df) / total_exploded * 100

    print(f"\n{'=' * 60}")
    print("Label Join Summary")
    print(f"{'=' * 60}")
    print(f"  Total exploded rows (input):    {total_exploded:>12,}")
    print(f"  Rows with successful match:     {matched_count:>12,}")
    print(f"  Rows after all filters:         {len(df):>12,}")
    print(f"  Label join success rate:        {success_rate:>11.1f}%")
    print()
    print(f"  Label distribution (time_to_arrival_seconds):")
    print(f"    Min:    {label_col.min():>10.1f}")
    print(f"    25th:   {label_col.quantile(0.25):>10.1f}")
    print(f"    Median: {label_col.quantile(0.50):>10.1f}")
    print(f"    75th:   {label_col.quantile(0.75):>10.1f}")
    print(f"    Max:    {label_col.max():>10.1f}")
    print(f"    Mean:   {label_col.mean():>10.1f}")
    print(f"    Std:    {label_col.std():>10.1f}")
    print()
    print(f"  Filter breakdown:")
    print(f"    No match (NaT):          {no_match:>10,}")
    print(f"    Negative/zero:           {negative:>10,}")
    print(f"    Too close (<= 10s):      {too_close:>10,}")
    print(f"    Too far (> 7200s):       {too_far:>10,}")
    print(f"    Per-route outliers:      {outlier_count:>10,}")
    print()
    print(f"  Timezone check:")
    print(f"    3540-3660s range:        {spike_count:>10,} ({spike_pct:.2f}%)")
    print()
    print(f"  Per-route match rates:")
    route_stats = df.groupby("route_id").agg(
        count=("time_to_arrival_seconds", "count"),
        mean_label=("time_to_arrival_seconds", "mean"),
        median_label=("time_to_arrival_seconds", "median"),
    )
    for route_id, row in route_stats.iterrows():
        print(f"    Route {route_id}: {row['count']:>8,} rows, "
              f"mean={row['mean_label']:.0f}s, median={row['median_label']:.0f}s")
    print()
    print(f"  Output columns: {list(df.columns)}")
    print(f"  Final row count: {len(df):,}")
    print(f"  Elapsed: {elapsed:.1f}s")

    # ── Assertions ───────────────────────────────────────────
    assert len(df) > 0, "No labeled rows produced!"
    assert (df["time_to_arrival_seconds"] > 10).all(), "Labels <= 10s found!"
    assert (df["time_to_arrival_seconds"] <= 7200).all(), "Labels > 7200s found!"
    assert (df["time_to_arrival_seconds"] > 0).all(), "Negative labels found!"
    assert df["actual_arrival"].notna().all(), "NaT actual_arrival in output!"
    assert success_rate > 60, f"Label join success rate {success_rate:.1f}% is below 60% minimum!"
    print("\nAll assertions passed.")
    print("Done.")


if __name__ == "__main__":
    main()
