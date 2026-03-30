"""
Label creation for the data preparation pipeline.

Joins telemetry with arrivals data to create ground truth labels
(time until arrival at target stop).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from tqdm import tqdm

from .config import DATA_PATHS, QUALITY_THRESHOLDS
from .historical_stats import load_arrivals_data


def build_stop_name_mapping(stops_file: Path = None) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Build mappings between stop IDs and stop names.

    Args:
        stops_file: Path to stops.json file

    Returns:
        Tuple of (id_to_name, name_to_id) dictionaries
    """
    if stops_file is None:
        stops_file = DATA_PATHS['stops_file']

    stops_file = Path(stops_file)
    if not stops_file.exists():
        print(f"Warning: stops file not found at {stops_file}")
        return {}, {}

    with open(stops_file, 'r') as f:
        stops = json.load(f)

    id_to_name = {str(s['id']): s['name'].strip() for s in stops}

    # For duplicate names (e.g. "Eagles West Apartments" has ids 149 and 224),
    # keep the first occurrence. Both IDs refer to the same physical stop,
    # so either mapping works for label matching.
    name_to_id = {}
    for s in stops:
        name = s['name'].strip()
        if name not in name_to_id:
            name_to_id[name] = str(s['id'])

    # Also add lowercase versions for case-insensitive matching
    name_to_id_lower = {}
    for name, sid in name_to_id.items():
        lower = name.lower()
        if lower not in name_to_id_lower:
            name_to_id_lower[lower] = sid

    return id_to_name, {**name_to_id, **name_to_id_lower}


def prepare_arrivals_for_matching(
    arrivals_df: pd.DataFrame,
    name_to_id: Dict[str, str]
) -> pd.DataFrame:
    """
    Prepare arrivals data for efficient matching with telemetry.

    Args:
        arrivals_df: Raw arrivals DataFrame
        name_to_id: Mapping from stop name to stop ID

    Returns:
        Prepared arrivals DataFrame
    """
    df = arrivals_df.copy()

    # Strip whitespace from station names (CSV has trailing spaces on some names)
    df['Station'] = df['Station'].str.strip()

    # Map station names to IDs
    df['stop_id'] = df['Station'].map(name_to_id)

    # Also try lowercase matching for unmatched
    unmatched_mask = df['stop_id'].isna()
    df.loc[unmatched_mask, 'stop_id'] = df.loc[unmatched_mask, 'Station'].str.lower().map(name_to_id)

    # Convert arrival time to timestamp in milliseconds
    df['arrival_timestamp_ms'] = df['arrival_datetime'].astype(np.int64) // 10**6

    # Keep only needed columns
    df = df[['Vehicle ID', 'stop_id', 'arrival_timestamp_ms', 'arrival_datetime', 'Station']].copy()
    df = df.rename(columns={'Vehicle ID': 'vid'})

    # Drop rows without stop_id mapping
    initial_count = len(df)
    df = df.dropna(subset=['stop_id'])
    dropped = initial_count - len(df)
    if dropped > 0:
        print(f"Warning: {dropped} arrivals could not be mapped to stop IDs")

    # Sort by vehicle and time for efficient lookup
    df = df.sort_values(['vid', 'arrival_timestamp_ms'])

    return df


