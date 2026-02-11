"""
Data Preparation Module for ETA Prediction

Joins three data sources:
1. Raw telemetry (GPS pings with vehicle position, speed, next stop)
2. Arrivals/Departures (ground truth - actual arrival times at stops)
3. Weather data (hourly weather conditions)

Creates training labels by matching telemetry entries with actual arrival times.
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Tuple
from collections import defaultdict
import math


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine distance between two points in miles."""
    R = 3959  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


class GTFSRouteData:
    """
    Loads GTFS data and calculates route distances along shapes.
    """

    def __init__(self, gtfs_dir: str):
        """
        Load GTFS shapes, trips, and stop_times.

        Args:
            gtfs_dir: Path to directory containing GTFS txt files
        """
        gtfs_path = Path(gtfs_dir)

        # Load shapes (route polylines with distances)
        print("Loading GTFS shapes...")
        self.shapes_df = pd.read_csv(gtfs_path / 'shapes.txt')
        # Remove quotes from shape_id if present
        self.shapes_df['shape_id'] = self.shapes_df['shape_id'].astype(str).str.strip('"')

        # Load trips (maps trip_id -> shape_id)
        print("Loading GTFS trips...")
        self.trips_df = pd.read_csv(gtfs_path / 'trips.txt')
        self.trips_df['trip_id'] = self.trips_df['trip_id'].astype(str).str.strip('"')
        self.trips_df['shape_id'] = self.trips_df['shape_id'].astype(str).str.strip('"')
        self.trip_to_shape = dict(zip(self.trips_df['trip_id'], self.trips_df['shape_id']))

        # Load stop_times (stop distances along each trip)
        print("Loading GTFS stop_times...")
        self.stop_times_df = pd.read_csv(gtfs_path / 'stop_times.txt')
        self.stop_times_df['trip_id'] = self.stop_times_df['trip_id'].astype(str).str.strip('"')
        self.stop_times_df['stop_id'] = self.stop_times_df['stop_id'].astype(str)

        # Build index: (trip_id, stop_id) -> shape_dist_traveled
        self.stop_distances = {}
        for _, row in self.stop_times_df.iterrows():
            key = (row['trip_id'], str(row['stop_id']))
            self.stop_distances[key] = row['shape_dist_traveled']

        # Build shape point index: shape_id -> list of (lat, lon, dist)
        self.shape_points = {}
        for shape_id, group in self.shapes_df.groupby('shape_id'):
            sorted_points = group.sort_values('shape_pt_sequence')
            self.shape_points[shape_id] = list(zip(
                sorted_points['shape_pt_lat'],
                sorted_points['shape_pt_lon'],
                sorted_points['shape_dist_traveled']
            ))

        print(f"Loaded {len(self.shape_points)} shapes, {len(self.trip_to_shape)} trips")

    def find_position_on_shape(self, shape_id: str, lat: float, lon: float) -> Optional[float]:
        """
        Find the distance along the shape closest to the given position.

        Args:
            shape_id: The shape ID
            lat, lon: Current position

        Returns:
            Distance along shape in miles, or None if shape not found
        """
        if shape_id not in self.shape_points:
            return None

        points = self.shape_points[shape_id]
        if not points:
            return None

        # Find closest point on shape
        min_dist = float('inf')
        closest_shape_dist = 0

        for i, (pt_lat, pt_lon, pt_dist) in enumerate(points):
            dist = haversine_distance(lat, lon, pt_lat, pt_lon)
            if dist < min_dist:
                min_dist = dist
                closest_shape_dist = pt_dist

                # Interpolate between this point and next for better accuracy
                if i < len(points) - 1:
                    next_lat, next_lon, next_dist = points[i + 1]
                    dist_to_next = haversine_distance(lat, lon, next_lat, next_lon)
                    if dist_to_next < dist:
                        # We might be between points, interpolate
                        segment_len = haversine_distance(pt_lat, pt_lon, next_lat, next_lon)
                        if segment_len > 0:
                            ratio = dist / (dist + dist_to_next)
                            closest_shape_dist = pt_dist + ratio * (next_dist - pt_dist)

        return closest_shape_dist

    def calculate_route_distance(
        self,
        trip_id: str,
        current_lat: float,
        current_lon: float,
        target_stop_id: str
    ) -> Optional[float]:
        """
        Calculate route distance from current position to target stop.

        Args:
            trip_id: Current trip ID
            current_lat, current_lon: Current bus position
            target_stop_id: Target stop ID

        Returns:
            Distance in miles along the route, or None if can't calculate
        """
        # Get shape for this trip
        shape_id = self.trip_to_shape.get(str(trip_id))
        if not shape_id:
            return None

        # Get distance to target stop along shape
        stop_key = (str(trip_id), str(target_stop_id))
        stop_dist = self.stop_distances.get(stop_key)
        if stop_dist is None:
            return None

        # Find current position on shape
        current_dist = self.find_position_on_shape(shape_id, current_lat, current_lon)
        if current_dist is None:
            return None

        # Route distance = stop distance - current distance
        # Handle wrap-around for loop routes
        route_dist = stop_dist - current_dist
        if route_dist < 0:
            # Bus might have passed the stop or it's a loop route
            # Use straight-line distance as fallback
            return None

        return route_dist

    def get_straight_line_distance(
        self,
        current_lat: float,
        current_lon: float,
        stop_lat: float,
        stop_lon: float
    ) -> float:
        """Calculate straight-line distance in miles."""
        return haversine_distance(current_lat, current_lon, stop_lat, stop_lon)


