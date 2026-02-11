"""
Debug Predictions Script

Shows detailed input features, model predictions, and actual values
to help understand model behavior and identify improvement opportunities.
"""

import json
import numpy as np
import torch
from pathlib import Path
from datetime import datetime, timedelta

from model import load_model
from dataset import ETADataset


# Feature names matching the order in build_feature_vector()
# NOTE: With distance feature, there are now 28 features
FEATURE_NAMES = [
    # Core features (0-7)
    'speed',
    'heading_normalized',
    'load',
    'progress',
    'lastStopOnTime',
    'system_eta_sec',      # Computed from etaSeconds
    'scheduled_eta',
    'distance_to_stop',    # Route distance in miles (NEW!)

    # Time features (8-13)
    'time_sin',
    'time_cos',
    'day_normalized',
    'is_morning_rush',
    'is_afternoon_rush',
    'is_class_change',

    # Day of week one-hot (14-20)
    'is_monday',
    'is_tuesday',
    'is_wednesday',
    'is_thursday',
    'is_friday',
    'is_saturday',
    'is_sunday',

    # Weather features (21-24)
    'precipitation',
    'is_raining',
    'precip_probability',
    'temperature_normalized',

    # Historical features (25-27)
    'dwell_sec',
    'boardings',
    'alightings',
]


def load_test_data(data_dir: str, n_samples: int = 100):
    """Load test data samples."""
    data_path = Path(data_dir)

    features = np.load(data_path / 'features.npy')
    labels = np.load(data_path / 'labels.npy')
    vehicle_ids = np.load(data_path / 'vehicle_ids.npy')

    # Load normalization stats
    with open(data_path / 'normalization_stats.json') as f:
        norm_stats = json.load(f)

    # Load vehicle mapping
    with open(data_path / 'vehicle_mapping.json') as f:
        vehicle_mapping = json.load(f)

    # Reverse vehicle mapping (idx -> name)
    idx_to_vehicle = {v: k for k, v in vehicle_mapping.items()}

    # Load metadata if available
    metadata = None
    metadata_path = data_path / 'metadata.json'
    if metadata_path.exists():
        with open(metadata_path) as f:
            metadata = json.load(f)

    # Get test split (last 10%)
    n_total = len(features)
    n_test = int(n_total * 0.1)
    test_start = n_total - n_test

    # Sample from test set
    indices = np.random.choice(range(test_start, n_total), min(n_samples, n_test), replace=False)

    return {
        'features': features[indices],
        'labels': labels[indices],
        'vehicle_ids': vehicle_ids[indices],
        'norm_stats': norm_stats,
        'idx_to_vehicle': idx_to_vehicle,
        'indices': indices,
        'metadata': metadata
    }


def normalize_features(features: np.ndarray, means: list, stds: list) -> np.ndarray:
    """Normalize features using z-score."""
    means = np.array(means)
    stds = np.array(stds)
    stds[stds < 1e-6] = 1.0  # Avoid division by zero
    return (features - means) / stds


def format_feature_value(name: str, raw_value: float, denorm_value: float) -> str:
    """Format a feature value for display."""

    # Boolean/flag features
    if name.startswith('is_') or name in ['is_raining']:
        return f"{denorm_value:.0f}" if denorm_value > 0.5 else "0"

    # Time-related
    if name in ['speed']:
        return f"{denorm_value:.1f} mph"
    if name in ['system_eta_sec', 'scheduled_eta', 'dwell_sec']:
        return f"{denorm_value:.0f}s ({denorm_value/60:.1f}min)"
    if name == 'distance_to_stop':
        return f"{denorm_value:.3f} mi ({denorm_value*5280:.0f} ft)"
    if name == 'lastStopOnTime':
        return f"{denorm_value:+.0f}s"
    if name == 'load':
        return f"{denorm_value:.0f} passengers"
    if name == 'progress':
        return f"{denorm_value:.1%}"
    if name == 'heading_normalized':
        return f"{denorm_value * 360:.0f} deg"
    if name == 'precipitation':
        return f"{denorm_value:.1f}mm"
    if name == 'precip_probability':
        return f"{denorm_value * 100:.0f}%"
    if name == 'temperature_normalized':
        return f"{denorm_value * 40:.1f}C"
    if name in ['boardings', 'alightings']:
        return f"{denorm_value:.1f}"
    if name == 'day_normalized':
        days = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
        day_idx = int(denorm_value * 6)
        return days[min(day_idx, 6)]

    # Cyclical time features
    if name in ['time_sin', 'time_cos']:
        return f"{denorm_value:.3f}"

    return f"{denorm_value:.2f}"


