"""
Feature Extraction and Engineering for ETA Prediction

This module handles the extraction of all features from raw telemetry data,
including:
- Core features (distance, speed, heading, etc.)
- Temporal features (time of day, day of week)
- Historical features (segment times, boarding rates)
- Weather features
- Context features (game day, vehicle embeddings)
"""

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict, field

import numpy as np
import pandas as pd


@dataclass
class FeatureConfig:
    """Configuration for feature extraction."""
    num_stops: int = 3
    use_weather: bool = True
    use_historical: bool = True
    use_game_day: bool = True

    # Class change times (minutes since midnight)
    class_change_times: list[int] = field(default_factory=lambda: [
        480, 530, 590, 640, 700, 750, 810, 860, 920, 970  # Typical class end times
    ])
    class_change_window: int = 10  # Minutes before/after

    # Rush hour definition
    rush_hour_morning: tuple[int, int] = (420, 540)   # 7am - 9am
    rush_hour_evening: tuple[int, int] = (960, 1080)  # 4pm - 6pm


@dataclass
class NormalizationStats:
    """Statistics for feature normalization."""
    means: dict = field(default_factory=dict)
    stds: dict = field(default_factory=dict)

    def save(self, path: str):
        with open(path, 'w') as f:
            json.dump({'means': self.means, 'stds': self.stds}, f, indent=2)

    @classmethod
    def load(cls, path: str) -> 'NormalizationStats':
        with open(path, 'r') as f:
            data = json.load(f)
        return cls(means=data['means'], stds=data['stds'])


# Feature names for documentation and ordering
CORE_FEATURES = [
    'route_distance_stop1',
    'route_distance_stop2',
    'route_distance_stop3',
    'current_speed',
    'heading_sin',
    'heading_cos',
    'passenger_load',
    'stops_remaining_1',
    'stops_remaining_2',
    'stops_remaining_3',
    'route_progress',
    'current_delay',
    'scheduled_eta_stop1',
    'scheduled_eta_stop2',
    'scheduled_eta_stop3',
]

TEMPORAL_FEATURES = [
    'time_of_day_sin',
    'time_of_day_cos',
    'day_of_week_0',  # Monday
    'day_of_week_1',
    'day_of_week_2',
    'day_of_week_3',
    'day_of_week_4',
    'day_of_week_5',
    'day_of_week_6',  # Sunday
    'is_rush_hour',
    'is_class_change',
]

HISTORICAL_FEATURES = [
    'historical_segment_time_mean',
    'historical_segment_time_std',
    'stop1_boarding_rate',
    'stop2_boarding_rate',
    'stop3_boarding_rate',
    'predicted_dwell_time',
    'vehicle_speed_avg',
]

WEATHER_FEATURES = [
    'precipitation_mm',
    'is_raining',
    'temperature_c',
]

CONTEXT_FEATURES = [
    'is_game_day',
    'hours_to_kickoff',
]

ALL_FEATURES = CORE_FEATURES + TEMPORAL_FEATURES + HISTORICAL_FEATURES + WEATHER_FEATURES + CONTEXT_FEATURES
NUM_FEATURES = len(ALL_FEATURES)


def extract_temporal_features(timestamp_ms: int, config: FeatureConfig = None) -> dict:
    """
    Extract temporal features from a timestamp.

    Args:
        timestamp_ms: Unix timestamp in milliseconds
        config: Feature configuration

    Returns:
        Dictionary of temporal features
    """
    config = config or FeatureConfig()

    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    minutes = dt.hour * 60 + dt.minute
    day = dt.weekday()

    # Cyclical encoding for time of day
    time_sin = math.sin(2 * math.pi * minutes / 1440)
    time_cos = math.cos(2 * math.pi * minutes / 1440)

    # One-hot day of week
    day_onehot = [1.0 if i == day else 0.0 for i in range(7)]

    # Rush hour check
    is_rush = (
        (config.rush_hour_morning[0] <= minutes <= config.rush_hour_morning[1]) or
        (config.rush_hour_evening[0] <= minutes <= config.rush_hour_evening[1])
    )

    # Class change check
    is_class_change = any(
        abs(minutes - t) <= config.class_change_window
        for t in config.class_change_times
    )

    return {
        'time_of_day_sin': time_sin,
        'time_of_day_cos': time_cos,
        'day_of_week_0': day_onehot[0],
        'day_of_week_1': day_onehot[1],
        'day_of_week_2': day_onehot[2],
        'day_of_week_3': day_onehot[3],
        'day_of_week_4': day_onehot[4],
        'day_of_week_5': day_onehot[5],
        'day_of_week_6': day_onehot[6],
        'is_rush_hour': 1.0 if is_rush else 0.0,
        'is_class_change': 1.0 if is_class_change else 0.0,
    }


