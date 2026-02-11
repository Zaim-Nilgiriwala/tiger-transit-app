"""
ETA Accuracy Analysis Script (v2 - Corrected)

IMPORTANT: etaSeconds is NOT "seconds until arrival"
It's "minutes since midnight (local time)" representing scheduled arrival time.

To get ETA in minutes:
  eta_minutes = etaSeconds - (current_hour * 60 + current_minute)

To get ETA in seconds:
  eta_seconds = (etaSeconds - (current_hour * 60 + current_minute)) * 60 + current_second
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
    """
    Convert etaSeconds (minutes since midnight) to seconds until arrival.

    etaSeconds field = scheduled arrival time as minutes since midnight (local)
    System ETA = etaSeconds - current_time_in_minutes
    """
    eta_minutes_since_midnight = row.get('etaSeconds', 0)
    if eta_minutes_since_midnight <= 0:
        return None

    current_minutes = dt_local.hour * 60 + dt_local.minute + dt_local.second / 60.0
    eta_minutes = eta_minutes_since_midnight - current_minutes

    # Convert to seconds
    return eta_minutes * 60


def analyze_eta_accuracy(
    telemetry_path: str,
    arrivals_csv: str,
    stops_json: str,
    num_examples: int = 15
):
    """
    Analyze ETA accuracy with CORRECT interpretation of etaSeconds field.
    """
    print("=" * 80)
    print("ETA ACCURACY ANALYSIS (v2 - Corrected Interpretation)")
    print("=" * 80)
    print("\nNOTE: etaSeconds is 'minutes since midnight (local time)'")
    print("      NOT 'seconds until arrival'\n")

    # Load data
    print("Loading data...")
    stop_mapper = StopNameMapper(stops_json)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = load_telemetry_file(Path(telemetry_path))

    # Filter
    telemetry = telemetry[telemetry['patternId'] != 9998]
    telemetry = telemetry[telemetry['routeId'].notna()]
    telemetry = telemetry[telemetry['routeId'] != 777]
    telemetry = telemetry[telemetry['nextStopId'] > 0]
    telemetry = telemetry[telemetry['vid'].str.startswith('21-')]

    print(f"Loaded {len(telemetry)} valid telemetry records")

    vehicles = telemetry['vid'].unique()
    print(f"Found {len(vehicles)} unique vehicles\n")

    comparisons = []
    examples_found = 0

    print("=" * 80)
    print("DETAILED EXAMPLES")
    print("=" * 80)

    for vid in vehicles[:10]:
        if examples_found >= num_examples:
            break

        vid_data = telemetry[telemetry['vid'] == vid].sort_values('t')

        last_stop = None
        approach_sequence = []

        for idx, row in vid_data.iterrows():
            next_stop_id = str(int(row['nextStopId']))

            if last_stop is None:
                last_stop = next_stop_id
                approach_sequence = [(row, next_stop_id)]
            elif next_stop_id == last_stop:
                approach_sequence.append((row, next_stop_id))
            else:
                if len(approach_sequence) >= 5 and examples_found < num_examples:
                    result = analyze_approach_sequence(
                        approach_sequence, arrivals, stop_mapper, vid
                    )
                    if result and result['valid_points'] >= 5:
                        comparisons.append(result)
                        examples_found += 1
                        print_approach_example(result, examples_found)

                last_stop = next_stop_id
                approach_sequence = [(row, next_stop_id)]

    print("\n" + "=" * 80)
    print("AGGREGATE STATISTICS")
    print("=" * 80)

    if comparisons:
        analyze_aggregate_stats(comparisons)
    else:
        print("No valid comparisons found!")

    return comparisons


def analyze_approach_sequence(sequence, arrivals, stop_mapper, vid):
    """Analyze approach with correct ETA interpretation."""
    if not sequence:
        return None

    first_row, target_stop_id = sequence[0]
    ts_start = int(first_row['t'])

    # Get actual arrival
    arrival_info = arrivals.get_arrival_info(vid, ts_start, target_stop_id)
    if arrival_info is None:
        return None

    actual_arrival_ts = arrival_info['arrival_ts']

    timeline = []
    for row, stop_id in sequence:
        ts = int(row['t'])

        # Convert to local time (Central, UTC-6)
        dt_utc = datetime.utcfromtimestamp(ts / 1000)
        dt_local = dt_utc - timedelta(hours=6)

        # Get system ETA (correctly interpreted)
        system_eta_sec = get_system_eta_seconds(row, dt_local)

        # Get actual ETA
        actual_eta_sec = (actual_arrival_ts - ts) / 1000.0

        if actual_eta_sec < 0:
            continue

        error = None
        if system_eta_sec is not None and system_eta_sec > 0:
            error = system_eta_sec - actual_eta_sec

        timeline.append({
            'timestamp': ts,
            'time_str': dt_local.strftime('%H:%M:%S'),
            'system_eta_sec': system_eta_sec,
            'actual_eta_sec': actual_eta_sec,
            'error_sec': error,
            'speed': float(row['speed']) if pd.notna(row.get('speed')) else 0,
            'eta_field_raw': row.get('etaSeconds', 0)
        })

    if not timeline:
        return None

    valid_points = sum(1 for p in timeline if p['error_sec'] is not None)
    stop_name = stop_mapper.id_to_name.get(target_stop_id, f"Stop {target_stop_id}")

    return {
        'vehicle_id': vid,
        'stop_id': target_stop_id,
        'stop_name': stop_name,
        'arrival_time': datetime.utcfromtimestamp(actual_arrival_ts/1000 - 6*3600).strftime('%H:%M:%S'),
        'timeline': timeline,
        'route': first_row.get('routeId'),
        'valid_points': valid_points
    }


def print_approach_example(result, example_num):
    """Print example with correct interpretation."""
    print(f"\n--- Example {example_num}: {result['vehicle_id']} -> {result['stop_name']} ---")
    print(f"Route: {result['route']} | Actual Arrival: {result['arrival_time']} (local)")
    print(f"\n{'Local Time':<12} {'Sys ETA':<10} {'Actual':<10} {'Error':<10} {'Speed':<6} {'Raw Field':<10}")
    print("-" * 68)

    for point in result['timeline'][-10:]:
        sys_eta = f"{point['system_eta_sec']:.0f}s" if point['system_eta_sec'] else "N/A"
        actual_eta = f"{point['actual_eta_sec']:.0f}s"
        error = f"{point['error_sec']:+.0f}s" if point['error_sec'] else "N/A"
        speed = f"{point['speed']:.0f}"
        raw = str(int(point['eta_field_raw']))

        print(f"{point['time_str']:<12} {sys_eta:<10} {actual_eta:<10} {error:<10} {speed:<6} {raw:<10}")

    errors = [p['error_sec'] for p in result['timeline'] if p['error_sec'] is not None]
    if errors:
        print(f"\nThis approach: Mean Error = {np.mean(errors):+.1f}s, MAE = {np.mean(np.abs(errors)):.1f}s")


def analyze_aggregate_stats(comparisons):
    """Compute aggregate statistics."""
    all_errors = []
    all_system_etas = []
    all_actual_etas = []

    for comp in comparisons:
        for point in comp['timeline']:
            if point['error_sec'] is not None and point['system_eta_sec'] is not None:
                all_errors.append(point['error_sec'])
                all_system_etas.append(point['system_eta_sec'])
                all_actual_etas.append(point['actual_eta_sec'])

    if not all_errors:
        print("No valid measurements!")
        return

    errors = np.array(all_errors)
    system_etas = np.array(all_system_etas)
    actual_etas = np.array(all_actual_etas)

    print(f"\nTotal data points: {len(errors)}")
    print(f"Approaches analyzed: {len(comparisons)}")

    print("\n--- ERROR STATISTICS ---")
    print(f"Mean Absolute Error (MAE): {np.abs(errors).mean():.1f} seconds ({np.abs(errors).mean()/60:.1f} min)")
    print(f"Mean Error: {errors.mean():+.1f} seconds (positive = system overestimates)")
    print(f"Std Dev: {errors.std():.1f} seconds")
    print(f"Median Error: {np.median(errors):+.1f} seconds")

    print("\n--- ACCURACY DISTRIBUTION ---")
    within_30s = (np.abs(errors) <= 30).sum()
    within_60s = (np.abs(errors) <= 60).sum()
    within_120s = (np.abs(errors) <= 120).sum()
    within_180s = (np.abs(errors) <= 180).sum()
    print(f"Within 30s:  {within_30s:4d} ({within_30s/len(errors)*100:5.1f}%)")
    print(f"Within 1min: {within_60s:4d} ({within_60s/len(errors)*100:5.1f}%)")
    print(f"Within 2min: {within_120s:4d} ({within_120s/len(errors)*100:5.1f}%)")
    print(f"Within 3min: {within_180s:4d} ({within_180s/len(errors)*100:5.1f}%)")

    print("\n--- DIRECTIONAL BIAS ---")
    overestimates = (errors > 0).sum()
    underestimates = (errors < 0).sum()
    print(f"Overestimates (bus arrives earlier): {overestimates} ({overestimates/len(errors)*100:.1f}%)")
    print(f"Underestimates (bus arrives later):  {underestimates} ({underestimates/len(errors)*100:.1f}%)")

    # Large errors
    print("\n--- LARGE ERROR ANALYSIS ---")
    over_2min = (errors > 120).sum()
    over_5min = (errors > 300).sum()
    under_2min = (errors < -120).sum()
    under_5min = (errors < -300).sum()
    print(f"Overestimate by >2min: {over_2min} ({over_2min/len(errors)*100:.1f}%)")
    print(f"Overestimate by >5min: {over_5min} ({over_5min/len(errors)*100:.1f}%)")
    print(f"Underestimate by >2min: {under_2min} ({under_2min/len(errors)*100:.1f}%)")
    print(f"Underestimate by >5min: {under_5min} ({under_5min/len(errors)*100:.1f}%)")

    print("\n--- CORRELATION ---")
    correlation = np.corrcoef(system_etas, actual_etas)[0, 1]
    print(f"Correlation between system ETA and actual: {correlation:.3f}")

    print("\n--- INTERPRETATION ---")
    mae_min = np.abs(errors).mean() / 60
    if mae_min < 1:
        print("EXCELLENT: System predictions are within 1 minute on average!")
    elif mae_min < 2:
        print("GOOD: System predictions are within 2 minutes on average.")
        print("ML model may provide modest improvements.")
    elif mae_min < 5:
        print("MODERATE: System predictions have 2-5 minute average error.")
        print("ML model should provide meaningful improvements.")
    else:
        print("POOR: System predictions have >5 minute average error.")
        print("ML model will likely provide significant improvements.")


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Analyze ETA accuracy (v2)')
    parser.add_argument('--telemetry', type=str, required=True)
    parser.add_argument('--arrivals', type=str, required=True)
    parser.add_argument('--stops', type=str, required=True)
    parser.add_argument('--examples', type=int, default=15)
    args = parser.parse_args()

    analyze_eta_accuracy(
        telemetry_path=args.telemetry,
        arrivals_csv=args.arrivals,
        stops_json=args.stops,
        num_examples=args.examples
    )


if __name__ == '__main__':
    main()
