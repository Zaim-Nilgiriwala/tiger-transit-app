"""
Optimized Data Preparation Module for ETA Prediction

Memory-efficient streaming approach:
1. Process one telemetry file at a time
2. Use vectorized pandas operations
3. Write results incrementally to disk
4. Avoid loading all data into memory

Uses GTFS route distance (not straight-line haversine) for accurate distance calculations.
Separates jAUnt (route 232) data into a separate folder for independent training.

DATA FILE PATHS (relative to ETA-Model/src/):
  --telemetry  ../raw_data
  --arrivals   ../raw_data/Arrivals - Departures by Date (POST)_11_06_2025 12_00 AM_01_14_2026 12_00 AM_.csv
  --weather    ../raw_data/weather_data.csv
  --stops      ../stops.json
  --gtfs       ../../../../gtfs_data
  --output     ../processed_data_v6  (creates _jaunt suffix for jAUnt data)

Example command:
  python data_prep_optimized.py --telemetry "../raw_data" \\
      --arrivals "../raw_data/Arrivals - Departures by Date (POST)_11_06_2025 12_00 AM_01_14_2026 12_00 AM_.csv" \\
      --weather "../raw_data/weather_data.csv" --stops "../stops.json" \\
      --gtfs "../../../../gtfs_data" --output "../processed_data_v6"
"""

import json
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Generator
from collections import defaultdict
import math
import gc

