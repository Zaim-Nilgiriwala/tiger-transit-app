"""
Vehicle and trip filtering for the data preparation pipeline.

Filters out jAUnt, Shuttle vehicles and inactive trips to keep only
main transit route data suitable for GBDT model training.
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

from .config import (
    EXCLUDED_VEHICLE_PREFIXES,
    ACTIVE_SERVICE_STATES,
    NIS_PATTERN_ID,
)


def filter_vehicles(df: pd.DataFrame, vid_column: str = 'vid') -> pd.DataFrame:
    """
    Filter out vehicles with excluded prefixes (jAUnt, Shuttle).

    Args:
        df: DataFrame containing vehicle data
        vid_column: Name of the vehicle ID column

    Returns:
        DataFrame with excluded vehicles removed
    """
    if vid_column not in df.columns:
        raise ValueError(f"Column '{vid_column}' not found in DataFrame")

    # Build regex pattern for exclusion
    pattern = '|'.join(EXCLUDED_VEHICLE_PREFIXES)

    # Filter out matching vehicles (case insensitive)
    mask = ~df[vid_column].str.contains(pattern, case=False, na=False)

    return df[mask].copy()


def filter_active_trips(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter to only active trips (status 7 or 71, not NIS pattern).

    Args:
        df: DataFrame with service_status, pattern_id, and target_stop_id columns

    Returns:
        DataFrame with only active trips
    """
    # Start with all True mask
    mask = pd.Series(True, index=df.index)

    # Filter by service status if column exists
    if 'service_status' in df.columns:
        mask &= df['service_status'].isin(ACTIVE_SERVICE_STATES)

    # Filter out NIS pattern if column exists
    if 'pattern_id' in df.columns:
        mask &= df['pattern_id'] != NIS_PATTERN_ID

    # Filter out records with no target stop
    if 'target_stop_id' in df.columns:
        mask &= (df['target_stop_id'] != 0) & (df['target_stop_id'].notna())

    return df[mask].copy()


def verify_filters(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    vid_column: str = 'vid'
) -> Dict[str, Any]:
    """
    Verify that vehicle filters worked correctly.

    Args:
        df_before: DataFrame before filtering
        df_after: DataFrame after filtering
        vid_column: Name of the vehicle ID column

    Returns:
        Dictionary with verification results

    Raises:
        AssertionError: If excluded vehicles are still present
    """
    pattern = '|'.join(EXCLUDED_VEHICLE_PREFIXES)

    # Count excluded vehicles before filtering
    excluded_before = df_before[
        df_before[vid_column].str.contains(pattern, case=False, na=False)
    ]

    # Check for excluded vehicles after filtering
    excluded_after = df_after[
        df_after[vid_column].str.contains(pattern, case=False, na=False)
    ]

    # Fail if any excluded vehicles remain
    if len(excluded_after) > 0:
        remaining = excluded_after[vid_column].unique().tolist()
        raise AssertionError(
            f"Filter failed: {len(excluded_after)} records with "
            f"jAUnt/Shuttle still present. Vehicles: {remaining[:5]}"
        )

    # Calculate statistics
    records_before = len(df_before)
    records_after = len(df_after)
    excluded_count = len(excluded_before)

    return {
        'records_before_filter': records_before,
        'records_after_filter': records_after,
        'excluded_count': excluded_count,
        'exclusion_rate': (excluded_count / records_before * 100) if records_before > 0 else 0,
        'retention_rate': (records_after / records_before * 100) if records_before > 0 else 0,
        'excluded_vehicles': excluded_before[vid_column].unique().tolist() if len(excluded_before) > 0 else [],
        'kept_vehicles': df_after[vid_column].unique().tolist() if len(df_after) > 0 else [],
    }


def apply_all_filters(df: pd.DataFrame, vid_column: str = 'vid') -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Apply all filters and return filtered DataFrame with verification report.

    Args:
        df: Raw DataFrame to filter
        vid_column: Name of the vehicle ID column

    Returns:
        Tuple of (filtered DataFrame, verification report)
    """
    # Store original for verification
    df_original = df.copy()

    # Apply vehicle filter
    df_filtered = filter_vehicles(df, vid_column)

    # Apply active trip filter
    df_filtered = filter_active_trips(df_filtered)

    # Verify filters
    verification = verify_filters(df_original, df_filtered, vid_column)

    return df_filtered, verification


def get_vehicle_stats(df: pd.DataFrame, vid_column: str = 'vid') -> Dict[str, Any]:
    """
    Get statistics about vehicles in the dataset.

    Args:
        df: DataFrame with vehicle data
        vid_column: Name of the vehicle ID column

    Returns:
        Dictionary with vehicle statistics
    """
    if vid_column not in df.columns or len(df) == 0:
        return {
            'total_vehicles': 0,
            'total_records': 0,
            'records_per_vehicle': {},
        }

    vehicles = df[vid_column].unique()
    records_per_vehicle = df.groupby(vid_column).size().to_dict()

    # Categorize vehicles
    pattern = '|'.join(EXCLUDED_VEHICLE_PREFIXES)
    excluded_vehicles = [v for v in vehicles if any(
        prefix.lower() in str(v).lower() for prefix in EXCLUDED_VEHICLE_PREFIXES
    )]
    main_vehicles = [v for v in vehicles if v not in excluded_vehicles]

    return {
        'total_vehicles': len(vehicles),
        'main_route_vehicles': len(main_vehicles),
        'excluded_vehicles': len(excluded_vehicles),
        'total_records': len(df),
        'records_per_vehicle': records_per_vehicle,
        'main_vehicle_list': sorted(main_vehicles),
        'excluded_vehicle_list': sorted(excluded_vehicles),
    }
