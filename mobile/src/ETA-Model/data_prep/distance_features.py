"""
Distance feature calculations for the data preparation pipeline.

Computes route distances using GTFS data and Haversine fallback,
plus stops remaining count.
"""

import json
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .config import DATA_PATHS


@dataclass
class StopInfo:
    """Information about a transit stop."""
    id: str
    name: str
    lat: float
    lon: float
    code: str


def haversine_distance_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points in miles.

    Args:
        lat1, lon1: Coordinates of first point (degrees)
        lat2, lon2: Coordinates of second point (degrees)

    Returns:
        Distance in miles
    """
    R = 3958.8  # Earth's radius in miles

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2)

    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in meters."""
    return haversine_distance_miles(lat1, lon1, lat2, lon2) * 1609.34


class StopLookup:
    """Lookup table for stop information."""

    def __init__(self, stops_file: Path = None):
        """
        Load stops from JSON file.

        Args:
            stops_file: Path to stops.json file
        """
        self.stops: Dict[str, StopInfo] = {}
        self.stops_by_name: Dict[str, StopInfo] = {}

        if stops_file is None:
            stops_file = DATA_PATHS['stops_file']

        self._load_stops(stops_file)

    def _load_stops(self, stops_file: Path):
        """Load stops from JSON file."""
        if not stops_file.exists():
            print(f"Warning: stops file not found at {stops_file}")
            return

        with open(stops_file, 'r') as f:
            stops_data = json.load(f)

        for stop in stops_data:
            stop_info = StopInfo(
                id=str(stop['id']),
                name=stop['name'],
                lat=stop['lat'],
                lon=stop['lon'],
                code=stop.get('code', stop['id'])
            )
            self.stops[stop_info.id] = stop_info
            # Also index by name for arrivals matching
            self.stops_by_name[stop_info.name.lower()] = stop_info

    def get_stop(self, stop_id: str) -> Optional[StopInfo]:
        """Get stop info by ID."""
        return self.stops.get(str(stop_id))

    def get_stop_by_name(self, name: str) -> Optional[StopInfo]:
        """Get stop info by name (case insensitive)."""
        return self.stops_by_name.get(name.lower())

    def get_coordinates(self, stop_id: str) -> Optional[Tuple[float, float]]:
        """Get (lat, lon) for a stop ID."""
        stop = self.get_stop(stop_id)
        if stop:
            return (stop.lat, stop.lon)
        return None


