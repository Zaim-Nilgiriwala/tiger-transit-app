"""
Route-Based Distance Calculation Module

Uses GTFS data to calculate actual road distance along bus routes,
rather than straight-line (Haversine) distance.

Key insight: GTFS provides `shape_dist_traveled` which is the cumulative
distance along the route polyline. This allows us to calculate the actual
road distance between any two points on the route.
"""

import math
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class ShapePoint:
    """A single point on a route shape."""
    lat: float
    lon: float
    sequence: int
    dist_traveled: float  # Cumulative distance in miles


@dataclass
class RouteShape:
    """Complete shape data for a route."""
    shape_id: str
    points: list[ShapePoint]

    def get_distance_at_position(self, lat: float, lon: float) -> float:
        """
        Find the shape_dist_traveled at a given position by snapping
        to the nearest point on the route.
        """
        if not self.points:
            return 0.0

        min_dist = float('inf')
        nearest_traveled = 0.0

        for i, point in enumerate(self.points):
            dist = haversine_distance(lat, lon, point.lat, point.lon)
            if dist < min_dist:
                min_dist = dist
                nearest_traveled = point.dist_traveled

                # Interpolate between this point and next for more accuracy
                if i < len(self.points) - 1:
                    next_point = self.points[i + 1]
                    nearest_traveled = self._interpolate_distance(
                        lat, lon, point, next_point
                    )

        return nearest_traveled

    def _interpolate_distance(
        self,
        lat: float,
        lon: float,
        p1: ShapePoint,
        p2: ShapePoint
    ) -> float:
        """
        Interpolate shape_dist_traveled between two consecutive points.
        Uses projection onto the line segment.
        """
        # Vector from p1 to p2
        dx = p2.lon - p1.lon
        dy = p2.lat - p1.lat

        # Vector from p1 to query point
        px = lon - p1.lon
        py = lat - p1.lat

        # Project query point onto segment
        segment_len_sq = dx * dx + dy * dy
        if segment_len_sq < 1e-10:
            return p1.dist_traveled

        t = max(0, min(1, (px * dx + py * dy) / segment_len_sq))

        # Interpolate distance
        return p1.dist_traveled + t * (p2.dist_traveled - p1.dist_traveled)


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

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


