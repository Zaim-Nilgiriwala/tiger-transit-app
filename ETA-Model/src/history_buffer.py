"""
Vehicle History Buffer for Rolling Feature Computation

This module tracks the last 90 seconds of telemetry per vehicle to compute
history-based features that significantly improve ETA prediction accuracy.

Key insight: A single snapshot can't distinguish "about to go" vs "stuck at a
light / loading / blocked". History-based features address this by providing
context about recent vehicle behavior.

Features computed:
- progress_rate: Rate of progress change (how fast is bus moving through route)
- speed_rolling_mean: Average speed over 60s window
- speed_rolling_min/max: Min/max speed over 60s window
- acceleration: Change in speed over 30s
- time_stopped: Seconds with speed < 1 mph in last 90s
- is_stopped: Currently stopped (speed < 1 mph)
"""

from collections import deque
from typing import Optional
import numpy as np


class VehicleHistoryBuffer:
    """
    Maintains a rolling history buffer for each vehicle.

    Stores (timestamp, speed, progress) tuples for the last max_history_seconds
    and computes rolling features on demand.
    """

    def __init__(self, max_history_seconds: int = 90):
        """
        Initialize the history buffer.

        Args:
            max_history_seconds: Maximum history to retain (default 90s)
        """
        self.max_history_ms = max_history_seconds * 1000  # Convert to milliseconds
        self._buffers: dict[str, deque] = {}  # vid -> deque of (ts, speed, progress)

    def add_observation(
        self,
        vid: str,
        timestamp_ms: int,
        speed: float,
        progress: float
    ):
        """
        Add a new observation for a vehicle.

        Args:
            vid: Vehicle ID
            timestamp_ms: Timestamp in milliseconds
            speed: Current speed (mph)
            progress: Current progress (0-1)
        """
        if vid not in self._buffers:
            self._buffers[vid] = deque(maxlen=1000)  # ~16 min at 1s intervals

        self._buffers[vid].append((timestamp_ms, speed, progress))
        self._prune_old(vid, timestamp_ms)

    def _prune_old(self, vid: str, current_ts: int):
        """Remove observations older than max_history_seconds."""
        buffer = self._buffers.get(vid)
        if not buffer:
            return

        cutoff = current_ts - self.max_history_ms
        while buffer and buffer[0][0] < cutoff:
            buffer.popleft()

    def get_history_features(self, vid: str, current_ts: int) -> dict:
        """
        Compute history-based features for a vehicle.

        Args:
            vid: Vehicle ID
            current_ts: Current timestamp in milliseconds

        Returns:
            Dictionary of computed features:
            - progress_rate: Change in progress per second
            - speed_rolling_mean: Mean speed over available history
            - speed_rolling_min: Min speed over available history
            - speed_rolling_max: Max speed over available history
            - acceleration: Speed change over ~30s
            - time_stopped: Seconds with speed < 1 mph
            - is_stopped: 1.0 if current speed < 1 mph
        """
        buffer = self._buffers.get(vid, [])

        if len(buffer) < 2:
            return self._default_features()

        # Convert to arrays for easier computation
        timestamps = np.array([obs[0] for obs in buffer])
        speeds = np.array([obs[1] for obs in buffer])
        progresses = np.array([obs[2] for obs in buffer])

        # Current values (most recent)
        current_speed = speeds[-1]
        current_progress = progresses[-1]

        # Progress rate: (current_progress - earliest_progress) / elapsed_time
        elapsed_sec = (timestamps[-1] - timestamps[0]) / 1000
        if elapsed_sec > 0:
            progress_rate = (progresses[-1] - progresses[0]) / elapsed_sec
        else:
            progress_rate = 0.0

        # Speed statistics over available history
        speed_mean = np.mean(speeds)
        speed_min = np.min(speeds)
        speed_max = np.max(speeds)

        # Acceleration: speed change over ~30 seconds
        # Find observation closest to 30s ago
        target_ts = current_ts - 30000
        idx_30s = np.argmin(np.abs(timestamps - target_ts))
        if timestamps[-1] - timestamps[idx_30s] > 5000:  # At least 5s difference
            acceleration = (speeds[-1] - speeds[idx_30s])
        else:
            acceleration = 0.0

        # Time stopped: count observations with speed < 1 mph
        # Estimate seconds based on number of samples and time range
        stopped_count = np.sum(speeds < 1.0)
        total_count = len(speeds)
        if total_count > 1:
            time_stopped = (stopped_count / total_count) * elapsed_sec
        else:
            time_stopped = 0.0

        # Currently stopped
        is_stopped = 1.0 if current_speed < 1.0 else 0.0

        return {
            'progress_rate': float(progress_rate),
            'speed_rolling_mean': float(speed_mean),
            'speed_rolling_min': float(speed_min),
            'speed_rolling_max': float(speed_max),
            'acceleration': float(acceleration),
            'time_stopped': float(time_stopped),
            'is_stopped': float(is_stopped),
        }

    def _default_features(self) -> dict:
        """Return default values when history is insufficient."""
        return {
            'progress_rate': 0.0,
            'speed_rolling_mean': 0.0,
            'speed_rolling_min': 0.0,
            'speed_rolling_max': 0.0,
            'acceleration': 0.0,
            'time_stopped': 0.0,
            'is_stopped': 0.0,
        }

    def clear(self, vid: Optional[str] = None):
        """
        Clear history for a vehicle or all vehicles.

        Args:
            vid: Vehicle ID to clear, or None to clear all
        """
        if vid is not None:
            if vid in self._buffers:
                del self._buffers[vid]
        else:
            self._buffers.clear()

    def __len__(self) -> int:
        """Return number of vehicles being tracked."""
        return len(self._buffers)