class GTFSDistanceCalculator:
    """
    Calculate route distances using GTFS shapes data.

    Falls back to Haversine when route data is unavailable.
    """

    def __init__(self, gtfs_dir: Path = None, stops_lookup: StopLookup = None):
        """
        Load GTFS data for distance calculations.

        Args:
            gtfs_dir: Path to GTFS data directory
            stops_lookup: StopLookup instance (created if not provided)
        """
        if gtfs_dir is None:
            gtfs_dir = DATA_PATHS['gtfs_dir']

        self.gtfs_dir = Path(gtfs_dir)
        self.stops_lookup = stops_lookup or StopLookup()

        # Loaded data
        self._shapes: Dict[str, List[Tuple[float, float, float]]] = {}  # shape_id -> [(lat, lon, dist)]
        self._trip_to_shape: Dict[str, str] = {}
        self._stop_distances: Dict[str, Dict[str, float]] = {}  # trip_id -> {stop_id -> dist}
        self._stop_sequences: Dict[str, List[str]] = {}  # trip_id -> [stop_ids in order]

        self._load_gtfs()

    def _load_gtfs(self):
        """Load GTFS data files."""
        self._load_shapes()
        self._load_trips()
        self._load_stop_times()

    def _load_shapes(self):
        """Load route shapes from shapes.txt."""
        shapes_file = self.gtfs_dir / 'shapes.txt'
        if not shapes_file.exists():
            print(f"Warning: shapes.txt not found at {shapes_file}")
            return

        df = pd.read_csv(shapes_file)

        for shape_id, group in df.groupby('shape_id'):
            shape_id = str(shape_id).strip('"')
            points = []
            for _, row in group.sort_values('shape_pt_sequence').iterrows():
                points.append((
                    row['shape_pt_lat'],
                    row['shape_pt_lon'],
                    row['shape_dist_traveled']
                ))
            self._shapes[shape_id] = points

        print(f"Loaded {len(self._shapes)} route shapes")

    def _load_trips(self):
        """Load trip to shape mapping from trips.txt."""
        trips_file = self.gtfs_dir / 'trips.txt'
        if not trips_file.exists():
            print(f"Warning: trips.txt not found at {trips_file}")
            return

        df = pd.read_csv(trips_file)

        for _, row in df.iterrows():
            trip_id = str(row['trip_id']).strip('"')
            shape_id = str(row['shape_id']).strip('"')
            self._trip_to_shape[trip_id] = shape_id

        print(f"Loaded {len(self._trip_to_shape)} trip mappings")

    def _load_stop_times(self):
        """Load stop distances from stop_times.txt."""
        stop_times_file = self.gtfs_dir / 'stop_times.txt'
        if not stop_times_file.exists():
            print(f"Warning: stop_times.txt not found at {stop_times_file}")
            return

        df = pd.read_csv(stop_times_file)

        for trip_id, group in df.groupby('trip_id'):
            trip_id = str(trip_id).strip('"')
            sorted_group = group.sort_values('stop_sequence')

            self._stop_distances[trip_id] = {}
            self._stop_sequences[trip_id] = []

            for _, row in sorted_group.iterrows():
                stop_id = str(row['stop_id']).strip('"')
                dist = row.get('shape_dist_traveled', 0) or 0

                self._stop_distances[trip_id][stop_id] = dist
                self._stop_sequences[trip_id].append(stop_id)

        print(f"Loaded stop distances for {len(self._stop_distances)} trips")

    def _get_shape_points(self, trip_id: str) -> Optional[List[Tuple[float, float, float]]]:
        """Get shape points for a trip."""
        trip_id = str(trip_id).strip('"')
        shape_id = self._trip_to_shape.get(trip_id)
        if shape_id:
            return self._shapes.get(shape_id)
        return None

    def _snap_to_route(self, lat: float, lon: float, shape_points: List[Tuple[float, float, float]]) -> float:
        """
        Find the shape_dist_traveled at a given position by snapping to nearest point.

        Args:
            lat, lon: Position to snap
            shape_points: List of (lat, lon, dist_traveled) tuples

        Returns:
            Estimated shape_dist_traveled at the position
        """
        if not shape_points:
            return 0.0

        min_dist = float('inf')
        nearest_traveled = 0.0

        for i, (pt_lat, pt_lon, pt_dist) in enumerate(shape_points):
            dist = haversine_distance_miles(lat, lon, pt_lat, pt_lon)
            if dist < min_dist:
                min_dist = dist
                # Interpolate between this point and next for better accuracy
                if i < len(shape_points) - 1:
                    next_pt = shape_points[i + 1]
                    nearest_traveled = self._interpolate_distance(
                        lat, lon,
                        (pt_lat, pt_lon, pt_dist),
                        next_pt
                    )
                else:
                    nearest_traveled = pt_dist

        return nearest_traveled

    def _interpolate_distance(
        self,
        lat: float,
        lon: float,
        p1: Tuple[float, float, float],
        p2: Tuple[float, float, float]
    ) -> float:
        """Interpolate shape_dist_traveled between two consecutive points."""
        # Vector from p1 to p2
        dx = p2[1] - p1[1]  # lon
        dy = p2[0] - p1[0]  # lat

        # Vector from p1 to query point
        px = lon - p1[1]
        py = lat - p1[0]

        # Project query point onto segment
        segment_len_sq = dx * dx + dy * dy
        if segment_len_sq < 1e-10:
            return p1[2]

        t = max(0, min(1, (px * dx + py * dy) / segment_len_sq))

        return p1[2] + t * (p2[2] - p1[2])

    def calculate_route_distance(
        self,
        bus_lat: float,
        bus_lon: float,
        target_stop_id: str,
        trip_id: str = None
    ) -> Optional[float]:
        """
        Calculate route distance from bus to target stop in miles.

        Args:
            bus_lat, bus_lon: Current bus position
            target_stop_id: Target stop ID
            trip_id: Trip ID (optional, for GTFS lookup)

        Returns:
            Distance in miles, or None if data unavailable
        """
        target_stop_id = str(target_stop_id)

        # Try GTFS-based calculation if trip_id provided
        if trip_id:
            shape_points = self._get_shape_points(trip_id)
            if shape_points:
                # Get stop's distance along route
                trip_stops = self._stop_distances.get(str(trip_id).strip('"'), {})
                stop_dist = trip_stops.get(target_stop_id)

                if stop_dist is not None:
                    # Find bus's position on route
                    bus_dist = self._snap_to_route(bus_lat, bus_lon, shape_points)

                    # Calculate remaining distance
                    remaining = stop_dist - bus_dist

                    # Handle circular routes (bus may have passed the stop)
                    if remaining < 0 and shape_points:
                        total_route_dist = shape_points[-1][2]
                        remaining = total_route_dist + remaining

                    return max(0, remaining)

        # Fallback to Haversine
        stop_coords = self.stops_lookup.get_coordinates(target_stop_id)
        if stop_coords:
            return haversine_distance_miles(bus_lat, bus_lon, stop_coords[0], stop_coords[1])

        return None

    def count_stops_remaining(
        self,
        current_stop_id: str,
        target_stop_id: str,
        trip_id: str
    ) -> int:
        """
        Count the number of stops between current and target.

        Args:
            current_stop_id: Current/last stop ID
            target_stop_id: Target stop ID
            trip_id: Trip ID

        Returns:
            Number of stops between current and target (0 if not found)
        """
        trip_id = str(trip_id).strip('"')
        current_stop_id = str(current_stop_id)
        target_stop_id = str(target_stop_id)

        stop_sequence = self._stop_sequences.get(trip_id, [])
        if not stop_sequence:
            return 0

        try:
            current_idx = stop_sequence.index(current_stop_id)
            target_idx = stop_sequence.index(target_stop_id)

            if target_idx > current_idx:
                return target_idx - current_idx
            else:
                # Circular route or past target
                return len(stop_sequence) - current_idx + target_idx
        except ValueError:
            return 0