from history_buffer import compute_history_features_vectorized


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate haversine (straight-line) distance between two points in miles."""
    R = 3959  # Earth radius in miles
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = math.sin(dlat/2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon/2)**2
    c = 2 * math.asin(math.sqrt(a))
    return R * c


def haversine_distance_vectorized(lat1: np.ndarray, lon1: np.ndarray,
                                   lat2: float, lon2: float) -> np.ndarray:
    """Vectorized haversine distance calculation."""
    R = 3959  # Earth radius in miles
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = np.sin(dlat/2)**2 + np.cos(lat1_rad) * np.cos(lat2_rad) * np.sin(dlon/2)**2
    c = 2 * np.arcsin(np.sqrt(a))
    return R * c


class GTFSRouteDistance:
    """
    GTFS-based route distance calculator.

    Uses actual road distance along bus routes instead of straight-line distance.
    Loads shapes.txt, trips.txt, and stop_times.txt to calculate distances.
    """

    def __init__(self, gtfs_dir: str):
        self.gtfs_dir = Path(gtfs_dir)

        # shape_id -> list of (lat, lon, dist_traveled) sorted by sequence
        self._shapes: dict[str, list[tuple[float, float, float]]] = {}

        # route_id -> list of shape_ids
        self._route_shapes: dict[str, list[str]] = defaultdict(list)

        # (shape_id, stop_id) -> shape_dist_traveled
        self._stop_distances: dict[tuple[str, str], float] = {}

        # shape_id -> set of stop_ids
        self._shape_stops: dict[str, set[str]] = defaultdict(set)

        # (route_id, stop_id) -> stop_sequence (position along route, 1-indexed)
        self._route_stop_sequences: dict[tuple[str, str], int] = {}

        # route_id -> max stop_sequence (total number of stops on route)
        self._route_max_sequence: dict[str, int] = {}

        self._load_data()

    def _load_data(self):
        """Load GTFS data files."""
        self._load_shapes()
        self._load_trips()
        self._load_stop_times()

        print(f"GTFSRouteDistance loaded: {len(self._shapes)} shapes, "
              f"{len(self._route_shapes)} routes, {len(self._stop_distances)} stop distances")

    def _load_shapes(self):
        """Load route shapes from shapes.txt"""
        shapes_file = self.gtfs_dir / 'shapes.txt'
        if not shapes_file.exists():
            print(f"Warning: shapes.txt not found at {shapes_file}")
            return

        df = pd.read_csv(shapes_file)

        for shape_id, group in df.groupby('shape_id'):
            shape_id = str(shape_id).strip('"')

            # Sort by sequence and extract points
            sorted_group = group.sort_values('shape_pt_sequence')
            points = [
                (row['shape_pt_lat'], row['shape_pt_lon'], row['shape_dist_traveled'])
                for _, row in sorted_group.iterrows()
            ]

            self._shapes[shape_id] = points

        print(f"  Loaded {len(self._shapes)} route shapes")

    def _load_trips(self):
        """Load route -> shape mappings from trips.txt"""
        trips_file = self.gtfs_dir / 'trips.txt'
        if not trips_file.exists():
            print(f"Warning: trips.txt not found at {trips_file}")
            return

        df = pd.read_csv(trips_file)

        for _, row in df.iterrows():
            route_id = str(row['route_id']).strip('"')
            shape_id = str(row['shape_id']).strip('"')

            if shape_id not in self._route_shapes[route_id]:
                self._route_shapes[route_id].append(shape_id)

        print(f"  Loaded route mappings for {len(self._route_shapes)} routes")

    def _load_stop_times(self):
        """Load stop distances and stop sequences from stop_times.txt"""
        stop_times_file = self.gtfs_dir / 'stop_times.txt'
        if not stop_times_file.exists():
            print(f"Warning: stop_times.txt not found at {stop_times_file}")
            return

        df = pd.read_csv(stop_times_file)

        # Load trips to get trip_id -> (shape_id, route_id) mapping
        trips_file = self.gtfs_dir / 'trips.txt'
        trips_df = pd.read_csv(trips_file)
        trip_to_shape = {}
        trip_to_route = {}
        for _, row in trips_df.iterrows():
            trip_id = str(row['trip_id']).strip('"')
            trip_to_shape[trip_id] = str(row['shape_id']).strip('"')
            trip_to_route[trip_id] = str(row['route_id']).strip('"')

        # Track stop sequences per route
        route_stop_sequences_raw = defaultdict(dict)  # route_id -> {stop_id: [sequences]}

        for _, row in df.iterrows():
            trip_id = str(row['trip_id']).strip('"')
            stop_id = str(row['stop_id']).strip('"')
            dist = row['shape_dist_traveled']
            stop_seq = int(row['stop_sequence'])

            shape_id = trip_to_shape.get(trip_id)
            route_id = trip_to_route.get(trip_id)

            if shape_id:
                key = (shape_id, stop_id)
                # Keep the distance (may overwrite but should be same for same shape)
                self._stop_distances[key] = dist
                self._shape_stops[shape_id].add(stop_id)

            # Build route -> stop -> sequence mapping
            # Use the minimum sequence number seen for each (route, stop) pair
            if route_id:
                if stop_id not in route_stop_sequences_raw[route_id]:
                    route_stop_sequences_raw[route_id][stop_id] = stop_seq
                else:
                    # Keep the minimum (first occurrence on route)
                    route_stop_sequences_raw[route_id][stop_id] = min(
                        route_stop_sequences_raw[route_id][stop_id], stop_seq
                    )

        # Convert to final format: (route_id, stop_id) -> stop_sequence
        for route_id, stop_seqs in route_stop_sequences_raw.items():
            max_seq = max(stop_seqs.values()) if stop_seqs else 1
            self._route_max_sequence[route_id] = max_seq
            for stop_id, seq in stop_seqs.items():
                self._route_stop_sequences[(route_id, stop_id)] = seq

        print(f"  Loaded {len(self._stop_distances)} (shape, stop) distances")
        print(f"  Loaded {len(self._route_stop_sequences)} (route, stop) sequences for {len(self._route_max_sequence)} routes")

    def _snap_to_shape(self, shape_id: str, lat: float, lon: float) -> Optional[float]:
        """
        Find the shape_dist_traveled at a given position by snapping to nearest point on route.
        Uses linear interpolation for accuracy.
        """
        points = self._shapes.get(shape_id)
        if not points:
            return None

        min_dist = float('inf')
        best_traveled = 0.0

        for i, (pt_lat, pt_lon, pt_dist) in enumerate(points):
            dist = haversine_distance(lat, lon, pt_lat, pt_lon)

            if dist < min_dist:
                min_dist = dist

                # Interpolate between this point and next for accuracy
                if i < len(points) - 1:
                    next_lat, next_lon, next_dist = points[i + 1]
                    best_traveled = self._interpolate_distance(
                        lat, lon,
                        pt_lat, pt_lon, pt_dist,
                        next_lat, next_lon, next_dist
                    )
                else:
                    best_traveled = pt_dist

        return best_traveled

    def _interpolate_distance(
        self, lat: float, lon: float,
        p1_lat: float, p1_lon: float, p1_dist: float,
        p2_lat: float, p2_lon: float, p2_dist: float
    ) -> float:
        """Interpolate shape_dist_traveled between two consecutive shape points."""
        # Vector from p1 to p2 (in degrees, approximate for small distances)
        dx = p2_lon - p1_lon
        dy = p2_lat - p1_lat

        # Vector from p1 to query point
        px = lon - p1_lon
        py = lat - p1_lat

        # Project query point onto segment
        segment_len_sq = dx * dx + dy * dy
        if segment_len_sq < 1e-12:
            return p1_dist

        t = max(0, min(1, (px * dx + py * dy) / segment_len_sq))

        return p1_dist + t * (p2_dist - p1_dist)

    def get_route_distance(
        self,
        route_id: int,
        bus_lat: float,
        bus_lon: float,
        target_stop_id: str
    ) -> Optional[float]:
        """
        Calculate the actual route distance from bus position to target stop.

        Args:
            route_id: Route ID from telemetry
            bus_lat: Bus latitude
            bus_lon: Bus longitude
            target_stop_id: Target stop ID

        Returns:
            Distance in miles along the route, or None if cannot be calculated
        """
        route_id_str = str(route_id)
        target_stop_str = str(target_stop_id)

        # Get all shapes for this route
        shape_ids = self._route_shapes.get(route_id_str, [])
        if not shape_ids:
            return None

        # Collect candidates: (remaining_distance, snap_distance, is_approaching)
        candidates = []

        for shape_id in shape_ids:
            # Check if this shape serves the target stop
            if target_stop_str not in self._shape_stops.get(shape_id, set()):
                continue

            # Get stop's distance on this shape
            stop_dist = self._stop_distances.get((shape_id, target_stop_str))
            if stop_dist is None:
                continue

            # Snap bus to this shape
            bus_dist = self._snap_to_shape(shape_id, bus_lat, bus_lon)
            if bus_dist is None:
                continue

            # Calculate how close bus is to this shape (for selecting best match)
            points = self._shapes.get(shape_id, [])
            if not points:
                continue

            snap_dist = min(
                haversine_distance(bus_lat, bus_lon, pt[0], pt[1])
                for pt in points[:100:5]  # Sample every 5th point for speed
            )

            # Skip if bus is too far from this shape
            if snap_dist > 0.2:  # More than 0.2 miles from shape
                continue

            remaining = stop_dist - bus_dist

            if remaining >= 0:
                # Bus is approaching the stop - this is the preferred case
                candidates.append((remaining, snap_dist, True, shape_id))
            else:
                # Bus appears to have passed the stop on this shape
                # Only consider wraparound if remaining is significantly negative
                # (not just floating point error or bus barely past)
                if remaining < -0.1:  # More than 0.1 miles past
                    total_route_dist = points[-1][2]
                    wrapped = total_route_dist + remaining
                    if wrapped > 0:
                        candidates.append((wrapped, snap_dist, False, shape_id))
                else:
                    # Bus just barely passed - treat as at the stop
                    candidates.append((0.0, snap_dist, True, shape_id))

        if not candidates:
            return None

        # Prefer approaching candidates (remaining >= 0) over wrapped candidates
        approaching = [c for c in candidates if c[2]]
        if approaching:
            # Among approaching candidates, prefer shortest remaining distance
            # Only consider candidates where bus is reasonably close to route (snap < 0.1 mi)
            close_approaching = [c for c in approaching if c[1] < 0.1]
            if close_approaching:
                # Pick the shortest remaining distance among close candidates
                close_approaching.sort(key=lambda x: x[0])
                return close_approaching[0][0]
            else:
                # Fall back to closest to route
                approaching.sort(key=lambda x: (x[1], x[0]))
                return approaching[0][0]
        else:
            # All candidates have wrapped - pick smallest wrapped distance
            candidates.sort(key=lambda x: x[0])
            wrapped_dist = candidates[0][0]

            # Sanity check: if wrapped distance is very large compared to what
            # would be reasonable, return None to fall back to haversine.
            # This handles cases where the bus just passed the stop and telemetry
            # hasn't updated nextStopId yet.
            if wrapped_dist > 5.0:
                # Let the caller fall back to haversine for these edge cases
                return None

            return wrapped_dist

    def get_route_distance_vectorized(
        self,
        route_id: int,
        lats: np.ndarray,
        lons: np.ndarray,
        target_stop_id: str,
        stop_coords: tuple[float, float]
    ) -> np.ndarray:
        """
        Vectorized route distance calculation with haversine fallback.

        Args:
            route_id: Route ID from telemetry
            lats: Array of bus latitudes
            lons: Array of bus longitudes
            target_stop_id: Target stop ID
            stop_coords: (lat, lon) of target stop for haversine fallback

        Returns:
            Array of distances in miles
        """
        n = len(lats)
        distances = np.zeros(n, dtype=np.float32)

        for i in range(n):
            route_dist = self.get_route_distance(
                route_id, lats[i], lons[i], target_stop_id
            )

            if route_dist is not None:
                distances[i] = route_dist
            else:
                # Fallback to haversine
                distances[i] = haversine_distance(
                    lats[i], lons[i], stop_coords[0], stop_coords[1]
                )

        return distances

    def get_stop_sequence(self, route_id: int, stop_id: int) -> Optional[int]:
        """
        Get the stop sequence number for a stop on a route.

        Args:
            route_id: Route ID
            stop_id: Stop ID

        Returns:
            Stop sequence (1-indexed position along route), or None if not found
        """
        key = (str(route_id), str(stop_id))
        return self._route_stop_sequences.get(key)

    def get_max_stop_sequence(self, route_id: int) -> int:
        """
        Get the maximum stop sequence for a route.

        Args:
            route_id: Route ID

        Returns:
            Maximum stop sequence (total stops on route), or 1 if not found
        """
        return self._route_max_sequence.get(str(route_id), 1)


class StopMapper:
    """Lightweight stop name to ID mapper."""

    def __init__(self, stops_json_path: str):
        with open(stops_json_path, 'r') as f:
            stops = json.load(f)

        self.name_to_id = {s['name']: str(s['id']) for s in stops}
        # Store coords with BOTH string and int keys for flexible lookup
        self.id_to_coords = {}
        for s in stops:
            coords = (s['lat'], s['lon'])
            self.id_to_coords[str(s['id'])] = coords  # String key
            try:
                self.id_to_coords[int(s['id'])] = coords  # Int key
            except (ValueError, TypeError):
                pass

        # Normalized names for fuzzy matching
        self.normalized = {}
        for name, sid in self.name_to_id.items():
            normalized = name.lower().replace('&', 'and').replace('-', ' ').strip()
            self.normalized[normalized] = sid

    def get_stop_id(self, station_name: str) -> Optional[str]:
        if station_name in self.name_to_id:
            return self.name_to_id[station_name]
        normalized = station_name.lower().replace('&', 'and').replace('-', ' ').strip()
        return self.normalized.get(normalized)

    def get_coords(self, stop_id) -> Optional[tuple]:
        """Get coordinates for a stop ID (accepts int or string)."""
        # Try direct lookup first
        coords = self.id_to_coords.get(stop_id)
        if coords:
            return coords
        # Try as string if int was passed
        return self.id_to_coords.get(str(stop_id))


class WeatherIndex:
    """Memory-efficient weather lookup."""

    def __init__(self, weather_csv_path: str):
        df = pd.read_csv(weather_csv_path)
        df['time'] = pd.to_datetime(df['time'])

        # Store as dict for O(1) lookup
        self.data = {}
        for _, row in df.iterrows():
            key = row['time'].strftime('%Y-%m-%d-%H')
            self.data[key] = (
                row['precipitation'],
                row['precipitation_probability'],
                row['temperature_2m']
            )

        del df
        gc.collect()

    def get(self, timestamp_ms: int) -> tuple:
        dt = datetime.utcfromtimestamp(timestamp_ms / 1000)
        key = dt.strftime('%Y-%m-%d-%H')
        return self.data.get(key, (0.0, 0, 20.0))


class ArrivalsIndex:
    """Memory-efficient arrivals lookup using sorted arrays."""

    def __init__(self, arrivals_csv_path: str, stop_mapper: StopMapper):
        print("Loading arrivals data...")
        df = pd.read_csv(arrivals_csv_path, skiprows=1, low_memory=False)

        # Parse dates vectorized (much faster than apply)
        df['date'] = pd.to_datetime(df['DATE'])

        # Parse times - handle overflow past midnight
        df['arrival_td'] = pd.to_timedelta(df['ARRIVAL'].fillna('0:00:00'))
        df['departure_td'] = pd.to_timedelta(df['DEPARTURE'].fillna('0:00:00'))

        # Vectorized datetime creation
        df['arrival_dt'] = df['date'] + df['arrival_td']
        df['departure_dt'] = df['date'] + df['departure_td']

        # Vectorized timestamp conversion (assume CST = UTC+6)
        df['arrival_ts'] = (df['arrival_dt'].astype('int64') // 10**6 + 6 * 3600 * 1000)
        df['departure_ts'] = (df['departure_dt'].astype('int64') // 10**6 + 6 * 3600 * 1000)

        # Map stop names
        df['stop_id'] = df['Station'].apply(stop_mapper.get_stop_id)
        df['vehicle_id'] = df['Vehicle ID'].str.strip()

        # Extract dwell/boarding info
        df['dwell_sec'] = pd.to_numeric(df['Dwell (sec)'], errors='coerce').fillna(0)
        df['boardings'] = pd.to_numeric(df['APC Boardings'], errors='coerce').fillna(0)
        df['alightings'] = pd.to_numeric(df['APC Alightings'], errors='coerce').fillna(0)

        # Build index: vehicle_id -> sorted list of (arrival_ts, stop_id, dwell, board, alight)
        self.index = defaultdict(list)

        valid = df[df['stop_id'].notna()].copy()
        for _, row in valid.iterrows():
            self.index[row['vehicle_id']].append((
                row['arrival_ts'],
                row['stop_id'],
                row['dwell_sec'],
                row['boardings'],
                row['alightings']
            ))

        # Sort each vehicle's arrivals by time
        for vid in self.index:
            self.index[vid].sort(key=lambda x: x[0])

        print(f"Indexed {len(valid)} arrivals for {len(self.index)} vehicles")

        del df, valid
        gc.collect()

    def find_arrival(self, vehicle_id: str, transition_ts: int, stop_id: str,
                     window_before: int = 60000, window_after: int = 120000) -> Optional[dict]:
        """Binary search for arrival near transition."""
        arrivals = self.index.get(vehicle_id, [])
        if not arrivals:
            return None

        # Binary search for timestamp
        lo, hi = 0, len(arrivals)
        target = transition_ts

        while lo < hi:
            mid = (lo + hi) // 2
            if arrivals[mid][0] < target - window_before:
                lo = mid + 1
            else:
                hi = mid

        # Check arrivals in window
        for i in range(max(0, lo - 5), min(len(arrivals), lo + 10)):
            arr_ts, arr_stop, dwell, board, alight = arrivals[i]

            if arr_ts < transition_ts - window_before:
                continue
            if arr_ts > transition_ts + window_after:
                break

            if arr_stop == stop_id:
                return {
                    'arrival_ts': arr_ts,
                    'dwell_sec': dwell,
                    'boardings': board,
                    'alightings': alight
                }

        return None


def normalize_record(record: dict) -> Optional[dict]:
    """Normalize different JSONL formats to a common structure."""
    # Check if it's the new flat format
    if 'vid' in record and 'lat' in record:
        return record

    # Old nested format - extract and flatten
    if 'lt' in record and 'ln' in record:
        try:
            normalized = {
                't': record.get('ts', record.get('t', 0)),
                'vid': record.get('did', record.get('aID', '')),
                'lat': record['lt'],
                'lon': record['ln'],
                'heading': record.get('h', 0),
                'speed': record.get('v', 0),
                'load': record.get('load', 0),
                'routeId': record.get('serviceState', {}).get('rID', 0) if isinstance(record.get('serviceState'), dict) else 0,
                'patternId': record.get('serviceState', {}).get('patternID', 0) if isinstance(record.get('serviceState'), dict) else 0,
                'progress': record.get('serviceState', {}).get('nextStopPercentProgress', 0) if isinstance(record.get('serviceState'), dict) else 0,
                'lastStopId': record.get('lastStop', {}).get('stopID', 0) if isinstance(record.get('lastStop'), dict) else 0,
                'lastStopTime': record.get('lastStop', {}).get('time', 0) if isinstance(record.get('lastStop'), dict) else 0,
                'lastStopOnTime': record.get('lastStop', {}).get('onTime', 0) if isinstance(record.get('lastStop'), dict) else 0,
                'nextStopId': record.get('eta', {}).get('stopID', 0) if isinstance(record.get('eta'), dict) else 0,
                'etaSeconds': record.get('eta', {}).get('eta', 0) if isinstance(record.get('eta'), dict) else 0,
                'scheduledEta': record.get('eta', {}).get('seta', 0) if isinstance(record.get('eta'), dict) else 0,
                'isDelayed': record.get('isDelayed', False)
            }
            return normalized
        except (KeyError, TypeError):
            return None

    return None


def stream_jsonl_files(directory: Path) -> Generator[pd.DataFrame, None, None]:
    """Stream JSONL files one at a time to save memory."""
    jsonl_files = sorted(directory.glob('*.jsonl'))
    print(f"Found {len(jsonl_files)} JSONL files to process")

    for file_path in jsonl_files:
        if file_path.stat().st_size == 0:
            continue

        print(f"  Processing {file_path.name}...")

        # Load and normalize records
        records = []
        with open(file_path, 'r') as f:
            for line in f:
                if line.strip():
                    try:
                        raw = json.loads(line)
                        normalized = normalize_record(raw)
                        if normalized:
                            records.append(normalized)
                    except json.JSONDecodeError:
                        continue

        if records:
            df = pd.DataFrame(records)

            # Filter invalid rows - check columns exist first
            required_cols = ['vid', 'lat', 'lon', 'patternId', 'routeId', 'nextStopId']
            if not all(col in df.columns for col in required_cols):
                print(f"    Skipping - missing required columns")
                del records
                gc.collect()
                continue

            df = df.dropna(subset=['vid', 'lat', 'lon'])
            df = df[df['patternId'] != 9998]
            df = df[df['routeId'].notna() & (df['routeId'] != 777)]
            df = df[df['nextStopId'] > 0]

            if len(df) > 0:
                yield df

            del df, records
            gc.collect()


def build_features_vectorized(df: pd.DataFrame, weather: WeatherIndex,
                               arrival_info: dict, distances: np.ndarray) -> np.ndarray:
    """Build feature vectors using vectorized operations.

    Feature layout (35 total):
    0-7:   Core features (speed, heading, load, progress, delay, eta, scheduled_eta, distance)
    8-13:  Time features (time_sin, time_cos, day_normalized, morning_rush, afternoon_rush, class_change)
    14-20: Day of week one-hot (7 features)
    21-24: Weather features (precip, is_raining, precip_prob, temp)
    25-26: ETA indicator flags (has_system_eta, has_scheduled_eta)
    27-30: Segment features (route_id, pattern_id, stop_sequence_raw, stop_sequence_normalized)
           - stop_sequence_raw: GTFS stop sequence (1, 2, ..., ~216) - position along route
           - stop_sequence_normalized: stop_sequence / max_stops (0 to 1)
    31-34: History features (progress_rate, speed_mean, time_stopped, is_stopped)

    NOTE: dwell_sec, boardings, alightings REMOVED (near-zero correlation with ETA)
    NOTE: segment_id is now GTFS stop_sequence, not hash of (from->to)
    """
    n = len(df)
    features = np.zeros((n, 35), dtype=np.float32)

    # Convert timestamps to LOCAL time (Central = UTC-6)
    ts_seconds = df['t'].values / 1000
    ts_local = ts_seconds - 6 * 3600  # UTC to Central time

    # Core features (vectorized)
    features[:, 0] = df['speed'].fillna(0).values
    features[:, 1] = df['heading'].fillna(0).values / 360.0
    features[:, 2] = df['load'].fillna(0).values
    features[:, 3] = df['progress'].fillna(0).clip(0, 1).values  # FIXED: Clip to [0,1]
    features[:, 4] = df['lastStopOnTime'].fillna(0).values

    # ETA features with indicator flags for missing values
    # Treat 0 as "missing" since 0 seconds ETA is impossible
    system_eta_raw = df['etaSeconds'].fillna(0).values
    scheduled_eta_raw = df['scheduledEta'].fillna(0).values

    # Indicator flags: 1.0 if valid ETA exists, 0.0 if missing
    has_system_eta = (system_eta_raw > 0).astype(np.float32)
    has_scheduled_eta = (scheduled_eta_raw > 0).astype(np.float32)

    # Replace 0 with -1 sentinel (will normalize to distinct value)
    # This prevents 0 from being interpreted as "ETA is 0 seconds"
    system_eta_clean = np.where(system_eta_raw > 0, system_eta_raw, -1)
    scheduled_eta_clean = np.where(scheduled_eta_raw > 0, scheduled_eta_raw, -1)

    features[:, 5] = system_eta_clean
    features[:, 6] = scheduled_eta_clean
    features[:, 25] = has_system_eta
    features[:, 26] = has_scheduled_eta

    # Distance feature
    features[:, 7] = distances

    # Time features - FIXED: Use local time and correct calculation
    # Direct calculation: seconds since midnight / 60 = minutes since midnight
    time_of_day_minutes = (ts_local % 86400) / 60  # FIXED: No double-counting

    features[:, 8] = np.sin(2 * np.pi * time_of_day_minutes / 1440)  # time_sin (1440 = 24*60)
    features[:, 9] = np.cos(2 * np.pi * time_of_day_minutes / 1440)  # time_cos

    # Day of week - FIXED: Use local time for correct day boundaries
    day_of_week = ((ts_local // 86400) + 4) % 7  # Unix epoch was Thursday
    features[:, 10] = day_of_week / 6.0  # day_normalized

    # Rush hour flags - FIXED: Use integer hours from local time
    hours_local = (ts_local % 86400) // 3600  # Integer hours 0-23
    minutes_local = ((ts_local % 86400) % 3600) // 60  # Integer minutes 0-59

    features[:, 11] = ((hours_local >= 7) & (hours_local < 9)).astype(np.float32)  # morning rush
    features[:, 12] = ((hours_local >= 16) & (hours_local < 18)).astype(np.float32)  # afternoon rush
    features[:, 13] = ((minutes_local >= 50) | (minutes_local <= 10)).astype(np.float32)  # class change

    # Day of week one-hot (14-20)
    for d in range(7):
        features[:, 14 + d] = (day_of_week == d).astype(np.float32)

    # Weather features (need to look up per row - but batch by hour)
    hour_keys = {}
    for i, ts in enumerate(df['t'].values):
        dt = datetime.utcfromtimestamp(ts / 1000)
        key = dt.strftime('%Y-%m-%d-%H')
        if key not in hour_keys:
            hour_keys[key] = weather.get(ts)
        precip, precip_prob, temp = hour_keys[key]
        features[i, 21] = precip
        features[i, 22] = 1.0 if precip > 0 else 0.0
        features[i, 23] = precip_prob / 100.0
        features[i, 24] = temp / 40.0

    # NOTE: dwell_sec, boardings, alightings REMOVED - near-zero correlation with ETA

    # Segment position features (27-30)
    # Route ID normalized (routes typically 6-232)
    features[:, 27] = df['routeId'].fillna(0).values / 300.0

    # Pattern ID normalized (patterns typically 0-30000)
    features[:, 28] = df['patternId'].fillna(0).values / 30000.0

    # Stop sequence features (29-30)
    # NOTE: These are placeholder values that will be overwritten in process_vehicle_batch
    # with actual GTFS stop sequence data. Column 29 = raw sequence, Column 30 = normalized.
    # Default to progress as fallback if GTFS data not available.
    features[:, 29] = 0.0  # Will be set to GTFS stop_sequence in process_vehicle_batch
    features[:, 30] = df['progress'].fillna(0).clip(0, 1).values  # Fallback if no GTFS

    return features


def process_vehicle_batch(vid_data: pd.DataFrame, vid: str, vid_idx: int,
                          arrivals: ArrivalsIndex, weather: WeatherIndex,
                          stop_mapper: StopMapper, gtfs_distance: Optional[GTFSRouteDistance],
                          min_eta: int, max_eta: int, sample_rate: int) -> tuple:
    """Process a single vehicle's data efficiently.

    Returns:
        Tuple of (features, labels, vehicle_ids, route_ids) or (None, None, None, None)
    """

    features_batch = []
    labels_batch = []
    vehicle_ids_batch = []
    route_ids_batch = []  # Track route IDs to separate jAUnt data

    # Sort by timestamp
    vid_data = vid_data.sort_values('t')
    timestamps = vid_data['t'].values
    next_stops = vid_data['nextStopId'].values.astype(str)
    route_ids = vid_data['routeId'].values

    # Pre-compute history features for entire vehicle timeline
    # These will be indexed later for each valid sample
    speeds_arr = vid_data['speed'].fillna(0).values
    progress_arr = vid_data['progress'].fillna(0).values
    history_feats = compute_history_features_vectorized(
        timestamps, speeds_arr, progress_arr, window_seconds=90
    )

    # Detect transitions
    transitions = []
    prev_stop = None
    prev_ts = None

    for i in range(len(vid_data)):
        curr_stop = next_stops[i] if next_stops[i] != 'nan' and next_stops[i] != '0' else None
        ts = int(timestamps[i])

        if prev_stop is not None and prev_stop != curr_stop:
            # Transition detected
            arrival_info = arrivals.find_arrival(vid, ts, prev_stop)
            if arrival_info:
                transitions.append((i, ts, prev_stop, arrival_info))

        prev_stop = curr_stop
        prev_ts = ts

    # Process approach sequences
    prev_stop = None
    approach_start = 0

    for i in range(len(vid_data)):
        curr_stop = next_stops[i] if next_stops[i] != 'nan' and next_stops[i] != '0' else None
        ts = int(timestamps[i])

        if prev_stop != curr_stop:
            # End of approach
            if prev_stop is not None:
                # Find matching transition
                for trans_idx, trans_ts, trans_stop, arrival_info in transitions:
                    if trans_stop == prev_stop and abs(trans_ts - ts) < 5000:
                        actual_arrival_ts = arrival_info['arrival_ts']

                        # Get approach data
                        approach_df = vid_data.iloc[approach_start:i:sample_rate]

                        if len(approach_df) > 0:
                            # Get stop coordinates for fallback
                            stop_coords = stop_mapper.get_coords(int(prev_stop))

                            # Calculate distances using GTFS route distance if available
                            if gtfs_distance is not None and stop_coords:
                                # Get route_id from first record (should be consistent)
                                route_id = int(approach_df['routeId'].iloc[0])
                                distances = gtfs_distance.get_route_distance_vectorized(
                                    route_id,
                                    approach_df['lat'].values,
                                    approach_df['lon'].values,
                                    prev_stop,
                                    stop_coords
                                )
                            elif stop_coords:
                                # Fallback to haversine
                                distances = haversine_distance_vectorized(
                                    approach_df['lat'].values,
                                    approach_df['lon'].values,
                                    stop_coords[0], stop_coords[1]
                                )
                            else:
                                distances = np.zeros(len(approach_df))

                            # Calculate actual ETAs
                            actual_etas = (actual_arrival_ts - approach_df['t'].values) / 1000.0

                            # Filter valid ETAs
                            valid_mask = (actual_etas > min_eta) & (actual_etas < max_eta)

                            if valid_mask.any():
                                valid_df = approach_df[valid_mask]
                                valid_etas = actual_etas[valid_mask]
                                valid_distances = distances[valid_mask]

                                # Build features
                                feats = build_features_vectorized(
                                    valid_df, weather, arrival_info, valid_distances
                                )

                                # Convert ETA fields to seconds until arrival
                                # etaSeconds is "minutes since midnight" not "seconds until arrival"
                                ts_local = valid_df['t'].values / 1000 - 6 * 3600
                                current_minutes = ((ts_local % 86400) / 60)

                                eta_field = valid_df['etaSeconds'].fillna(0).values
                                sched_field = valid_df['scheduledEta'].fillna(0).values

                                # Convert from minutes-since-midnight to seconds-until-arrival
                                system_eta_sec = (eta_field - current_minutes) * 60
                                sched_eta_sec = (sched_field - current_minutes) * 60

                                # Use -1 sentinel for missing/invalid ETAs, set indicator flags
                                # Valid ETA: field > 0 AND result > 0 (positive time until arrival)
                                valid_system = (eta_field > 0) & (system_eta_sec > 0)
                                valid_sched = (sched_field > 0) & (sched_eta_sec > 0)

                                feats[:, 5] = np.where(valid_system, system_eta_sec, -1)
                                feats[:, 6] = np.where(valid_sched, sched_eta_sec, -1)
                                feats[:, 25] = valid_system.astype(np.float32)  # has_system_eta
                                feats[:, 26] = valid_sched.astype(np.float32)   # has_scheduled_eta

                                # Add history features (columns 31-34)
                                # Map valid_df timestamps to original vid_data indices
                                valid_timestamps = valid_df['t'].values
                                for j, vts in enumerate(valid_timestamps):
                                    # Find index in original timeline
                                    orig_idx = np.searchsorted(timestamps, vts)
                                    if orig_idx < len(timestamps) and timestamps[orig_idx] == vts:
                                        feats[j, 31] = history_feats['progress_rate'][orig_idx]
                                        feats[j, 32] = history_feats['speed_rolling_mean'][orig_idx]
                                        feats[j, 33] = history_feats['time_stopped'][orig_idx]
                                        feats[j, 34] = history_feats['is_stopped'][orig_idx]

                                # Update segment_id to use GTFS stop sequence
                                # Column 29 = raw stop sequence (1, 2, ..., ~216)
                                # Column 30 = normalized stop sequence (seq / max_seq)
                                if gtfs_distance is not None:
                                    stop_seq = gtfs_distance.get_stop_sequence(route_id, int(prev_stop))
                                    max_seq = gtfs_distance.get_max_stop_sequence(route_id)
                                    if stop_seq is not None:
                                        feats[:, 29] = float(stop_seq)  # Raw sequence number
                                        feats[:, 30] = float(stop_seq) / max_seq  # Normalized 0-1

                                features_batch.append(feats)
                                labels_batch.append(valid_etas.reshape(-1, 1))
                                vehicle_ids_batch.extend([vid_idx] * len(valid_etas))
                                # Track route IDs for each sample
                                route_ids_batch.extend(valid_df['routeId'].values.astype(np.int32))

                        break

            approach_start = i

        prev_stop = curr_stop

    if features_batch:
        return (
            np.vstack(features_batch),
            np.vstack(labels_batch),
            np.array(vehicle_ids_batch, dtype=np.int64),
            np.array(route_ids_batch, dtype=np.int32)
        )

    return None, None, None, None


def prepare_training_data_streaming(
    telemetry_dir: str,
    arrivals_csv: str,
    weather_csv: str,
    stops_json: str,
    output_dir: str,
    gtfs_dir: str = None,
    min_eta_seconds: int = 30,
    max_eta_seconds: int = 900,
    sample_rate: int = 5,
    max_files: int = None,
    route_filter: int = None
) -> dict:
    """
    Memory-efficient streaming data preparation.

    Processes one telemetry file at a time, writes results incrementally.
    Uses GTFS route distance instead of straight-line distance.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("STREAMING DATA PREPARATION (Memory Optimized)")
    if route_filter is not None:
        print(f"*** FILTERING TO ROUTE {route_filter} ONLY ***")
    print("=" * 60)

    # Load lightweight indexes
    print("\nLoading indexes...")
    stop_mapper = StopMapper(stops_json)
    weather = WeatherIndex(weather_csv)
    arrivals = ArrivalsIndex(arrivals_csv, stop_mapper)

    # Load GTFS route distance calculator
    gtfs_distance = None
    if gtfs_dir:
        print("\nLoading GTFS data for route distance...")
        gtfs_distance = GTFSRouteDistance(gtfs_dir)
    else:
        print("\nWarning: No GTFS directory specified, using haversine (straight-line) distance")

    # Vehicle ID mapping
    vehicle_id_to_idx = {}
    next_vehicle_idx = 0

    # Stats
    stats = {
        'total_files': 0,
        'total_transitions': 0,
        'valid_training_points': 0,
        'jaunt_training_points': 0
    }

    # jAUnt route ID (route 232)
    JAUNT_ROUTE_ID = 232

    # Accumulate results (or write incrementally for very large datasets)
    all_features = []
    all_labels = []
    all_vehicle_ids = []
    all_route_ids = []

    # Separate accumulators for jAUnt data
    jaunt_features = []
    jaunt_labels = []
    jaunt_vehicle_ids = []

    # Stream through files
    file_count = 0
    for df in stream_jsonl_files(Path(telemetry_dir)):
        file_count += 1
        if max_files and file_count > max_files:
            print(f"  Stopping after {max_files} files (--max-files)")
            break

        stats['total_files'] += 1

        # Filter by route if specified (dramatically speeds up processing)
        if route_filter is not None:
            df = df[df['routeId'] == route_filter]
            if len(df) == 0:
                continue  # Skip files with no data for this route

        # Process each vehicle in this file
        for vid in df['vid'].unique():
            # Skip jAUnt vehicles entirely (they go to separate dataset)
            is_jaunt_vehicle = str(vid).lower().startswith('jaunt')

            if vid not in vehicle_id_to_idx:
                vehicle_id_to_idx[vid] = next_vehicle_idx
                next_vehicle_idx += 1

            vid_idx = vehicle_id_to_idx[vid]
            vid_data = df[df['vid'] == vid]

            # For jAUnt vehicles, only process for the separate jAUnt dataset
            if is_jaunt_vehicle:
                # Skip adding to main vehicle mapping (will be filtered later)
                pass

            feats, labels, vids, routes = process_vehicle_batch(
                vid_data, vid, vid_idx,
                arrivals, weather, stop_mapper, gtfs_distance,
                min_eta_seconds, max_eta_seconds, sample_rate
            )

            if feats is not None:
                # Separate jAUnt (route 232) from other routes
                jaunt_mask = (routes == JAUNT_ROUTE_ID)
                other_mask = ~jaunt_mask

                # Add non-jAUnt data to main dataset
                if other_mask.any():
                    all_features.append(feats[other_mask])
                    all_labels.append(labels[other_mask])
                    all_vehicle_ids.append(vids[other_mask])
                    all_route_ids.append(routes[other_mask])  # NEW: Track route IDs
                    stats['valid_training_points'] += int(other_mask.sum())

                # Add jAUnt data to separate dataset
                if jaunt_mask.any():
                    jaunt_features.append(feats[jaunt_mask])
                    jaunt_labels.append(labels[jaunt_mask])
                    jaunt_vehicle_ids.append(vids[jaunt_mask])
                    stats['jaunt_training_points'] += int(jaunt_mask.sum())

        # Free memory
        del df
        gc.collect()

        print(f"    Running total: {stats['valid_training_points']} valid points, "
              f"{stats['jaunt_training_points']} jAUnt points")

    if not all_features and not jaunt_features:
        print("ERROR: No valid training points!")
        return stats

    # Save main dataset (non-jAUnt)
    if all_features:
        print("\nCombining main dataset results...")
        features_array = np.vstack(all_features)
        labels_array = np.vstack(all_labels)
        vehicle_ids_array = np.concatenate(all_vehicle_ids)
        route_ids_array = np.concatenate(all_route_ids)  # NEW: Save route IDs

        # FIXED: Deduplicate samples
        # Same telemetry point can appear in multiple approach sequences for loop routes
        combined = np.column_stack([vehicle_ids_array, features_array[:, 0:8]])
        _, unique_idx = np.unique(combined, axis=0, return_index=True)
        unique_idx = np.sort(unique_idx)  # Preserve original order

        before_count = len(features_array)
        features_array = features_array[unique_idx]
        labels_array = labels_array[unique_idx]
        vehicle_ids_array = vehicle_ids_array[unique_idx]
        route_ids_array = route_ids_array[unique_idx]

        print(f"Deduplicated: {before_count} -> {len(features_array)} samples "
              f"(removed {before_count - len(features_array)} duplicates)")

        # Update stats after deduplication
        stats['valid_training_points'] = len(features_array)

        # Compute normalization stats
        means = features_array.mean(axis=0)
        stds = features_array.std(axis=0)
        stds[stds < 1e-6] = 1.0

        print(f"\nSaving main dataset to {output_path}...")
        np.save(output_path / 'features.npy', features_array)
        np.save(output_path / 'labels.npy', labels_array)
        np.save(output_path / 'vehicle_ids.npy', vehicle_ids_array)
        np.save(output_path / 'route_ids.npy', route_ids_array)  # NEW: Save route IDs

        # Filter out jAUnt vehicles from the main vehicle mapping
        main_vehicle_mapping = {
            vid: idx for vid, idx in vehicle_id_to_idx.items()
            if not str(vid).lower().startswith('jaunt')
        }
        with open(output_path / 'vehicle_mapping.json', 'w') as f:
            json.dump(main_vehicle_mapping, f, indent=2)
        print(f"  Filtered vehicle mapping: {len(main_vehicle_mapping)} vehicles (excluded {len(vehicle_id_to_idx) - len(main_vehicle_mapping)} jAUnt)")

        with open(output_path / 'normalization_stats.json', 'w') as f:
            json.dump({'means': means.tolist(), 'stds': stds.tolist()}, f, indent=2)

        with open(output_path / 'stats.json', 'w') as f:
            json.dump(stats, f, indent=2)

        print(f"\nMain dataset complete!")
        print(f"  Features: {features_array.shape}")
        print(f"  Labels: {labels_array.shape}")
        print(f"  Mean ETA: {labels_array.mean():.1f}s")
    else:
        print("\nNo main dataset points (all routes may be jAUnt)")

    # Save jAUnt dataset separately
    if jaunt_features:
        jaunt_output_path = output_path.parent / (output_path.name + '_jaunt')
        jaunt_output_path.mkdir(parents=True, exist_ok=True)

        print(f"\nCombining jAUnt dataset results...")
        jaunt_features_array = np.vstack(jaunt_features)
        jaunt_labels_array = np.vstack(jaunt_labels)
        jaunt_vehicle_ids_array = np.concatenate(jaunt_vehicle_ids)

        # Compute normalization stats for jAUnt
        jaunt_means = jaunt_features_array.mean(axis=0)
        jaunt_stds = jaunt_features_array.std(axis=0)
        jaunt_stds[jaunt_stds < 1e-6] = 1.0

        print(f"\nSaving jAUnt dataset to {jaunt_output_path}...")
        np.save(jaunt_output_path / 'features.npy', jaunt_features_array)
        np.save(jaunt_output_path / 'labels.npy', jaunt_labels_array)
        np.save(jaunt_output_path / 'vehicle_ids.npy', jaunt_vehicle_ids_array)

        with open(jaunt_output_path / 'vehicle_mapping.json', 'w') as f:
            json.dump(vehicle_id_to_idx, f, indent=2)

        with open(jaunt_output_path / 'normalization_stats.json', 'w') as f:
            json.dump({'means': jaunt_means.tolist(), 'stds': jaunt_stds.tolist()}, f, indent=2)

        jaunt_stats = {
            'total_files': stats['total_files'],
            'valid_training_points': stats['jaunt_training_points'],
            'route_id': JAUNT_ROUTE_ID,
            'route_name': 'jAUnt'
        }
        with open(jaunt_output_path / 'stats.json', 'w') as f:
            json.dump(jaunt_stats, f, indent=2)

        print(f"\njAUnt dataset complete!")
        print(f"  Features: {jaunt_features_array.shape}")
        print(f"  Labels: {jaunt_labels_array.shape}")
        print(f"  Mean ETA: {jaunt_labels_array.mean():.1f}s")
    else:
        print("\nNo jAUnt data points found")

    return stats


