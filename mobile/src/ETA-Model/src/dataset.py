"""
PyTorch Dataset for ETA Prediction Training

This module provides Dataset classes for loading and batching telemetry data
for model training.
"""

import json
from pathlib import Path
from typing import Optional, Callable

import numpy as np
import pandas as pd
import torch
from torch.utils.data import Dataset, DataLoader


class ETADataset(Dataset):
    """
    PyTorch Dataset for ETA prediction training.

    Loads pre-processed feature/label arrays from disk and provides
    efficient batching for training.
    """

    def __init__(
        self,
        features: np.ndarray,
        labels: np.ndarray,
        vehicle_ids: np.ndarray,
        normalize: bool = True,
        feature_means: np.ndarray = None,
        feature_stds: np.ndarray = None,
        use_log_transform: bool = False
    ):
        """
        Initialize the dataset.

        Args:
            features: Feature array, shape (n_samples, n_features)
            labels: Label array, shape (n_samples, n_stops)
            vehicle_ids: Vehicle ID indices, shape (n_samples,)
            normalize: Whether to normalize features
            feature_means: Pre-computed feature means
            feature_stds: Pre-computed feature stds
            use_log_transform: If True, apply log1p transform to labels.
                This helps reduce underestimation bias on long ETAs by
                making the model predict in log-space where long and short
                ETAs contribute more equally to the loss.
        """
        self.features = features.astype(np.float32)
        self.vehicle_ids = vehicle_ids.astype(np.int64)
        self.use_log_transform = use_log_transform

        # Apply log transform to labels if requested
        # log1p(x) = log(1 + x), which handles x=0 gracefully
        if use_log_transform:
            self.labels = np.log1p(labels.astype(np.float32))
            self.label_scale = 'log1p'
        else:
            self.labels = labels.astype(np.float32)
            self.label_scale = 'linear'

        # Normalize features if requested
        if normalize:
            if feature_means is None:
                self.means = self.features.mean(axis=0)
                self.stds = self.features.std(axis=0)
                self.stds[self.stds < 1e-6] = 1.0  # Avoid div by zero
            else:
                self.means = feature_means
                self.stds = feature_stds

            self.features = (self.features - self.means) / self.stds
        else:
            self.means = None
            self.stds = None

    def __len__(self) -> int:
        return len(self.features)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """
        Get a single sample.

        Returns:
            Tuple of (features, labels, vehicle_id)
        """
        return (
            torch.from_numpy(self.features[idx]),
            torch.from_numpy(self.labels[idx]),
            torch.tensor(self.vehicle_ids[idx], dtype=torch.long)
        )

    def get_normalization_stats(self) -> tuple[np.ndarray, np.ndarray]:
        """Return normalization statistics for use in inference."""
        return self.means, self.stds


class StreamingETADataset(Dataset):
    """
    Dataset that streams data from JSONL files.

    Useful for very large datasets that don't fit in memory.
    """

    def __init__(
        self,
        data_files: list[str],
        feature_extractor: Callable,
        label_extractor: Callable,
        max_samples: int = None
    ):
        """
        Initialize streaming dataset.

        Args:
            data_files: List of paths to JSONL files
            feature_extractor: Function to extract features from telemetry
            label_extractor: Function to extract labels (actual ETAs)
            max_samples: Maximum number of samples to load
        """
        self.data_files = data_files
        self.feature_extractor = feature_extractor
        self.label_extractor = label_extractor

        # Build index of file positions
        self.index = self._build_index(max_samples)

    def _build_index(self, max_samples: int = None) -> list[tuple[str, int]]:
        """Build index mapping sample idx to (file, line_number)."""
        index = []

        for file_path in self.data_files:
            with open(file_path, 'r') as f:
                for line_num, line in enumerate(f):
                    if max_samples and len(index) >= max_samples:
                        return index

                    try:
                        data = json.loads(line)
                        # Only index valid samples
                        if self._is_valid_sample(data):
                            index.append((file_path, line_num))
                    except json.JSONDecodeError:
                        continue

        return index

    def _is_valid_sample(self, data: dict) -> bool:
        """Check if a telemetry record is valid for training."""
        # Must have basic required fields
        if not data.get('ts') and not data.get('t'):
            return False
        if not data.get('serviceState', {}).get('rID'):
            return False
        if data.get('serviceState', {}).get('patternID') == 9998:
            return False  # Not in service
        return True

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        file_path, line_num = self.index[idx]

        with open(file_path, 'r') as f:
            for i, line in enumerate(f):
                if i == line_num:
                    data = json.loads(line)
                    break

        features, vehicle_id = self.feature_extractor(data)
        labels = self.label_extractor(data)

        return (
            torch.from_numpy(features),
            torch.from_numpy(labels),
            torch.tensor(vehicle_id, dtype=torch.long)
        )