def compute_distance_features(
    df: pd.DataFrame,
    gtfs_calculator: GTFSDistanceCalculator = None,
    show_progress: bool = True
) -> pd.DataFrame:
    """
    Compute distance features for all records.

    Args:
        df: DataFrame with lat, lon, target_stop_id, trip_id, last_stop_id columns
        gtfs_calculator: GTFSDistanceCalculator instance (created if not provided)
        show_progress: Whether to show progress

    Returns:
        DataFrame with distance features added
    """
    if gtfs_calculator is None:
        gtfs_calculator = GTFSDistanceCalculator()

    df = df.copy()

    # Initialize columns
    df['route_distance_to_stop_miles'] = np.nan
    df['haversine_distance_to_stop_m'] = np.nan
    df['stops_remaining'] = 0

    total = len(df)
    progress_step = max(1, total // 100)

    for idx, row in df.iterrows():
        if show_progress and idx % progress_step == 0:
            print(f"Computing distance features: {idx}/{total} ({100*idx/total:.1f}%)", end='\r')

        lat = row.get('lat')
        lon = row.get('lon')
        target_stop_id = row.get('target_stop_id')
        trip_id = row.get('trip_id')
        last_stop_id = row.get('last_stop_id')

        if pd.isna(lat) or pd.isna(lon) or pd.isna(target_stop_id):
            continue

        # Route distance (GTFS-based)
        route_dist = gtfs_calculator.calculate_route_distance(
            lat, lon, target_stop_id, trip_id
        )
        if route_dist is not None:
            df.at[idx, 'route_distance_to_stop_miles'] = route_dist

        # Haversine distance (straight-line fallback)
        stop_coords = gtfs_calculator.stops_lookup.get_coordinates(str(target_stop_id))
        if stop_coords:
            h_dist = haversine_distance_meters(lat, lon, stop_coords[0], stop_coords[1])
            df.at[idx, 'haversine_distance_to_stop_m'] = h_dist

        # Stops remaining
        if trip_id and last_stop_id:
            stops_rem = gtfs_calculator.count_stops_remaining(
                last_stop_id, target_stop_id, trip_id
            )
            df.at[idx, 'stops_remaining'] = stops_rem

    if show_progress:
        print(f"Computing distance features: {total}/{total} (100.0%)")

    return df
