"""
Historical statistics computation for the data preparation pipeline.

Pre-computes segment travel times, stop dwell times, and vehicle speed factors
from arrivals data for use as features.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .config import DATA_PATHS


def load_arrivals_data(arrivals_files: List[Path] = None) -> pd.DataFrame:
    """
    Load and combine arrivals data from CSV files.

    Args:
        arrivals_files: List of paths to arrivals CSV files

    Returns:
        Combined arrivals DataFrame
    """
    if arrivals_files is None:
        arrivals_files = DATA_PATHS['arrivals_files']

    all_dfs = []

    for file_path in arrivals_files:
        file_path = Path(file_path)
        if not file_path.exists():
            print(f"Warning: Arrivals file not found: {file_path}")
            continue

        # Read CSV, skipping the header row (row 0 has date range info)
        df = pd.read_csv(file_path, skiprows=1)

        # Clean column names (remove quotes)
        df.columns = df.columns.str.strip('"')

        all_dfs.append(df)

    if not all_dfs:
        print("Warning: No arrivals data loaded")
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)

    # Strip whitespace from string columns (CSV has trailing spaces on some names)
    for col in ['Station', 'Route', 'Vehicle ID']:
        if col in combined.columns:
            combined[col] = combined[col].str.strip()

    # Filter out "No Route" entries
    combined = combined[combined['Route'] != 'No Route']

    # Parse datetime
    combined['arrival_datetime'] = pd.to_datetime(
        combined['DATE'] + ' ' + combined['ARRIVAL'],
        format='%Y-%m-%d %H:%M:%S',
        errors='coerce'
    )

    # Parse departure
    combined['departure_datetime'] = pd.to_datetime(
        combined['DATE'] + ' ' + combined['DEPARTURE'],
        format='%Y-%m-%d %H:%M:%S',
        errors='coerce'
    )

    # Extract hour for grouping
    combined['hour'] = combined['arrival_datetime'].dt.hour

    print(f"Loaded {len(combined)} arrival records from {combined['DATE'].min()} to {combined['DATE'].max()}")

    return combined


def compute_segment_travel_times(arrivals_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Compute average travel times between consecutive stops.

    Groups by (route, from_stop, to_stop, hour).

    Args:
        arrivals_df: Arrivals DataFrame

    Returns:
        Dictionary mapping segment key to {mean, std} travel times
    """
    if arrivals_df.empty:
        return {}

    # Sort by vehicle and arrival time to get consecutive stops
    arrivals_df = arrivals_df.sort_values(['Vehicle ID', 'arrival_datetime'])

    # Create previous stop columns
    arrivals_df['prev_station'] = arrivals_df.groupby('Vehicle ID')['Station'].shift(1)
    arrivals_df['prev_departure'] = arrivals_df.groupby('Vehicle ID')['departure_datetime'].shift(1)

    # Calculate travel time (arrival at current - departure from previous)
    arrivals_df['travel_time_sec'] = (
        arrivals_df['arrival_datetime'] - arrivals_df['prev_departure']
    ).dt.total_seconds()

    # Filter valid travel times (positive, less than 1 hour)
    valid = arrivals_df[
        (arrivals_df['travel_time_sec'] > 0) &
        (arrivals_df['travel_time_sec'] < 3600)
    ].copy()

    # Group by route, segment, and hour
    segment_stats = valid.groupby(
        ['Route', 'prev_station', 'Station', 'hour']
    )['travel_time_sec'].agg(['mean', 'std', 'count']).reset_index()

    # Convert to dictionary format
    result = {}
    for _, row in segment_stats.iterrows():
        key = f"{row['Route']}|{row['prev_station']}|{row['Station']}|{row['hour']}"
        result[key] = {
            'mean': float(row['mean']),
            'std': float(row['std']) if pd.notna(row['std']) else 0.0,
            'count': int(row['count']),
        }

    print(f"Computed travel times for {len(result)} route segments")
    return result


