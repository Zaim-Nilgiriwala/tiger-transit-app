"""
Temporal feature extraction for the data preparation pipeline.

Computes time-based features including hour, day of week, cyclical encoding,
rush hour indicators, and class change indicators.
"""

import math
from datetime import datetime
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd

from .config import (
    RUSH_HOUR_MORNING_START,
    RUSH_HOUR_MORNING_END,
    RUSH_HOUR_EVENING_START,
    RUSH_HOUR_EVENING_END,
    CLASS_CHANGE_TIMES,
    CLASS_CHANGE_WINDOW_MINUTES,
)


def is_rush_hour(hour: int, minute: int = 0) -> bool:
    """
    Check if the given time is during rush hour.

    Rush hours:
    - Morning: 7-9 AM
    - Evening: 4-6 PM

    Args:
        hour: Hour of day (0-23)
        minute: Minute of hour (0-59)

    Returns:
        True if during rush hour
    """
    total_minutes = hour * 60 + minute
    morning_start = RUSH_HOUR_MORNING_START * 60
    morning_end = RUSH_HOUR_MORNING_END * 60
    evening_start = RUSH_HOUR_EVENING_START * 60
    evening_end = RUSH_HOUR_EVENING_END * 60

    return (morning_start <= total_minutes < morning_end) or \
           (evening_start <= total_minutes < evening_end)


def is_class_change(hour: int, minute: int, window_minutes: int = None) -> bool:
    """
    Check if the given time is near a class change time.

    Args:
        hour: Hour of day (0-23)
        minute: Minute of hour (0-59)
        window_minutes: Window around class change time (default from config)

    Returns:
        True if near a class change time
    """
    if window_minutes is None:
        window_minutes = CLASS_CHANGE_WINDOW_MINUTES

    current_minutes = hour * 60 + minute

    for class_hour, class_minute in CLASS_CHANGE_TIMES:
        class_minutes = class_hour * 60 + class_minute
        if abs(current_minutes - class_minutes) <= window_minutes:
            return True

    return False


def cyclical_encode(value: float, max_value: float) -> Tuple[float, float]:
    """
    Encode a cyclical value (like time) using sin/cos.

    This handles wrap-around properly (e.g., 23:59 is close to 00:00).

    Args:
        value: The value to encode
        max_value: The maximum value (e.g., 1440 for minutes in a day)

    Returns:
        Tuple of (sin_encoding, cos_encoding)
    """
    angle = 2 * math.pi * value / max_value
    return math.sin(angle), math.cos(angle)


def extract_temporal_features_single(timestamp_ms: int) -> Dict[str, float]:
    """
    Extract temporal features from a single timestamp.

    Args:
        timestamp_ms: Unix timestamp in milliseconds

    Returns:
        Dictionary of temporal features
    """
    dt = datetime.fromtimestamp(timestamp_ms / 1000)

    hour = dt.hour
    minute = dt.minute
    day_of_week = dt.weekday()  # 0=Monday, 6=Sunday

    # Minutes since midnight for cyclical encoding
    minutes_since_midnight = hour * 60 + minute

    # Cyclical encoding of time of day
    time_sin, time_cos = cyclical_encode(minutes_since_midnight, 1440)

    return {
        'hour_of_day': hour,
        'minute_of_hour': minute,
        'time_of_day_sin': time_sin,
        'time_of_day_cos': time_cos,
        'day_of_week': day_of_week,
        'is_weekend': 1 if day_of_week >= 5 else 0,
        'is_rush_hour': 1 if is_rush_hour(hour, minute) else 0,
        'is_class_change': 1 if is_class_change(hour, minute) else 0,
    }


def compute_minutes_since_last_stop(
    current_timestamp_ms: int,
    last_stop_time_ms: int
) -> float:
    """
    Calculate minutes since the bus departed the last stop.

    Args:
        current_timestamp_ms: Current timestamp in milliseconds
        last_stop_time_ms: Timestamp when bus left last stop (milliseconds)

    Returns:
        Minutes since last stop (0 if invalid)
    """
    if pd.isna(last_stop_time_ms) or last_stop_time_ms <= 0:
        return 0.0

    if pd.isna(current_timestamp_ms) or current_timestamp_ms <= 0:
        return 0.0

    diff_ms = current_timestamp_ms - last_stop_time_ms

    # Sanity check - should be positive and reasonable (< 1 hour)
    if diff_ms < 0 or diff_ms > 3600000:
        return 0.0

    return diff_ms / 60000.0  # Convert to minutes


