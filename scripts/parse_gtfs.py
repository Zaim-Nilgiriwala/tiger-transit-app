"""
Parse GTFS static files into parquet format for downstream processing.

Reads from: gtfs_data/
Writes to:  data/processed/gtfs_{routes,stops,stop_times,shapes}.parquet
"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GTFS_DIR = PROJECT_ROOT / "gtfs_data"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"


def parse_routes() -> pd.DataFrame:
    """Parse routes.txt, adding numeric route_id_num from compound IDs."""
    df = pd.read_csv(GTFS_DIR / "routes.txt")

    # Extract first numeric part from compound IDs like "215_202_201_156" -> 215
    df["route_id_num"] = (
        df["route_id"]
        .astype(str)
        .str.split("_")
        .str[0]
        .replace("", pd.NA)  # handle trailing underscore like "227_"
        .astype("Int64")
    )

    keep_cols = ["route_id", "route_id_num", "route_short_name", "route_long_name"]
    df = df[keep_cols]
    df.to_parquet(OUTPUT_DIR / "gtfs_routes.parquet", index=False)

    compound = df[df["route_id"].astype(str).str.contains("_")]
    print(f"[Routes] {len(df)} routes total, {len(compound)} with compound IDs")
    if len(compound) > 0:
        print(f"  Compound ID mappings:")
        for _, row in compound.iterrows():
            print(f"    {row['route_id']} -> {row['route_id_num']}  ({row['route_long_name']})")
    print(f"  Sample: {df[['route_id', 'route_id_num', 'route_short_name']].head(5).to_string(index=False)}")
    return df


def parse_stops() -> pd.DataFrame:
    """Parse stops.txt with numeric stop_id."""
    df = pd.read_csv(GTFS_DIR / "stops.txt")
    keep_cols = ["stop_id", "stop_name", "stop_lat", "stop_lon"]
    df = df[keep_cols]
    df["stop_id"] = df["stop_id"].astype(int)
    df.to_parquet(OUTPUT_DIR / "gtfs_stops.parquet", index=False)

    print(f"\n[Stops] {len(df)} stops")
    print(f"  Sample names: {df['stop_name'].head(5).tolist()}")
    return df


def parse_stop_times() -> pd.DataFrame:
    """Parse stop_times.txt joined with trips.txt for route_id and shape_id."""
    st = pd.read_csv(GTFS_DIR / "stop_times.txt")
    trips = pd.read_csv(GTFS_DIR / "trips.txt")

    keep_st = [
        "trip_id", "arrival_time", "departure_time",
        "stop_id", "stop_sequence", "shape_dist_traveled",
    ]
    st = st[keep_st]

    # Join trips to get route_id and shape_id
    trips_subset = trips[["trip_id", "route_id", "shape_id"]].drop_duplicates()
    st = st.merge(trips_subset, on="trip_id", how="left")

    st.to_parquet(OUTPUT_DIR / "gtfs_stop_times.parquet", index=False)

    null_sdt = st["shape_dist_traveled"].isna().sum()
    print(f"\n[Stop Times] {len(st):,} rows")
    print(f"  shape_dist_traveled nulls: {null_sdt}")
    print(f"  Unique trips: {st['trip_id'].nunique()}")
    print(f"  Unique routes: {st['route_id'].nunique()}")
    return st


def parse_shapes() -> pd.DataFrame:
    """Parse shapes.txt."""
    df = pd.read_csv(GTFS_DIR / "shapes.txt")
    keep_cols = [
        "shape_id", "shape_pt_lat", "shape_pt_lon",
        "shape_pt_sequence", "shape_dist_traveled",
    ]
    df = df[keep_cols]
    df.to_parquet(OUTPUT_DIR / "gtfs_shapes.parquet", index=False)

    print(f"\n[Shapes] {df['shape_id'].nunique()} shapes, {len(df):,} total points")
    print(f"  Sample distances (first shape): {df.groupby('shape_id')['shape_dist_traveled'].max().head(3).to_dict()}")
    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print("=" * 60)
    print("GTFS Static File Parser")
    print("=" * 60)

    routes = parse_routes()
    stops = parse_stops()
    stop_times = parse_stop_times()
    shapes = parse_shapes()

    # Validation summary
    print("\n" + "=" * 60)
    print("Validation Summary")
    print("=" * 60)
    files = ["gtfs_routes", "gtfs_stops", "gtfs_stop_times", "gtfs_shapes"]
    for f in files:
        p = OUTPUT_DIR / f"{f}.parquet"
        size_kb = p.stat().st_size / 1024
        print(f"  {f}.parquet: {size_kb:.1f} KB")

    sdt_stop_times = stop_times["shape_dist_traveled"].isna().sum()
    sdt_shapes = shapes["shape_dist_traveled"].isna().sum()
    print(f"\n  Distance computation readiness:")
    print(f"    stop_times shape_dist_traveled nulls: {sdt_stop_times}")
    print(f"    shapes shape_dist_traveled nulls: {sdt_shapes}")
    if sdt_stop_times == 0 and sdt_shapes == 0:
        print(f"    STATUS: READY -- distance between any two stops computable")
    else:
        print(f"    STATUS: WARNING -- some null distances detected")


if __name__ == "__main__":
    main()