class StopNameMapper:
    """Maps stop names from arrivals data to stop IDs in telemetry."""

    def __init__(self, stops_json_path: str):
        """Load stops.json and create name mappings."""
        with open(stops_json_path, 'r') as f:
            stops = json.load(f)

        # Create multiple lookup methods
        self.id_to_name = {s['id']: s['name'] for s in stops}
        self.name_to_id = {s['name']: s['id'] for s in stops}
        self.code_to_id = {s['code']: s['id'] for s in stops}

        # Create normalized name lookup (lowercase, no special chars)
        self.normalized_to_id = {}
        for s in stops:
            normalized = self._normalize(s['name'])
            self.normalized_to_id[normalized] = s['id']

        # Store stop coordinates for distance-based fallback
        self.stop_coords = {s['id']: (s['lat'], s['lon']) for s in stops}

    def _normalize(self, name: str) -> str:
        """Normalize stop name for fuzzy matching."""
        return name.lower().replace('&', 'and').replace('-', ' ').strip()

    def get_stop_id(self, station_name: str) -> Optional[str]:
        """Get stop ID from station name with fuzzy matching."""
        # Exact match
        if station_name in self.name_to_id:
            return self.name_to_id[station_name]

        # Normalized match
        normalized = self._normalize(station_name)
        if normalized in self.normalized_to_id:
            return self.normalized_to_id[normalized]

        # Partial match (if station name contains a known stop name)
        for name, stop_id in self.name_to_id.items():
            if self._normalize(name) in normalized or normalized in self._normalize(name):
                return stop_id

        return None


class WeatherData:
    """Loads and provides hourly weather data."""

    def __init__(self, weather_csv_path: str):
        """Load weather CSV file."""
        self.df = pd.read_csv(weather_csv_path)

        # Parse timestamps
        self.df['time'] = pd.to_datetime(self.df['time'])
        self.df['hour_key'] = self.df['time'].dt.strftime('%Y-%m-%d-%H')

        # Create lookup dict
        self.weather_by_hour = {}
        for _, row in self.df.iterrows():
            self.weather_by_hour[row['hour_key']] = {
                'precipitation': row['precipitation'],
                'precipitation_probability': row['precipitation_probability'],
                'temperature_c': row['temperature_2m']
            }

    def get_weather(self, timestamp_ms: int) -> dict:
        """Get weather for a given timestamp."""
        dt = datetime.utcfromtimestamp(timestamp_ms / 1000)
        hour_key = dt.strftime('%Y-%m-%d-%H')

        if hour_key in self.weather_by_hour:
            return self.weather_by_hour[hour_key]

        # Return defaults if not found
        return {
            'precipitation': 0.0,
            'precipitation_probability': 0,
            'temperature_c': 20.0
        }