def compute_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute temporal features for all records.

    Args:
        df: DataFrame with timestamp_ms and last_stop_time_ms columns

    Returns:
        DataFrame with temporal features added
    """
    df = df.copy()

    # Vectorized datetime extraction
    df['_datetime'] = pd.to_datetime(df['timestamp_ms'], unit='ms')

    # Extract components
    df['hour_of_day'] = df['_datetime'].dt.hour
    df['minute_of_hour'] = df['_datetime'].dt.minute
    df['day_of_week'] = df['_datetime'].dt.dayofweek  # 0=Monday

    # Weekend flag
    df['is_weekend'] = (df['day_of_week'] >= 5).astype(int)

    # Minutes since midnight for cyclical encoding
    minutes_since_midnight = df['hour_of_day'] * 60 + df['minute_of_hour']

    # Cyclical encoding
    df['time_of_day_sin'] = np.sin(2 * np.pi * minutes_since_midnight / 1440)
    df['time_of_day_cos'] = np.cos(2 * np.pi * minutes_since_midnight / 1440)

    # Rush hour (vectorized)
    morning_rush = (df['hour_of_day'] >= RUSH_HOUR_MORNING_START) & \
                   (df['hour_of_day'] < RUSH_HOUR_MORNING_END)
    evening_rush = (df['hour_of_day'] >= RUSH_HOUR_EVENING_START) & \
                   (df['hour_of_day'] < RUSH_HOUR_EVENING_END)
    df['is_rush_hour'] = (morning_rush | evening_rush).astype(int)

    # Class change (vectorized approximation)
    # Check if within window of any class change time
    df['is_class_change'] = 0
    for class_hour, class_minute in CLASS_CHANGE_TIMES:
        class_minutes = class_hour * 60 + class_minute
        time_diff = np.abs(minutes_since_midnight - class_minutes)
        df.loc[time_diff <= CLASS_CHANGE_WINDOW_MINUTES, 'is_class_change'] = 1

    # Minutes since last stop
    if 'last_stop_time_ms' in df.columns:
        time_diff = df['timestamp_ms'] - df['last_stop_time_ms']
        # Set to 0 for invalid values
        time_diff = time_diff.where(
            (time_diff > 0) & (time_diff < 3600000),  # Valid: 0 to 1 hour
            0
        )
        df['minutes_since_last_stop'] = time_diff / 60000.0
    else:
        df['minutes_since_last_stop'] = 0.0

    # Clean up temporary column
    df = df.drop(columns=['_datetime'], errors='ignore')

    return df


def get_schedule_time_to_stop(schedule_stops: List[Dict], target_stop_id: str) -> float:
    """
    Extract scheduled time to target stop from schedule data.

    Args:
        schedule_stops: List of schedule stop dictionaries from telemetry
        target_stop_id: Target stop ID

    Returns:
        Scheduled time to stop in seconds (0 if not found)
    """
    if not schedule_stops:
        return 0.0

    target_stop_id = str(target_stop_id)

    for stop in schedule_stops:
        stop_id = str(stop.get('id', ''))
        if stop_id == target_stop_id:
            # Time is in minutes since midnight
            time_minutes = stop.get('time')
            if time_minutes is not None:
                try:
                    return float(time_minutes) * 60  # Convert to seconds
                except (ValueError, TypeError):
                    return 0.0

    return 0.0


def add_scheduled_baseline(
    df: pd.DataFrame,
    schedule_col: str = 'schedule_stops'
) -> pd.DataFrame:
    """
    Add scheduled time to stop baseline feature.

    Args:
        df: DataFrame with schedule_stops and target_stop_id columns
        schedule_col: Name of schedule stops column

    Returns:
        DataFrame with scheduled_time_to_stop_sec added
    """
    df = df.copy()

    if schedule_col not in df.columns or 'target_stop_id' not in df.columns:
        df['scheduled_time_to_stop_sec'] = 0.0
        return df

    # Current time of day in minutes since midnight
    if '_datetime' not in df.columns:
        df['_datetime'] = pd.to_datetime(df['timestamp_ms'], unit='ms')

    current_minutes = df['_datetime'].dt.hour * 60 + df['_datetime'].dt.minute

    scheduled_times = []
    for idx, row in df.iterrows():
        schedule_stops = row.get(schedule_col)
        target_stop_id = row.get('target_stop_id')

        if isinstance(schedule_stops, list) and target_stop_id:
            sched_time = get_schedule_time_to_stop(schedule_stops, target_stop_id)
            # Convert from minutes-since-midnight to time-until-arrival
            if sched_time > 0:
                curr_min = current_minutes.iloc[idx] if hasattr(current_minutes, 'iloc') else current_minutes
                sched_min = sched_time / 60
                diff_sec = (sched_min - curr_min) * 60
                # Handle negative (past) - clamp to 0
                scheduled_times.append(max(0, diff_sec))
            else:
                scheduled_times.append(0.0)
        else:
            scheduled_times.append(0.0)

    df['scheduled_time_to_stop_sec'] = scheduled_times
    df = df.drop(columns=['_datetime'], errors='ignore')

    return df