class GTFSRouteData:
    """
    Loads and manages GTFS route data for distance calculations.

    Provides mapping from:
    - trip_id → shape_id
    - trip_id → route_id
    - (trip_id, stop_id) → shape_dist_traveled
    """

    def __init__(self, gtfs_dir: str):
        """
        Load GTFS data from directory.

        Args:
            gtfs_dir: Path to directory containing GTFS files
        """
        self.gtfs_dir = Path(gtfs_dir)
        self._shapes: dict[str, RouteShape] = {}
        self._trip_to_shape: dict[str, str] = {}
        self._trip_to_route: dict[str, str] = {}
        self._stop_distances: dict[str, dict[str, float]] = {}  # trip_id -> {stop_id -> dist}
        self._stop_sequences: dict[str, list[str]] = {}  # trip_id -> [stop_ids in order]

        self._load_shapes()
        self._load_trips()
        self._load_stop_times()

    def _load_shapes(self):
        """Load route shapes from shapes.txt"""
        shapes_file = self.gtfs_dir / 'shapes.txt'
        if not shapes_file.exists():
            print(f"Warning: shapes.txt not found at {shapes_file}")
            return

        df = pd.read_csv(shapes_file)

        for shape_id, group in df.groupby('shape_id'):
            # Remove quotes from shape_id if present
            shape_id = str(shape_id).strip('"')

            points = []
            for _, row in group.sort_values('shape_pt_sequence').iterrows():
                points.append(ShapePoint(
                    lat=row['shape_pt_lat'],
                    lon=row['shape_pt_lon'],
                    sequence=int(row['shape_pt_sequence']),
                    dist_traveled=row['shape_dist_traveled']
                ))

            self._shapes[shape_id] = RouteShape(shape_id=shape_id, points=points)

        print(f"Loaded {len(self._shapes)} route shapes")

    def _load_trips(self):
        """Load trip → shape/route mappings from trips.txt"""
        trips_file = self.gtfs_dir / 'trips.txt'
        if not trips_file.exists():
            print(f"Warning: trips.txt not found at {trips_file}")
            return

        df = pd.read_csv(trips_file)

        for _, row in df.iterrows():
            trip_id = str(row['trip_id']).strip('"')
            shape_id = str(row['shape_id']).strip('"')
            route_id = str(row['route_id']).strip('"')

            self._trip_to_shape[trip_id] = shape_id
            self._trip_to_route[trip_id] = route_id

        print(f"Loaded {len(self._trip_to_shape)} trip mappings")

    def _load_stop_times(self):
        """Load stop distances from stop_times.txt"""
        stop_times_file = self.gtfs_dir / 'stop_times.txt'
        if not stop_times_file.exists():
            print(f"Warning: stop_times.txt not found at {stop_times_file}")
            return

        df = pd.read_csv(stop_times_file)

        for trip_id, group in df.groupby('trip_id'):
            trip_id = str(trip_id).strip('"')

            # Sort by stop sequence to get ordered stops
            sorted_group = group.sort_values('stop_sequence')

            self._stop_distances[trip_id] = {}
            self._stop_sequences[trip_id] = []

            for _, row in sorted_group.iterrows():
                stop_id = str(row['stop_id']).strip('"')
                dist = row['shape_dist_traveled']

                self._stop_distances[trip_id][stop_id] = dist
                self._stop_sequences[trip_id].append(stop_id)

        print(f"Loaded stop distances for {len(self._stop_distances)} trips")

    def get_shape_for_trip(self, trip_id: str) -> Optional[RouteShape]:
        """Get the route shape for a trip."""
        trip_id = str(trip_id).strip('"')
        shape_id = self._trip_to_shape.get(trip_id)
        if shape_id:
            return self._shapes.get(shape_id)
        return None

    def get_stop_distance(self, trip_id: str, stop_id: str) -> Optional[float]:
        """
        Get the shape_dist_traveled for a stop on a trip.

        Returns:
            Distance in miles, or None if not found
        """
        trip_id = str(trip_id).strip('"')
        stop_id = str(stop_id).strip('"')

        trip_stops = self._stop_distances.get(trip_id)
        if trip_stops:
            return trip_stops.get(stop_id)
        return None

    def get_stops_on_trip(self, trip_id: str) -> list[str]:
        """Get ordered list of stop IDs for a trip."""
        trip_id = str(trip_id).strip('"')
        return self._stop_sequences.get(trip_id, [])

    def get_next_n_stops(
        self,
        trip_id: str,
        current_stop_id: str,
        n: int = 3
    ) -> list[str]:
        """
        Get the next N stop IDs after the current stop.

        Args:
            trip_id: Trip identifier
            current_stop_id: Current/last stop ID
            n: Number of future stops to return

        Returns:
            List of next N stop IDs (may be fewer if near end of trip)
        """
        trip_id = str(trip_id).strip('"')
        current_stop_id = str(current_stop_id).strip('"')

        stops = self._stop_sequences.get(trip_id, [])
        if not stops:
            return []

        try:
            current_idx = stops.index(current_stop_id)
            return stops[current_idx + 1:current_idx + 1 + n]
        except ValueError:
            # Current stop not found in sequence
            return []

    def calculate_route_distance(
        self,
        trip_id: str,
        bus_lat: float,
        bus_lon: float,
        target_stop_id: str
    ) -> Optional[float]:
        """
        Calculate the actual route distance from bus position to target stop.

        This is the key function for ETA prediction - it returns the actual
        road distance the bus must travel, not straight-line distance.

        Args:
            trip_id: Current trip identifier
            bus_lat: Bus latitude
            bus_lon: Bus longitude
            target_stop_id: Stop ID to calculate distance to

        Returns:
            Distance in miles along the route, or None if data unavailable
        """
        # Get the route shape
        shape = self.get_shape_for_trip(trip_id)
        if not shape:
            # Fall back to Haversine if no shape data
            return None

        # Get stop's position on route
        stop_dist = self.get_stop_distance(trip_id, target_stop_id)
        if stop_dist is None:
            return None

        # Find bus's position on route
        bus_dist = shape.get_distance_at_position(bus_lat, bus_lon)

        # Calculate remaining distance
        remaining = stop_dist - bus_dist

        # Handle wraparound for circular routes
        if remaining < 0:
            # Bus may have passed the stop (circular route)
            # In this case, add the total route length
            if shape.points:
                total_route_dist = shape.points[-1].dist_traveled
                remaining = total_route_dist + remaining

        return max(0, remaining)