def compute_stop_dwell_times(arrivals_df: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    """
    Compute average dwell times at each stop.

    Groups by (station, hour).

    Args:
        arrivals_df: Arrivals DataFrame

    Returns:
        Dictionary mapping stop_hour key to {mean, std} dwell times
    """
    if arrivals_df.empty:
        return {}

    # Parse dwell time if not already numeric
    if 'Dwell (sec)' in arrivals_df.columns:
        dwell_col = 'Dwell (sec)'
    else:
        return {}

    arrivals_df[dwell_col] = pd.to_numeric(arrivals_df[dwell_col], errors='coerce')

    # Filter valid dwell times (positive, less than 10 minutes)
    valid = arrivals_df[
        (arrivals_df[dwell_col] > 0) &
        (arrivals_df[dwell_col] < 600)
    ].copy()

    # Group by station and hour
    dwell_stats = valid.groupby(
        ['Station', 'hour']
    )[dwell_col].agg(['mean', 'std', 'count']).reset_index()

    # Convert to dictionary format
    result = {}
    for _, row in dwell_stats.iterrows():
        key = f"{row['Station']}|{row['hour']}"
        result[key] = {
            'mean': float(row['mean']),
            'std': float(row['std']) if pd.notna(row['std']) else 0.0,
            'count': int(row['count']),
        }

    print(f"Computed dwell times for {len(result)} stop-hour combinations")
    return result


def compute_vehicle_speed_factors(arrivals_df: pd.DataFrame) -> Dict[str, float]:
    """
    Compute vehicle speed factors relative to fleet average.

    Args:
        arrivals_df: Arrivals DataFrame

    Returns:
        Dictionary mapping vehicle ID to speed factor (1.0 = fleet average)
    """
    if arrivals_df.empty:
        return {}

    # Sort to get consecutive stops
    arrivals_df = arrivals_df.sort_values(['Vehicle ID', 'arrival_datetime'])

    # Calculate travel times
    arrivals_df['prev_departure'] = arrivals_df.groupby('Vehicle ID')['departure_datetime'].shift(1)
    arrivals_df['travel_time_sec'] = (
        arrivals_df['arrival_datetime'] - arrivals_df['prev_departure']
    ).dt.total_seconds()

    # Filter valid
    valid = arrivals_df[
        (arrivals_df['travel_time_sec'] > 0) &
        (arrivals_df['travel_time_sec'] < 3600)
    ].copy()

    if len(valid) == 0:
        return {}

    # Fleet average travel time
    fleet_avg = valid['travel_time_sec'].mean()

    # Vehicle averages
    vehicle_avg = valid.groupby('Vehicle ID')['travel_time_sec'].mean()

    # Speed factor: fleet_avg / vehicle_avg (higher = faster than average)
    # Clamp to reasonable range [0.5, 2.0]
    speed_factors = {}
    for vid, vavg in vehicle_avg.items():
        factor = fleet_avg / vavg if vavg > 0 else 1.0
        factor = max(0.5, min(2.0, factor))
        speed_factors[vid] = factor

    print(f"Computed speed factors for {len(speed_factors)} vehicles")
    return speed_factors


def compute_historical_stats(arrivals_files: List[Path] = None) -> Dict[str, any]:
    """
    Compute all historical statistics from arrivals data.

    Args:
        arrivals_files: List of paths to arrivals CSV files

    Returns:
        Dictionary with all historical statistics
    """
    arrivals_df = load_arrivals_data(arrivals_files)

    if arrivals_df.empty:
        return {
            'segment_times': {},
            'stop_dwell_times': {},
            'vehicle_speed_factors': {},
        }

    return {
        'segment_times': compute_segment_travel_times(arrivals_df),
        'stop_dwell_times': compute_stop_dwell_times(arrivals_df),
        'vehicle_speed_factors': compute_vehicle_speed_factors(arrivals_df),
    }


def save_historical_stats(stats: Dict[str, any], output_file: Path = None):
    """
    Save historical statistics to JSON file.

    Args:
        stats: Historical statistics dictionary
        output_file: Output file path
    """
    if output_file is None:
        output_file = DATA_PATHS['historical_stats_file']

    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, 'w') as f:
        json.dump(stats, f, indent=2)

    print(f"Saved historical stats to {output_file}")