def extract_core_features(
    telemetry: dict,
    distances: list[float],
    stops_remaining: list[int],
    scheduled_etas: list[float] = None
) -> dict:
    """
    Extract core features from telemetry data.

    Args:
        telemetry: Raw telemetry packet
        distances: Route distances to each target stop (miles)
        stops_remaining: Number of stops until each target
        scheduled_etas: Scheduled ETAs in seconds (optional)

    Returns:
        Dictionary of core features
    """
    speed = telemetry.get('v', 0) or 0
    heading = telemetry.get('h', 0) or 0
    load = telemetry.get('load', 0) or 0
    progress = telemetry.get('serviceState', {}).get('nextStopPercentProgress', 0) or 0
    delay = telemetry.get('lastStop', {}).get('onTime', 0) or 0

    # Encode heading as sin/cos for continuity at 0/360
    heading_rad = math.radians(heading)

    features = {
        'route_distance_stop1': distances[0] if len(distances) > 0 else 0,
        'route_distance_stop2': distances[1] if len(distances) > 1 else 0,
        'route_distance_stop3': distances[2] if len(distances) > 2 else 0,
        'current_speed': speed,
        'heading_sin': math.sin(heading_rad),
        'heading_cos': math.cos(heading_rad),
        'passenger_load': load,
        'stops_remaining_1': stops_remaining[0] if len(stops_remaining) > 0 else 0,
        'stops_remaining_2': stops_remaining[1] if len(stops_remaining) > 1 else 0,
        'stops_remaining_3': stops_remaining[2] if len(stops_remaining) > 2 else 0,
        'route_progress': max(0, min(1, progress)),  # Clamp to [0, 1]
        'current_delay': delay,
    }

    # Add scheduled ETAs if available
    if scheduled_etas:
        features['scheduled_eta_stop1'] = scheduled_etas[0] if len(scheduled_etas) > 0 else 0
        features['scheduled_eta_stop2'] = scheduled_etas[1] if len(scheduled_etas) > 1 else 0
        features['scheduled_eta_stop3'] = scheduled_etas[2] if len(scheduled_etas) > 2 else 0
    else:
        features['scheduled_eta_stop1'] = 0
        features['scheduled_eta_stop2'] = 0
        features['scheduled_eta_stop3'] = 0

    return features


def extract_historical_features(
    route_id: int,
    from_stop: str,
    to_stops: list[str],
    hour: int,
    vehicle_id: str,
    historical_stats: dict
) -> dict:
    """
    Extract historical/statistical features.

    Args:
        route_id: Current route ID
        from_stop: Last visited stop ID
        to_stops: Target stop IDs
        hour: Current hour of day
        vehicle_id: Vehicle identifier
        historical_stats: Pre-computed historical statistics

    Returns:
        Dictionary of historical features
    """
    features = {
        'historical_segment_time_mean': 0.0,
        'historical_segment_time_std': 0.0,
        'stop1_boarding_rate': 0.0,
        'stop2_boarding_rate': 0.0,
        'stop3_boarding_rate': 0.0,
        'predicted_dwell_time': 0.0,
        'vehicle_speed_avg': 0.0,
    }

    if not historical_stats:
        return features

    # Segment times
    segment_key = (route_id, from_stop, to_stops[0] if to_stops else '', hour)
    if 'segment_times' in historical_stats:
        segment_data = historical_stats['segment_times'].get(str(segment_key), {})
        features['historical_segment_time_mean'] = segment_data.get('mean', 0)
        features['historical_segment_time_std'] = segment_data.get('std', 0)

    # Boarding rates
    if 'stop_boarding' in historical_stats:
        for i, stop_id in enumerate(to_stops[:3]):
            key = (stop_id, hour)
            rate = historical_stats['stop_boarding'].get(str(key), 0)
            features[f'stop{i+1}_boarding_rate'] = rate

    # Predicted dwell time (simple: boarding rate * avg time per passenger)
    avg_board_time = 3.0  # seconds per passenger
    total_boarding = sum(features[f'stop{i+1}_boarding_rate'] for i in range(3))
    features['predicted_dwell_time'] = total_boarding * avg_board_time

    # Vehicle speed average
    if 'vehicle_speeds' in historical_stats:
        features['vehicle_speed_avg'] = historical_stats['vehicle_speeds'].get(vehicle_id, 0)

    return features


