"""
Build per-route stop sequences with normalized progress fractions.

Reads:  data/processed/gtfs_stop_times.parquet, data/processed/gtfs_shapes.parquet
Writes: data/processed/stop_sequences.parquet

For each route, selects the canonical shape (most trips), orders stops by
stop_sequence, and computes stop_progress = shape_dist_traveled / max_shape_dist.
Output route_id is numeric int to match telemetry.parquet.
"""

import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_PATH = OUTPUT_DIR / "stop_sequences.parquet"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Build Stop Sequences")
    print("=" * 60)

    # ── Load data ──────────────────────────────────────────────
    st = pd.read_parquet(OUTPUT_DIR / "gtfs_stop_times.parquet")
    shapes = pd.read_parquet(OUTPUT_DIR / "gtfs_shapes.parquet")

    print(f"Loaded stop_times: {len(st):,} rows, {st['route_id'].nunique()} routes")
    print(f"Loaded shapes: {shapes['shape_id'].nunique()} shapes")

    # ── Extract numeric route_id ───────────────────────────────
    st["route_id_num"] = (
        st["route_id"]
        .astype(str)
        .str.split("_")
        .str[0]
        .replace("", pd.NA)
        .astype("Int64")
    )

    # ── Max shape_dist_traveled per shape from shapes table ────
    max_dist = (
        shapes.groupby("shape_id")["shape_dist_traveled"]
        .max()
        .rename("max_shape_dist")
    )

    # ── Canonical shape: shape_id with most trips per route ────
    # Count distinct trips per (route_id, shape_id)
    trip_counts = (
        st.groupby(["route_id", "shape_id"])["trip_id"]
        .nunique()
        .reset_index(name="trip_count")
    )
    # Pick shape with highest trip count per route
    canonical_idx = trip_counts.groupby("route_id")["trip_count"].idxmax()
    canonical = trip_counts.loc[canonical_idx, ["route_id", "shape_id"]].copy()
    print(f"\nCanonical shapes selected for {len(canonical)} routes")

    # ── Filter stop_times to canonical shapes only ─────────────
    st_canon = st.merge(canonical, on=["route_id", "shape_id"], how="inner")

    # ── Get unique stops per (route, shape) ordered by stop_sequence ─
    # For each (route_id, shape_id, stop_id), take the row with the
    # lowest stop_sequence (first occurrence), then deduplicate by stop_id.
    st_canon = st_canon.sort_values(["route_id", "stop_sequence"])

    # Deduplicate: keep first occurrence of each stop_id per route
    st_dedup = st_canon.drop_duplicates(
        subset=["route_id", "stop_id"], keep="first"
    )

    # ── Build output ───────────────────────────────────────────
    result = (
        st_dedup[["route_id", "route_id_num", "stop_id", "stop_sequence",
                   "shape_dist_traveled", "shape_id"]]
        .copy()
    )

    # Join max_shape_dist from shapes table
    result = result.merge(
        max_dist.reset_index(), on="shape_id", how="left"
    )

    # Compute stop_progress
    result["stop_progress"] = result["shape_dist_traveled"] / result["max_shape_dist"]

    # Use numeric route_id as the output route_id
    result["route_id"] = result["route_id_num"]
    result = result.drop(columns=["route_id_num", "shape_id"])

    # Sort for clean output
    result = result.sort_values(["route_id", "stop_sequence"]).reset_index(drop=True)

    # Final columns
    result = result[["route_id", "stop_id", "stop_sequence",
                      "shape_dist_traveled", "max_shape_dist", "stop_progress"]]

    # ── Validation ─────────────────────────────────────────────
    n_routes = result["route_id"].nunique()
    stops_per_route = result.groupby("route_id")["stop_id"].count()

    print(f"\n--- Validation Summary ---")
    print(f"Routes: {n_routes}")
    print(f"Stops per route: min={stops_per_route.min()}, "
          f"max={stops_per_route.max()}, mean={stops_per_route.mean():.1f}")
    print(f"Total rows: {len(result):,}")

    # Per-route stop_progress range
    prog_stats = result.groupby("route_id")["stop_progress"].agg(["min", "max"])
    print(f"\nStop progress range per route:")
    for route_id, row in prog_stats.iterrows():
        n_stops = stops_per_route.loc[route_id]
        print(f"  Route {route_id:>3d}: {row['min']:.4f} - {row['max']:.4f}  "
              f"({n_stops} stops)")

    # Assertions
    assert result["stop_progress"].between(0.0, 1.0).all(), \
        "stop_progress out of [0, 1] range!"
    assert result["route_id"].notna().all(), "Null route_id found!"
    assert result["stop_id"].notna().all(), "Null stop_id found!"
    assert result["max_shape_dist"].notna().all(), "Null max_shape_dist found!"
    assert (result["max_shape_dist"] > 0).all(), "Zero max_shape_dist found!"
    print("\nAll assertions passed.")

    # ── Write output ───────────────────────────────────────────
    result.to_parquet(OUTPUT_PATH, index=False)
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nWritten to {OUTPUT_PATH}")
    print(f"File size: {size_kb:.1f} KB")
    print("Done.")


if __name__ == "__main__":
    main()
