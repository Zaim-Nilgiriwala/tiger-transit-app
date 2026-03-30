"""
ETA Accuracy Analysis Script

Analyzes how accurate the current system's ETA predictions (etaSeconds field)
are compared to actual arrival times from the ground truth data.

This helps validate:
1. The need for ML-based predictions
2. Correct data alignment between telemetry and arrivals
3. Patterns in current system errors
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from data_prep import StopNameMapper, ArrivalsData, WeatherData


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


def analyze_eta_accuracy(
    telemetry_path: str,
    arrivals_csv: str,
    stops_json: str,
    num_examples: int = 20
):
    """
    Analyze ETA accuracy by comparing system predictions to actual arrivals.

    Args:
        telemetry_path: Path to telemetry JSONL file
        arrivals_csv: Path to arrivals CSV
        stops_json: Path to stops.json
        num_examples: Number of examples to analyze
    """
    print("=" * 80)
    print("ETA ACCURACY ANALYSIS")
    print("=" * 80)

    # Load data
    print("\nLoading data...")
    stop_mapper = StopNameMapper(stops_json)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = load_telemetry_file(Path(telemetry_path))

    # Filter out invalid records
    telemetry = telemetry[telemetry['patternId'] != 9998]
    telemetry = telemetry[telemetry['routeId'].notna()]
    telemetry = telemetry[telemetry['routeId'] != 777]
    telemetry = telemetry[telemetry['nextStopId'] > 0]

    # Filter for buses with 21- prefix (main fleet)
    telemetry = telemetry[telemetry['vid'].str.startswith('21-')]

    print(f"Loaded {len(telemetry)} valid telemetry records")

    # Get unique vehicles
    vehicles = telemetry['vid'].unique()
    print(f"Found {len(vehicles)} unique vehicles")

    # Collect comparison data
    comparisons = []
    examples_found = 0

    print("\n" + "=" * 80)
    print("DETAILED EXAMPLES OF BUSES APPROACHING STOPS")
    print("=" * 80)

    for vid in vehicles[:10]:  # Check first 10 vehicles
        if examples_found >= num_examples:
            break

        vid_data = telemetry[telemetry['vid'] == vid].sort_values('t')

        # Look for sequences approaching a stop
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
                # Stop changed - analyze the sequence if we have enough points
                if len(approach_sequence) >= 3 and examples_found < num_examples:
                    result = analyze_approach_sequence(
                        approach_sequence, arrivals, stop_mapper, vid
                    )
                    if result:
                        comparisons.append(result)
                        examples_found += 1
                        print_approach_example(result, examples_found)

                # Start new sequence
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
    """
    Analyze a sequence of telemetry points approaching a single stop.

    Returns dict with comparison data or None if arrival not found.
    """
    if not sequence:
        return None

    first_row, target_stop_id = sequence[0]
    last_row, _ = sequence[-1]

    ts_start = int(first_row['t'])
    ts_end = int(last_row['t'])

    # Get actual arrival
    arrival_info = arrivals.get_arrival_info(vid, ts_start, target_stop_id)

    if arrival_info is None:
        return None

    actual_arrival_ts = arrival_info['arrival_ts']

    # Build timeline of predictions
    timeline = []
    for row, stop_id in sequence:
        ts = int(row['t'])

        system_eta_sec = float(row['etaSeconds']) if pd.notna(row.get('etaSeconds')) else None
        scheduled_eta_sec = float(row['scheduledEta']) if pd.notna(row.get('scheduledEta')) else None
        actual_eta_sec = (actual_arrival_ts - ts) / 1000.0

        if actual_eta_sec < 0:
            continue  # Already past the stop

        error = None
        if system_eta_sec is not None:
            error = system_eta_sec - actual_eta_sec

        timeline.append({
            'timestamp': ts,
            'time_str': datetime.utcfromtimestamp(ts/1000).strftime('%H:%M:%S'),
            'system_eta_sec': system_eta_sec,
            'scheduled_eta_sec': scheduled_eta_sec,
            'actual_eta_sec': actual_eta_sec,
            'error_sec': error,
            'speed': float(row['speed']) if pd.notna(row.get('speed')) else 0,
            'lat': float(row['lat']),
            'lon': float(row['lon'])
        })

    if not timeline:
        return None

    # Get stop name
    stop_name = stop_mapper.id_to_name.get(target_stop_id, f"Stop {target_stop_id}")

    return {
        'vehicle_id': vid,
        'stop_id': target_stop_id,
        'stop_name': stop_name,
        'arrival_time': datetime.utcfromtimestamp(actual_arrival_ts/1000).strftime('%H:%M:%S'),
        'timeline': timeline,
        'route': first_row.get('routeId')
    }


def print_approach_example(result, example_num):
    """Print a detailed example of a bus approaching a stop."""
    print(f"\n--- Example {example_num}: Vehicle {result['vehicle_id']} -> {result['stop_name']} ---")
    print(f"Route: {result['route']}")
    print(f"Actual Arrival: {result['arrival_time']} UTC")
    print(f"\n{'Time (UTC)':<12} {'System ETA':<12} {'Actual ETA':<12} {'Error':<12} {'Speed':<8}")
    print("-" * 60)

    for point in result['timeline'][-10:]:  # Last 10 points
        sys_eta = f"{point['system_eta_sec']:.0f}s" if point['system_eta_sec'] else "N/A"
        actual_eta = f"{point['actual_eta_sec']:.0f}s"
        error = f"{point['error_sec']:+.0f}s" if point['error_sec'] else "N/A"
        speed = f"{point['speed']:.1f}"

        print(f"{point['time_str']:<12} {sys_eta:<12} {actual_eta:<12} {error:<12} {speed:<8}")

    # Summary for this example
    errors = [p['error_sec'] for p in result['timeline'] if p['error_sec'] is not None]
    if errors:
        print(f"\nSummary for this approach:")
        print(f"  Mean Error: {np.mean(errors):+.1f}s (positive = overestimate)")
        print(f"  Max Error: {max(errors):+.1f}s")
        print(f"  Min Error: {min(errors):+.1f}s")


def analyze_aggregate_stats(comparisons):
    """Analyze aggregate statistics across all comparisons."""
    all_errors = []
    all_system_etas = []
    all_actual_etas = []

    for comp in comparisons:
        for point in comp['timeline']:
            if point['error_sec'] is not None:
                all_errors.append(point['error_sec'])
                all_system_etas.append(point['system_eta_sec'])
                all_actual_etas.append(point['actual_eta_sec'])

    if not all_errors:
        print("No valid error measurements!")
        return

    errors = np.array(all_errors)
    system_etas = np.array(all_system_etas)
    actual_etas = np.array(all_actual_etas)

    print(f"\nTotal data points: {len(errors)}")
    print(f"Unique bus approaches analyzed: {len(comparisons)}")

    print("\n--- ERROR STATISTICS ---")
    print(f"Mean Absolute Error (MAE): {np.abs(errors).mean():.1f} seconds")
    print(f"Mean Error: {errors.mean():+.1f} seconds")
    print(f"Std Dev: {errors.std():.1f} seconds")
    print(f"Median Error: {np.median(errors):+.1f} seconds")

    print("\n--- ERROR DISTRIBUTION ---")
    overestimates = (errors > 0).sum()
    underestimates = (errors < 0).sum()
    print(f"Overestimates (system > actual): {overestimates} ({overestimates/len(errors)*100:.1f}%)")
    print(f"Underestimates (system < actual): {underestimates} ({underestimates/len(errors)*100:.1f}%)")

    print("\n--- ERROR BY MAGNITUDE ---")
    within_30s = (np.abs(errors) <= 30).sum()
    within_60s = (np.abs(errors) <= 60).sum()
    within_120s = (np.abs(errors) <= 120).sum()
    print(f"Within 30 seconds: {within_30s} ({within_30s/len(errors)*100:.1f}%)")
    print(f"Within 60 seconds: {within_60s} ({within_60s/len(errors)*100:.1f}%)")
    print(f"Within 120 seconds: {within_120s} ({within_120s/len(errors)*100:.1f}%)")

    print("\n--- OVERESTIMATE SEVERITY ---")
    # For rider at stop: overestimate is BAD (bus arrives earlier than predicted)
    large_overestimates = (errors > 120).sum()
    very_large = (errors > 300).sum()
    print(f"Overestimate by >2 min: {large_overestimates} ({large_overestimates/len(errors)*100:.1f}%)")
    print(f"Overestimate by >5 min: {very_large} ({very_large/len(errors)*100:.1f}%)")

    print("\n--- SYSTEM ETA FIELD ANALYSIS ---")
    print(f"etaSeconds range: {system_etas.min():.0f}s to {system_etas.max():.0f}s")
    print(f"etaSeconds mean: {system_etas.mean():.1f}s")

    # Check if etaSeconds looks like it's updating or static
    unique_etas = len(np.unique(system_etas.astype(int)))
    print(f"Unique etaSeconds values: {unique_etas}")

    print("\n--- INTERPRETATION ---")
    if errors.mean() > 60:
        print("WARNING: The current system SIGNIFICANTLY OVERESTIMATES arrival times")
        print("   This means buses arrive much earlier than predicted.")
        print("   For riders at stops, this is problematic - they may miss the bus!")
    elif errors.mean() < -60:
        print("WARNING: The current system SIGNIFICANTLY UNDERESTIMATES arrival times")
        print("   Buses arrive later than predicted.")
    else:
        print("OK: The current system has reasonable average error")

    if very_large / len(errors) > 0.3:
        print("\nWARNING: Over 30% of predictions are off by more than 5 minutes!")
        print("   This strongly validates the need for ML-based predictions.")


def main():
    """Run the analysis."""
    import argparse

    parser = argparse.ArgumentParser(description='Analyze ETA prediction accuracy')
    parser.add_argument('--telemetry', type=str, required=True,
                        help='Path to telemetry JSONL file')
    parser.add_argument('--arrivals', type=str, required=True,
                        help='Path to arrivals CSV')
    parser.add_argument('--stops', type=str, required=True,
                        help='Path to stops.json')
    parser.add_argument('--examples', type=int, default=20,
                        help='Number of examples to analyze')

    args = parser.parse_args()

    analyze_eta_accuracy(
        telemetry_path=args.telemetry,
        arrivals_csv=args.arrivals,
        stops_json=args.stops,
        num_examples=args.examples
    )


if __name__ == '__main__':
    main()