def extract_weather_features(
    timestamp_ms: int,
    weather_data: pd.DataFrame = None
) -> dict:
    """
    Extract weather features for a given timestamp.

    Args:
        timestamp_ms: Unix timestamp in milliseconds
        weather_data: DataFrame with hourly weather data

    Returns:
        Dictionary of weather features
    """
    features = {
        'precipitation_mm': 0.0,
        'is_raining': 0.0,
        'temperature_c': 20.0,  # Default room temperature
    }

    if weather_data is None or weather_data.empty:
        return features

    # Find nearest hour in weather data
    target_time = pd.Timestamp(timestamp_ms, unit='ms')

    try:
        # Find closest timestamp
        idx = weather_data.index.get_indexer([target_time], method='nearest')[0]
        row = weather_data.iloc[idx]

        features['precipitation_mm'] = row.get('precipitation_mm', 0) or 0
        features['is_raining'] = 1.0 if features['precipitation_mm'] > 0.1 else 0.0
        features['temperature_c'] = row.get('temperature_c', 20) or 20
    except Exception:
        pass

    return features


def extract_game_day_features(
    timestamp_ms: int,
    game_schedule: list[dict] = None
) -> dict:
    """
    Extract game day features.

    Args:
        timestamp_ms: Unix timestamp in milliseconds
        game_schedule: List of {'date': 'YYYY-MM-DD', 'kickoff_time': 'HH:MM'} dicts

    Returns:
        Dictionary of game day features
    """
    features = {
        'is_game_day': 0.0,
        'hours_to_kickoff': 0.0,
    }

    if not game_schedule:
        return features

    current_dt = datetime.fromtimestamp(timestamp_ms / 1000)
    current_date = current_dt.date()

    for game in game_schedule:
        game_date = datetime.strptime(game['date'], '%Y-%m-%d').date()

        if game_date == current_date:
            features['is_game_day'] = 1.0

            # Calculate hours to kickoff
            kickoff_time = datetime.strptime(game['kickoff_time'], '%H:%M').time()
            kickoff_dt = datetime.combine(game_date, kickoff_time)
            delta = (kickoff_dt - current_dt).total_seconds() / 3600
            features['hours_to_kickoff'] = delta
            break

    return features


class FeatureExtractor:
    """
    Main class for extracting all features from telemetry data.
    """

    def __init__(
        self,
        config: FeatureConfig = None,
        historical_stats: dict = None,
        weather_data: pd.DataFrame = None,
        game_schedule: list[dict] = None,
        vehicle_mapping: dict[str, int] = None,
        distance_calculator=None  # GTFSRouteData instance
    ):
        """
        Initialize the feature extractor.

        Args:
            config: Feature configuration
            historical_stats: Pre-computed historical statistics
            weather_data: Weather DataFrame
            game_schedule: List of game day info
            vehicle_mapping: Mapping from vehicle ID string to integer
            distance_calculator: GTFSRouteData instance for distance calculation
        """
        self.config = config or FeatureConfig()
        self.historical_stats = historical_stats or {}
        self.weather_data = weather_data
        self.game_schedule = game_schedule or []
        self.vehicle_mapping = vehicle_mapping or {}
        self.distance_calculator = distance_calculator
        self.normalization_stats = None

    def extract(
        self,
        telemetry: dict,
        target_stops: list[str],
        distances: list[float] = None,
        stops_remaining: list[int] = None
    ) -> tuple[np.ndarray, int]:
        """
        Extract all features from a telemetry packet.

        Args:
            telemetry: Raw telemetry dictionary
            target_stops: List of target stop IDs
            distances: Pre-computed route distances (optional)
            stops_remaining: Pre-computed stop counts (optional)

        Returns:
            Tuple of (feature_array, vehicle_id_int)
        """
        timestamp = telemetry.get('ts', telemetry.get('t', 0))
        vehicle_id = telemetry.get('vid', '')
        route_id = telemetry.get('serviceState', {}).get('rID', 0)
        last_stop = str(telemetry.get('lastStop', {}).get('stopID', 0))

        # Calculate distances if not provided
        if distances is None:
            if self.distance_calculator:
                trip_id = telemetry.get('serviceState', {}).get('tripID', '')
                lat = telemetry.get('lt', 0)
                lon = telemetry.get('ln', 0)
                distances = []
                for stop_id in target_stops:
                    dist = self.distance_calculator.calculate_route_distance(
                        trip_id, lat, lon, stop_id
                    )
                    distances.append(dist if dist is not None else 0)
            else:
                distances = [0.0] * len(target_stops)

        # Calculate stops remaining if not provided
        if stops_remaining is None:
            stops_remaining = list(range(1, len(target_stops) + 1))

        # Get scheduled ETAs from telemetry
        schedule = telemetry.get('schedule', {})
        scheduled_stops = schedule.get('stops', [])
        scheduled_etas = []
        for stop in scheduled_stops[:3]:
            eta = stop.get('time', 0)
            if isinstance(eta, str):
                eta = int(eta)
            scheduled_etas.append(eta * 60)  # Convert minutes to seconds

        # Extract all feature groups
        hour = datetime.fromtimestamp(timestamp / 1000).hour

        core = extract_core_features(telemetry, distances, stops_remaining, scheduled_etas)
        temporal = extract_temporal_features(timestamp, self.config)
        historical = extract_historical_features(
            route_id, last_stop, target_stops, hour, vehicle_id, self.historical_stats
        )
        weather = extract_weather_features(timestamp, self.weather_data)
        game_day = extract_game_day_features(timestamp, self.game_schedule)

        # Combine all features
        all_features = {**core, **temporal, **historical, **weather, **game_day}

        # Convert to ordered array
        feature_array = np.array([
            all_features.get(name, 0.0) for name in ALL_FEATURES
        ], dtype=np.float32)

        # Get vehicle ID as integer
        vehicle_id_int = self.vehicle_mapping.get(vehicle_id, 0)

        return feature_array, vehicle_id_int

    def compute_normalization_stats(self, features: np.ndarray) -> NormalizationStats:
        """
        Compute normalization statistics from training data.

        Args:
            features: Array of shape (n_samples, n_features)

        Returns:
            NormalizationStats with means and stds
        """
        means = {}
        stds = {}

        for i, name in enumerate(ALL_FEATURES):
            col = features[:, i]
            means[name] = float(np.mean(col))
            stds[name] = float(np.std(col))
            if stds[name] < 1e-6:
                stds[name] = 1.0  # Avoid division by zero

        self.normalization_stats = NormalizationStats(means=means, stds=stds)
        return self.normalization_stats

    def normalize(self, features: np.ndarray) -> np.ndarray:
        """
        Apply z-score normalization.

        Args:
            features: Raw feature array

        Returns:
            Normalized feature array
        """
        if self.normalization_stats is None:
            return features

        normalized = np.zeros_like(features)
        for i, name in enumerate(ALL_FEATURES):
            mean = self.normalization_stats.means.get(name, 0)
            std = self.normalization_stats.stds.get(name, 1)
            normalized[:, i] = (features[:, i] - mean) / std

        return normalized