class ArrivalsData:
    """Loads and indexes actual arrival times."""

    # Auburn, AL is in Central Time (UTC-6, or UTC-5 during DST)
    # DST ends first Sunday of November, starts second Sunday of March
    TIMEZONE_OFFSET_HOURS = 6  # Standard time offset (will adjust for DST)

    def __init__(self, arrivals_csv_path: str, stop_mapper: StopNameMapper):
        """
        Load arrivals CSV and create lookup indices.

        Args:
            arrivals_csv_path: Path to arrivals CSV
            stop_mapper: StopNameMapper instance for name→ID conversion
        """
        self.stop_mapper = stop_mapper

        # Read CSV, skip the header row with date range
        self.df = pd.read_csv(arrivals_csv_path, skiprows=1)

        # Parse dates and times
        self.df['date'] = pd.to_datetime(self.df['DATE'])

        # Parse arrival time (HH:MM:SS format)
        self.df['arrival_time'] = pd.to_timedelta(self.df['ARRIVAL'])
        self.df['departure_time'] = pd.to_timedelta(self.df['DEPARTURE'])

        # Create full datetime (in LOCAL time - Central)
        self.df['arrival_datetime_local'] = self.df['date'] + self.df['arrival_time']
        self.df['departure_datetime_local'] = self.df['date'] + self.df['departure_time']

        # Convert LOCAL time to UTC timestamps
        # Arrivals data is in Central Time, telemetry timestamps are in UTC
        # Central Time = UTC - 6 hours (standard) or UTC - 5 hours (DST)
        # For simplicity, we'll use a function to determine offset based on date
        self.df['arrival_ts'] = self.df.apply(
            lambda row: self._local_to_utc_timestamp(row['arrival_datetime_local']),
            axis=1
        )
        self.df['departure_ts'] = self.df.apply(
            lambda row: self._local_to_utc_timestamp(row['departure_datetime_local']),
            axis=1
        )

        # Map station names to stop IDs
        self.df['stop_id'] = self.df['Station'].apply(stop_mapper.get_stop_id)

        # Normalize vehicle IDs
        self.df['vehicle_id'] = self.df['Vehicle ID'].str.strip()

        # Create index by (vehicle_id, date) for fast lookup
        self._build_index()

        print(f"Loaded {len(self.df)} arrival records")
        print(f"  Matched {self.df['stop_id'].notna().sum()} to stop IDs")
        print(f"  Unmatched: {self.df['stop_id'].isna().sum()}")

    def _local_to_utc_timestamp(self, local_dt: pd.Timestamp) -> int:
        """
        Convert local Central Time datetime to UTC timestamp in milliseconds.

        Handles DST: Central is UTC-5 during DST, UTC-6 during standard time.
        DST ends first Sunday of November, starts second Sunday of March.
        """
        if pd.isna(local_dt):
            return 0

        month = local_dt.month

        # Determine if DST is in effect
        # For our data range (Nov 2025 - Jan 2026), DST is NOT in effect
        # Nov 2, 2025 is the first Sunday of November (DST ends)
        # So all our data is in Central Standard Time (UTC-6)

        # Simple check: if month is Nov, Dec, Jan, Feb -> Standard time (UTC-6)
        # Mar-Oct -> could be DST, need more careful check
        if month in [11, 12, 1, 2]:
            offset_hours = 6  # Central Standard Time
        elif month in [4, 5, 6, 7, 8, 9, 10]:
            offset_hours = 5  # Central Daylight Time
        else:  # March - need to check if before/after second Sunday
            offset_hours = 5  # Assume DST for March

        # Convert local time to UTC by adding the offset
        # Use datetime to handle hour overflow properly (e.g., 23 + 6 = next day 05:00)
        utc_dt = local_dt.to_pydatetime() + timedelta(hours=offset_hours)

        # Convert to Unix timestamp (seconds since 1970-01-01 00:00:00 UTC)
        epoch = datetime(1970, 1, 1)
        utc_timestamp_sec = (utc_dt - epoch).total_seconds()

        return int(utc_timestamp_sec * 1000)

    def _build_index(self):
        """Build lookup index for fast queries."""
        # Index: vehicle_id -> date -> sorted list of (arrival_ts, stop_id, dwell, boardings)
        self.arrivals_index = defaultdict(lambda: defaultdict(list))

        for _, row in self.df.iterrows():
            if pd.isna(row['stop_id']):
                continue

            vid = row['vehicle_id']
            date_key = row['date'].strftime('%Y-%m-%d')

            self.arrivals_index[vid][date_key].append({
                'arrival_ts': row['arrival_ts'],
                'departure_ts': row['departure_ts'],
                'stop_id': str(row['stop_id']),
                'dwell_sec': row['Dwell (sec)'],
                'boardings': row['APC Boardings'] + row['EPC Boardings'],
                'alightings': row['APC Alightings'] + row['EPC Alightings'],
                'route': row['Route']
            })

        # Sort each day's arrivals by time
        for vid in self.arrivals_index:
            for date_key in self.arrivals_index[vid]:
                self.arrivals_index[vid][date_key].sort(key=lambda x: x['arrival_ts'])

    def find_next_arrivals(
        self,
        vehicle_id: str,
        timestamp_ms: int,
        target_stop_ids: list[str],
        max_time_window_ms: int = 30 * 60 * 1000  # 30 minutes
    ) -> dict[str, Optional[int]]:
        """
        Find actual arrival times at target stops after a given timestamp.

        Args:
            vehicle_id: Vehicle ID to look up
            timestamp_ms: Current timestamp in milliseconds
            target_stop_ids: List of stop IDs to find arrivals for
            max_time_window_ms: Maximum time window to search

        Returns:
            Dict mapping stop_id -> actual_arrival_timestamp (or None if not found)
        """
        dt = datetime.utcfromtimestamp(timestamp_ms / 1000)
        date_key = dt.strftime('%Y-%m-%d')

        result = {stop_id: None for stop_id in target_stop_ids}

        if vehicle_id not in self.arrivals_index:
            return result

        if date_key not in self.arrivals_index[vehicle_id]:
            return result

        arrivals = self.arrivals_index[vehicle_id][date_key]

        # Find arrivals after timestamp
        for arrival in arrivals:
            if arrival['arrival_ts'] <= timestamp_ms:
                continue  # This arrival is in the past

            if arrival['arrival_ts'] > timestamp_ms + max_time_window_ms:
                break  # Too far in the future

            stop_id = arrival['stop_id']
            if stop_id in result and result[stop_id] is None:
                result[stop_id] = arrival['arrival_ts']

        return result

    def get_arrival_info(
        self,
        vehicle_id: str,
        timestamp_ms: int,
        stop_id: str
    ) -> Optional[dict]:
        """
        Get full arrival info for a specific vehicle/stop after timestamp.

        Returns dict with arrival_ts, dwell_sec, boardings, alightings.
        """
        dt = datetime.utcfromtimestamp(timestamp_ms / 1000)
        date_key = dt.strftime('%Y-%m-%d')

        if vehicle_id not in self.arrivals_index:
            return None
        if date_key not in self.arrivals_index[vehicle_id]:
            return None

        for arrival in self.arrivals_index[vehicle_id][date_key]:
            if arrival['arrival_ts'] > timestamp_ms and arrival['stop_id'] == str(stop_id):
                return arrival

        return None

    def get_arrival_near_transition(
        self,
        vehicle_id: str,
        transition_ts: int,
        stop_id: str,
        window_before_ms: int = 60000,   # 1 min before
        window_after_ms: int = 120000    # 2 min after
    ) -> Optional[dict]:
        """
        Find arrival at a stop that occurred near a transition event.

        This is more accurate than get_arrival_info for loop routes where
        a bus visits the same stop multiple times. We look for arrivals
        in a narrow window around when the telemetry shows the bus left
        that stop.

        Args:
            vehicle_id: Vehicle ID
            transition_ts: Timestamp when nextStopId changed FROM this stop
            stop_id: The stop ID we're looking for arrival at
            window_before_ms: How far before transition to look
            window_after_ms: How far after transition to look

        Returns:
            Arrival info dict or None
        """
        dt = datetime.utcfromtimestamp(transition_ts / 1000)
        date_key = dt.strftime('%Y-%m-%d')

        if vehicle_id not in self.arrivals_index:
            return None
        if date_key not in self.arrivals_index[vehicle_id]:
            return None

        # Find arrivals within the window
        candidates = []
        for arrival in self.arrivals_index[vehicle_id][date_key]:
            if arrival['stop_id'] != str(stop_id):
                continue

            arr_ts = arrival['arrival_ts']
            # Check if arrival is within window around transition
            if transition_ts - window_before_ms <= arr_ts <= transition_ts + window_after_ms:
                candidates.append(arrival)

        if not candidates:
            return None

        # Return the one closest to the transition
        return min(candidates, key=lambda a: abs(a['arrival_ts'] - transition_ts))


