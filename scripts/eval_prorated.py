"""Evaluate prorated segment-sum baseline.

Prorate the current segment (using distance fraction remaining),
then sum full historical medians for future segments.

Usage:
    python scripts/eval_prorated.py
"""

import numpy as np
import pandas as pd

DATA_DIR = "data/processed"
MIN_OBS = 5


def main():
    # ---- Load data ----
    print("Loading data...")
    train = pd.read_parquet(f"{DATA_DIR}/train.parquet")
    test = pd.read_parquet(f"{DATA_DIR}/test.parquet")
    ss = pd.read_parquet(f"{DATA_DIR}/stop_sequences.parquet")
    ss["route_id"] = ss["route_id"].astype("int64")

    # ---- Step 1: Per-segment median travel times from stop transitions ----
    print("Computing segment medians from stop transitions...")
    pings = train.drop_duplicates(subset=["vehicle_id", "timestamp"]).copy()
    pings = pings.sort_values(["vehicle_id", "route_id", "timestamp"]).reset_index(drop=True)

    grp = pings.groupby(["vehicle_id", "route_id"])
    prev_stop = grp["last_stop_id"].shift(1)
    stop_changed = (pings["last_stop_id"] != prev_stop) & prev_stop.notna()

    transitions = pings[stop_changed].copy()
    transitions = transitions.sort_values(["vehicle_id", "route_id", "timestamp"])
    trans_grp = transitions.groupby(["vehicle_id", "route_id"])
    transitions["prev_ts"] = trans_grp["timestamp"].shift(1)
    transitions["segment_s"] = (
        transitions["timestamp"] - transitions["prev_ts"]
    ).dt.total_seconds()

    transitions = transitions[
        transitions["prev_ts"].notna()
        & (transitions["segment_s"] > 0)
        & (transitions["segment_s"] <= 300)
    ].copy()
    transitions["day_type"] = transitions["is_weekday"].astype(int)
    print(f"  Valid transitions: {len(transitions):,}")

    # (route_id, arriving_stop_id, day_type) -> median
    seg_dt = (
        transitions.groupby(["route_id", "last_stop_id", "day_type"])["segment_s"]
        .agg(["median", "count"])
        .reset_index()
    )
    seg_dt = seg_dt[seg_dt["count"] >= MIN_OBS].rename(columns={"median": "seg_med"})
    seg_dt.drop(columns="count", inplace=True)
    print(f"  (route, stop, day_type) combos: {len(seg_dt):,}")

    # Fallback: (route_id, arriving_stop_id)
    seg_all = (
        transitions.groupby(["route_id", "last_stop_id"])["segment_s"]
        .agg(["median", "count"])
        .reset_index()
    )
    seg_all = seg_all[seg_all["count"] >= MIN_OBS].rename(columns={"median": "seg_med_fb"})
    seg_all.drop(columns="count", inplace=True)
    print(f"  (route, stop) combos (fallback): {len(seg_all):,}")

    del pings, transitions

    # ---- Step 2: Route sequences + cumulative segment-time tables ----
    print("\nBuilding cumulative segment tables...")

    route_seqs = {}
    for rid, grp in ss.sort_values(["route_id", "stop_sequence"]).groupby("route_id"):
        route_seqs[rid] = grp[
            ["stop_id", "stop_sequence", "shape_dist_traveled", "stop_progress", "max_shape_dist"]
        ].reset_index(drop=True)

    # Fast dicts
    seg_med_dict = {}
    for _, row in seg_dt.iterrows():
        seg_med_dict[(int(row["route_id"]), int(row["last_stop_id"]), int(row["day_type"]))] = row["seg_med"]
    seg_fb_dict = {}
    for _, row in seg_all.iterrows():
        seg_fb_dict[(int(row["route_id"]), int(row["last_stop_id"]))] = row["seg_med_fb"]

    # Per-route average segment time for hard fallback
    route_avg_seg = {}
    for rid in route_seqs:
        vals = [v for (r, s), v in seg_fb_dict.items() if r == rid]
        route_avg_seg[rid] = np.mean(vals) if vals else 60.0

    # Cumulative tables: (route_id, day_type) -> np.array
    cumsum_tables = {}
    for rid, seq in route_seqs.items():
        n_stops = len(seq)
        for dt in [0, 1]:
            cs = np.zeros(n_stops)
            for i in range(1, n_stops):
                arriving_stop = int(seq.iloc[i]["stop_id"])
                seg_time = seg_med_dict.get((rid, arriving_stop, dt))
                if seg_time is None:
                    seg_time = seg_fb_dict.get((rid, arriving_stop))
                if seg_time is None:
                    seg_time = route_avg_seg[rid]
                cs[i] = cs[i - 1] + seg_time
            cumsum_tables[(rid, dt)] = cs

    print(f"  Cumsum tables: {len(cumsum_tables)} (route, day_type) combos")

    # ---- Step 3: Compute prorated baseline for test set ----
    print("\nComputing prorated baseline for test set...")
    test["day_type"] = test["is_weekday"].astype(int)
    n = len(test)
    baseline_prorated = np.full(n, np.nan)

    for rid, seq in route_seqs.items():
        rmask = (test["route_id"] == rid).values
        if not rmask.any():
            continue

        rdf = test.loc[rmask]
        stop_ids = seq["stop_id"].values
        stop_dists = seq["shape_dist_traveled"].values
        max_sd = seq.iloc[0]["max_shape_dist"]
        n_stops = len(stop_ids)
        sid_to_idx = {int(sid): i for i, sid in enumerate(stop_ids)}

        last_stop_ids = rdf["last_stop_id"].values
        target_stop_ids = rdf["target_stop_id"].values
        progresses = rdf["progress"].values
        day_types = rdf["day_type"].values

        results = np.full(len(rdf), np.nan)

        for j in range(len(rdf)):
            lsid = int(last_stop_ids[j])
            tsid = int(target_stop_ids[j])
            dt = int(day_types[j])
            prog = progresses[j]

            ls_idx = sid_to_idx.get(lsid)
            ts_idx = sid_to_idx.get(tsid)
            if ls_idx is None or ts_idx is None:
                continue
            if ts_idx < ls_idx:
                continue  # wrap-around

            cs = cumsum_tables.get((rid, dt))
            if cs is None:
                continue

            # Future segments: last_stop -> target
            future_time = cs[ts_idx] - cs[ls_idx]

            # Current segment proration
            if ls_idx > 0:
                prev_dist = stop_dists[ls_idx - 1]
                ls_dist = stop_dists[ls_idx]
                bus_dist = prog * max_sd
                seg_length = ls_dist - prev_dist

                if seg_length > 0:
                    remaining = max(0.0, ls_dist - bus_dist)
                    fraction = min(1.0, remaining / seg_length)
                else:
                    fraction = 0.5

                seg_time = seg_med_dict.get((rid, lsid, dt))
                if seg_time is None:
                    seg_time = seg_fb_dict.get((rid, lsid))
                if seg_time is None:
                    seg_time = route_avg_seg[rid]

                prorated = fraction * seg_time
            else:
                prorated = 0.0

            results[j] = prorated + future_time

        baseline_prorated[rmask] = results

    valid = ~np.isnan(baseline_prorated)
    print(f"  Valid: {valid.sum():,} / {n:,} ({valid.sum()/n*100:.1f}%)")

    # ---- Step 4: Evaluate ----
    actual = test["time_to_arrival_seconds"].values
    mae = np.nanmean(np.abs(actual - baseline_prorated))
    seg_mae = np.nanmean(np.abs(actual - test["baseline_seg_sum"].values))
    blend_mae = np.nanmean(np.abs(actual - test["baseline_eta"].values))
    s2s_mae = np.nanmean(np.abs(actual - test["baseline_s2s"].values))

    print(f"\n{'='*60}")
    print(f"Prorated segment-sum baseline MAE: {mae:.1f}s")
    print(f"  vs SegSum (elapsed+segment):     {seg_mae:.1f}s")
    print(f"  vs Blended (70/30):              {blend_mae:.1f}s")
    print(f"  vs S2S:                          {s2s_mae:.1f}s")
    print(f"{'='*60}")

    print(f"\n{'Bucket':>8} | {'N':>8} | {'Prorated':>8} | {'SegSum':>7} | {'Blend':>7} | {'S2S':>7}")
    print(f"{'-'*8}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}-+-{'-'*7}-+-{'-'*7}")
    for lo, hi, label in [
        (0, 60, "0-1min"), (60, 120, "1-2min"), (120, 300, "2-5min"),
        (300, 600, "5-10min"), (600, 1200, "10-20min"), (1200, 9999, "20min+"),
    ]:
        m = (actual >= lo) & (actual < hi)
        nn = m.sum()
        pm = np.nanmean(np.abs(actual[m] - baseline_prorated[m]))
        sm = np.nanmean(np.abs(actual[m] - test.loc[m, "baseline_seg_sum"].values))
        bm = np.nanmean(np.abs(actual[m] - test.loc[m, "baseline_eta"].values))
        s2 = np.nanmean(np.abs(actual[m] - test.loc[m, "baseline_s2s"].values))
        print(f"{label:>8} | {nn:8,} | {pm:8.1f} | {sm:7.1f} | {bm:7.1f} | {s2:7.1f}")

    # Bias
    print(f"\nBias (mean error = predicted - actual):")
    print(f"  Overall:         {np.nanmean(baseline_prorated - actual):+.1f}s")
    short = actual < 60
    med = (actual >= 60) & (actual < 300)
    long = actual >= 300
    print(f"  Short (<60s):    {np.nanmean(baseline_prorated[short] - actual[short]):+.1f}s")
    print(f"  Medium (60-300s):{np.nanmean(baseline_prorated[med] - actual[med]):+.1f}s")
    print(f"  Long (300s+):    {np.nanmean(baseline_prorated[long] - actual[long]):+.1f}s")

    # Per stops_away
    print(f"\n{'stops':>6} | {'N':>8} | {'Prorated':>8} | {'SegSum':>7}")
    print(f"{'-'*6}-+-{'-'*8}-+-{'-'*8}-+-{'-'*7}")
    for sa in sorted(test["stops_away"].unique()):
        m = test["stops_away"] == sa
        nn = m.sum()
        if nn < 50:
            continue
        pm = np.nanmean(np.abs(actual[m] - baseline_prorated[m]))
        sm = np.nanmean(np.abs(actual[m] - test.loc[m, "baseline_seg_sum"].values))
        print(f"{sa:6d} | {nn:8,} | {pm:8.1f} | {sm:7.1f}")


if __name__ == "__main__":
    main()
