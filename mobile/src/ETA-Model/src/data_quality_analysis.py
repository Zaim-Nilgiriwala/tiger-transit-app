"""
Data Quality Analysis for ETA Training Data

Identifies problematic patterns that would corrupt training data:
1. Stop transition mismatch - telemetry nextStopId changes before/after actual arrival
2. Negative ETAs - scheduled time already passed
3. Large ETA jumps - system switched to next stop or schedule updated
4. Stale data - bus stopped for extended period
5. Impossible ETAs - ETA longer than reasonable for distance
6. Wrong stop pairing - telemetry shows different stop than arrivals matched
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
    """Load a single JSONL telemetry file."""
    records = []
    with open(path, 'r') as f:
        for line in f:
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return pd.DataFrame(records)


def get_system_eta_seconds(row, dt_local):
    """Convert etaSeconds (minutes since midnight) to seconds until arrival."""
    eta_minutes_since_midnight = row.get('etaSeconds', 0)
    if eta_minutes_since_midnight <= 0:
        return None
    current_minutes = dt_local.hour * 60 + dt_local.minute + dt_local.second / 60.0
    eta_minutes = eta_minutes_since_midnight - current_minutes
    return eta_minutes * 60


def analyze_data_quality(
    telemetry_path: str,
    arrivals_csv: str,
    stops_json: str
):
    """Analyze data quality issues that would corrupt training."""

    print("=" * 80)
    print("DATA QUALITY ANALYSIS FOR ETA TRAINING")
    print("=" * 80)

    # Load data
    print("\nLoading data...")
    stop_mapper = StopNameMapper(stops_json)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = load_telemetry_file(Path(telemetry_path))

    # Filter
    telemetry = telemetry[telemetry['patternId'] != 9998]
    telemetry = telemetry[telemetry['routeId'].notna()]
    telemetry = telemetry[telemetry['routeId'] != 777]
    telemetry = telemetry[telemetry['nextStopId'] > 0]
    telemetry = telemetry[telemetry['vid'].str.startswith('21-')]

    print(f"Analyzing {len(telemetry)} telemetry records...")

    # Issue counters
    issues = {
        'negative_eta': 0,
        'large_eta_jump': 0,
        'stop_transition_mismatch': 0,
        'stale_position': 0,
        'eta_after_arrival': 0,
        'impossible_eta': 0,
        'total_records': 0,
        'valid_records': 0
    }

    # Detailed examples of each issue
    issue_examples = defaultdict(list)

    vehicles = telemetry['vid'].unique()

    for vid in vehicles[:20]:  # Check first 20 vehicles
        vid_data = telemetry[telemetry['vid'] == vid].sort_values('t')

        prev_row = None
        prev_eta_field = None
        prev_next_stop = None

        for idx, row in vid_data.iterrows():
            issues['total_records'] += 1

            ts = int(row['t'])
            dt_utc = datetime.utcfromtimestamp(ts / 1000)
            dt_local = dt_utc - timedelta(hours=6)

            next_stop_id = str(int(row['nextStopId']))
            eta_field = row.get('etaSeconds', 0)
            system_eta = get_system_eta_seconds(row, dt_local)
            speed = row.get('speed', 0)

            issue_found = False

            # Issue 1: Negative ETA (scheduled time already passed)
            if system_eta is not None and system_eta < 0:
                issues['negative_eta'] += 1
                issue_found = True
                if len(issue_examples['negative_eta']) < 3:
                    issue_examples['negative_eta'].append({
                        'time': dt_local.strftime('%H:%M:%S'),
                        'vehicle': vid,
                        'stop': next_stop_id,
                        'eta_field': eta_field,
                        'computed_eta': f"{system_eta:.0f}s"
                    })

            # Issue 2: Large ETA jump (>2 min change between consecutive records)
            if prev_eta_field is not None and prev_next_stop == next_stop_id:
                eta_change = abs(eta_field - prev_eta_field) * 60  # Convert to seconds
                time_elapsed = (ts - int(prev_row['t'])) / 1000

                # If ETA changed by more than time elapsed + 60s, something jumped
                if eta_change > time_elapsed + 120:  # 2 minute tolerance
                    issues['large_eta_jump'] += 1
                    issue_found = True
                    if len(issue_examples['large_eta_jump']) < 3:
                        issue_examples['large_eta_jump'].append({
                            'time': dt_local.strftime('%H:%M:%S'),
                            'vehicle': vid,
                            'stop': next_stop_id,
                            'prev_eta': prev_eta_field,
                            'new_eta': eta_field,
                            'change_sec': eta_change,
                            'time_elapsed': time_elapsed
                        })

            # Issue 3: Stop transition - check if we're getting ETA for wrong stop
            if prev_next_stop is not None and prev_next_stop != next_stop_id:
                # Stop changed - this is a transition point
                # Check if the arrival for the PREVIOUS stop happened
                arrival_info = arrivals.get_arrival_info(vid, int(prev_row['t']), prev_next_stop)

                if arrival_info:
                    prev_ts = int(prev_row['t'])
                    arrival_ts = arrival_info['arrival_ts']

                    # If telemetry stop changed BEFORE actual arrival, we have a mismatch
                    if ts < arrival_ts:
                        issues['stop_transition_mismatch'] += 1
                        issue_found = True
                        if len(issue_examples['stop_transition_mismatch']) < 3:
                            issue_examples['stop_transition_mismatch'].append({
                                'time': dt_local.strftime('%H:%M:%S'),
                                'vehicle': vid,
                                'prev_stop': prev_next_stop,
                                'new_stop': next_stop_id,
                                'transition_ts': ts,
                                'actual_arrival_ts': arrival_ts,
                                'gap_sec': (arrival_ts - ts) / 1000
                            })

            # Issue 4: Stale position (speed = 0 for extended period but ETA not updating)
            if speed == 0 and prev_row is not None:
                prev_speed = prev_row.get('speed', 0)
                if prev_speed == 0:
                    # Check if ETA is changing appropriately
                    time_elapsed = (ts - int(prev_row['t'])) / 1000
                    if time_elapsed > 30:  # More than 30 seconds stationary
                        issues['stale_position'] += 1
                        issue_found = True

            # Issue 5: ETA showing after bus already arrived at stop
            arrival_info = arrivals.get_arrival_info(vid, ts, next_stop_id)
            if arrival_info:
                actual_arrival_ts = arrival_info['arrival_ts']
                if ts > actual_arrival_ts:
                    # We're past the arrival time but still have this as next stop
                    issues['eta_after_arrival'] += 1
                    issue_found = True
                    if len(issue_examples['eta_after_arrival']) < 3:
                        issue_examples['eta_after_arrival'].append({
                            'time': dt_local.strftime('%H:%M:%S'),
                            'vehicle': vid,
                            'stop': next_stop_id,
                            'telemetry_ts': ts,
                            'arrival_ts': actual_arrival_ts,
                            'gap_sec': (ts - actual_arrival_ts) / 1000
                        })

            # Issue 6: Impossible ETA (>30 min for any stop, or ETA increasing over time)
            if system_eta is not None and system_eta > 30 * 60:
                issues['impossible_eta'] += 1
                issue_found = True

            if not issue_found:
                issues['valid_records'] += 1

            prev_row = row
            prev_eta_field = eta_field
            prev_next_stop = next_stop_id

    # Print results
    print("\n" + "=" * 80)
    print("ISSUE SUMMARY")
    print("=" * 80)

    total = issues['total_records']
    print(f"\nTotal records analyzed: {total}")
    print(f"Valid records: {issues['valid_records']} ({issues['valid_records']/total*100:.1f}%)")

    print("\n--- ISSUE BREAKDOWN ---")
    print(f"1. Negative ETA (past scheduled time):     {issues['negative_eta']:6d} ({issues['negative_eta']/total*100:.2f}%)")
    print(f"2. Large ETA jumps (schedule updates):    {issues['large_eta_jump']:6d} ({issues['large_eta_jump']/total*100:.2f}%)")
    print(f"3. Stop transition mismatch:              {issues['stop_transition_mismatch']:6d} ({issues['stop_transition_mismatch']/total*100:.2f}%)")
    print(f"4. Stale position (stopped, not updating):{issues['stale_position']:6d} ({issues['stale_position']/total*100:.2f}%)")
    print(f"5. ETA shown after actual arrival:        {issues['eta_after_arrival']:6d} ({issues['eta_after_arrival']/total*100:.2f}%)")
    print(f"6. Impossible ETA (>30 min):              {issues['impossible_eta']:6d} ({issues['impossible_eta']/total*100:.2f}%)")

    print("\n" + "=" * 80)
    print("EXAMPLE ISSUES")
    print("=" * 80)

    for issue_type, examples in issue_examples.items():
        if examples:
            print(f"\n--- {issue_type.upper().replace('_', ' ')} ---")
            for ex in examples:
                print(f"  {ex}")

    print("\n" + "=" * 80)
    print("RECOMMENDED FILTERS FOR TRAINING DATA")
    print("=" * 80)

    print("""