class TelemetryData:
    """Loads raw telemetry data from JSONL or CSV files."""

    def __init__(self, telemetry_path: str, file_format: str = 'auto'):
        """
        Load telemetry file(s).

        Args:
            telemetry_path: Path to single file or directory of files
            file_format: 'jsonl', 'csv', or 'auto' (detect from extension)
        """
        path = Path(telemetry_path)

        if path.is_dir():
            # Load all JSONL files in directory
            self.df = self._load_directory(path)
        elif path.suffix == '.jsonl' or file_format == 'jsonl':
            self.df = self._load_jsonl(path)
        else:
            self.df = pd.read_csv(path)

        # Basic cleaning
        self.df = self.df.dropna(subset=['vid', 'lat', 'lon'])

        # Filter out vehicles not in service (patternId = 9998)
        self.df = self.df[self.df['patternId'] != 9998]

        # Filter out rows without route or with routeId 777 (not in service)
        self.df = self.df[self.df['routeId'].notna()]
        self.df = self.df[self.df['routeId'] != 777]

        # Filter out rows without valid next stop
        self.df = self.df[self.df['nextStopId'] > 0]

        print(f"Loaded {len(self.df)} valid telemetry records")

    def _load_jsonl(self, path: Path) -> pd.DataFrame:
        """Load a single JSONL file."""
        records = []
        with open(path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        return pd.DataFrame(records)

    def _load_directory(self, dir_path: Path) -> pd.DataFrame:
        """Load all JSONL files in a directory."""
        all_dfs = []
        jsonl_files = sorted(dir_path.glob('*.jsonl'))

        print(f"Found {len(jsonl_files)} JSONL files")

        for file_path in jsonl_files:
            if file_path.stat().st_size == 0:
                print(f"  Skipping empty file: {file_path.name}")
                continue

            print(f"  Loading {file_path.name}...")
            df = self._load_jsonl(file_path)
            if len(df) > 0:
                all_dfs.append(df)

        if not all_dfs:
            return pd.DataFrame()

        return pd.concat(all_dfs, ignore_index=True)


def prepare_training_data(
    telemetry_path: str,
    arrivals_csv: str,
    weather_csv: str,
    stops_json: str,
    output_dir: str,
    num_future_stops: int = 3,
    sample_rate: int = 10  # Use every Nth telemetry record
) -> dict:
    """
    Prepare training data by joining telemetry with actual arrivals and weather.

    Args:
        telemetry_path: Path to raw telemetry JSONL file, CSV file, or directory of JSONL files
        arrivals_csv: Path to arrivals/departures CSV
        weather_csv: Path to weather data CSV
        stops_json: Path to stops.json
        output_dir: Directory to save processed data
        num_future_stops: Number of future stops to predict
        sample_rate: Subsample telemetry (every Nth record)

    Returns:
        Statistics about the prepared data
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("Loading data sources...")

    # Load all data sources
    stop_mapper = StopNameMapper(stops_json)
    weather = WeatherData(weather_csv)
    arrivals = ArrivalsData(arrivals_csv, stop_mapper)
    telemetry = TelemetryData(telemetry_path)

    print(f"\nProcessing {len(telemetry.df)} telemetry records...")

    # Prepare output arrays
    features_list = []
    labels_list = []
    vehicle_ids_list = []
    metadata_list = []

    # Vehicle ID mapping for embeddings
    vehicle_id_to_idx = {}
    next_vehicle_idx = 0

    # Process telemetry records
    matched = 0
    unmatched = 0

    for idx, row in telemetry.df.iloc[::sample_rate].iterrows():
        # Get vehicle ID
        vid = str(row['vid']).strip()

        # Map vehicle ID to index
        if vid not in vehicle_id_to_idx:
            vehicle_id_to_idx[vid] = next_vehicle_idx
            next_vehicle_idx += 1

        vehicle_idx = vehicle_id_to_idx[vid]

        # Get timestamp
        ts = int(row['t'])

        # Get next stop from telemetry
        next_stop_id = str(int(row['nextStopId'])) if pd.notna(row['nextStopId']) else None

        if next_stop_id is None or next_stop_id == '0':
            unmatched += 1
            continue

        # Find actual arrival at next stop
        arrival_info = arrivals.get_arrival_info(vid, ts, next_stop_id)

        if arrival_info is None:
            unmatched += 1
            continue

        # Calculate actual ETA (label) in seconds
        actual_eta = (arrival_info['arrival_ts'] - ts) / 1000.0

        # Skip if ETA is negative or too large
        if actual_eta <= 0 or actual_eta > 30 * 60:  # Max 30 minutes
            unmatched += 1
            continue

        # Get weather data
        weather_data = weather.get_weather(ts)

        # Build feature vector
        features = build_feature_vector(row, weather_data, arrival_info)

        # Build label (for now, just the next stop ETA)
        # TODO: Extend to multiple stops
        labels = [actual_eta]

        features_list.append(features)
        labels_list.append(labels)
        vehicle_ids_list.append(vehicle_idx)

        metadata_list.append({
            'timestamp': ts,
            'vehicle_id': vid,
            'route_id': row['routeId'],
            'next_stop_id': next_stop_id
        })

        matched += 1

        if matched % 10000 == 0:
            print(f"  Processed {matched} matched records...")

    print(f"\nMatched: {matched}, Unmatched: {unmatched}")
    print(f"Match rate: {matched / (matched + unmatched) * 100:.1f}%")

    if matched == 0:
        print("ERROR: No matched records found!")
        return {'matched': 0, 'unmatched': unmatched}

    # Convert to numpy arrays
    features_array = np.array(features_list, dtype=np.float32)
    labels_array = np.array(labels_list, dtype=np.float32)
    vehicle_ids_array = np.array(vehicle_ids_list, dtype=np.int64)

    # Compute normalization statistics
    means = features_array.mean(axis=0)
    stds = features_array.std(axis=0)
    stds[stds < 1e-6] = 1.0  # Avoid division by zero

    # Save arrays
    np.save(output_path / 'features.npy', features_array)
    np.save(output_path / 'labels.npy', labels_array)
    np.save(output_path / 'vehicle_ids.npy', vehicle_ids_array)

    # Save vehicle mapping
    with open(output_path / 'vehicle_mapping.json', 'w') as f:
        json.dump(vehicle_id_to_idx, f, indent=2)

    # Save normalization stats
    with open(output_path / 'normalization_stats.json', 'w') as f:
        json.dump({
            'means': means.tolist(),
            'stds': stds.tolist()
        }, f, indent=2)

    # Save metadata (for debugging)
    with open(output_path / 'metadata.json', 'w') as f:
        json.dump(metadata_list[:1000], f, indent=2)  # Just first 1000 for debugging

    stats = {
        'matched': matched,
        'unmatched': unmatched,
        'n_features': features_array.shape[1],
        'n_vehicles': len(vehicle_id_to_idx),
        'label_mean': float(labels_array.mean()),
        'label_std': float(labels_array.std())
    }

    print(f"\nSaved to {output_path}:")
    print(f"  features.npy: {features_array.shape}")
    print(f"  labels.npy: {labels_array.shape}")
    print(f"  Mean ETA: {stats['label_mean']:.1f} seconds")
    print(f"  Std ETA: {stats['label_std']:.1f} seconds")

    return stats


def build_feature_vector(
    row: pd.Series,
    weather: dict,
    arrival_info: dict,
    distance_to_stop: float = 0.0
) -> list:
    """
    Build feature vector from telemetry row, weather, and arrival info.

    Args:
        row: Telemetry data row
        weather: Weather data dict
        arrival_info: Arrival info dict (dwell, boardings, etc.)
        distance_to_stop: Route distance to next stop in miles

    Returns list of features (28 total).
    """
    ts = int(row['t'])
    dt = datetime.utcfromtimestamp(ts / 1000)

    # Time features
    hour = dt.hour
    minute = dt.minute
    time_of_day_minutes = hour * 60 + minute

    # Cyclical time encoding
    time_sin = np.sin(2 * np.pi * time_of_day_minutes / (24 * 60))
    time_cos = np.cos(2 * np.pi * time_of_day_minutes / (24 * 60))

    # Day of week (0=Monday)
    day_of_week = dt.weekday()

    # Rush hour flags
    is_morning_rush = 1.0 if 7 <= hour < 9 else 0.0
    is_afternoon_rush = 1.0 if 16 <= hour < 18 else 0.0

    # Class change (assuming :50 and :00 marks)
    is_class_change = 1.0 if minute >= 50 or minute <= 10 else 0.0

    features = [
        # Core features (0-7)
        float(row['speed']) if pd.notna(row['speed']) else 0.0,
        float(row['heading']) / 360.0 if pd.notna(row['heading']) else 0.0,
        float(row['load']) if pd.notna(row['load']) else 0.0,
        float(row['progress']) if pd.notna(row['progress']) else 0.0,
        float(row['lastStopOnTime']) if pd.notna(row['lastStopOnTime']) else 0.0,

        # Scheduled ETA (baseline) - will be converted to seconds in v2
        float(row['etaSeconds']) if pd.notna(row['etaSeconds']) else 0.0,
        float(row['scheduledEta']) if pd.notna(row['scheduledEta']) else 0.0,

        # DISTANCE TO STOP (new feature!) - index 7
        distance_to_stop,

        # Time features (8-12)
        time_sin,
        time_cos,
        float(day_of_week) / 6.0,  # Normalize to [0, 1]
        is_morning_rush,
        is_afternoon_rush,
        is_class_change,

        # Day of week one-hot (14-20)
        1.0 if day_of_week == 0 else 0.0,  # Monday
        1.0 if day_of_week == 1 else 0.0,  # Tuesday
        1.0 if day_of_week == 2 else 0.0,  # Wednesday
        1.0 if day_of_week == 3 else 0.0,  # Thursday
        1.0 if day_of_week == 4 else 0.0,  # Friday
        1.0 if day_of_week == 5 else 0.0,  # Saturday
        1.0 if day_of_week == 6 else 0.0,  # Sunday

        # Weather features (21-24)
        weather['precipitation'],
        1.0 if weather['precipitation'] > 0 else 0.0,  # is_raining
        weather['precipitation_probability'] / 100.0,
        weather['temperature_c'] / 40.0,  # Normalize roughly to [0, 1]

        # Historical features from arrival (25-27)
        float(arrival_info.get('dwell_sec', 0)) if arrival_info else 0.0,
        float(arrival_info.get('boardings', 0)) if arrival_info else 0.0,
        float(arrival_info.get('alightings', 0)) if arrival_info else 0.0,
    ]

    return features


def prepare_training_data_v2(
    telemetry_path: str,
    arrivals_csv: str,
    weather_csv: str,
    stops_json: str,
    output_dir: str,
    gtfs_dir: str = None,           # GTFS data for route distances
    min_eta_seconds: int = 30,      # Exclude if too close to arrival
    max_eta_seconds: int = 900,     # Exclude if more than 15 minutes
    sample_rate: int = 5,           # Use every Nth telemetry record
    use_transition_times: bool = False  # Use transition timestamps as arrival times
) -> dict:
    """
    Prepare training data using improved transition-based arrival matching.

    This version:
    1. Detects stop transitions (when nextStopId changes)
    2. Matches arrivals using narrow time windows around transitions
    3. Assigns correct arrival to all approaching telemetry points
    4. Filters out problematic data points
    5. Calculates route distance to stop using GTFS shapes

    Args:
        telemetry_path: Path to telemetry data
        arrivals_csv: Path to arrivals CSV
        weather_csv: Path to weather data
        stops_json: Path to stops.json
        output_dir: Output directory
        gtfs_dir: Path to GTFS data directory (for route distances)
        min_eta_seconds: Exclude points with actual ETA below this
        max_eta_seconds: Exclude points with actual ETA above this
        sample_rate: Use every Nth telemetry record within valid approaches

    Returns:
        Statistics dict
    """
    from datetime import datetime, timedelta

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("PREPARING TRAINING DATA (v2 - With Route Distance)")
    print("=" * 60)

    # Load data sources
    print("\nLoading data sources...")
    stop_mapper = StopNameMapper(stops_json)
    weather = WeatherData(weather_csv)
    telemetry = TelemetryData(telemetry_path)

    # Load arrivals data (optional if using transition times)
    arrivals = None
    if not use_transition_times:
        try:
            arrivals = ArrivalsData(arrivals_csv, stop_mapper)
        except Exception as e:
            print(f"Warning: Could not load arrivals data: {e}")
            print("Falling back to transition-based timestamps")
            use_transition_times = True
    else:
        print("Using transition timestamps as arrival times (no arrivals file)")

    # Load GTFS for route distance calculation
    gtfs = None
    if gtfs_dir:
        try:
            gtfs = GTFSRouteData(gtfs_dir)
        except Exception as e:
            print(f"Warning: Could not load GTFS data: {e}")
            print("Will use straight-line distance as fallback")

    # Stats tracking
    stats = {
        'total_transitions': 0,
        'matched_transitions': 0,
        'unmatched_transitions': 0,
        'total_telemetry_points': 0,
        'valid_training_points': 0,
        'filtered_negative_eta': 0,
        'filtered_too_close': 0,
        'filtered_too_far': 0,
        'filtered_no_arrival': 0,
        'route_distance_calculated': 0,
        'straight_line_fallback': 0
    }

    # Output lists
    features_list = []
    labels_list = []
    vehicle_ids_list = []
    metadata_list = []

    # Vehicle ID mapping
    vehicle_id_to_idx = {}
    next_vehicle_idx = 0

    vehicles = telemetry.df['vid'].unique()
    print(f"\nProcessing {len(vehicles)} vehicles...")

    for vid in vehicles:
        if vid not in vehicle_id_to_idx:
            vehicle_id_to_idx[vid] = next_vehicle_idx
            next_vehicle_idx += 1

        vid_idx = vehicle_id_to_idx[vid]
        vid_data = telemetry.df[telemetry.df['vid'] == vid].sort_values('t')

        # Phase 1: Detect transitions and match arrivals
        transitions = []  # List of (transition_ts, stop_id, arrival_info)
        prev_stop = None
        prev_ts = None

        for idx, row in vid_data.iterrows():
            next_stop = str(int(row['nextStopId'])) if row['nextStopId'] > 0 else None
            ts = int(row['t'])

            if prev_stop is not None and prev_stop != next_stop:
                # Transition detected: bus left prev_stop
                stats['total_transitions'] += 1

                if use_transition_times:
                    # Use transition timestamp directly as arrival time
                    # Estimate arrival as slightly before the transition
                    # (transition happens when bus leaves, arrival is when it came)
                    arrival_info = {
                        'arrival_ts': prev_ts if prev_ts else ts - 30000,  # Use last timestamp at prev_stop
                        'departure_ts': ts,
                        'dwell_sec': 0,
                        'boardings': 0,
                        'alightings': 0
                    }
                    transitions.append((ts, prev_stop, arrival_info))
                    stats['matched_transitions'] += 1
                else:
                    # Find the arrival using transition-based matching
                    arrival_info = arrivals.get_arrival_near_transition(
                        vid, ts, prev_stop,
                        window_before_ms=60000,   # 1 min before
                        window_after_ms=120000    # 2 min after
                    )

                    if arrival_info:
                        transitions.append((ts, prev_stop, arrival_info))
                        stats['matched_transitions'] += 1
                    else:
                        stats['unmatched_transitions'] += 1

            prev_stop = next_stop
            prev_ts = ts

        # Phase 2: Build training data for each approach sequence
        # For each transition, go back and find telemetry points approaching that stop
        prev_stop = None
        approach_start_idx = 0

        for idx, (i, row) in enumerate(vid_data.iterrows()):
            next_stop = str(int(row['nextStopId'])) if row['nextStopId'] > 0 else None
            ts = int(row['t'])

            if prev_stop != next_stop:
                # End of an approach sequence
                if prev_stop is not None:
                    # Find the matching transition
                    matching_transition = None
                    for trans_ts, trans_stop, trans_arrival in transitions:
                        if trans_stop == prev_stop and abs(trans_ts - ts) < 5000:  # Within 5 sec
                            matching_transition = (trans_ts, trans_stop, trans_arrival)
                            break

                    if matching_transition:
                        trans_ts, trans_stop, arrival_info = matching_transition
                        actual_arrival_ts = arrival_info['arrival_ts']

                        # Process telemetry points in this approach (with sampling)
                        approach_rows = vid_data.iloc[approach_start_idx:idx]

                        for sample_idx, (_, approach_row) in enumerate(approach_rows.iterrows()):
                            if sample_idx % sample_rate != 0:
                                continue

                            stats['total_telemetry_points'] += 1

                            row_ts = int(approach_row['t'])
                            actual_eta = (actual_arrival_ts - row_ts) / 1000.0

                            # Apply filters
                            if actual_eta <= 0:
                                stats['filtered_negative_eta'] += 1
                                continue

                            if actual_eta < min_eta_seconds:
                                stats['filtered_too_close'] += 1
                                continue

                            if actual_eta > max_eta_seconds:
                                stats['filtered_too_far'] += 1
                                continue

                            # Get weather
                            weather_data = weather.get_weather(row_ts)

                            # Calculate route distance to stop
                            distance_to_stop = 0.0
                            used_route_dist = False
                            if gtfs:
                                # Get trip_id from telemetry (may be stored differently)
                                trip_id = approach_row.get('tripId', approach_row.get('patternId', ''))
                                lat = approach_row.get('lat', 0)
                                lon = approach_row.get('lon', 0)

                                if trip_id and lat and lon:
                                    route_dist = gtfs.calculate_route_distance(
                                        str(trip_id), lat, lon, str(prev_stop)
                                    )
                                    if route_dist is not None:
                                        distance_to_stop = route_dist
                                        used_route_dist = True
                                        stats['route_distance_calculated'] += 1
                                    else:
                                        # Fallback to straight-line distance
                                        stop_coords = stop_mapper.stop_coords.get(int(prev_stop))
                                        if stop_coords:
                                            distance_to_stop = gtfs.get_straight_line_distance(
                                                lat, lon, stop_coords[0], stop_coords[1]
                                            )
                                            stats['straight_line_fallback'] += 1

                            if not used_route_dist:
                                # No GTFS or couldn't calculate - use straight-line distance
                                lat = approach_row.get('lat', 0)
                                lon = approach_row.get('lon', 0)
                                try:
                                    stop_coords = stop_mapper.stop_coords.get(int(prev_stop))
                                except:
                                    stop_coords = None
                                if lat and lon and stop_coords:
                                    distance_to_stop = haversine_distance(
                                        lat, lon, stop_coords[0], stop_coords[1]
                                    )
                                    if not gtfs:
                                        stats['straight_line_fallback'] += 1

                            # Build features with distance
                            features = build_feature_vector(
                                approach_row, weather_data, arrival_info, distance_to_stop
                            )

                            # Convert time features to local time for proper encoding
                            dt_local = datetime.utcfromtimestamp(row_ts / 1000) - timedelta(hours=6)

                            # Add computed system ETA as feature (properly interpreted)
                            # Both etaSeconds and scheduledEta are in "minutes since midnight (local time)"
                            # Convert to "seconds until arrival"
                            current_minutes = dt_local.hour * 60 + dt_local.minute + dt_local.second / 60.0

                            eta_field = approach_row.get('etaSeconds', 0)
                            if eta_field > 0:
                                system_eta_sec = (eta_field - current_minutes) * 60
                            else:
                                system_eta_sec = 0

                            sched_eta_field = approach_row.get('scheduledEta', 0)
                            if sched_eta_field > 0:
                                scheduled_eta_sec = (sched_eta_field - current_minutes) * 60
                            else:
                                scheduled_eta_sec = 0

                            # Replace the raw values with computed ETAs in seconds
                            features[5] = max(0, system_eta_sec)      # Index 5 is etaSeconds -> system_eta_sec
                            features[6] = max(0, scheduled_eta_sec)   # Index 6 is scheduledEta -> scheduled_eta_sec

                            features_list.append(features)
                            labels_list.append([actual_eta])
                            vehicle_ids_list.append(vid_idx)

                            metadata_list.append({
                                'timestamp': row_ts,
                                'vehicle_id': vid,
                                'route_id': approach_row['routeId'],
                                'next_stop_id': prev_stop,
                                'actual_eta': actual_eta,
                                'lat': approach_row.get('lat', 0),
                                'lon': approach_row.get('lon', 0),
                                'distance_to_stop': distance_to_stop
                            })

                            stats['valid_training_points'] += 1

                approach_start_idx = idx

            prev_stop = next_stop

    # Print stats
    print("\n" + "=" * 60)
    print("DATA PREPARATION STATISTICS")
    print("=" * 60)
    print(f"\nTransition matching:")
    print(f"  Total transitions: {stats['total_transitions']}")
    print(f"  Matched: {stats['matched_transitions']} ({stats['matched_transitions']/max(1,stats['total_transitions'])*100:.1f}%)")
    print(f"  Unmatched: {stats['unmatched_transitions']}")

    print(f"\nTelemetry filtering:")
    print(f"  Total points considered: {stats['total_telemetry_points']}")
    print(f"  Filtered (negative ETA): {stats['filtered_negative_eta']}")
    print(f"  Filtered (too close <{min_eta_seconds}s): {stats['filtered_too_close']}")
    print(f"  Filtered (too far >{max_eta_seconds}s): {stats['filtered_too_far']}")
    print(f"  Valid training points: {stats['valid_training_points']}")

    print(f"\nDistance calculation:")
    print(f"  Route distance (GTFS): {stats['route_distance_calculated']}")
    print(f"  Straight-line fallback: {stats['straight_line_fallback']}")

    if stats['valid_training_points'] == 0:
        print("\nERROR: No valid training points generated!")
        return stats

    # Convert to numpy arrays
    features_array = np.array(features_list, dtype=np.float32)
    labels_array = np.array(labels_list, dtype=np.float32)
    vehicle_ids_array = np.array(vehicle_ids_list, dtype=np.int64)

    # Compute normalization statistics
    means = features_array.mean(axis=0)
    stds = features_array.std(axis=0)
    stds[stds < 1e-6] = 1.0

    # Save arrays
    np.save(output_path / 'features.npy', features_array)
    np.save(output_path / 'labels.npy', labels_array)
    np.save(output_path / 'vehicle_ids.npy', vehicle_ids_array)

    with open(output_path / 'vehicle_mapping.json', 'w') as f:
        json.dump(vehicle_id_to_idx, f, indent=2)

    with open(output_path / 'normalization_stats.json', 'w') as f:
        json.dump({'means': means.tolist(), 'stds': stds.tolist()}, f, indent=2)

    with open(output_path / 'metadata.json', 'w') as f:
        json.dump(metadata_list[:1000], f, indent=2)

    with open(output_path / 'stats.json', 'w') as f:
        json.dump(stats, f, indent=2)

    stats['n_features'] = features_array.shape[1]
    stats['n_vehicles'] = len(vehicle_id_to_idx)
    stats['label_mean'] = float(labels_array.mean())
    stats['label_std'] = float(labels_array.std())

    print(f"\nSaved to {output_path}:")
    print(f"  features.npy: {features_array.shape}")
    print(f"  labels.npy: {labels_array.shape}")
    print(f"  Mean ETA: {stats['label_mean']:.1f} seconds ({stats['label_mean']/60:.1f} min)")
    print(f"  Std ETA: {stats['label_std']:.1f} seconds")

    return stats


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Prepare training data for ETA model')

    parser.add_argument('--telemetry', type=str, required=True,
                        help='Path to telemetry data: single JSONL/CSV file or directory of JSONL files')
    parser.add_argument('--arrivals', type=str, required=True,
                        help='Path to arrivals/departures CSV')
    parser.add_argument('--weather', type=str, required=True,
                        help='Path to weather data CSV')
    parser.add_argument('--stops', type=str, required=True,
                        help='Path to stops.json')
    parser.add_argument('--output', type=str, default='./processed_data',
                        help='Output directory')
    parser.add_argument('--gtfs', type=str, default=None,
                        help='Path to GTFS data directory (for route distances)')
    parser.add_argument('--sample-rate', type=int, default=5,
                        help='Use every Nth telemetry record (default: 5)')
    parser.add_argument('--v2', action='store_true',
                        help='Use v2 transition-based matching (recommended)')
    parser.add_argument('--use-transition-times', action='store_true',
                        help='Use transition timestamps as arrival times (no arrivals file needed)')

    args = parser.parse_args()

    if args.v2:
        prepare_training_data_v2(
            telemetry_path=args.telemetry,
            arrivals_csv=args.arrivals,
            weather_csv=args.weather,
            stops_json=args.stops,
            output_dir=args.output,
            gtfs_dir=args.gtfs,
            sample_rate=args.sample_rate,
            use_transition_times=args.use_transition_times
        )
    else:
        prepare_training_data(
            telemetry_path=args.telemetry,
            arrivals_csv=args.arrivals,
            weather_csv=args.weather,
            stops_json=args.stops,
            output_dir=args.output,
            sample_rate=args.sample_rate
        )


if __name__ == '__main__':
    main()