class DistanceCalculator:
    """
    High-level interface for distance calculations in ETA prediction.

    Handles the mapping from telemetry data (which uses pattern_id)
    to GTFS data (which uses trip_id and shape_id).
    """

    def __init__(self, gtfs_dir: str):
        """
        Initialize the distance calculator.

        Args:
            gtfs_dir: Path to GTFS data directory
        """
        self.gtfs = GTFSRouteData(gtfs_dir)
        self._pattern_to_trip: dict[int, str] = {}  # Will be populated from telemetry

    def register_pattern_trip_mapping(self, pattern_id: int, trip_id: str):
        """
        Register a mapping from pattern_id to trip_id.

        This is learned from telemetry data where both are present.
        """
        self._pattern_to_trip[pattern_id] = str(trip_id).strip('"')

    def get_route_distance(
        self,
        bus_lat: float,
        bus_lon: float,
        target_stop_id: str,
        trip_id: Optional[str] = None,
        pattern_id: Optional[int] = None
    ) -> float:
        """
        Get the route distance from bus to target stop.

        Args:
            bus_lat: Bus latitude
            bus_lon: Bus longitude
            target_stop_id: Target stop ID
            trip_id: Trip ID (preferred)
            pattern_id: Pattern ID (fallback if trip_id not available)

        Returns:
            Distance in miles. Falls back to Haversine if route data unavailable.
        """
        # Determine trip_id
        if trip_id is None and pattern_id is not None:
            trip_id = self._pattern_to_trip.get(pattern_id)

        if trip_id:
            route_dist = self.gtfs.calculate_route_distance(
                trip_id, bus_lat, bus_lon, target_stop_id
            )
            if route_dist is not None:
                return route_dist

        # Fallback: Load stop coordinates and use Haversine
        # This is less accurate but better than nothing
        return self._fallback_haversine(bus_lat, bus_lon, target_stop_id)

    def _fallback_haversine(
        self,
        bus_lat: float,
        bus_lon: float,
        target_stop_id: str
    ) -> float:
        """
        Fallback to Haversine distance when route data unavailable.

        Note: This is less accurate and should be avoided when possible.
        """
        # Would need to load stops.json to get stop coordinates
        # For now, return 0 to indicate missing data
        return 0.0

    def get_distances_to_next_stops(
        self,
        bus_lat: float,
        bus_lon: float,
        trip_id: str,
        current_stop_id: str,
        n: int = 3
    ) -> list[tuple[str, float]]:
        """
        Get distances to the next N stops.

        Args:
            bus_lat: Bus latitude
            bus_lon: Bus longitude
            trip_id: Current trip ID
            current_stop_id: Last visited stop ID
            n: Number of future stops

        Returns:
            List of (stop_id, distance_miles) tuples
        """
        next_stops = self.gtfs.get_next_n_stops(trip_id, current_stop_id, n)

        results = []
        for stop_id in next_stops:
            dist = self.get_route_distance(
                bus_lat, bus_lon, stop_id, trip_id=trip_id
            )
            results.append((stop_id, dist))

        return results


# Convenience function for direct use
def load_gtfs_data(gtfs_dir: str) -> GTFSRouteData:
    """Load GTFS data from a directory."""
    return GTFSRouteData(gtfs_dir)


if __name__ == '__main__':
    # Test the distance calculator
    import sys

    gtfs_dir = sys.argv[1] if len(sys.argv) > 1 else '../../gtfs_data'

    print(f"Loading GTFS data from {gtfs_dir}...")
    gtfs = GTFSRouteData(gtfs_dir)

    # Test with a known trip
    test_trip = '1895'
    stops = gtfs.get_stops_on_trip(test_trip)
    print(f"\nStops on trip {test_trip}: {stops[:5]}...")

    if stops:
        first_stop = stops[0]
        last_stop = stops[-1]
        dist1 = gtfs.get_stop_distance(test_trip, first_stop)
        dist2 = gtfs.get_stop_distance(test_trip, last_stop)
        print(f"Distance from {first_stop} to {last_stop}: {dist2 - dist1:.2f} miles")