def generate_training_data(
    telemetry_files: list[str],
    gtfs_dir: str,
    output_dir: str,
    num_stops: int = 3
) -> dict:
    """
    Generate training data from raw telemetry files.

    This function processes telemetry data to create (features, labels) pairs
    where labels are the actual arrival times at the next N stops.

    Args:
        telemetry_files: List of paths to JSONL telemetry files
        gtfs_dir: Path to GTFS data directory
        output_dir: Directory to save processed data
        num_stops: Number of future stops to predict

    Returns:
        Dictionary with paths to generated files and statistics
    """
    from .features import FeatureExtractor, build_vehicle_mapping, FeatureConfig
    from .distance import GTFSRouteData

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load GTFS data
    print("Loading GTFS data...")
    gtfs = GTFSRouteData(gtfs_dir)

    # Build vehicle mapping
    print("Building vehicle mapping...")
    vehicle_mapping = build_vehicle_mapping(telemetry_files)

    # Save vehicle mapping
    with open(output_path / 'vehicle_mapping.json', 'w') as f:
        json.dump(vehicle_mapping, f, indent=2)

    # Initialize feature extractor
    config = FeatureConfig(num_stops=num_stops)
    extractor = FeatureExtractor(
        config=config,
        vehicle_mapping=vehicle_mapping,
        distance_calculator=gtfs
    )

    # Process files and generate samples
    print("Processing telemetry files...")
    all_features = []
    all_labels = []
    all_vehicle_ids = []

    for file_path in telemetry_files:
        print(f"  Processing {file_path}...")
        samples = _process_telemetry_file(
            file_path, extractor, gtfs, num_stops
        )

        for features, labels, vid in samples:
            all_features.append(features)
            all_labels.append(labels)
            all_vehicle_ids.append(vid)

    if not all_features:
        raise ValueError("No valid samples generated!")

    # Convert to arrays
    features_array = np.array(all_features, dtype=np.float32)
    labels_array = np.array(all_labels, dtype=np.float32)
    vehicle_ids_array = np.array(all_vehicle_ids, dtype=np.int64)

    print(f"Generated {len(features_array)} samples")

    # Compute and save normalization stats
    norm_stats = extractor.compute_normalization_stats(features_array)
    norm_stats.save(str(output_path / 'normalization_stats.json'))

    # Save arrays
    np.save(output_path / 'features.npy', features_array)
    np.save(output_path / 'labels.npy', labels_array)
    np.save(output_path / 'vehicle_ids.npy', vehicle_ids_array)

    stats = {
        'num_samples': len(features_array),
        'num_features': features_array.shape[1],
        'num_stops': labels_array.shape[1],
        'num_vehicles': len(vehicle_mapping),
        'files_processed': len(telemetry_files),
    }

    with open(output_path / 'stats.json', 'w') as f:
        json.dump(stats, f, indent=2)

    return {
        'features_path': str(output_path / 'features.npy'),
        'labels_path': str(output_path / 'labels.npy'),
        'vehicle_ids_path': str(output_path / 'vehicle_ids.npy'),
        'vehicle_mapping_path': str(output_path / 'vehicle_mapping.json'),
        'norm_stats_path': str(output_path / 'normalization_stats.json'),
        'stats': stats,
    }