def build_vehicle_mapping(telemetry_files: list[str]) -> dict[str, int]:
    """
    Build a mapping from vehicle ID strings to integers.

    Args:
        telemetry_files: List of paths to JSONL telemetry files

    Returns:
        Dictionary mapping vehicle ID to integer index
    """
    vehicle_ids = set()

    for file_path in telemetry_files:
        with open(file_path, 'r') as f:
            for line in f:
                try:
                    data = json.loads(line)
                    vid = data.get('vid', '')
                    if vid:
                        vehicle_ids.add(vid)
                except json.JSONDecodeError:
                    continue

    # Sort for consistency
    sorted_ids = sorted(vehicle_ids)
    return {vid: i for i, vid in enumerate(sorted_ids)}


if __name__ == '__main__':
    # Test feature extraction
    config = FeatureConfig()

    # Test temporal features
    timestamp = int(datetime(2025, 10, 22, 8, 30).timestamp() * 1000)
    temporal = extract_temporal_features(timestamp, config)
    print("Temporal features:")
    for k, v in temporal.items():
        print(f"  {k}: {v:.4f}")

    # Test with mock telemetry
    mock_telemetry = {
        'ts': timestamp,
        'vid': 'jAUnt 1',
        'lt': 32.605,
        'ln': -85.485,
        'v': 15,
        'h': 90,
        'load': 5,
        'serviceState': {
            'rID': 24,
            'patternID': 1234,
            'tripID': '1895',
            'nextStopPercentProgress': 0.5,
        },
        'lastStop': {'stopID': 181, 'time': timestamp - 60000, 'onTime': -30},
        'eta': {'stopID': 152, 'seta': 300, 'eta': 290},
    }

    extractor = FeatureExtractor(
        config=config,
        vehicle_mapping={'jAUnt 1': 0, 'jAUnt 2': 1}
    )

    features, vid = extractor.extract(
        mock_telemetry,
        target_stops=['152', '47', '88'],
        distances=[0.5, 1.2, 2.0],
        stops_remaining=[1, 2, 3]
    )

    print(f"\nExtracted {len(features)} features")
    print(f"Vehicle ID: {vid}")
    print(f"Feature sample: {features[:5]}")
