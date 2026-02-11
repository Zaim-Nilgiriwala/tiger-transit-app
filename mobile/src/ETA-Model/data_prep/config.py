"""
Configuration constants for the data preparation pipeline.

Contains paths, feature lists, and filter rules for GBDT ETA model training.
"""

from pathlib import Path
from typing import List, Dict, Any

# =============================================================================
# FILE PATHS
# =============================================================================

# Base directory (relative to this file's location)
BASE_DIR = Path(__file__).parent.parent

DATA_PATHS = {
    # Input files
    'telemetry_dir': BASE_DIR / 'live_data',
    'arrivals_files': [
        BASE_DIR / 'raw_data' / 'Arrivals - Departures by Date (POST)_11_06_2025 12_00 AM_01_14_2026 12_00 AM_.csv',
        BASE_DIR / 'raw_data' / 'Arrivals - Departures by Date (POST)_01_14_2026 12_00 AM_01_23_2026 12_00 AM_.csv',
    ],
    'weather_file': BASE_DIR / 'raw_data' / 'weather_data.csv',
    'stops_file': BASE_DIR / 'stops.json',
    'gtfs_dir': BASE_DIR / 'gtfs_data',

    # Output files
    'output_dir': BASE_DIR / 'data_prep' / 'output',
    'train_file': BASE_DIR / 'data_prep' / 'output' / 'train.parquet',
    'val_file': BASE_DIR / 'data_prep' / 'output' / 'val.parquet',
    'test_file': BASE_DIR / 'data_prep' / 'output' / 'test.parquet',
    'quality_report': BASE_DIR / 'data_prep' / 'output' / 'quality_report.md',
    'historical_stats_file': BASE_DIR / 'data_prep' / 'output' / 'historical_stats.json',
}

# =============================================================================
# VEHICLE FILTERING
# =============================================================================

# Exclude these vehicle prefixes from training (different route characteristics)
EXCLUDED_VEHICLE_PREFIXES = ['jAUnt', 'Shuttle']

# Active service states for filtering
ACTIVE_SERVICE_STATES = [7, 71]  # Status codes indicating active trips

# Pattern ID to exclude (NIS = Not In Service)
NIS_PATTERN_ID = 9998

# =============================================================================
# ROLLING WINDOW FEATURES
# =============================================================================

# Window sizes in seconds for rolling features
ROLLING_WINDOWS = [30, 60, 90, 120, 180, 300]

# Rolling feature types to compute
ROLLING_SPEED_FEATURES = ['avg', 'std', 'max', 'min']
ROLLING_POSITION_FEATURES = ['distance_traveled', 'heading_change']

# =============================================================================
# TEMPORAL FEATURES
# =============================================================================

# Rush hour definitions (hours, 24h format)
RUSH_HOUR_MORNING_START = 7
RUSH_HOUR_MORNING_END = 9
RUSH_HOUR_EVENING_START = 16
RUSH_HOUR_EVENING_END = 18

# Class change times (hours and minutes)
CLASS_CHANGE_TIMES = [
    (8, 0), (8, 50), (9, 50), (10, 40), (11, 40), (12, 30),
    (13, 30), (14, 20), (15, 20), (16, 10),
]
CLASS_CHANGE_WINDOW_MINUTES = 10

# =============================================================================
# FEATURE COLUMNS
# =============================================================================

# Identifiers (not used as features, kept for debugging/analysis)
ID_COLUMNS = [
    'row_id',
    'vid',
    'timestamp_ms',
    'target_stop_id',
]

# Core features from telemetry
CORE_FEATURES = [
    'lat',
    'lon',
    'speed_mph',
    'heading_sin',
    'heading_cos',
    'passenger_count',
    'progress_to_next_stop',
    'current_delay_sec',
]

# Distance features
DISTANCE_FEATURES = [
    'route_distance_to_stop_miles',
    'haversine_distance_to_stop_m',
    'stops_remaining',
]

# Rolling window features (dynamically generated)
def get_rolling_feature_names() -> List[str]:
    """Generate list of all rolling feature column names."""
    features = []
    for window in ROLLING_WINDOWS:
        # Speed features
        for metric in ROLLING_SPEED_FEATURES:
            features.append(f'speed_{metric}_{window}s')
        # Position features
        features.append(f'distance_traveled_{window}s')
        features.append(f'heading_change_{window}s')
    return features