def load_historical_stats(stats_file: Path = None) -> Dict[str, any]:
    """
    Load historical statistics from JSON file.

    Args:
        stats_file: Path to stats JSON file

    Returns:
        Historical statistics dictionary
    """
    if stats_file is None:
        stats_file = DATA_PATHS['historical_stats_file']

    stats_file = Path(stats_file)
    if not stats_file.exists():
        return {
            'segment_times': {},
            'stop_dwell_times': {},
            'vehicle_speed_factors': {},
        }

    with open(stats_file, 'r') as f:
        return json.load(f)


def join_historical_features(
    df: pd.DataFrame,
    historical_stats: Dict[str, any] = None,
    stop_name_mapping: Dict[str, str] = None
) -> pd.DataFrame:
    """
    Join historical statistics as features to telemetry data.

    Args:
        df: Telemetry DataFrame with route, stops, hour, and vid columns
        historical_stats: Pre-computed historical statistics
        stop_name_mapping: Mapping from stop ID to stop name (for arrivals matching)

    Returns:
        DataFrame with historical features added
    """
    df = df.copy()

    if historical_stats is None:
        historical_stats = load_historical_stats()

    # Initialize columns
    df['segment_avg_travel_time_sec'] = np.nan
    df['segment_std_travel_time_sec'] = np.nan
    df['stop_avg_dwell_time_sec'] = np.nan
    df['vehicle_speed_factor'] = 1.0

    segment_times = historical_stats.get('segment_times', {})
    stop_dwell_times = historical_stats.get('stop_dwell_times', {})
    vehicle_speed_factors = historical_stats.get('vehicle_speed_factors', {})

    # Load stop mapping if not provided
    if stop_name_mapping is None:
        stops_file = DATA_PATHS['stops_file']
        if stops_file.exists():
            import json
            with open(stops_file, 'r') as f:
                stops = json.load(f)
            stop_name_mapping = {str(s['id']): s['name'] for s in stops}
        else:
            stop_name_mapping = {}

    # For each record, look up historical stats
    for idx, row in df.iterrows():
        # Get identifiers
        route = row.get('route_id', '')
        last_stop_id = str(row.get('last_stop_id', ''))
        target_stop_id = str(row.get('target_stop_id', ''))
        hour = row.get('hour_of_day', 0)
        vid = row.get('vid', '')

        # Convert stop IDs to names for arrivals matching
        last_stop_name = stop_name_mapping.get(last_stop_id, last_stop_id)
        target_stop_name = stop_name_mapping.get(target_stop_id, target_stop_id)

        # Segment travel time
        # Try with route name first
        segment_key = f"{route}|{last_stop_name}|{target_stop_name}|{hour}"
        if segment_key in segment_times:
            stats = segment_times[segment_key]
            df.at[idx, 'segment_avg_travel_time_sec'] = stats['mean']
            df.at[idx, 'segment_std_travel_time_sec'] = stats['std']

        # Stop dwell time
        dwell_key = f"{target_stop_name}|{hour}"
        if dwell_key in stop_dwell_times:
            stats = stop_dwell_times[dwell_key]
            df.at[idx, 'stop_avg_dwell_time_sec'] = stats['mean']

        # Vehicle speed factor
        if vid in vehicle_speed_factors:
            df.at[idx, 'vehicle_speed_factor'] = vehicle_speed_factors[vid]

    # Fill NaN with defaults
    df['segment_avg_travel_time_sec'] = df['segment_avg_travel_time_sec'].fillna(0.0)
    df['segment_std_travel_time_sec'] = df['segment_std_travel_time_sec'].fillna(0.0)
    df['stop_avg_dwell_time_sec'] = df['stop_avg_dwell_time_sec'].fillna(0.0)
    df['vehicle_speed_factor'] = df['vehicle_speed_factor'].fillna(1.0)

    return df