def _process_telemetry_file(
    file_path: str,
    extractor,
    gtfs,
    num_stops: int
) -> list[tuple[np.ndarray, np.ndarray, int]]:
    """
    Process a single telemetry file to generate training samples.

    Groups data by vehicle, detects stop arrivals, and creates
    (features, labels) pairs where labels are actual arrival times.
    """
    # Load all packets
    packets = []
    with open(file_path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line)
                packets.append(data)
            except json.JSONDecodeError:
                continue

    if not packets:
        return []

    # Group by vehicle
    vehicle_packets = {}
    for p in packets:
        vid = p.get('vid', '')
        if vid:
            if vid not in vehicle_packets:
                vehicle_packets[vid] = []
            vehicle_packets[vid].append(p)

    samples = []

    for vid, vehicle_data in vehicle_packets.items():
        # Sort by timestamp
        vehicle_data.sort(key=lambda x: x.get('ts', x.get('t', 0)))

        # Detect stop arrivals
        arrivals = _detect_stop_arrivals(vehicle_data)

        # Generate samples
        for i, packet in enumerate(vehicle_data):
            ts = packet.get('ts', packet.get('t', 0))
            trip_id = packet.get('serviceState', {}).get('tripID', '')
            last_stop = str(packet.get('lastStop', {}).get('stopID', 0))

            # Skip invalid packets
            if packet.get('serviceState', {}).get('patternID') == 9998:
                continue

            # Get next stops
            if trip_id:
                next_stops = gtfs.get_next_n_stops(trip_id, last_stop, num_stops)
            else:
                next_stops = []

            if len(next_stops) < num_stops:
                continue

            # Find actual arrival times for each stop
            labels = []
            for stop_id in next_stops:
                arrival_time = _find_arrival_time(arrivals, stop_id, ts)
                if arrival_time is None:
                    break
                eta = (arrival_time - ts) / 1000  # Convert to seconds
                if eta < 0 or eta > 3600:  # Filter unreasonable values
                    break
                labels.append(eta)

            if len(labels) != num_stops:
                continue

            # Calculate distances
            lat = packet.get('lt', 0)
            lon = packet.get('ln', 0)
            distances = []
            for stop_id in next_stops:
                dist = gtfs.calculate_route_distance(trip_id, lat, lon, stop_id)
                distances.append(dist if dist is not None else 0)

            stops_remaining = list(range(1, num_stops + 1))

            # Extract features
            features, vehicle_id_int = extractor.extract(
                packet, next_stops, distances, stops_remaining
            )

            samples.append((features, np.array(labels, dtype=np.float32), vehicle_id_int))

    return samples


def _detect_stop_arrivals(packets: list[dict]) -> list[tuple[str, int]]:
    """
    Detect stop arrivals from lastStop changes.

    Returns list of (stop_id, arrival_timestamp) tuples.
    """
    arrivals = []
    prev_stop = None

    for packet in packets:
        current_stop = str(packet.get('lastStop', {}).get('stopID', 0))
        stop_time = packet.get('lastStop', {}).get('time')

        if current_stop and current_stop != '0' and current_stop != prev_stop:
            if stop_time:
                arrivals.append((current_stop, int(stop_time)))
            else:
                # Use packet timestamp as fallback
                ts = packet.get('ts', packet.get('t', 0))
                arrivals.append((current_stop, int(ts)))

        prev_stop = current_stop

    return arrivals


def _find_arrival_time(
    arrivals: list[tuple[str, int]],
    stop_id: str,
    after_time: int
) -> Optional[int]:
    """Find the arrival time at a stop after a given time."""
    for arr_stop, arr_time in arrivals:
        if arr_stop == stop_id and arr_time > after_time:
            return arr_time
    return None


