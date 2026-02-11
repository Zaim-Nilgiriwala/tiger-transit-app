"""
Data Preparation Pipeline for GBDT ETA Prediction Model

This package transforms raw telemetry and arrivals data into an optimal
training dataset for a GBDT model to predict time until arrival at a stop.
"""

from .config import (
    EXCLUDED_VEHICLE_PREFIXES,
    ROLLING_WINDOWS,
    FEATURE_COLUMNS,
    CATEGORICAL_COLUMNS,
    DATA_PATHS,
)
from .filters import filter_vehicles, filter_active_trips
from .rolling_features import compute_rolling_features
from .distance_features import compute_distance_features
from .temporal_features import compute_temporal_features
from .weather_features import join_weather_data
from .historical_stats import compute_historical_stats
from .label_creator import create_labels
from .data_quality import (
    check_input_quality,
    verify_filters,
    check_feature_quality,
    check_label_quality,
    generate_quality_report,
)
from .pipeline import DataPipeline

__all__ = [
    # Config
    'EXCLUDED_VEHICLE_PREFIXES',
    'ROLLING_WINDOWS',
    'FEATURE_COLUMNS',
    'CATEGORICAL_COLUMNS',
    'DATA_PATHS',
    # Filters
    'filter_vehicles',
    'filter_active_trips',
    # Features
    'compute_rolling_features',
    'compute_distance_features',
    'compute_temporal_features',
    'join_weather_data',
    'compute_historical_stats',
    # Labels
    'create_labels',
    # Quality
    'check_input_quality',
    'verify_filters',
    'check_feature_quality',
    'check_label_quality',
    'generate_quality_report',
    # Pipeline
    'DataPipeline',
]