def debug_predictions(
    model_path: str,
    data_dir: str,
    n_samples: int = 20,
    show_all_features: bool = False
):
    """
    Run predictions and show detailed debug info.

    Args:
        model_path: Path to trained model
        data_dir: Path to processed data directory
        n_samples: Number of samples to analyze
        show_all_features: Show all features or just key ones
    """
    print("=" * 80)
    print("DEBUG: MODEL PREDICTIONS ANALYSIS")
    print("=" * 80)

    # Load model
    print(f"\nLoading model from {model_path}...")
    model = load_model(model_path)
    model.eval()

    # Load data
    print(f"Loading test data from {data_dir}...")
    data = load_test_data(data_dir, n_samples)

    features_raw = data['features']  # Raw (unnormalized) features for display
    labels = data['labels']
    vehicle_ids = data['vehicle_ids']
    means = data['norm_stats']['means']
    stds = data['norm_stats']['stds']
    idx_to_vehicle = data['idx_to_vehicle']

    # Normalize features before passing to model (model was trained on normalized data)
    features_normalized = normalize_features(features_raw, means, stds)

    # Run predictions
    with torch.no_grad():
        features_tensor = torch.from_numpy(features_normalized).float()
        vehicle_ids_tensor = torch.from_numpy(vehicle_ids).long()
        predictions = model(features_tensor, vehicle_ids_tensor).numpy()

    # Compute errors
    errors = predictions - labels
    abs_errors = np.abs(errors)

    # Key features to always show
    key_features = [
        'speed', 'distance_to_stop', 'system_eta_sec', 'scheduled_eta',
        'progress', 'load', 'lastStopOnTime', 'is_morning_rush', 'is_afternoon_rush'
    ]

    print(f"\nAnalyzing {n_samples} samples...")
    print("\n" + "=" * 80)

    # Sort by error magnitude to see worst cases first
    sorted_indices = np.argsort(abs_errors.flatten())[::-1]

    # Load metadata for additional context (timestamps, route info)
    metadata = data.get('metadata', None)
    original_indices = data.get('indices', None)

    for rank, idx in enumerate(sorted_indices[:n_samples]):
        pred = predictions[idx, 0]
        actual = labels[idx, 0]
        error = errors[idx, 0]
        vid = vehicle_ids[idx]
        vehicle_name = idx_to_vehicle.get(vid, f"ID_{vid}")

        # Determine error type
        if error > 0:
            error_type = "OVERESTIMATE (bus arrives EARLIER than predicted)"
        else:
            error_type = "UNDERESTIMATE (bus arrives LATER than predicted)"

        print(f"\n{'='*80}")
        print(f"--- Sample {rank+1} (Error Rank: {rank+1}/{n_samples}) ---")
        print(f"{'='*80}")

        # Show metadata if available
        if metadata and original_indices is not None and idx < len(original_indices):
            orig_idx = original_indices[idx]
            if orig_idx < len(metadata):
                meta = metadata[orig_idx]
                ts = meta.get('timestamp', 0)
                if ts > 0:
                    dt_utc = datetime.utcfromtimestamp(ts / 1000)
                    dt_local = dt_utc - timedelta(hours=6)  # Central Time
                    print(f"\nMETADATA:")
                    print(f"  Timestamp (UTC):   {dt_utc.strftime('%Y-%m-%d %H:%M:%S')}")
                    print(f"  Timestamp (Local): {dt_local.strftime('%Y-%m-%d %H:%M:%S')} (Central)")
                    print(f"  Timestamp (ms):    {ts}")
                print(f"  Vehicle ID:        {meta.get('vehicle_id', 'N/A')}")
                print(f"  Route ID:          {meta.get('route_id', 'N/A')}")
                print(f"  Next Stop ID:      {meta.get('next_stop_id', 'N/A')}")
                if 'actual_eta' in meta:
                    print(f"  Actual ETA (meta): {meta['actual_eta']:.1f}s")

        print(f"\nPREDICTION:")
        print(f"  Vehicle: {vehicle_name}")
        print(f"  Predicted: {pred:.1f}s ({pred/60:.2f} min)")
        print(f"  Actual:    {actual:.1f}s ({actual/60:.2f} min)")
        print(f"  Error:     {error:+.1f}s ({error/60:+.2f} min) - {error_type}")

        # Always show ALL raw features
        print(f"\nALL RAW INPUT FEATURES ({len(features_raw[idx])} features):")
        for feat_idx, feat_name in enumerate(FEATURE_NAMES):
            if feat_idx < len(features_raw[idx]):
                val = features_raw[idx, feat_idx]
                formatted = format_feature_value(feat_name, val, val)
                print(f"  [{feat_idx:2d}] {feat_name:22s}: {val:>12.4f}  ({formatted})")

        print("-" * 80)

    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)

    print(f"\nOverall:")
    print(f"  MAE: {abs_errors.mean():.1f}s ({abs_errors.mean()/60:.2f} min)")
    print(f"  Median Error: {np.median(abs_errors):.1f}s")
    print(f"  Max Error: {abs_errors.max():.1f}s")

    overestimates = errors > 0
    underestimates = errors < 0
    print(f"\nError Direction:")
    print(f"  Overestimates:  {overestimates.sum()} ({overestimates.mean()*100:.1f}%)")
    print(f"  Underestimates: {underestimates.sum()} ({underestimates.mean()*100:.1f}%)")

    if overestimates.any():
        print(f"  Avg Overestimate:  {errors[overestimates].mean():+.1f}s")
    if underestimates.any():
        print(f"  Avg Underestimate: {errors[underestimates].mean():+.1f}s")

    # Analyze errors by feature ranges
    print("\n" + "=" * 80)
    print("ERROR ANALYSIS BY FEATURE")
    print("=" * 80)

    # By actual ETA range
    print("\nBy Actual ETA Range:")
    ranges = [(0, 60), (60, 120), (120, 300), (300, 600), (600, 900)]
    for low, high in ranges:
        mask = (labels >= low) & (labels < high)
        if mask.any():
            range_mae = abs_errors[mask].mean()
            range_bias = errors[mask].mean()
            print(f"  {low:3d}-{high:3d}s: MAE={range_mae:.1f}s, Bias={range_bias:+.1f}s, N={mask.sum()}")

    # By speed
    print("\nBy Speed:")
    speed_idx = FEATURE_NAMES.index('speed')
    speeds = features_raw[:, speed_idx]
    speed_ranges = [(0, 5), (5, 15), (15, 25), (25, 50)]
    for low, high in speed_ranges:
        mask = (speeds >= low) & (speeds < high)
        if mask.any():
            range_mae = abs_errors[mask.flatten()].mean()
            range_bias = errors[mask.flatten()].mean()
            print(f"  {low:2d}-{high:2d} mph: MAE={range_mae:.1f}s, Bias={range_bias:+.1f}s, N={mask.sum()}")

    # By system ETA
    print("\nBy System ETA (baseline):")
    sys_eta_idx = FEATURE_NAMES.index('system_eta_sec')
    sys_etas = features_raw[:, sys_eta_idx]
    for low, high in ranges:
        mask = (sys_etas >= low) & (sys_etas < high)
        if mask.any():
            range_mae = abs_errors[mask.flatten()].mean()
            model_better = abs_errors[mask.flatten()].mean() < np.abs(sys_etas[mask] - labels[mask].flatten()).mean()
            baseline_mae = np.abs(sys_etas[mask] - labels[mask].flatten()).mean()
            print(f"  {low:3d}-{high:3d}s: Model MAE={range_mae:.1f}s, Baseline MAE={baseline_mae:.1f}s, Model {'BETTER' if model_better else 'WORSE'}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Debug model predictions')
    parser.add_argument('--model', type=str, required=True, help='Path to trained model')
    parser.add_argument('--data-dir', type=str, required=True, help='Path to processed data')
    parser.add_argument('--n-samples', type=int, default=20, help='Number of samples to analyze')
    parser.add_argument('--all-features', action='store_true', help='Show all features')

    args = parser.parse_args()

    debug_predictions(
        model_path=args.model,
        data_dir=args.data_dir,
        n_samples=args.n_samples,
        show_all_features=args.all_features
    )


if __name__ == '__main__':
    main()
