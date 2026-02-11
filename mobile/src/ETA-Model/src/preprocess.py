"""
Data Preprocessing and Feature Engineering for ETA Prediction

Handles:
- Loading raw CSV/JSONL data
- Feature extraction and engineering
- Normalization (per-route)
- Training data generation with 3-stop labels
"""

import json
import math
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler


@dataclass
class NormalizationParams:
    """Stores normalization parameters for a route's features."""
    lat_mean: float = 0.0
    lat_std: float = 1.0
    lon_mean: float = 0.0
    lon_std: float = 1.0
    speed_mean: float = 0.0
    speed_std: float = 1.0
    heading_mean: float = 0.0
    heading_std: float = 1.0
    load_mean: float = 0.0
    load_std: float = 1.0
    progress_mean: float = 0.0
    progress_std: float = 1.0
    distance_mean: float = 0.0
    distance_std: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> 'NormalizationParams':
        return cls(**d)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

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


def bearing_to_point(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate bearing from point 1 to point 2.

    Args:
        lat1, lon1: Origin coordinates (degrees)
        lat2, lon2: Destination coordinates (degrees)

    Returns:
        Bearing in degrees (0-360)
    """
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_lambda = math.radians(lon2 - lon1)

    x = math.sin(delta_lambda) * math.cos(phi2)
    y = (math.cos(phi1) * math.sin(phi2) -
         math.sin(phi1) * math.cos(phi2) * math.cos(delta_lambda))

    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360) % 360


def heading_alignment(heading: float, bearing: float) -> float:
    """
    Calculate how aligned the heading is with the bearing to destination.

    Args:
        heading: Current heading (degrees)
        bearing: Bearing to destination (degrees)

    Returns:
        Alignment score between -1 (opposite) and 1 (aligned)
    """
    diff = abs(heading - bearing)
    if diff > 180:
        diff = 360 - diff
    return math.cos(math.radians(diff))


def load_stops(stops_path: str) -> dict:
    """
    Load stop data from JSON file.

    Args:
        stops_path: Path to stops.json

    Returns:
        Dictionary mapping stop_id (str) -> (lat, lon, name)
    """
    with open(stops_path, 'r') as f:
        stops_list = json.load(f)

    return {
        str(stop['id']): (stop['lat'], stop['lon'], stop.get('name', ''))
        for stop in stops_list
    }


def load_raw_data(data_path: str) -> pd.DataFrame:
    """
    Load raw data from CSV file.

    Args:
        data_path: Path to CSV file

    Returns:
        DataFrame with raw telemetry data
    """
    df = pd.read_csv(data_path)

    # Filter out invalid records
    df = df[df['patternId'] != 9998]  # Not at depot
    df = df[df['nextStopId'] != 0]     # Has valid next stop

    return df


def filter_by_route(df: pd.DataFrame, route_id: int) -> pd.DataFrame:
    """Filter data to a specific route."""
    return df[df['routeId'] == route_id].copy()


def extract_features_for_prediction(
    lat: float,
    lon: float,
    heading: float,
    speed: float,
    load: int,
    progress: float,
    timestamp_ms: int,
    next_stop_coords: list[tuple[float, float]],
    norm_params: Optional[NormalizationParams] = None
) -> np.ndarray:
    """
    Extract features for a single prediction request.

    Args:
        lat, lon: Current bus position
        heading: Current heading (degrees)
        speed: Current speed
        load: Passenger count
        progress: Route progress (0-1)
        timestamp_ms: Current timestamp in milliseconds
        next_stop_coords: List of (lat, lon) for next 3 stops
        norm_params: Optional normalization parameters

    Returns:
        Feature array ready for model input
    """
    # Time features
    from datetime import datetime
    dt = datetime.fromtimestamp(timestamp_ms / 1000)
    time_of_day = dt.hour * 60 + dt.minute  # Minutes since midnight
    day_of_week = dt.weekday()

    # Calculate distance and alignment to each stop
    distances = []
    alignments = []
    for stop_lat, stop_lon in next_stop_coords:
        dist = haversine_distance(lat, lon, stop_lat, stop_lon)
        bear = bearing_to_point(lat, lon, stop_lat, stop_lon)
        align = heading_alignment(heading, bear)
        distances.append(dist)
        alignments.append(align)

    # Build feature vector
    features = np.array([
        lat,
        lon,
        heading / 360.0,  # Normalize heading to 0-1
        speed,
        load,
        progress,
        time_of_day / 1440.0,  # Normalize to 0-1 (1440 minutes in day)
        day_of_week / 6.0,     # Normalize to 0-1
        distances[0],
        distances[1],
        distances[2],
        alignments[0],
        alignments[1],
        alignments[2],
        1,  # stops_remaining for stop 1
        2,  # stops_remaining for stop 2
        3,  # stops_remaining for stop 3
    ], dtype=np.float32)

    # Apply normalization if provided
    if norm_params:
        features = normalize_features(features, norm_params)

    return features


def normalize_features(features: np.ndarray, params: NormalizationParams) -> np.ndarray:
    """
    Apply z-score normalization to features.

    Args:
        features: Raw feature array
        params: Normalization parameters

    Returns:
        Normalized feature array
    """
    normalized = features.copy()

    # Normalize each relevant feature
    normalized[0] = (features[0] - params.lat_mean) / (params.lat_std + 1e-8)
    normalized[1] = (features[1] - params.lon_mean) / (params.lon_std + 1e-8)
    normalized[3] = (features[3] - params.speed_mean) / (params.speed_std + 1e-8)
    normalized[4] = (features[4] - params.load_mean) / (params.load_std + 1e-8)
    normalized[5] = (features[5] - params.progress_mean) / (params.progress_std + 1e-8)

    # Normalize distances
    for i in [8, 9, 10]:  # distance indices
        normalized[i] = (features[i] - params.distance_mean) / (params.distance_std + 1e-8)

    return normalized


def compute_normalization_params(df: pd.DataFrame, stops: dict) -> NormalizationParams:
    """
    Compute normalization parameters from training data.

    Args:
        df: Training DataFrame
        stops: Stop coordinate dictionary

    Returns:
        NormalizationParams with computed statistics
    """
    # Compute distances for all records
    distances = []
    for _, row in df.iterrows():
        stop_id = str(int(row['nextStopId']))
        if stop_id in stops:
            dist = haversine_distance(
                row['lat'], row['lon'],
                stops[stop_id][0], stops[stop_id][1]
            )
            distances.append(dist)

    distances = np.array(distances) if distances else np.array([0])

    return NormalizationParams(
        lat_mean=df['lat'].mean(),
        lat_std=df['lat'].std(),
        lon_mean=df['lon'].mean(),
        lon_std=df['lon'].std(),
        speed_mean=df['speed'].mean(),
        speed_std=df['speed'].std() if df['speed'].std() > 0 else 1.0,
        heading_mean=df['heading'].mean(),
        heading_std=df['heading'].std() if df['heading'].std() > 0 else 1.0,
        load_mean=df['load'].mean(),
        load_std=df['load'].std() if df['load'].std() > 0 else 1.0,
        progress_mean=df['progress'].mean() if 'progress' in df else 0.0,
        progress_std=df['progress'].std() if 'progress' in df and df['progress'].std() > 0 else 1.0,
        distance_mean=distances.mean(),
        distance_std=distances.std() if distances.std() > 0 else 1.0,
    )


def save_normalization_params(params: NormalizationParams, path: str):
    """Save normalization parameters to JSON file."""
    with open(path, 'w') as f:
        json.dump(params.to_dict(), f, indent=2)


def load_normalization_params(path: str) -> NormalizationParams:
    """Load normalization parameters from JSON file."""
    with open(path, 'r') as f:
        return NormalizationParams.from_dict(json.load(f))


class TrainingDataGenerator:
    """
    Generates training samples with 3-stop labels from raw vehicle trajectories.

    For each GPS packet, finds when the vehicle actually arrived at the next 3 stops
    and creates (features, [eta1, eta2, eta3]) training pairs.
    """

    def __init__(self, stops: dict, route_patterns: Optional[dict] = None):
        """
        Args:
            stops: Stop coordinate dictionary
            route_patterns: Optional dict mapping route_id -> ordered list of stop_ids
        """
        self.stops = stops
        self.route_patterns = route_patterns or {}

    def generate_samples(
        self,
        df: pd.DataFrame,
        route_id: int
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Generate training samples for a route.

        Args:
            df: Raw data DataFrame (already filtered to route)
            route_id: Route ID

        Returns:
            (X, y) tuple where X is features and y is labels [eta1, eta2, eta3]
        """
        # Group by vehicle
        vehicle_groups = df.groupby('vid')

        all_features = []
        all_labels = []

        for vid, group in vehicle_groups:
            # Sort by timestamp
            trajectory = group.sort_values('t').reset_index(drop=True)

            samples = self._process_trajectory(trajectory, route_id)
            for features, labels in samples:
                all_features.append(features)
                all_labels.append(labels)

        if not all_features:
            return np.array([]), np.array([])

        return np.array(all_features, dtype=np.float32), np.array(all_labels, dtype=np.float32)

    def _process_trajectory(
        self,
        trajectory: pd.DataFrame,
        route_id: int
    ) -> list[tuple[np.ndarray, np.ndarray]]:
        """Process a single vehicle's trajectory into training samples."""
        samples = []

        # Track stop arrivals by detecting lastStopId changes
        stop_arrivals = self._detect_stop_arrivals(trajectory)

        for i, row in trajectory.iterrows():
            if pd.isna(row['nextStopId']) or row['nextStopId'] == 0:
                continue

            current_time = row['t']
            current_stop = str(int(row['lastStopId'])) if row['lastStopId'] > 0 else None

            # Find next 3 stops and their actual arrival times
            next_stops_info = self._find_next_stops_arrivals(
                current_stop, current_time, stop_arrivals, 3
            )

            if len(next_stops_info) < 3:
                continue  # Need all 3 stops for complete sample

            # Extract features
            stop_coords = []
            etas = []
            for stop_id, arrival_time in next_stops_info:
                if stop_id not in self.stops:
                    break
                stop_coords.append((self.stops[stop_id][0], self.stops[stop_id][1]))
                etas.append((arrival_time - current_time) / 1000.0)  # Convert to seconds

            if len(stop_coords) < 3:
                continue

            features = extract_features_for_prediction(
                lat=row['lat'],
                lon=row['lon'],
                heading=row['heading'],
                speed=row['speed'],
                load=row['load'],
                progress=row['progress'] if 'progress' in row and row['progress'] >= 0 else 0.0,
                timestamp_ms=int(row['t']),
                next_stop_coords=stop_coords,
                norm_params=None  # Normalize later
            )

            samples.append((features, np.array(etas[:3])))

        return samples

    def _detect_stop_arrivals(self, trajectory: pd.DataFrame) -> list[tuple[str, int]]:
        """
        Detect when vehicle arrived at each stop based on lastStopId changes.

        Returns list of (stop_id, arrival_timestamp) tuples.
        """
        arrivals = []
        prev_stop = None

        for _, row in trajectory.iterrows():
            current_stop = str(int(row['lastStopId'])) if row['lastStopId'] > 0 else None

            if current_stop and current_stop != prev_stop:
                # Vehicle arrived at a new stop
                arrival_time = row['lastStopTime'] if pd.notna(row['lastStopTime']) else row['t']
                arrivals.append((current_stop, int(arrival_time)))

            prev_stop = current_stop

        return arrivals

    def _find_next_stops_arrivals(
        self,
        current_stop: Optional[str],
        current_time: int,
        stop_arrivals: list[tuple[str, int]],
        n: int
    ) -> list[tuple[str, int]]:
        """
        Find the next n stop arrivals after current time.

        Args:
            current_stop: Current/last stop ID
            current_time: Current timestamp
            stop_arrivals: List of (stop_id, arrival_time)
            n: Number of stops to find

        Returns:
            List of (stop_id, arrival_time) for next n stops
        """
        future_arrivals = [
            (stop_id, arrival_time)
            for stop_id, arrival_time in stop_arrivals
            if arrival_time > current_time
        ]

        return future_arrivals[:n]


# Feature names for documentation
FEATURE_NAMES = [
    'lat',
    'lon',
    'heading_normalized',
    'speed',
    'load',
    'progress',
    'time_of_day_normalized',
    'day_of_week_normalized',
    'distance_to_stop_1',
    'distance_to_stop_2',
    'distance_to_stop_3',
    'alignment_stop_1',
    'alignment_stop_2',
    'alignment_stop_3',
    'stops_remaining_1',
    'stops_remaining_2',
    'stops_remaining_3',
]

NUM_FEATURES = len(FEATURE_NAMES)