ROLLING_FEATURES = get_rolling_feature_names()

# Temporal features
TEMPORAL_FEATURES = [
    'hour_of_day',
    'minute_of_hour',
    'time_of_day_sin',
    'time_of_day_cos',
    'day_of_week',
    'is_weekend',
    'is_rush_hour',
    'is_class_change',
    'minutes_since_last_stop',
]

# Historical/statistical features
HISTORICAL_FEATURES = [
    'segment_avg_travel_time_sec',
    'segment_std_travel_time_sec',
    'stop_avg_dwell_time_sec',
    'vehicle_speed_factor',
]

# Weather features
WEATHER_FEATURES = [
    'temperature_c',
    'precipitation_mm',
    'precipitation_probability',
    'is_raining',
]

# Scheduled baseline
SCHEDULE_FEATURES = [
    'scheduled_time_to_stop_sec',
]

# Route identifier (categorical)
ROUTE_FEATURES = [
    'route_id',
]

# All feature columns
FEATURE_COLUMNS = (
    CORE_FEATURES +
    DISTANCE_FEATURES +
    ROLLING_FEATURES +
    TEMPORAL_FEATURES +
    HISTORICAL_FEATURES +
    WEATHER_FEATURES +
    SCHEDULE_FEATURES +
    ROUTE_FEATURES
)

# Target column
TARGET_COLUMN = 'time_to_arrival_sec'

# Categorical columns (for GBDT)
CATEGORICAL_COLUMNS = [
    'hour_of_day',
    'day_of_week',
    'route_id',
]

# =============================================================================
# FIELDS TO KEEP FROM RAW TELEMETRY
# =============================================================================

# Fields to extract from raw telemetry JSON
TELEMETRY_FIELDS_KEEP = {
    # Position
    'lt': 'lat',
    'ln': 'lon',
    'h': 'heading',
    'v': 'speed_mph',
    't': 'timestamp_ms',

    # Load
    'load': 'passenger_count',
    'capacity': 'vehicle_capacity',

    # Vehicle ID
    'vid': 'vid',

    # Service state (nested)
    'serviceState_rID': 'route_id',
    'serviceState_status': 'service_status',
    'serviceState_patternID': 'pattern_id',
    'serviceState_tripID': 'trip_id',
    'serviceState_nextStopPercentProgress': 'progress_to_next_stop',

    # Last stop (nested)
    'lastStop_stopID': 'last_stop_id',
    'lastStop_time': 'last_stop_time_ms',
    'lastStop_onTime': 'current_delay_sec',

    # ETA info (nested)
    'eta_stopID': 'target_stop_id',

    # Schedule info (nested)
    'schedule_stops': 'schedule_stops',
}

# =============================================================================
# DATA QUALITY THRESHOLDS
# =============================================================================

QUALITY_THRESHOLDS = {
    'min_join_success_rate': 50.0,  # Minimum % of telemetry matched to arrivals
    'max_label_missing_rate': 30.0,  # Maximum % of missing labels allowed
    'max_weather_missing_rate': 5.0,  # Maximum % of missing weather data
    'max_speed_out_of_range_rate': 1.0,  # Maximum % of speed values outside 0-80 mph
    'max_label_seconds': 3600,  # Maximum label value (1 hour)
    'min_label_seconds': 0,  # Minimum label value

    # Auburn, AL geographic bounds
    'lat_min': 32.5,
    'lat_max': 32.7,
    'lon_min': -85.6,
    'lon_max': -85.4,

    # Temperature bounds (Celsius)
    'temp_min': -10,
    'temp_max': 45,
}

# =============================================================================
# TRAIN/VAL/TEST SPLIT
# =============================================================================

SPLIT_RATIOS = {
    'train': 0.70,
    'val': 0.15,
    'test': 0.15,
}

# =============================================================================
# DATA TYPES FOR PARQUET
# =============================================================================

# Float32 for all continuous features (saves space)
FLOAT_COLUMNS = [col for col in FEATURE_COLUMNS if col not in CATEGORICAL_COLUMNS]

# Int8/Int16 for categorical columns
CATEGORICAL_DTYPES = {
    'hour_of_day': 'int8',
    'day_of_week': 'int8',
    'route_id': 'int16',
}
