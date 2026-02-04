"""
Downsample telemetry to ~60s intervals and explode into per-stop rows.

Reads:  data/processed/telemetry.parquet, data/processed/stop_sequences.parquet
Writes: data/processed/exploded.parquet

Processing:
1. Load stop sequences for route->stop lookup
2. Process telemetry one day at a time (PyArrow predicate pushdown)
3. Filter idle vehicles (progress==0 & speed==0, next_stop_id==0)
4. Downsample to 60s buckets per (vehicle_id, route_id)
5. Explode: merge with stop_sequences, keep stops ahead (up to 8)
6. Write concatenated result
"""

import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
TELEMETRY_PATH = OUTPUT_DIR / "telemetry.parquet"
STOP_SEQ_PATH = OUTPUT_DIR / "stop_sequences.parquet"
OUTPUT_PATH = OUTPUT_DIR / "exploded.parquet"

# Route 237 has no GTFS data -- exclude explicitly
EXCLUDE_ROUTES = {237}
MAX_STOPS_AHEAD = 8


def load_stop_sequences() -> pd.DataFrame:
    """Load stop sequences and return DataFrame for merge."""
    df = pd.read_parquet(STOP_SEQ_PATH)
    # Rename columns for the merge to avoid collision with telemetry columns
    df = df.rename(columns={
        "stop_id": "target_stop_id",
        "stop_sequence": "target_stop_sequence",
        "stop_progress": "target_stop_progress",
    })
    # Keep only columns needed for merge
    df = df[["route_id", "target_stop_id", "target_stop_sequence",
             "target_stop_progress"]]
    return df


def get_unique_dates() -> list:
    """Get sorted unique dates from telemetry using metadata scan."""
    # Read just the timestamp column to find date range
    table = pq.read_table(str(TELEMETRY_PATH), columns=["timestamp"])
    ts = table.column("timestamp").to_pandas()
    dates = sorted(ts.dt.date.unique())
    del table, ts
    return dates