def find_next_arrival(
    vid: str,
    target_stop_id: str,
    current_timestamp_ms: int,
    arrivals_df: pd.DataFrame,
    max_lookahead_ms: int = 3600000  # 1 hour
) -> Optional[int]:
    """
    Find the next arrival at target stop for a vehicle.

    Args:
        vid: Vehicle ID
        target_stop_id: Target stop ID
        current_timestamp_ms: Current telemetry timestamp
        arrivals_df: Prepared arrivals DataFrame
        max_lookahead_ms: Maximum time to look ahead (default 1 hour)

    Returns:
        Arrival timestamp in ms, or None if not found
    """
    target_stop_id = str(target_stop_id)

    # Filter to this vehicle and stop
    mask = (arrivals_df['vid'] == vid) & (arrivals_df['stop_id'] == target_stop_id)
    vehicle_arrivals = arrivals_df[mask]

    if vehicle_arrivals.empty:
        return None

    # Find arrivals after current time but within lookahead window
    future_mask = (
        (vehicle_arrivals['arrival_timestamp_ms'] > current_timestamp_ms) &
        (vehicle_arrivals['arrival_timestamp_ms'] <= current_timestamp_ms + max_lookahead_ms)
    )
    future_arrivals = vehicle_arrivals[future_mask]

    if future_arrivals.empty:
        return None

    # Return the first (nearest) future arrival
    return int(future_arrivals['arrival_timestamp_ms'].iloc[0])


def create_labels(
    df: pd.DataFrame,
    arrivals_files: List[Path] = None,
    max_label_seconds: int = None,
    show_progress: bool = True
) -> pd.DataFrame:
    """
    Create time_to_arrival_sec labels by joining telemetry with arrivals.

    Args:
        df: Telemetry DataFrame with vid, target_stop_id, timestamp_ms columns
        arrivals_files: List of arrivals CSV files (uses default if None)
        max_label_seconds: Maximum label value in seconds (default from config)
        show_progress: Whether to show progress bar

    Returns:
        DataFrame with time_to_arrival_sec label column added
    """
    if max_label_seconds is None:
        max_label_seconds = QUALITY_THRESHOLDS['max_label_seconds']

    df = df.copy()

    # Load and prepare arrivals data
    arrivals_df = load_arrivals_data(arrivals_files)
    if arrivals_df.empty:
        df['time_to_arrival_sec'] = np.nan
        print("Warning: No arrivals data available for label creation")
        return df

    # Build stop name mapping
    id_to_name, name_to_id = build_stop_name_mapping()

    # Prepare arrivals for matching
    arrivals_prepared = prepare_arrivals_for_matching(arrivals_df, name_to_id)

    print(f"Prepared {len(arrivals_prepared)} arrivals for matching")

    # Create label column
    df['time_to_arrival_sec'] = np.nan

    # Group telemetry by vehicle for efficient processing
    vehicles = df['vid'].unique()
    total_matched = 0

    iterator = tqdm(vehicles, desc="Creating labels") if show_progress else vehicles

    for vid in iterator:
        # Get telemetry for this vehicle
        vehicle_mask = df['vid'] == vid
        vehicle_telemetry = df[vehicle_mask]

        # Get arrivals for this vehicle
        vehicle_arrivals = arrivals_prepared[arrivals_prepared['vid'] == vid]

        if vehicle_arrivals.empty:
            continue

        # For each telemetry record, find the next arrival at target stop
        for idx in vehicle_telemetry.index:
            target_stop_id = str(df.at[idx, 'target_stop_id'])
            current_timestamp_ms = df.at[idx, 'timestamp_ms']

            if pd.isna(target_stop_id) or pd.isna(current_timestamp_ms):
                continue

            # Find next arrival
            arrival_ms = find_next_arrival(
                vid, target_stop_id, current_timestamp_ms,
                vehicle_arrivals, max_label_seconds * 1000
            )

            if arrival_ms is not None:
                # Calculate time to arrival in seconds
                time_to_arrival = (arrival_ms - current_timestamp_ms) / 1000.0

                # Validate label
                if 0 <= time_to_arrival <= max_label_seconds:
                    df.at[idx, 'time_to_arrival_sec'] = time_to_arrival
                    total_matched += 1

    labeled_count = df['time_to_arrival_sec'].notna().sum()
    total_count = len(df)
    print(f"Created {labeled_count} labels from {total_count} records ({100*labeled_count/total_count:.1f}%)")

    return df


