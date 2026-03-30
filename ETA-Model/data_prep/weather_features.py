"""
Weather feature integration for the data preparation pipeline.

Joins hourly weather data with telemetry based on timestamp.
"""

from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd

from .config import DATA_PATHS


def load_weather_data(weather_file: Path = None) -> pd.DataFrame:
    """
    Load and preprocess weather data.

    Args:
        weather_file: Path to weather CSV file

    Returns:
        DataFrame with weather data indexed by hour
    """
    if weather_file is None:
        weather_file = DATA_PATHS['weather_file']

    weather_file = Path(weather_file)
    if not weather_file.exists():
        print(f"Warning: Weather file not found at {weather_file}")
        return pd.DataFrame()

    df = pd.read_csv(weather_file)

    # Rename columns to standard names
    column_mapping = {
        'precipitation': 'precipitation_mm',
        'precipitation_probability': 'precipitation_probability',
        'temperature_2m': 'temperature_c',
    }

    for old_name, new_name in column_mapping.items():
        if old_name in df.columns:
            df = df.rename(columns={old_name: new_name})

    # Parse timestamp and create hour index
    df['time'] = pd.to_datetime(df['time'], utc=True)
    # Remove timezone info so join works with naive telemetry timestamps
    df['time'] = df['time'].dt.tz_localize(None)
    df['hour'] = df['time'].dt.floor('h')

    # Calculate derived features
    if 'precipitation_mm' in df.columns:
        df['is_raining'] = (df['precipitation_mm'] > 0.1).astype(int)
    else:
        df['is_raining'] = 0

    # Keep only needed columns
    weather_cols = ['hour', 'temperature_c', 'precipitation_mm',
                    'precipitation_probability', 'is_raining']
    available_cols = [c for c in weather_cols if c in df.columns]
    df = df[available_cols].copy()

    # Remove duplicates (keep first per hour)
    df = df.drop_duplicates(subset=['hour'], keep='first')

    print(f"Loaded weather data: {len(df)} hours from {df['hour'].min()} to {df['hour'].max()}")

    return df


def check_weather_coverage(
    weather_df: pd.DataFrame,
    start_date: pd.Timestamp,
    end_date: pd.Timestamp
) -> Dict[str, any]:
    """
    Check weather data coverage for a date range.

    Args:
        weather_df: Weather DataFrame
        start_date: Start of date range
        end_date: End of date range

    Returns:
        Dictionary with coverage statistics
    """
    if weather_df.empty:
        return {
            'total_hours_needed': 0,
            'hours_available': 0,
            'missing_hours': 0,
            'coverage_rate': 0.0,
        }

    # Generate expected hours
    expected_hours = pd.date_range(start=start_date, end=end_date, freq='H')
    total_needed = len(expected_hours)

    # Check available
    available_hours = set(weather_df['hour'])
    expected_set = set(expected_hours)

    missing = expected_set - available_hours
    available = total_needed - len(missing)

    return {
        'total_hours_needed': total_needed,
        'hours_available': available,
        'missing_hours': len(missing),
        'coverage_rate': (available / total_needed * 100) if total_needed > 0 else 0.0,
        'first_missing_hours': sorted(list(missing))[:10] if missing else [],
    }


def join_weather_data(
    df: pd.DataFrame,
    weather_df: pd.DataFrame = None,
    timestamp_col: str = 'timestamp_ms'
) -> pd.DataFrame:
    """
    Join weather data to telemetry based on hour.

    Args:
        df: Telemetry DataFrame with timestamp column
        weather_df: Weather DataFrame (loaded if not provided)
        timestamp_col: Name of timestamp column in telemetry

    Returns:
        DataFrame with weather features added
    """
    df = df.copy()

    # Load weather if not provided
    if weather_df is None:
        weather_df = load_weather_data()

    if weather_df.empty:
        # Add empty weather columns
        df['temperature_c'] = np.nan
        df['precipitation_mm'] = np.nan
        df['precipitation_probability'] = np.nan
        df['is_raining'] = 0
        return df

    # Create hour column for joining (timezone-naive to match weather)
    df['_join_hour'] = pd.to_datetime(df[timestamp_col], unit='ms').dt.floor('h')

    # Merge on hour
    df = df.merge(
        weather_df,
        left_on='_join_hour',
        right_on='hour',
        how='left'
    )

    # Clean up
    df = df.drop(columns=['_join_hour', 'hour'], errors='ignore')

    # Fill missing with defaults
    df['temperature_c'] = df['temperature_c'].fillna(20.0)  # Room temp default
    df['precipitation_mm'] = df['precipitation_mm'].fillna(0.0)
    df['precipitation_probability'] = df['precipitation_probability'].fillna(0.0)
    df['is_raining'] = df['is_raining'].fillna(0).astype(int)

    return df


def check_weather_join(
    df: pd.DataFrame,
    weather_df: pd.DataFrame = None
) -> Dict[str, any]:
    """
    Check quality of weather join.

    Args:
        df: DataFrame after weather join
        weather_df: Original weather DataFrame

    Returns:
        Dictionary with join quality metrics
    """
    report = {}

    # Check weather columns exist
    weather_cols = ['temperature_c', 'precipitation_mm', 'precipitation_probability']
    report['weather_cols_present'] = all(col in df.columns for col in weather_cols)

    # Missing weather data
    if 'temperature_c' in df.columns:
        # Original null values before fillna would have been tracked
        # Check for values that are exactly the default (20.0)
        report['records_with_default_temp'] = (df['temperature_c'] == 20.0).sum()
        report['default_temp_rate'] = report['records_with_default_temp'] / len(df) * 100 if len(df) > 0 else 0

    # Temperature range check (Auburn, AL climate)
    if 'temperature_c' in df.columns:
        temps = df['temperature_c'].dropna()
        report['temp_min'] = temps.min() if len(temps) > 0 else np.nan
        report['temp_max'] = temps.max() if len(temps) > 0 else np.nan
        report['temp_mean'] = temps.mean() if len(temps) > 0 else np.nan
        report['temp_out_of_range'] = ((temps < -10) | (temps > 45)).sum()

    # Precipitation stats
    if 'precipitation_mm' in df.columns:
        precip = df['precipitation_mm'].dropna()
        report['precip_mean'] = precip.mean() if len(precip) > 0 else 0
        report['precip_max'] = precip.max() if len(precip) > 0 else 0
        report['rainy_records'] = (df.get('is_raining', pd.Series([0])) == 1).sum()
        report['rainy_rate'] = report['rainy_records'] / len(df) * 100 if len(df) > 0 else 0

    return report