def create_data_loaders(
    features_path: str,
    labels_path: str,
    vehicle_ids_path: str,
    batch_size: int = 64,
    train_split: float = 0.8,
    val_split: float = 0.1,
    num_workers: int = 0,
    normalize: bool = True
) -> tuple[DataLoader, DataLoader, DataLoader, dict]:
    """
    Create train/val/test data loaders from saved arrays.

    Args:
        features_path: Path to features.npy
        labels_path: Path to labels.npy
        vehicle_ids_path: Path to vehicle_ids.npy
        batch_size: Batch size
        train_split: Fraction for training
        val_split: Fraction for validation
        num_workers: DataLoader workers
        normalize: Whether to normalize features

    Returns:
        Tuple of (train_loader, val_loader, test_loader, stats_dict)
    """
    # Load arrays
    features = np.load(features_path)
    labels = np.load(labels_path)
    vehicle_ids = np.load(vehicle_ids_path)

    n_samples = len(features)
    n_train = int(n_samples * train_split)
    n_val = int(n_samples * val_split)

    # Shuffle indices
    indices = np.random.permutation(n_samples)

    train_idx = indices[:n_train]
    val_idx = indices[n_train:n_train + n_val]
    test_idx = indices[n_train + n_val:]

    # Compute normalization stats from training data only
    train_features = features[train_idx]
    means = train_features.mean(axis=0)
    stds = train_features.std(axis=0)
    stds[stds < 1e-6] = 1.0

    # Create datasets
    train_dataset = ETADataset(
        features[train_idx], labels[train_idx], vehicle_ids[train_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )
    val_dataset = ETADataset(
        features[val_idx], labels[val_idx], vehicle_ids[val_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )
    test_dataset = ETADataset(
        features[test_idx], labels[test_idx], vehicle_ids[test_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )

    # Create loaders
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )

    stats = {
        'n_train': len(train_idx),
        'n_val': len(val_idx),
        'n_test': len(test_idx),
        'n_features': features.shape[1],
        'n_stops': labels.shape[1],
        'means': means.tolist(),
        'stds': stds.tolist(),
    }

    return train_loader, val_loader, test_loader, stats


def create_data_loaders_from_arrays(
    features: np.ndarray,
    labels: np.ndarray,
    vehicle_ids: np.ndarray,
    batch_size: int = 64,
    train_split: float = 0.8,
    val_split: float = 0.1,
    num_workers: int = 0,
    normalize: bool = True
) -> tuple[DataLoader, DataLoader, DataLoader, dict]:
    """
    Create train/val/test data loaders from numpy arrays.

    Args:
        features: Feature array, shape (n_samples, n_features)
        labels: Label array, shape (n_samples, n_stops)
        vehicle_ids: Vehicle ID indices, shape (n_samples,)
        batch_size: Batch size
        train_split: Fraction for training
        val_split: Fraction for validation
        num_workers: DataLoader workers
        normalize: Whether to normalize features

    Returns:
        Tuple of (train_loader, val_loader, test_loader, stats_dict)
    """
    n_samples = len(features)
    n_train = int(n_samples * train_split)
    n_val = int(n_samples * val_split)

    # Shuffle indices
    indices = np.random.permutation(n_samples)

    train_idx = indices[:n_train]
    val_idx = indices[n_train:n_train + n_val]
    test_idx = indices[n_train + n_val:]

    # Compute normalization stats from training data only
    train_features = features[train_idx]
    means = train_features.mean(axis=0)
    stds = train_features.std(axis=0)
    stds[stds < 1e-6] = 1.0

    # Create datasets
    train_dataset = ETADataset(
        features[train_idx], labels[train_idx], vehicle_ids[train_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )
    val_dataset = ETADataset(
        features[val_idx], labels[val_idx], vehicle_ids[val_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )
    test_dataset = ETADataset(
        features[test_idx], labels[test_idx], vehicle_ids[test_idx],
        normalize=normalize, feature_means=means, feature_stds=stds
    )

    # Create loaders
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, num_workers=num_workers
    )
    val_loader = DataLoader(
        val_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )
    test_loader = DataLoader(
        test_dataset, batch_size=batch_size, shuffle=False, num_workers=num_workers
    )

    stats = {
        'n_train': len(train_idx),
        'n_val': len(val_idx),
        'n_test': len(test_idx),
        'n_features': features.shape[1],
        'n_stops': labels.shape[1],
        'means': means.tolist(),
        'stds': stds.tolist(),
    }

    return train_loader, val_loader, test_loader, stats


if __name__ == '__main__':
    # Test dataset creation
    import tempfile

    # Create mock data
    n_samples = 1000
    n_features = 32
    n_stops = 3
    n_vehicles = 10

    features = np.random.randn(n_samples, n_features).astype(np.float32)
    labels = np.abs(np.random.randn(n_samples, n_stops) * 100 + 200).astype(np.float32)
    vehicle_ids = np.random.randint(0, n_vehicles, n_samples)

    # Create dataset
    dataset = ETADataset(features, labels, vehicle_ids, normalize=True)

    print(f"Dataset size: {len(dataset)}")
    print(f"Sample shapes: {dataset[0][0].shape}, {dataset[0][1].shape}, {dataset[0][2].shape}")

    # Test DataLoader
    loader = DataLoader(dataset, batch_size=32, shuffle=True)
    batch = next(iter(loader))
    print(f"Batch shapes: {batch[0].shape}, {batch[1].shape}, {batch[2].shape}")
