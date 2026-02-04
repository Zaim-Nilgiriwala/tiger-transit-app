"""
Parse raw telemetry JSONL files into a clean parquet file.

Reads all raw_data_*.jsonl files from the raw data directory,
applies filtering and validation per file to manage memory,
and writes a clean parquet to data/processed/telemetry.parquet.
"""

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "mobile" / "src" / "ETA-Model" / "raw_data"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = OUTPUT_DIR / "telemetry.parquet"

# Column rename mapping: original -> snake_case
COLUMN_RENAME = {
    "t": "timestamp_ms",
    "vid": "vehicle_id",
    "routeId": "route_id",
    "patternId": "pattern_id",
    "lastStopId": "last_stop_id",
    "nextStopId": "next_stop_id",
    "etaSeconds": "eta_seconds",
    "scheduledEta": "scheduled_eta_seconds",
    "isDelayed": "is_delayed",
    "lastStopTime": "last_stop_time_ms",
    "lastStopOnTime": "last_stop_on_time",
    # These stay as-is
    "lat": "lat",
    "lon": "lon",
    "heading": "heading",
    "speed": "speed",
    "load": "load",
    "progress": "progress",
}

# Routes to exclude: staging, Charter, Vans, Game Day Shuttle
EXCLUDE_ROUTE_IDS = {777, 230, 231} | set(range(216, 229))