def check_label_quality(df: pd.DataFrame) -> Dict[str, any]:
    """
    Check quality of created labels.

    Args:
        df: DataFrame with time_to_arrival_sec column

    Returns:
        Dictionary with label quality metrics
    """
    report = {}

    if 'time_to_arrival_sec' not in df.columns:
        return {'error': 'time_to_arrival_sec column not found'}

    # Label coverage
    labels = df['time_to_arrival_sec']
    report['label_count'] = labels.notna().sum()
    report['label_missing'] = labels.isna().sum()
    report['label_missing_rate'] = labels.isna().mean() * 100

    # Range statistics
    valid_labels = labels.dropna()
    if len(valid_labels) > 0:
        report['label_min'] = valid_labels.min()
        report['label_max'] = valid_labels.max()
        report['label_mean'] = valid_labels.mean()
        report['label_median'] = valid_labels.median()
        report['label_std'] = valid_labels.std()

        # Outlier detection
        report['labels_negative'] = (valid_labels < 0).sum()
        report['labels_over_1hour'] = (valid_labels > 3600).sum()
        report['labels_over_30min'] = (valid_labels > 1800).sum()

        # Distribution buckets
        report['labels_0_60s'] = ((valid_labels >= 0) & (valid_labels < 60)).sum()
        report['labels_60_300s'] = ((valid_labels >= 60) & (valid_labels < 300)).sum()
        report['labels_300_600s'] = ((valid_labels >= 300) & (valid_labels < 600)).sum()
        report['labels_600_1800s'] = ((valid_labels >= 600) & (valid_labels < 1800)).sum()
        report['labels_1800_3600s'] = ((valid_labels >= 1800) & (valid_labels <= 3600)).sum()
    else:
        report['label_min'] = np.nan
        report['label_max'] = np.nan
        report['label_mean'] = np.nan
        report['label_median'] = np.nan
        report['label_std'] = np.nan
        report['labels_negative'] = 0
        report['labels_over_1hour'] = 0
        report['labels_over_30min'] = 0

    return report


def check_join_quality(
    telemetry_df: pd.DataFrame,
    labeled_df: pd.DataFrame
) -> Dict[str, any]:
    """
    Check quality of telemetry-arrivals join.

    Args:
        telemetry_df: Original telemetry DataFrame
        labeled_df: DataFrame after label creation

    Returns:
        Dictionary with join quality metrics
    """
    report = {}

    # Join success rate
    report['telemetry_records'] = len(telemetry_df)
    report['labeled_records'] = labeled_df['time_to_arrival_sec'].notna().sum()
    report['join_success_rate'] = (
        report['labeled_records'] / report['telemetry_records'] * 100
        if report['telemetry_records'] > 0 else 0
    )

    # By vehicle
    if 'vid' in labeled_df.columns:
        labeled_by_vehicle = labeled_df[labeled_df['time_to_arrival_sec'].notna()].groupby('vid').size()
        total_by_vehicle = telemetry_df.groupby('vid').size()
        join_rate_by_vehicle = (labeled_by_vehicle / total_by_vehicle * 100).dropna().to_dict()
        report['join_rate_by_vehicle'] = join_rate_by_vehicle
        report['vehicles_with_labels'] = len(labeled_by_vehicle)
        report['vehicles_total'] = len(total_by_vehicle)

    # By route
    if 'route_id' in labeled_df.columns:
        labeled_by_route = labeled_df[labeled_df['time_to_arrival_sec'].notna()].groupby('route_id').size()
        report['samples_by_route'] = labeled_by_route.to_dict()

    # By stop
    if 'target_stop_id' in labeled_df.columns:
        labeled_by_stop = labeled_df[labeled_df['time_to_arrival_sec'].notna()].groupby('target_stop_id').size()
        report['samples_by_stop'] = labeled_by_stop.to_dict()
        report['stops_with_labels'] = len(labeled_by_stop)
        report['stops_with_few_samples'] = (labeled_by_stop < 100).sum()

    return report