def test_distance_calculation(
    telemetry_dir: str,
    stops_json: str,
    max_files: int = 2
):
    """
    Test the distance calculation on a small sample to debug issues.
    """
    print("=" * 60)
    print("TESTING DISTANCE CALCULATION")
    print("=" * 60)

    # Load stop mapper
    stop_mapper = StopMapper(stops_json)
    print(f"\nLoaded {len(stop_mapper.id_to_coords)} stops")
    print("Sample stop IDs:", list(stop_mapper.id_to_coords.keys())[:10])

    # Track stats
    distance_stats = {
        'total_points': 0,
        'coords_found': 0,
        'coords_not_found': 0,
        'distance_calculated': 0,
        'zero_distance': 0,
        'missing_stop_ids': set()
    }

    file_count = 0
    for df in stream_jsonl_files(Path(telemetry_dir)):
        file_count += 1
        if file_count > max_files:
            break

        print(f"\nFile {file_count}: {len(df)} records")
        print(f"  Sample nextStopId values: {df['nextStopId'].head(10).tolist()}")

        # Check distance calculation
        for _, row in df.head(100).iterrows():
            stop_id = row['nextStopId']
            distance_stats['total_points'] += 1

            if pd.isna(stop_id) or stop_id == 0:
                continue

            try:
                stop_id_int = int(stop_id)
            except (ValueError, TypeError):
                distance_stats['missing_stop_ids'].add(str(stop_id))
                continue

            stop_coords = stop_mapper.get_coords(stop_id_int)

            if stop_coords:
                distance_stats['coords_found'] += 1
                lat, lon = row['lat'], row['lon']

                if pd.notna(lat) and pd.notna(lon):
                    dist = haversine_distance_vectorized(
                        np.array([lat]), np.array([lon]),
                        stop_coords[0], stop_coords[1]
                    )[0]

                    if dist > 0:
                        distance_stats['distance_calculated'] += 1
                    else:
                        distance_stats['zero_distance'] += 1

                    if distance_stats['distance_calculated'] <= 5:
                        print(f"    Stop {stop_id_int}: ({lat:.5f}, {lon:.5f}) -> "
                              f"({stop_coords[0]:.5f}, {stop_coords[1]:.5f}) = {dist:.3f} mi")
            else:
                distance_stats['coords_not_found'] += 1
                distance_stats['missing_stop_ids'].add(str(stop_id_int))

        del df
        gc.collect()

    print("\n" + "=" * 60)
    print("DISTANCE CALCULATION TEST RESULTS")
    print("=" * 60)
    print(f"  Total points checked: {distance_stats['total_points']}")
    print(f"  Coords found: {distance_stats['coords_found']}")
    print(f"  Coords NOT found: {distance_stats['coords_not_found']}")
    print(f"  Distance > 0: {distance_stats['distance_calculated']}")
    print(f"  Distance = 0: {distance_stats['zero_distance']}")

    if distance_stats['missing_stop_ids']:
        print(f"\n  Missing stop IDs (sample): {list(distance_stats['missing_stop_ids'])[:20]}")

    return distance_stats