def filter_df(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Apply all exclusion filters to a DataFrame. Returns filtered df and removal counts."""
    counts = {}
    n = len(df)

    # 1. Bounding box
    mask_bbox = (df["lat"] >= 32.5) & (df["lat"] <= 32.7) & (df["lon"] >= -85.6) & (df["lon"] <= -85.4)
    counts["bbox"] = int((~mask_bbox).sum())

    # 2. Speed <= 65
    mask_speed = df["speed"] <= 65
    counts["speed"] = int((~mask_speed).sum())

    # 3. Exclude jAUnt/Shuttle/empty vehicle_id
    vid_str = df["vehicle_id"].astype(str)
    vid_lower = vid_str.str.lower()
    mask_vid = ~(
        vid_lower.str.contains("jaunt", na=False)
        | vid_lower.str.contains("shuttle", na=False)
        | (vid_str == "")
    )
    counts["vid"] = int((~mask_vid).sum())

    # 4. Exclude pattern_id == 9998 (Not In Service)
    mask_pattern = df["pattern_id"] != 9998
    counts["pattern"] = int((~mask_pattern).sum())

    # 5. Exclude staging/charter/vans/gameday routes
    mask_route = ~df["route_id"].isin(EXCLUDE_ROUTE_IDS)
    counts["route"] = int((~mask_route).sum())

    # 6. Exclude progress == -1 (inactive)
    mask_progress = df["progress"] != -1
    counts["progress"] = int((~mask_progress).sum())

    combined = mask_bbox & mask_speed & mask_vid & mask_pattern & mask_route & mask_progress
    counts["total_removed"] = int((~combined).sum())
    counts["kept"] = int(combined.sum())

    return df[combined], counts


def load_and_filter_file(filepath: Path) -> tuple[pd.DataFrame, int, int]:
    """Load a single JSONL file, rename columns, and filter. Returns (filtered_df, raw_count, error_count)."""
    rows = []
    errors = 0
    with open(filepath, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                errors += 1

    if not rows:
        return pd.DataFrame(), 0, errors

    df = pd.DataFrame(rows)
    # Free the list immediately
    del rows

    # Check that expected columns exist (some files have different schema)
    required_raw_cols = {"t", "vid", "lat", "lon", "speed", "routeId", "patternId", "progress"}
    if not required_raw_cols.issubset(df.columns):
        missing = required_raw_cols - set(df.columns)
        print(f"    WARNING: Skipping file - missing columns: {missing}")
        raw_count = len(df)
        del df
        return pd.DataFrame(), raw_count, errors

    # Rename columns
    df = df.rename(columns=COLUMN_RENAME)

    # Filter
    df_filtered, _ = filter_df(df)
    raw_count = len(df)

    # Free unfiltered
    del df

    return df_filtered, raw_count, errors


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(RAW_DATA_DIR.glob("raw_data_*.jsonl"))
    print(f"Found {len(files)} JSONL files to process\n")

    filtered_dfs = []
    total_raw = 0
    total_filtered = 0
    total_errors = 0

    # Aggregate filter counts across all files
    agg_counts = {"bbox": 0, "speed": 0, "vid": 0, "pattern": 0, "route": 0, "progress": 0, "total_removed": 0}

    for i, f in enumerate(files, 1):
        df_filt, raw_count, err_count = load_and_filter_file(f)
        kept = len(df_filt)

        if kept > 0:
            filtered_dfs.append(df_filt)

        total_raw += raw_count
        total_filtered += kept
        total_errors += err_count

        print(f"  [{i:2d}/52] {f.name}: {raw_count:>10,} raw -> {kept:>10,} kept")
        sys.stdout.flush()

    print(f"\nTotal raw rows: {total_raw:,}")
    print(f"Total kept after filtering: {total_filtered:,}")
    print(f"Total removed: {total_raw - total_filtered:,} ({(total_raw - total_filtered) / total_raw * 100:.1f}%)")
    if total_errors:
        print(f"Total parse errors: {total_errors:,}")

    # Concatenate all filtered DataFrames
    print("\nConcatenating filtered data...")
    sys.stdout.flush()
    df = pd.concat(filtered_dfs, ignore_index=True)
    del filtered_dfs

    # Convert timestamps
    df["timestamp"] = pd.to_datetime(df["timestamp_ms"], unit="ms", utc=True)

    # Now compute per-filter removal counts on the full raw data is not feasible,
    # so re-run filter stats on the pre-filter data. Instead, let's just report
    # the combined filter stats by re-checking what's in the final df.
    print(f"\n--- Filtering Summary ---")
    print(f"Starting rows: {total_raw:,}")
    print(f"Rows after all filters: {len(df):,}")
    print(f"Removal rate: {(total_raw - len(df)) / total_raw * 100:.1f}%")

    # Reset index
    df = df.reset_index(drop=True)

    # Validation summary
    print(f"\n--- Validation Summary ---")
    print(f"Total rows: {len(df):,}")
    print(f"\nNull rates per column:")
    null_rates = df.isnull().mean()
    for col, rate in null_rates.items():
        if rate > 0:
            print(f"  {col}: {rate:.4%}")
    if (null_rates == 0).all():
        print("  (no nulls in any column)")

    print(f"\nUnique routes: {df['route_id'].nunique()}")
    print(f"Route IDs: {sorted(df['route_id'].unique())}")
    print(f"Unique vehicles: {df['vehicle_id'].nunique()}")

    date_col = df["timestamp"].dt.date
    print(f"Date range: {date_col.min()} to {date_col.max()}")

    rows_per_day = df.groupby(date_col).size()
    print(f"\nRows per day:")
    print(f"  Min: {rows_per_day.min():,}")
    print(f"  Max: {rows_per_day.max():,}")
    print(f"  Mean: {rows_per_day.mean():,.0f}")
    print(f"  Days: {len(rows_per_day)}")

    # Verify no excluded data leaked through
    vid_lower = df["vehicle_id"].astype(str).str.lower()
    assert not vid_lower.str.contains("jaunt").any(), "jAUnt vehicles found!"
    assert not vid_lower.str.contains("shuttle").any(), "Shuttle vehicles found!"
    assert not (df["pattern_id"] == 9998).any(), "NIS pattern found!"
    assert not df["route_id"].isin(EXCLUDE_ROUTE_IDS).any(), "Excluded routes found!"
    assert not (df["progress"] == -1).any(), "Inactive vehicles found!"
    assert ((df["lat"] >= 32.5) & (df["lat"] <= 32.7)).all(), "Out of bbox lat!"
    assert ((df["lon"] >= -85.6) & (df["lon"] <= -85.4)).all(), "Out of bbox lon!"
    assert (df["speed"] <= 65).all(), "Speed > 65!"
    print("\nAll filter assertions passed.")

    # Write parquet
    print(f"\nWriting to {OUTPUT_PATH}...")
    sys.stdout.flush()
    df.to_parquet(OUTPUT_PATH, index=False)
    print(f"File size: {OUTPUT_PATH.stat().st_size / 1024 / 1024:.1f} MB")
    print("Done.")


if __name__ == "__main__":
    main()