def compute_history_features_vectorized(
    timestamps: np.ndarray,
    speeds: np.ndarray,
    progresses: np.ndarray,
    window_seconds: int = 90
) -> dict:
    """
    Compute history features for a sorted sequence of telemetry.

    This is a vectorized alternative for batch processing where we have
    all data for a vehicle in memory.

    Args:
        timestamps: Array of timestamps in milliseconds
        speeds: Array of speeds
        progresses: Array of progress values
        window_seconds: Rolling window size

    Returns:
        Dictionary of feature arrays (same length as input)
    """
    n = len(timestamps)
    window_ms = window_seconds * 1000

    # Initialize output arrays
    progress_rates = np.zeros(n, dtype=np.float32)
    speed_means = np.zeros(n, dtype=np.float32)
    speed_mins = np.zeros(n, dtype=np.float32)
    speed_maxs = np.zeros(n, dtype=np.float32)
    accelerations = np.zeros(n, dtype=np.float32)
    time_stopped = np.zeros(n, dtype=np.float32)
    is_stopped = (speeds < 1.0).astype(np.float32)

    # For each position, compute rolling features from prior observations
    for i in range(n):
        current_ts = timestamps[i]
        cutoff_ts = current_ts - window_ms

        # Find start of window
        start_idx = np.searchsorted(timestamps[:i+1], cutoff_ts)

        if start_idx >= i:
            # Not enough history
            continue

        window_speeds = speeds[start_idx:i+1]
        window_progresses = progresses[start_idx:i+1]
        window_ts = timestamps[start_idx:i+1]

        # Progress rate
        elapsed_sec = (window_ts[-1] - window_ts[0]) / 1000
        if elapsed_sec > 0:
            progress_rates[i] = (window_progresses[-1] - window_progresses[0]) / elapsed_sec

        # Speed statistics
        speed_means[i] = np.mean(window_speeds)
        speed_mins[i] = np.min(window_speeds)
        speed_maxs[i] = np.max(window_speeds)

        # Time stopped (fraction of window with speed < 1)
        stopped_frac = np.mean(window_speeds < 1.0)
        time_stopped[i] = stopped_frac * elapsed_sec

        # Acceleration (compare to ~30s ago)
        target_ts = current_ts - 30000
        idx_30s = np.argmin(np.abs(window_ts - target_ts))
        if window_ts[-1] - window_ts[idx_30s] > 5000:
            accelerations[i] = window_speeds[-1] - window_speeds[idx_30s]

    return {
        'progress_rate': progress_rates,
        'speed_rolling_mean': speed_means,
        'speed_rolling_min': speed_mins,
        'speed_rolling_max': speed_maxs,
        'acceleration': accelerations,
        'time_stopped': time_stopped,
        'is_stopped': is_stopped,
    }


if __name__ == '__main__':
    # Test the history buffer
    buffer = VehicleHistoryBuffer(max_history_seconds=90)

    # Simulate telemetry for a vehicle
    vid = "test_bus"
    base_ts = 1700000000000  # Some base timestamp

    # Add observations over 2 minutes
    for i in range(120):
        ts = base_ts + i * 1000  # 1 second intervals
        speed = 15.0 if i % 30 > 5 else 0.0  # Stop every 30s for 5s
        progress = i / 120.0

        buffer.add_observation(vid, ts, speed, progress)

    # Get features at the end
    features = buffer.get_history_features(vid, base_ts + 119000)

    print("History Features Test:")
    for name, value in features.items():
        print(f"  {name}: {value:.4f}")

    # Test vectorized version
    print("\nVectorized Version Test:")
    timestamps = np.array([base_ts + i * 1000 for i in range(120)])
    speeds = np.array([15.0 if i % 30 > 5 else 0.0 for i in range(120)])
    progresses = np.array([i / 120.0 for i in range(120)])

    vec_features = compute_history_features_vectorized(timestamps, speeds, progresses)
    for name, values in vec_features.items():
        print(f"  {name}[-1]: {values[-1]:.4f}")