def process_day(day, stop_seqs: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Process one day of telemetry. Returns (exploded_df, raw_count, downsampled_count)."""
    import datetime

    day_start = pd.Timestamp(day, tz="UTC")
    day_end = pd.Timestamp(day + datetime.timedelta(days=1), tz="UTC")

    # Read day's data with predicate pushdown
    table = pq.read_table(
        str(TELEMETRY_PATH),
        filters=[("timestamp", ">=", day_start), ("timestamp", "<", day_end)],
    )
    df = table.to_pandas()
    del table
    raw_count = len(df)

    if raw_count == 0:
        return pd.DataFrame(), 0, 0

    # ── Filter idle vehicles ──────────────────────────────────
    # Remove parked/idle: progress==0 AND speed==0
    idle_mask = (df["progress"] == 0) & (df["speed"] == 0)
    # Remove no active trip: next_stop_id==0
    no_trip_mask = df["next_stop_id"] == 0
    # Exclude Route 237
    route_mask = df["route_id"].isin(EXCLUDE_ROUTES)

    df = df[~idle_mask & ~no_trip_mask & ~route_mask].copy()

    if len(df) == 0:
        return pd.DataFrame(), raw_count, 0

    # ── Downsample to 60s buckets ─────────────────────────────
    # Create 60-second time buckets
    df["time_bucket"] = df["timestamp"].dt.floor("60s")

    # Keep last observation per (vehicle_id, route_id, time_bucket)
    df = df.sort_values("timestamp")
    df = df.groupby(["vehicle_id", "route_id", "time_bucket"], observed=True).last()
    df = df.reset_index()
    df = df.drop(columns=["time_bucket"])

    downsampled_count = len(df)

    if downsampled_count == 0:
        return pd.DataFrame(), raw_count, 0

    # ── Explode: merge with stop sequences ────────────────────
    # Add a row index to track which telemetry row each exploded row came from
    df["_row_idx"] = range(len(df))

    # Merge on route_id -- this creates N rows per telemetry row
    # (one for each stop on that route)
    merged = df.merge(stop_seqs, on="route_id", how="inner")

    if len(merged) == 0:
        return pd.DataFrame(), raw_count, downsampled_count

    # Keep only stops ahead of vehicle (target_stop_progress > progress)
    merged = merged[merged["target_stop_progress"] > merged["progress"]].copy()

    if len(merged) == 0:
        return pd.DataFrame(), raw_count, downsampled_count

    # Rank by target_stop_progress within each telemetry row, keep top 8
    merged["stops_away"] = (
        merged.groupby("_row_idx")["target_stop_progress"]
        .rank(method="first")
        .astype(int)
    )
    merged = merged[merged["stops_away"] <= MAX_STOPS_AHEAD].copy()

    # Drop helper column
    merged = merged.drop(columns=["_row_idx"])

    return merged, raw_count, downsampled_count


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print("=" * 60)
    print("Downsample & Explode Telemetry")
    print("=" * 60)

    # ── Load stop sequences ────────────────────────────────────
    stop_seqs = load_stop_sequences()
    routes_with_seqs = set(stop_seqs["route_id"].unique())
    print(f"Loaded stop sequences: {len(routes_with_seqs)} routes")

    # ── Get unique dates ───────────────────────────────────────
    print("Scanning telemetry dates...")
    dates = get_unique_dates()
    print(f"Found {len(dates)} unique dates: {dates[0]} to {dates[-1]}")

    # ── Process each day ───────────────────────────────────────
    all_chunks = []
    total_raw = 0
    total_downsampled = 0
    total_exploded = 0
    day_exploded_counts = []
    skipped_no_seq = 0

    print(f"\nProcessing {len(dates)} days...")
    sys.stdout.flush()

    for i, day in enumerate(dates, 1):
        chunk, raw_ct, ds_ct = process_day(day, stop_seqs)
        exp_ct = len(chunk)

        total_raw += raw_ct
        total_downsampled += ds_ct
        total_exploded += exp_ct
        day_exploded_counts.append(exp_ct)

        if exp_ct > 0:
            all_chunks.append(chunk)

        print(f"  [{i:2d}/{len(dates)}] {day}: "
              f"{raw_ct:>9,} raw -> {ds_ct:>7,} downsampled -> {exp_ct:>8,} exploded")
        sys.stdout.flush()

    # ── Concatenate and write ──────────────────────────────────
    print(f"\nConcatenating {len(all_chunks)} day chunks...")
    sys.stdout.flush()

    if not all_chunks:
        print("ERROR: No exploded rows produced!")
        sys.exit(1)

    df = pd.concat(all_chunks, ignore_index=True)
    del all_chunks

    # ── Summary stats ──────────────────────────────────────────
    elapsed = time.time() - t0
    print(f"\n{'=' * 60}")
    print(f"Summary")
    print(f"{'=' * 60}")
    print(f"Total raw telemetry rows:  {total_raw:>12,}")
    print(f"After downsample (~60s):   {total_downsampled:>12,}")
    print(f"After explosion:           {total_exploded:>12,}")
    print(f"Expansion factor:          {total_exploded / max(total_downsampled, 1):.1f}x")
    print(f"\nExploded rows per day:")
    if day_exploded_counts:
        print(f"  Min:  {min(day_exploded_counts):>10,}")
        print(f"  Max:  {max(day_exploded_counts):>10,}")
        print(f"  Mean: {sum(day_exploded_counts) / len(day_exploded_counts):>10,.0f}")

    print(f"\nStops_away distribution:")
    stops_dist = df["stops_away"].value_counts().sort_index()
    for sa, count in stops_dist.items():
        print(f"  stops_away={sa}: {count:>10,} rows")

    print(f"\nRoutes represented: {df['route_id'].nunique()}")
    print(f"Date range: {df['timestamp'].dt.date.min()} to {df['timestamp'].dt.date.max()}")
    print(f"Output columns: {list(df.columns)}")
    print(f"Total rows: {len(df):,}")

    # ── Assertions ─────────────────────────────────────────────
    assert (df["stops_away"] > 0).all(), "Negative or zero stops_away!"
    assert (df["stops_away"] <= MAX_STOPS_AHEAD).all(), "stops_away exceeds max!"
    assert (df["target_stop_progress"] > df["progress"]).all(), \
        "target_stop_progress not ahead of vehicle progress!"
    print("\nAll assertions passed.")

    # ── Write output ───────────────────────────────────────────
    print(f"\nWriting to {OUTPUT_PATH}...")
    sys.stdout.flush()
    df.to_parquet(OUTPUT_PATH, index=False)
    size_mb = OUTPUT_PATH.stat().st_size / 1024 / 1024
    print(f"File size: {size_mb:.1f} MB")
    print(f"Elapsed: {elapsed:.0f}s")
    print("Done.")


if __name__ == "__main__":
    main()
