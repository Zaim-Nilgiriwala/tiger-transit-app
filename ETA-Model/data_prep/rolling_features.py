"""
Rolling window feature calculations for the data preparation pipeline.

Computes rolling speed statistics, distance traveled, and heading changes
over multiple time windows (30s, 60s, 90s, 120s, 180s, 300s).
"""

import math
import numpy as np
import pandas as pd
from typing import List, Dict, Optional
from tqdm import tqdm

from .config import ROLLING_WINDOWS, ROLLING_SPEED_FEATURES


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points in meters.

    Args:
        lat1, lon1: Coordinates of first point (degrees)
        lat2, lon2: Coordinates of second point (degrees)

    Returns:
        Distance in meters
    """
    R = 6371000  # Earth's radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def compute_heading_change(heading1: float, heading2: float) -> float:
    """
    Compute the absolute heading change between two headings.

    Handles wraparound at 0/360 degrees.

    Args:
        heading1: First heading in degrees (0-360)
        heading2: Second heading in degrees (0-360)

    Returns:
        Absolute heading change in degrees (0-180)
    """
    diff = abs(heading2 - heading1)
    return min(diff, 360 - diff)


def compute_rolling_features_for_vehicle(
    df: pd.DataFrame,
    windows: List[int] = None
) -> pd.DataFrame:
    """
    Compute rolling window features for a single vehicle's data.

    Must be called on data sorted by timestamp for a single vehicle.

    Args:
        df: DataFrame for a single vehicle, sorted by timestamp_ms
        windows: List of window sizes in seconds (default: ROLLING_WINDOWS)

    Returns:
        DataFrame with rolling features added
    """
    if windows is None:
        windows = ROLLING_WINDOWS

    df = df.copy()

    # Ensure sorted by timestamp
    df = df.sort_values('timestamp_ms')

    # Convert timestamp to datetime for rolling operations
    df['_datetime'] = pd.to_datetime(df['timestamp_ms'], unit='ms')
    df = df.set_index('_datetime')

    # Compute base columns needed for rolling
    # Speed is already in mph
    speed_col = 'speed_mph'

    # Compute distance traveled between consecutive points
    df['_lat_shift'] = df['lat'].shift(1)
    df['_lon_shift'] = df['lon'].shift(1)
    df['_heading_shift'] = df['heading'].shift(1) if 'heading' in df.columns else 0

    # Calculate instant distance and heading change
    df['_instant_distance'] = df.apply(
        lambda row: haversine_distance_meters(
            row['_lat_shift'], row['_lon_shift'],
            row['lat'], row['lon']
        ) if pd.notna(row['_lat_shift']) else 0,
        axis=1
    )

    if 'heading' in df.columns:
        df['_instant_heading_change'] = df.apply(
            lambda row: compute_heading_change(
                row['_heading_shift'], row['heading']
            ) if pd.notna(row['_heading_shift']) else 0,
            axis=1
        )
    else:
        df['_instant_heading_change'] = 0

    # Compute rolling features for each window
    for window in windows:
        window_str = f'{window}s'

        # Speed rolling statistics
        speed_rolling = df[speed_col].rolling(window_str, min_periods=1)

        df[f'speed_avg_{window}s'] = speed_rolling.mean()
        df[f'speed_std_{window}s'] = speed_rolling.std().fillna(0)
        df[f'speed_max_{window}s'] = speed_rolling.max()
        df[f'speed_min_{window}s'] = speed_rolling.min()

        # Acceleration: (current_speed - speed_at_window_start) / window
        # Approximated using the difference from rolling mean
        speed_first = df[speed_col].rolling(window_str, min_periods=1).apply(
            lambda x: x.iloc[0] if len(x) > 0 else np.nan, raw=False
        )
        df[f'acceleration_{window}s'] = (df[speed_col] - speed_first) / window

        # Distance traveled over window (sum of instant distances)
        df[f'distance_traveled_{window}s'] = df['_instant_distance'].rolling(
            window_str, min_periods=1
        ).sum()

        # Total heading change over window
        df[f'heading_change_{window}s'] = df['_instant_heading_change'].rolling(
            window_str, min_periods=1
        ).sum()

    # Reset index and clean up temp columns
    df = df.reset_index(drop=True)
    df = df.drop(columns=[
        '_lat_shift', '_lon_shift', '_heading_shift',
        '_instant_distance', '_instant_heading_change'
    ], errors='ignore')

    return df


def compute_rolling_features(
    df: pd.DataFrame,
    vid_column: str = 'vid',
    windows: List[int] = None,
    show_progress: bool = True
) -> pd.DataFrame:
    """
    Compute rolling window features for all vehicles.

    Args:
        df: DataFrame with telemetry data, must have vid, timestamp_ms, lat, lon, speed_mph
        vid_column: Name of vehicle ID column
        windows: List of window sizes in seconds
        show_progress: Whether to show progress bar

    Returns:
        DataFrame with rolling features added for all vehicles
    """
    if windows is None:
        windows = ROLLING_WINDOWS

    # Ensure required columns exist
    required_cols = [vid_column, 'timestamp_ms', 'lat', 'lon', 'speed_mph']
    missing = [c for c in required_cols if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    # Sort by vehicle and time
    df = df.sort_values([vid_column, 'timestamp_ms'])

    # Process each vehicle
    vehicles = df[vid_column].unique()
    results = []

    iterator = tqdm(vehicles, desc="Computing rolling features") if show_progress else vehicles

    for vid in iterator:
        vehicle_df = df[df[vid_column] == vid].copy()
        vehicle_df = compute_rolling_features_for_vehicle(vehicle_df, windows)
        results.append(vehicle_df)

    return pd.concat(results, ignore_index=True)


def check_rolling_consistency(df: pd.DataFrame) -> Dict[str, any]:
    """
    Verify rolling windows are calculated correctly.

    Args:
        df: DataFrame with rolling features

    Returns:
        Dictionary with consistency check results
    """
    report = {}

    # Check that longer windows have more smoothing (typically lower std variation)
    if 'speed_std_30s' in df.columns and 'speed_std_300s' in df.columns:
        avg_std_30s = df['speed_std_30s'].mean()
        avg_std_300s = df['speed_std_300s'].mean()
        # Generally expect shorter windows to show more variability
        report['shorter_windows_more_variable'] = avg_std_30s >= avg_std_300s
        report['speed_std_30s_mean'] = avg_std_30s
        report['speed_std_300s_mean'] = avg_std_300s

    # Check speed averages are within raw speed range
    if 'speed_mph' in df.columns and 'speed_avg_60s' in df.columns:
        avg_diff = (df['speed_avg_60s'] - df['speed_mph']).abs()
        report['avg_60s_differs_from_instant_mean'] = avg_diff.mean()

    # Check distance traveled is non-negative
    for window in ROLLING_WINDOWS:
        col = f'distance_traveled_{window}s'
        if col in df.columns:
            negative_count = (df[col] < 0).sum()
            report[f'{col}_negative_count'] = negative_count

    # Check heading change is within expected range (0-180 per change)
    for window in ROLLING_WINDOWS:
        col = f'heading_change_{window}s'
        if col in df.columns:
            max_change = df[col].max()
            report[f'{col}_max'] = max_change

    return report
