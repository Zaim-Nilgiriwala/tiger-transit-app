"""
Investigate the stop transition mismatches to understand why some are extreme.

Hypothesis: When a bus visits the same stop multiple times (loop routes),
we might be matching to the wrong arrival event.
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import sys
sys.path.insert(0, str(Path(__file__).parent))
from data_prep import StopNameMapper, ArrivalsData


def load_telemetry_file(path: Path) -> pd.DataFrame:
    records = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except:
                    continue
    return pd.DataFrame(records)


def investigate_mismatches(
    telemetry_path: str,
    arrivals_csv: str,
    stops_json: str
):
    print("=" * 80)
    print("INVESTIGATING STOP TRANSITION MISMATCHES")
    print("=" * 80)

    stop_mapper = StopNameMapper(stops_json)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = load_telemetry_file(Path(telemetry_path))

    telemetry = telemetry[telemetry['patternId'] != 9998]
    telemetry = telemetry[telemetry['vid'].str.startswith('21-')]

    # Find a specific mismatch case
    print("\n--- Case Study: Vehicle 21-119 at Charter Stop ---")

    vid = '21-119'
    vid_data = telemetry[telemetry['vid'] == vid].sort_values('t')

    # Find when nextStopId changes from Charter Stop (need to find its ID)
    charter_id = stop_mapper.get_stop_id('Charter Stop')
    print(f"Charter Stop ID: {charter_id}")

    # Find all arrivals for this vehicle at this stop on this day
    print("\nAll arrivals for 21-119 at Charter Stop on Nov 7:")
    date_key = '2025-11-07'
    if vid in arrivals.arrivals_index and date_key in arrivals.arrivals_index[vid]:
        for arr in arrivals.arrivals_index[vid][date_key]:
            if arr['stop_id'] == str(charter_id):
                arr_time = datetime.utcfromtimestamp(arr['arrival_ts']/1000)
                arr_local = arr_time - timedelta(hours=6)
                print(f"  Arrival at {arr_local.strftime('%H:%M:%S')} local (ts: {arr['arrival_ts']})")

    # Find telemetry transitions for this stop
    print("\nTelemetry transitions involving Charter Stop:")
    prev_stop = None
    for idx, row in vid_data.iterrows():
        next_stop = str(int(row['nextStopId'])) if row['nextStopId'] > 0 else None
        ts = int(row['t'])
        dt_local = datetime.utcfromtimestamp(ts/1000) - timedelta(hours=6)

        if prev_stop != next_stop:
            if prev_stop == str(charter_id):
                print(f"  Left Charter Stop at {dt_local.strftime('%H:%M:%S')} (ts: {ts})")
                print(f"    -> Now heading to stop {next_stop} ({stop_mapper.id_to_name.get(next_stop, '?')})")

                # What arrival does get_arrival_info find?
                arr_info = arrivals.get_arrival_info(vid, ts - 60000, str(charter_id))  # Look from 1 min before
                if arr_info:
                    arr_time = datetime.utcfromtimestamp(arr_info['arrival_ts']/1000) - timedelta(hours=6)
                    print(f"    Matched to arrival at {arr_time.strftime('%H:%M:%S')}")
                    diff = (arr_info['arrival_ts'] - ts) / 1000
                    print(f"    Difference: {diff:.0f}s ({diff/60:.1f} min)")

            if next_stop == str(charter_id):
                print(f"  Approaching Charter Stop at {dt_local.strftime('%H:%M:%S')} (ts: {ts})")

        prev_stop = next_stop

    # Analyze the general pattern
    print("\n" + "=" * 80)
    print("ANALYZING ARRIVAL MATCHING LOGIC")
    print("=" * 80)

    print("""
The current get_arrival_info() finds the FIRST arrival at a stop AFTER the
given timestamp. This is problematic because:

1. If bus visits stop A at 7:00, leaves at 7:02
2. Telemetry at 7:01 shows nextStopId = stop_A
3. At 7:02, nextStopId changes to stop_B
4. But if bus visits stop_A again at 8:00...
5. get_arrival_info(7:01, stop_A) might find the 8:00 arrival!

Solution: We need to find the NEAREST arrival, not just the first one after.
Or better: find the arrival that happens BEFORE the stop transition.
""")

    # Test improved matching
    print("\n--- IMPROVED MATCHING APPROACH ---")
    print("For training data, we should:")
    print("1. Track when nextStopId changes FROM a stop (transition point)")
    print("2. Find arrivals that happened JUST BEFORE that transition")
    print("3. Use a narrow time window (e.g., within 5 minutes before transition)")

    # Demonstrate improved matching
    print("\nDemonstrating improved matching for 21-119:")

    prev_stop = None
    prev_ts = None

    for idx, row in vid_data.iterrows():
        next_stop = str(int(row['nextStopId'])) if row['nextStopId'] > 0 else None
        ts = int(row['t'])

        if prev_stop is not None and prev_stop != next_stop:
            # Transition happened at ts, bus was at prev_stop
            # Find arrival at prev_stop that happened between prev_ts and ts

            stop_name = stop_mapper.id_to_name.get(prev_stop, prev_stop)
            dt_local = datetime.utcfromtimestamp(ts/1000) - timedelta(hours=6)

            # Look for arrivals in a narrow window BEFORE the transition
            # The arrival should have happened BEFORE or AT the transition
            date_key = datetime.utcfromtimestamp(ts/1000).strftime('%Y-%m-%d')

            if vid in arrivals.arrivals_index and date_key in arrivals.arrivals_index[vid]:
                matching_arrivals = []
                for arr in arrivals.arrivals_index[vid][date_key]:
                    if arr['stop_id'] == prev_stop:
                        # Arrival should be BEFORE or shortly after transition
                        # (within 2 minutes, accounting for door open delay)
                        arr_ts = arr['arrival_ts']
                        if prev_ts - 60000 < arr_ts < ts + 120000:  # -1min to +2min of transition
                            matching_arrivals.append(arr)

                if matching_arrivals:
                    # Use the closest one to the transition
                    best_arr = min(matching_arrivals, key=lambda a: abs(a['arrival_ts'] - ts))
                    arr_local = datetime.utcfromtimestamp(best_arr['arrival_ts']/1000) - timedelta(hours=6)
                    diff = (best_arr['arrival_ts'] - ts) / 1000

                    if abs(diff) < 180:  # Only show if within 3 minutes
                        print(f"  {stop_name}: transition at {dt_local.strftime('%H:%M:%S')}, "
                              f"arrival at {arr_local.strftime('%H:%M:%S')}, diff={diff:+.0f}s")

        prev_stop = next_stop
        prev_ts = ts


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--telemetry', type=str, required=True)
    parser.add_argument('--arrivals', type=str, required=True)
    parser.add_argument('--stops', type=str, required=True)
    args = parser.parse_args()

    investigate_mismatches(args.telemetry, args.arrivals, args.stops)


if __name__ == '__main__':
    main()