def test_route_distance_calculation(
    telemetry_dir: str,
    stops_json: str,
    gtfs_dir: str,
    max_files: int = 2
):
    """
    Test the GTFS route distance calculation on a small sample.
    Compares route distance vs haversine distance.
    """
    print("=" * 60)
    print("TESTING GTFS ROUTE DISTANCE CALCULATION")
    print("=" * 60)

    if not gtfs_dir:
        print("ERROR: --gtfs directory is required for this test")
        return

    # Load stop mapper and GTFS data
    stop_mapper = StopMapper(stops_json)
    gtfs_distance = GTFSRouteDistance(gtfs_dir)

    print(f"\nLoaded {len(stop_mapper.id_to_coords)} stops")

    # Track stats
    stats = {
        'total_points': 0,
        'route_distance_success': 0,
        'route_distance_fallback': 0,
        'route_distances': [],
        'haversine_distances': [],
        'ratios': []
    }

    file_count = 0
    for df in stream_jsonl_files(Path(telemetry_dir)):
        file_count += 1
        if file_count > max_files:
            break

        print(f"\nFile {file_count}: {len(df)} records")

        # Check distance calculation on sample
        sample_df = df[df['nextStopId'] > 0].head(200)

        for _, row in sample_df.iterrows():
            stop_id = int(row['nextStopId'])
            route_id = int(row['routeId'])
            lat = row['lat']
            lon = row['lon']

            stats['total_points'] += 1

            stop_coords = stop_mapper.get_coords(stop_id)
            if not stop_coords:
                continue

            # Calculate haversine distance
            haversine_dist = haversine_distance(lat, lon, stop_coords[0], stop_coords[1])

            # Calculate route distance
            route_dist = gtfs_distance.get_route_distance(route_id, lat, lon, str(stop_id))

            if route_dist is not None:
                stats['route_distance_success'] += 1
                stats['route_distances'].append(route_dist)
                stats['haversine_distances'].append(haversine_dist)

                # Calculate ratio (route should be >= haversine)
                if haversine_dist > 0.01:  # Only if meaningful distance
                    ratio = route_dist / haversine_dist
                    stats['ratios'].append(ratio)

                    if stats['route_distance_success'] <= 10:
                        print(f"  Route {route_id}, Stop {stop_id}: "
                              f"Route={route_dist:.3f}mi, Haversine={haversine_dist:.3f}mi, "
                              f"Ratio={ratio:.2f}x")
            else:
                stats['route_distance_fallback'] += 1

        del df
        gc.collect()

    print("\n" + "=" * 60)
    print("GTFS ROUTE DISTANCE TEST RESULTS")
    print("=" * 60)
    print(f"  Total points checked: {stats['total_points']}")
    print(f"  Route distance calculated: {stats['route_distance_success']}")
    print(f"  Fallback to haversine: {stats['route_distance_fallback']}")

    if stats['ratios']:
        import numpy as np
        ratios = np.array(stats['ratios'])
        print(f"\n  Route/Haversine Ratio Stats:")
        print(f"    Mean: {ratios.mean():.2f}x")
        print(f"    Median: {np.median(ratios):.2f}x")
        print(f"    Min: {ratios.min():.2f}x")
        print(f"    Max: {ratios.max():.2f}x")
        print(f"    Ratio >= 1.0 (valid): {(ratios >= 0.95).sum()} / {len(ratios)}")

    if stats['route_distances']:
        route_dists = np.array(stats['route_distances'])
        haver_dists = np.array(stats['haversine_distances'])
        print(f"\n  Distance Stats:")
        print(f"    Route distance mean: {route_dists.mean():.3f} miles")
        print(f"    Haversine distance mean: {haver_dists.mean():.3f} miles")

    return stats


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Optimized data preparation')
    parser.add_argument('--telemetry', type=str, required=True)
    parser.add_argument('--arrivals', type=str, required=True)
    parser.add_argument('--weather', type=str, required=True)
    parser.add_argument('--stops', type=str, required=True)
    parser.add_argument('--gtfs', type=str, default=None,
                        help='GTFS data directory for route distance calculation')
    parser.add_argument('--output', type=str, default='./processed_data_v3')
    parser.add_argument('--sample-rate', type=int, default=5)
    parser.add_argument('--route-filter', type=int, default=None,
                        help='Only process data for this route ID (e.g., 100)')
    parser.add_argument('--test-distance', action='store_true',
                        help='Test distance calculation only (2 files)')
    parser.add_argument('--test-route-distance', action='store_true',
                        help='Test GTFS route distance calculation')
    parser.add_argument('--max-files', type=int, default=None,
                        help='Limit number of files to process')

    args = parser.parse_args()

    if args.test_distance:
        test_distance_calculation(
            telemetry_dir=args.telemetry,
            stops_json=args.stops,
            max_files=2
        )
    elif args.test_route_distance:
        test_route_distance_calculation(
            telemetry_dir=args.telemetry,
            stops_json=args.stops,
            gtfs_dir=args.gtfs,
            max_files=2
        )
    else:
        prepare_training_data_streaming(
            telemetry_dir=args.telemetry,
            arrivals_csv=args.arrivals,
            weather_csv=args.weather,
            stops_json=args.stops,
            output_dir=args.output,
            gtfs_dir=args.gtfs,
            sample_rate=args.sample_rate,
            max_files=args.max_files,
            route_filter=args.route_filter
        )


if __name__ == '__main__':
    main()
