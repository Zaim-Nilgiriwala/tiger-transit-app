"""
Parse arrivals CSV files into parquet with GTFS stop_id and route_id mappings.

Reads from: mobile/src/ETA-Model/raw_data/ (arrivals CSVs)
             mobile/src/ETA-Model/stops.json (name -> stop_id mapping)
             data/processed/gtfs_routes.parquet OR gtfs_data/routes.txt
Writes to:  data/processed/arrivals.parquet
"""

import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_DATA_DIR = PROJECT_ROOT / "mobile" / "src" / "ETA-Model" / "raw_data"
STOPS_JSON = PROJECT_ROOT / "mobile" / "src" / "ETA-Model" / "stops.json"
GTFS_DIR = PROJECT_ROOT / "gtfs_data"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


def load_arrivals() -> pd.DataFrame:
    """Load and concatenate all arrivals CSVs."""
    csv_files = sorted(RAW_DATA_DIR.glob("Arrivals*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No arrivals CSVs found in {RAW_DATA_DIR}")

    dfs = []
    for f in csv_files:
        df = pd.read_csv(f, skiprows=1)
        print(f"  Loaded {f.name}: {len(df):,} rows")
        dfs.append(df)

    combined = pd.concat(dfs, ignore_index=True)
    print(f"  Combined: {len(combined):,} rows")
    return combined


def build_stop_name_to_id() -> dict:
    """Build station name -> numeric stop_id mapping from stops.json."""
    with open(STOPS_JSON) as f:
        stops = json.load(f)
    return {stop["name"].strip(): int(stop["id"]) for stop in stops}


def load_route_mapping() -> dict:
    """Load route_long_name -> route_id_num mapping.

    Prefers gtfs_routes.parquet if available, falls back to routes.txt.
    """
    parquet_path = OUTPUT_DIR / "gtfs_routes.parquet"
    if parquet_path.exists():
        routes = pd.read_parquet(parquet_path)
    else:
        print("  [Fallback] Reading routes.txt directly")
        routes = pd.read_csv(GTFS_DIR / "routes.txt")
        routes["route_id_num"] = (
            routes["route_id"]
            .astype(str)
            .str.split("_")
            .str[0]
            .replace("", pd.NA)
            .astype("Int64")
        )

    return dict(zip(
        routes["route_long_name"].str.strip(),
        routes["route_id_num"],
    ))


def parse_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """Parse DATE + ARRIVAL/DEPARTURE into timezone-aware timestamps."""
    # Parse date -- mixed formats across files (m/d/Y and Y-m-d)
    dates = pd.to_datetime(df["DATE"], format="mixed", dayfirst=False)

    for time_col, ts_col in [("ARRIVAL", "arrival_timestamp"), ("DEPARTURE", "departure_timestamp")]:
        # Parse time strings like "7:30:45" or "0:05:12"
        parts = df[time_col].str.split(":", expand=True).astype(int)
        hours = parts[0]
        minutes = parts[1]
        seconds = parts[2]
        td = pd.to_timedelta(hours, unit="h") + pd.to_timedelta(minutes, unit="m") + pd.to_timedelta(seconds, unit="s")
        ts = dates + td
        # Localize to US Central then convert to UTC
        ts = ts.dt.tz_localize("US/Central", ambiguous="NaT", nonexistent="shift_forward")
        ts = ts.dt.tz_convert("UTC")
        df[ts_col] = ts

    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("Arrivals Parser")
    print("=" * 60)

    # 1. Load raw data
    print("\n[1] Loading arrivals CSVs...")
    df = load_arrivals()
    raw_count = len(df)

    # 2. Filter out NIS and jAUnt
    print("\n[2] Filtering...")
    nis_count = (df["Number"] == "NIS").sum()
    jaunt_mask = df["Vehicle ID"].str.contains("jAUnt", case=False, na=False)
    jaunt_count = jaunt_mask.sum()
    df = df[df["Number"] != "NIS"]
    df = df[~df["Vehicle ID"].str.contains("jAUnt", case=False, na=False)]
    print(f"  Removed {nis_count:,} NIS rows, {jaunt_count:,} jAUnt rows")
    print(f"  Remaining: {len(df):,} rows")

    # 3. Map station names to GTFS stop IDs
    print("\n[3] Mapping station names to stop IDs...")
    name_to_id = build_stop_name_to_id()
    df["stop_id"] = df["Station"].str.strip().map(name_to_id)
    unmatched_stations = df[df["stop_id"].isna()]["Station"].str.strip().unique()
    unmatched_station_count = df["stop_id"].isna().sum()
    print(f"  Matched: {df['stop_id'].notna().sum():,} / {len(df):,}")
    print(f"  Unmatched stations ({len(unmatched_stations)}): {unmatched_stations.tolist()}")
    print(f"  Unmatched rows: {unmatched_station_count:,}")

    # Drop unmatched
    df = df[df["stop_id"].notna()]
    df["stop_id"] = df["stop_id"].astype(int)

    # 4. Map route names to numeric route IDs
    print("\n[4] Mapping route names to route IDs...")
    route_map = load_route_mapping()
    df["route_id"] = df["Route"].str.strip().map(route_map)
    unmatched_routes = df[df["route_id"].isna()]["Route"].str.strip().unique()
    unmatched_route_count = df["route_id"].isna().sum()
    print(f"  Matched: {df['route_id'].notna().sum():,} / {len(df):,}")
    if len(unmatched_routes) > 0:
        print(f"  Unmatched routes ({len(unmatched_routes)}): {unmatched_routes.tolist()}")
        print(f"  Unmatched route rows: {unmatched_route_count:,}")

    # Drop unmatched routes
    df = df[df["route_id"].notna()]
    df["route_id"] = df["route_id"].astype(int)

    # 5. Parse timestamps
    print("\n[5] Parsing timestamps...")
    df = parse_timestamps(df)
    nat_count = df["arrival_timestamp"].isna().sum()
    if nat_count > 0:
        print(f"  WARNING: {nat_count} NaT timestamps (ambiguous DST)")
        df = df[df["arrival_timestamp"].notna()]

    # 6. Rename columns to snake_case
    print("\n[6] Renaming columns...")
    df = df.rename(columns={
        "DATE": "date",
        "Vehicle ID": "vehicle_id",
        "Number": "trip_number",
        "Route": "route_name",
        "Station": "station_name",
        "ARRIVAL": "arrival_time_str",
        "DEPARTURE": "departure_time_str",
        "Dwell (sec)": "dwell_seconds",
        "APC Boardings": "apc_boardings",
        "APC Alightings": "apc_alightings",
        "EPC Boardings": "epc_boardings",
        "EPC Alightings": "epc_alightings",
    })

    # 7. Write parquet
    out_path = OUTPUT_DIR / "arrivals.parquet"
    df.to_parquet(out_path, index=False)

    # 8. Validation summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    print(f"  Raw rows: {raw_count:,}")
    print(f"  After filtering: {len(df):,}")
    print(f"  Unique stops: {df['stop_id'].nunique()}")
    print(f"  Unique routes: {df['route_id'].nunique()}")
    print(f"  Unique vehicles: {df['vehicle_id'].nunique()}")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")

    days = df["date"].nunique()
    print(f"  Days: {days}")
    print(f"  Avg rows/day: {len(df) / max(days, 1):,.0f}")
    print(f"  Output: {out_path} ({out_path.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