To create clean training data, apply these filters:

1. FILTER: Negative system ETA
   - Condition: (etaSeconds - current_minutes) * 60 < 0
   - Why: Bus is past scheduled time, ETA is meaningless

2. FILTER: Large ETA jumps between consecutive records
   - Condition: |eta_change| > time_elapsed + 120 seconds
   - Why: Schedule update or stop transition, not real ETA change

3. FILTER: Records after actual arrival at stop
   - Condition: telemetry_timestamp > actual_arrival_timestamp for that stop
   - Why: System is showing ETA for NEXT stop, not the one we matched

4. FILTER: Very large ETAs
   - Condition: computed_ETA > 20 minutes (1200 seconds)
   - Why: Likely unreliable for training, focus on near-term predictions

5. FILTER: Stop transition boundary records
   - Condition: Within 60 seconds of nextStopId change
   - Why: Uncertain which stop the ETA refers to

6. RECOMMENDED: Only use records where:
   - actual_ETA > 30 seconds (not too close to arrival)
   - actual_ETA < 900 seconds (within 15 minutes)
   - system_ETA > 0 (not past schedule)
   - speed > 0 OR stationary for < 60 seconds (active bus)
""")

    return issues, issue_examples


def analyze_stop_transition_timing(
    telemetry_path: str,
    arrivals_csv: str,
    stops_json: str
):
    """
    Specifically analyze when telemetry nextStopId changes vs actual arrival time.

    This helps understand the offset between:
    - When the system thinks bus arrived (geofence trigger)
    - When passengers could actually board (door open from arrivals data)
    """
    print("\n" + "=" * 80)
    print("STOP TRANSITION TIMING ANALYSIS")
    print("=" * 80)

    stop_mapper = StopNameMapper(stops_json)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = load_telemetry_file(Path(telemetry_path))

    telemetry = telemetry[telemetry['patternId'] != 9998]
    telemetry = telemetry[telemetry['routeId'].notna()]
    telemetry = telemetry[telemetry['vid'].str.startswith('21-')]

    timing_diffs = []

    vehicles = telemetry['vid'].unique()

    for vid in vehicles[:15]:
        vid_data = telemetry[telemetry['vid'] == vid].sort_values('t')

        prev_next_stop = None
        prev_ts = None

        for idx, row in vid_data.iterrows():
            ts = int(row['t'])
            next_stop_id = str(int(row['nextStopId'])) if row['nextStopId'] > 0 else None

            if prev_next_stop is not None and next_stop_id != prev_next_stop:
                # Stop changed! The bus "arrived" at prev_next_stop
                # The transition happened between prev_ts and ts
                transition_ts = ts  # When we first see the new stop

                # Get actual arrival from arrivals data
                arrival_info = arrivals.get_arrival_info(vid, prev_ts, prev_next_stop)

                if arrival_info:
                    actual_arrival_ts = arrival_info['arrival_ts']

                    # Difference: positive = telemetry changed AFTER actual arrival
                    #            negative = telemetry changed BEFORE actual arrival
                    diff_sec = (transition_ts - actual_arrival_ts) / 1000

                    timing_diffs.append({
                        'vehicle': vid,
                        'stop': prev_next_stop,
                        'stop_name': stop_mapper.id_to_name.get(prev_next_stop, 'Unknown'),
                        'telemetry_transition': transition_ts,
                        'actual_arrival': actual_arrival_ts,
                        'diff_sec': diff_sec
                    })

            prev_next_stop = next_stop_id
            prev_ts = ts

    if timing_diffs:
        diffs = [t['diff_sec'] for t in timing_diffs]

        print(f"\nAnalyzed {len(timing_diffs)} stop transitions")
        print(f"\nTiming difference (telemetry transition - actual arrival):")
        print(f"  Mean: {np.mean(diffs):+.1f} seconds")
        print(f"  Median: {np.median(diffs):+.1f} seconds")
        print(f"  Std: {np.std(diffs):.1f} seconds")
        print(f"  Min: {np.min(diffs):+.1f} seconds")
        print(f"  Max: {np.max(diffs):+.1f} seconds")

        early = sum(1 for d in diffs if d < -30)
        late = sum(1 for d in diffs if d > 30)
        on_time = len(diffs) - early - late

        print(f"\nDistribution:")
        print(f"  Telemetry changes >30s BEFORE arrival: {early} ({early/len(diffs)*100:.1f}%)")
        print(f"  Within 30 seconds: {on_time} ({on_time/len(diffs)*100:.1f}%)")
        print(f"  Telemetry changes >30s AFTER arrival: {late} ({late/len(diffs)*100:.1f}%)")

        print("\nSample transitions:")
        for t in timing_diffs[:5]:
            print(f"  {t['vehicle']} at {t['stop_name']}: {t['diff_sec']:+.0f}s")

    return timing_diffs


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Analyze data quality for ETA training')
    parser.add_argument('--telemetry', type=str, required=True)
    parser.add_argument('--arrivals', type=str, required=True)
    parser.add_argument('--stops', type=str, required=True)
    args = parser.parse_args()

    analyze_data_quality(
        telemetry_path=args.telemetry,
        arrivals_csv=args.arrivals,
        stops_json=args.stops
    )

    analyze_stop_transition_timing(
        telemetry_path=args.telemetry,
        arrivals_csv=args.arrivals,
        stops_json=args.stops
    )


if __name__ == '__main__':
    main()
