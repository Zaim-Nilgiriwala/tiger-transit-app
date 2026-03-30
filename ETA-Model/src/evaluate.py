"""
Model Evaluation Module for ETA Prediction

Comprehensive evaluation metrics including:
- MAE (Mean Absolute Error) overall and per-stop
- Overestimate/underestimate analysis
- Accuracy at time thresholds
- Comparison with baseline (scheduled ETA)
- Rush hour performance breakdown

Usage:
    python evaluate.py --model-path ./models/route_24/best_model.pt --data-dir ./processed_data
"""

import argparse
import json
from pathlib import Path
from typing import Optional

import numpy as np
import torch
from torch.utils.data import DataLoader

from model import load_model
from dataset import ETADataset, create_data_loaders_from_arrays


def compute_metrics(
    predictions: np.ndarray,
    actuals: np.ndarray,
    baseline_predictions: np.ndarray = None
) -> dict:
    """
    Compute comprehensive evaluation metrics.

    Args:
        predictions: Model predictions, shape (n_samples, n_stops)
        actuals: Actual ETAs, shape (n_samples, n_stops)
        baseline_predictions: Optional baseline (e.g., scheduled ETA)

    Returns:
        Dictionary of metrics
    """
    errors = predictions - actuals
    abs_errors = np.abs(errors)

    metrics = {}

    # ============================================================
    # Overall Metrics
    # ============================================================
    metrics['overall'] = {
        'mae': float(abs_errors.mean()),
        'rmse': float(np.sqrt((errors ** 2).mean())),
        'median_ae': float(np.median(abs_errors)),
        'std': float(abs_errors.std()),
        'n_samples': len(predictions)
    }

    # ============================================================
    # Per-Stop Metrics
    # ============================================================
    n_stops = predictions.shape[1]
    metrics['per_stop'] = {}

    for i in range(n_stops):
        stop_errors = errors[:, i]
        stop_abs_errors = abs_errors[:, i]

        metrics['per_stop'][f'stop_{i+1}'] = {
            'mae': float(stop_abs_errors.mean()),
            'rmse': float(np.sqrt((stop_errors ** 2).mean())),
            'median_ae': float(np.median(stop_abs_errors)),
            'std': float(stop_abs_errors.std())
        }

    # ============================================================
    # Directional Analysis (Critical for Asymmetric Loss)
    # ============================================================
    overestimate_mask = errors > 0  # Predicted > Actual (bus arrives early)
    underestimate_mask = errors < 0  # Predicted < Actual (bus arrives late)

    metrics['directional'] = {
        'overestimate_rate': float(overestimate_mask.mean()),
        'underestimate_rate': float(underestimate_mask.mean()),
        'overestimate_mae': float(abs_errors[overestimate_mask].mean()) if overestimate_mask.any() else 0,
        'underestimate_mae': float(abs_errors[underestimate_mask].mean()) if underestimate_mask.any() else 0,
        'overestimate_mean': float(errors[overestimate_mask].mean()) if overestimate_mask.any() else 0,
        'underestimate_mean': float(errors[underestimate_mask].mean()) if underestimate_mask.any() else 0,
    }

    # Per-stop directional analysis
    for i in range(n_stops):
        stop_errors = errors[:, i]
        stop_abs_errors = abs_errors[:, i]
        over_mask = stop_errors > 0
        under_mask = stop_errors < 0

        metrics['directional'][f'stop_{i+1}_overestimate_rate'] = float(over_mask.mean())
        metrics['directional'][f'stop_{i+1}_overestimate_mae'] = float(
            stop_abs_errors[over_mask].mean()
        ) if over_mask.any() else 0

    # ============================================================
    # Accuracy at Thresholds
    # ============================================================
    thresholds = [30, 60, 90, 120, 180, 300]  # seconds
    metrics['accuracy'] = {}

    for thresh in thresholds:
        metrics['accuracy'][f'within_{thresh}s'] = float((abs_errors < thresh).mean())
        metrics['accuracy'][f'within_{thresh}s_pct'] = float((abs_errors < thresh).mean() * 100)

    # Per-stop accuracy
    for i in range(n_stops):
        stop_abs_errors = abs_errors[:, i]
        metrics['accuracy'][f'stop_{i+1}_within_60s'] = float((stop_abs_errors < 60).mean())
        metrics['accuracy'][f'stop_{i+1}_within_120s'] = float((stop_abs_errors < 120).mean())

    # ============================================================
    # Percentile Analysis
    # ============================================================
    percentiles = [50, 75, 90, 95, 99]
    metrics['percentiles'] = {}

    for p in percentiles:
        metrics['percentiles'][f'p{p}'] = float(np.percentile(abs_errors, p))

    # ============================================================
    # Baseline Comparison (if provided)
    # ============================================================
    if baseline_predictions is not None:
        baseline_errors = baseline_predictions - actuals
        baseline_abs_errors = np.abs(baseline_errors)

        metrics['baseline_comparison'] = {
            'baseline_mae': float(baseline_abs_errors.mean()),
            'model_mae': float(abs_errors.mean()),
            'improvement_seconds': float(baseline_abs_errors.mean() - abs_errors.mean()),
            'improvement_percent': float(
                (baseline_abs_errors.mean() - abs_errors.mean()) / baseline_abs_errors.mean() * 100
            ) if baseline_abs_errors.mean() > 0 else 0,
            'model_better_rate': float((abs_errors < baseline_abs_errors).mean())
        }

    # ============================================================
    # Error Distribution
    # ============================================================
    metrics['distribution'] = {
        'min_error': float(errors.min()),
        'max_error': float(errors.max()),
        'min_abs_error': float(abs_errors.min()),
        'max_abs_error': float(abs_errors.max()),
        'mean_error': float(errors.mean()),  # Positive = tends to overestimate
        'error_skew': float(
            ((errors - errors.mean()) ** 3).mean() / (errors.std() ** 3)
        ) if errors.std() > 0 else 0
    }

    return metrics


def evaluate_by_time_period(
    predictions: np.ndarray,
    actuals: np.ndarray,
    timestamps: np.ndarray
) -> dict:
    """
    Evaluate model performance by time period.

    Args:
        predictions: Model predictions
        actuals: Actual ETAs
        timestamps: Unix timestamps for each sample

    Returns:
        Dictionary with metrics by time period
    """
    from datetime import datetime

    hours = np.array([
        datetime.fromtimestamp(ts / 1000).hour for ts in timestamps
    ])

    metrics = {}

    # Morning rush (7-9 AM)
    morning_mask = (hours >= 7) & (hours < 9)
    if morning_mask.any():
        metrics['morning_rush'] = compute_metrics(
            predictions[morning_mask],
            actuals[morning_mask]
        )['overall']
        metrics['morning_rush']['n_samples'] = int(morning_mask.sum())

    # Afternoon rush (4-6 PM)
    afternoon_mask = (hours >= 16) & (hours < 18)
    if afternoon_mask.any():
        metrics['afternoon_rush'] = compute_metrics(
            predictions[afternoon_mask],
            actuals[afternoon_mask]
        )['overall']
        metrics['afternoon_rush']['n_samples'] = int(afternoon_mask.sum())

    # Off-peak
    offpeak_mask = ~(morning_mask | afternoon_mask)
    if offpeak_mask.any():
        metrics['off_peak'] = compute_metrics(
            predictions[offpeak_mask],
            actuals[offpeak_mask]
        )['overall']
        metrics['off_peak']['n_samples'] = int(offpeak_mask.sum())

    # Hourly breakdown
    metrics['hourly'] = {}
    for hour in range(24):
        hour_mask = hours == hour
        if hour_mask.sum() > 10:  # Minimum samples
            hour_errors = np.abs(predictions[hour_mask] - actuals[hour_mask])
            metrics['hourly'][f'hour_{hour:02d}'] = {
                'mae': float(hour_errors.mean()),
                'n_samples': int(hour_mask.sum())
            }

    return metrics


def evaluate_model(
    model_path: str,
    data_dir: str,
    device: str = 'cpu',
    output_path: str = None,
    route_filter: int = None,
    detailed: bool = False,
    num_detailed_samples: int = 20
) -> dict:
    """
    Evaluate a trained model on test data.

    Args:
        model_path: Path to model checkpoint
        data_dir: Directory with processed data
        device: Device to run evaluation on
        output_path: Path to save results JSON
        route_filter: Filter to specific route ID (e.g., 100)
        detailed: If True, print detailed breakdown of worst predictions
        num_detailed_samples: Number of samples to show in detailed mode

    Returns:
        Dictionary with all evaluation metrics
    """
    print(f"Loading model from {model_path}...")
    model = load_model(model_path, device=device)

    data_path = Path(data_dir)

    # Load test data
    print("Loading test data...")
    features = np.load(data_path / 'features.npy')
    labels = np.load(data_path / 'labels.npy')
    vehicle_ids = np.load(data_path / 'vehicle_ids.npy')

    # Apply route filter if specified
    if route_filter is not None:
        print(f"Filtering to route {route_filter}...")

        # Prefer route_ids.npy if available (more accurate)
        route_ids_path = data_path / 'route_ids.npy'
        if route_ids_path.exists():
            route_ids_array = np.load(route_ids_path)
            route_mask = (route_ids_array == route_filter)
            print(f"  Using route_ids.npy for filtering")
        else:
            # Fallback: decode from normalized feature column
            ROUTE_FEATURE_IDX = 30  # routeId / 300.0
            expected_value = route_filter / 300.0
            tolerance = 0.5 / 300.0
            route_mask = np.abs(features[:, ROUTE_FEATURE_IDX] - expected_value) < tolerance
            print(f"  Warning: route_ids.npy not found, using feature decoding")

        features = features[route_mask]
        labels = labels[route_mask]
        vehicle_ids = vehicle_ids[route_mask]

        print(f"  Filtered to {len(features)} samples ({route_mask.mean()*100:.1f}% of data)")

    # Keep raw features for detailed breakdown (before normalization)
    raw_features = features.copy()

    # Use same random split as training (with fixed seed for reproducibility)
    # This ensures we evaluate on the same test set that training used
    np.random.seed(42)  # Fixed seed for reproducible split
    _, _, test_loader, data_stats = create_data_loaders_from_arrays(
        features, labels, vehicle_ids,
        batch_size=512,
        train_split=0.8,
        val_split=0.1,
        normalize=True
    )

    # Get test indices (same split as data loader)
    np.random.seed(42)
    n_samples = len(raw_features)
    n_train = int(n_samples * 0.8)
    n_val = int(n_samples * 0.1)
    indices = np.random.permutation(n_samples)
    test_indices = indices[n_train + n_val:]

    # Get raw features and vehicle IDs for test set
    test_raw_features = raw_features[test_indices]
    test_vehicle_ids = vehicle_ids[test_indices]

    print(f"Test samples: {data_stats['n_test']}")

    # Load vehicle mapping for detailed output
    vehicle_mapping = {}
    vehicle_mapping_path = data_path / 'vehicle_mapping.json'
    if vehicle_mapping_path.exists():
        with open(vehicle_mapping_path) as f:
            vehicle_mapping = json.load(f)

    # Get predictions
    print("Running inference...")
    model.eval()
    model.to(device)

    all_predictions = []
    all_labels = []

    # Data is already normalized from test_loader, run inference directly
    with torch.no_grad():
        for batch_features, batch_labels, batch_vids in test_loader:
            batch_features = batch_features.to(device)
            batch_vids = batch_vids.to(device)

            preds = model(batch_features, batch_vids)
            all_predictions.append(preds.cpu().numpy())
            all_labels.append(batch_labels.numpy())

    predictions = np.concatenate(all_predictions, axis=0)
    test_labels = np.concatenate(all_labels, axis=0)

    # Compute metrics
    print("Computing metrics...")
    metrics = compute_metrics(predictions, test_labels)

    # Print summary
    print("\n" + "=" * 60)
    print("EVALUATION RESULTS")
    print("=" * 60)

    print(f"\nOverall Performance:")
    print(f"  MAE: {metrics['overall']['mae']:.1f} seconds ({metrics['overall']['mae']/60:.2f} minutes)")
    print(f"  RMSE: {metrics['overall']['rmse']:.1f} seconds")
    print(f"  Median AE: {metrics['overall']['median_ae']:.1f} seconds")

    print(f"\nPer-Stop MAE:")
    for i in range(len(metrics['per_stop'])):
        stop_mae = metrics['per_stop'][f'stop_{i+1}']['mae']
        print(f"  Stop {i+1}: {stop_mae:.1f} seconds ({stop_mae/60:.2f} minutes)")

    print(f"\nDirectional Analysis (Critical for Rider Experience):")
    print(f"  Overestimate Rate: {metrics['directional']['overestimate_rate']*100:.1f}%")
    print(f"    (Target: < 20% - bus arrives earlier than predicted)")
    print(f"  Underestimate Rate: {metrics['directional']['underestimate_rate']*100:.1f}%")
    print(f"  Overestimate MAE: {metrics['directional']['overestimate_mae']:.1f}s")
    print(f"  Underestimate MAE: {metrics['directional']['underestimate_mae']:.1f}s")

    print(f"\nAccuracy Thresholds:")
    print(f"  Within 1 min: {metrics['accuracy']['within_60s_pct']:.1f}%")
    print(f"  Within 2 min: {metrics['accuracy']['within_120s_pct']:.1f}%")
    print(f"  Within 3 min: {metrics['accuracy']['within_180s_pct']:.1f}%")

    print(f"\nError Percentiles:")
    for p in [50, 75, 90, 95]:
        print(f"  P{p}: {metrics['percentiles'][f'p{p}']:.1f} seconds")

    # Save results
    if output_path:
        with open(output_path, 'w') as f:
            json.dump(metrics, f, indent=2)
        print(f"\nResults saved to {output_path}")

    # Detailed breakdown of worst predictions
    if detailed:
        print_detailed_breakdown(
            predictions=predictions,
            actuals=test_labels,
            raw_features=test_raw_features,
            vehicle_ids=test_vehicle_ids,
            vehicle_mapping=vehicle_mapping,
            num_samples=num_detailed_samples,
            sort_by_error=True
        )

    return metrics


# Feature layout must match data_prep_optimized.py build_features_vectorized()
# 0-7:   Core features (speed, heading, load, progress, delay, eta, scheduled_eta, distance)
# 8-13:  Time features (time_sin, time_cos, day_normalized, morning_rush, afternoon_rush, class_change)
# 14-20: Day of week one-hot (7 features)
# 21-24: Weather features (precip, is_raining, precip_prob, temp)
# 25-26: ETA indicator flags (has_system_eta, has_scheduled_eta)
# 27-30: Segment features (route_id, pattern_id, stop_seq_raw, stop_seq_normalized)
# 31-34: History features (progress_rate, speed_mean, time_stopped, is_stopped)
# NOTE: dwell_sec, boardings, alightings REMOVED (near-zero correlation with ETA)
# NOTE: stop_seq_raw = GTFS stop sequence (1, 2, ..., ~216), stop_seq_norm = seq/max_seq
FEATURE_NAMES = [
    # Core features (0-7)
    ('speed', 'mph', lambda x: f"{x:.1f} mph"),                               # 0
    ('heading_normalized', 'deg', lambda x: f"{int(x*360)} deg"),             # 1
    ('load', 'passengers', lambda x: f"{int(x)} passengers"),                 # 2
    ('progress', '%', lambda x: f"{x*100:.1f}%"),                             # 3
    ('lastStopOnTime', 's', lambda x: f"{x:+.0f}s"),                          # 4
    ('system_eta_sec', 's', lambda x: f"{x:.0f}s ({x/60:.1f}min)" if x > 0 else "N/A (-1)"),  # 5
    ('scheduled_eta', 's', lambda x: f"{x:.0f}s ({x/60:.1f}min)" if x > 0 else "N/A (-1)"),   # 6
    ('distance', 'mi', lambda x: f"{x:.3f} mi"),                              # 7

    # Time features (8-13)
    ('time_sin', '', lambda x: f"{x:.4f}" + (" OK" if -1 <= x <= 1 else " INVALID!")),  # 8
    ('time_cos', '', lambda x: f"{x:.4f}" + (" OK" if -1 <= x <= 1 else " INVALID!")),  # 9
    ('day_normalized', 'day', lambda x: ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'][min(6,int(round(x*6)))] if 0<=x<=1 else f"{x:.2f}"),  # 10
    ('is_morning_rush', '', lambda x: f"{int(round(x))}" + (" OK" if x in [0,1] else " INVALID!")),   # 11
    ('is_afternoon_rush', '', lambda x: f"{int(round(x))}" + (" OK" if x in [0,1] else " INVALID!")), # 12
    ('is_class_change', '', lambda x: f"{int(round(x))}" + (" OK" if x in [0,1] else " INVALID!")),   # 13

    # Day of week one-hot (14-20)
    ('is_sunday', '', lambda x: f"{int(round(x))}"),    # 14
    ('is_monday', '', lambda x: f"{int(round(x))}"),    # 15
    ('is_tuesday', '', lambda x: f"{int(round(x))}"),   # 16
    ('is_wednesday', '', lambda x: f"{int(round(x))}"), # 17
    ('is_thursday', '', lambda x: f"{int(round(x))}"),  # 18
    ('is_friday', '', lambda x: f"{int(round(x))}"),    # 19
    ('is_saturday', '', lambda x: f"{int(round(x))}"),  # 20

    # Weather features (21-24)
    ('precipitation', 'mm', lambda x: f"{x:.2f}mm"),           # 21
    ('is_raining', '', lambda x: f"{int(round(x))}"),          # 22
    ('precip_probability', '%', lambda x: f"{x*100:.0f}%"),    # 23
    ('temperature_normalized', 'C', lambda x: f"{x*40:.1f}C"), # 24

    # ETA indicator flags (25-26)
    ('has_system_eta', '', lambda x: f"{int(round(x))}" + (" OK" if x in [0,1] else " INVALID!")),    # 25
    ('has_scheduled_eta', '', lambda x: f"{int(round(x))}" + (" OK" if x in [0,1] else " INVALID!")), # 26

    # Segment features (27-30)
    ('routeId_norm', '', lambda x: f"route {int(x*300)}"),      # 27
    ('patternId_norm', '', lambda x: f"pattern {int(x*30000)}"),# 28
    ('stop_seq_raw', '', lambda x: f"stop #{int(x)} on route"), # 29 - GTFS stop sequence (1-216)
    ('stop_seq_norm', '', lambda x: f"{x*100:.1f}% along route"),  # 30 - normalized (0-1)

    # History features (31-34)
    ('progress_rate', '/s', lambda x: f"{x:.6f}/s"),      # 31
    ('speed_rolling_mean', 'mph', lambda x: f"{x:.1f}"),  # 32
    ('time_stopped', 's', lambda x: f"{x:.1f}s"),         # 33
    ('is_stopped', '', lambda x: f"{int(round(x))}"),     # 34
]


def print_detailed_breakdown(
    predictions: np.ndarray,
    actuals: np.ndarray,
    raw_features: np.ndarray,
    vehicle_ids: np.ndarray,
    vehicle_mapping: dict,
    num_samples: int = 20,
    sort_by_error: bool = True
):
    """
    Print detailed breakdown of predictions with all features.

    Args:
        predictions: Model predictions
        actuals: Actual ETAs
        raw_features: Unnormalized features
        vehicle_ids: Vehicle ID indices
        vehicle_mapping: Dict mapping index to vehicle string
        num_samples: Number of samples to show
        sort_by_error: If True, show worst predictions first
    """
    # Flatten if multi-stop (take first stop)
    if len(predictions.shape) > 1:
        predictions = predictions[:, 0]
    if len(actuals.shape) > 1:
        actuals = actuals[:, 0]

    errors = predictions - actuals
    abs_errors = np.abs(errors)

    # Get indices to show
    if sort_by_error:
        indices = np.argsort(-abs_errors)[:num_samples]  # Worst first
        print(f"\n{'='*80}")
        print(f"TOP {num_samples} WORST PREDICTIONS (sorted by absolute error)")
        print(f"{'='*80}")
    else:
        indices = np.random.choice(len(predictions), min(num_samples, len(predictions)), replace=False)
        print(f"\n{'='*80}")
        print(f"RANDOM SAMPLE OF {num_samples} PREDICTIONS")
        print(f"{'='*80}")

    # Reverse mapping: index -> vehicle string
    idx_to_vid = {v: k for k, v in vehicle_mapping.items()} if vehicle_mapping else {}

    for rank, idx in enumerate(indices, 1):
        pred = predictions[idx]
        actual = actuals[idx]
        error = errors[idx]
        vid_idx = vehicle_ids[idx]
        vid_str = idx_to_vid.get(vid_idx, f"Unknown ({vid_idx})")

        direction = "UNDERESTIMATE (bus arrives LATER)" if error < 0 else "OVERESTIMATE (bus arrives EARLIER)"

        print(f"\n{'='*80}")
        print(f"--- Sample {rank} (Error Rank: {rank}/{num_samples}) ---")
        print(f"{'='*80}")
        print(f"PREDICTION: Vehicle: {vid_str}")
        print(f"  Predicted: {pred:.1f}s ({pred/60:.2f} min)")
        print(f"  Actual:    {actual:.1f}s ({actual/60:.2f} min)")
        print(f"  Error:     {error:+.1f}s ({error/60:+.2f} min) - {direction}")

        print(f"\nALL RAW INPUT FEATURES ({raw_features.shape[1]} features):")

        for i in range(min(raw_features.shape[1], len(FEATURE_NAMES))):
            val = raw_features[idx, i]
            name, unit, fmt_func = FEATURE_NAMES[i]
            try:
                formatted = fmt_func(val)
            except:
                formatted = f"{val:.4f}"
            print(f"  [{i:2d}] {name:24s}: {val:8.4f} ({formatted})")

        # Show any extra features beyond defined names
        if raw_features.shape[1] > len(FEATURE_NAMES):
            for i in range(len(FEATURE_NAMES), raw_features.shape[1]):
                val = raw_features[idx, i]
                print(f"  [{i:2d}] feature_{i:02d}             : {val:8.4f}")

        print("-" * 80)


def compare_models(
    model_paths: list[str],
    model_names: list[str],
    data_dir: str,
    device: str = 'cpu'
) -> dict:
    """
    Compare multiple models on the same test set.

    Args:
        model_paths: List of model checkpoint paths
        model_names: Names for each model
        data_dir: Directory with test data
        device: Device for inference

    Returns:
        Dictionary with comparison results
    """
    results = {}

    for path, name in zip(model_paths, model_names):
        print(f"\n{'='*40}")
        print(f"Evaluating: {name}")
        print(f"{'='*40}")

        metrics = evaluate_model(path, data_dir, device)
        results[name] = metrics

    # Summary comparison
    print("\n" + "=" * 60)
    print("MODEL COMPARISON SUMMARY")
    print("=" * 60)

    print(f"\n{'Model':<20} {'MAE (s)':<10} {'Within 1min':<12} {'Overest. Rate':<12}")
    print("-" * 54)

    for name in model_names:
        mae = results[name]['overall']['mae']
        within_1m = results[name]['accuracy']['within_60s_pct']
        overest = results[name]['directional']['overestimate_rate'] * 100
        print(f"{name:<20} {mae:<10.1f} {within_1m:<12.1f}% {overest:<12.1f}%")

    return results


def generate_report(metrics: dict, output_path: str):
    """
    Generate a human-readable evaluation report.

    Args:
        metrics: Evaluation metrics dictionary
        output_path: Path to save report
    """
    lines = []
    lines.append("# ETA Prediction Model Evaluation Report")
    lines.append("")
    lines.append("## Overall Performance")
    lines.append("")
    lines.append(f"- **MAE**: {metrics['overall']['mae']:.1f} seconds ({metrics['overall']['mae']/60:.2f} minutes)")
    lines.append(f"- **RMSE**: {metrics['overall']['rmse']:.1f} seconds")
    lines.append(f"- **Median Absolute Error**: {metrics['overall']['median_ae']:.1f} seconds")
    lines.append(f"- **Test Samples**: {metrics['overall']['n_samples']:,}")
    lines.append("")

    lines.append("## Per-Stop Performance")
    lines.append("")
    lines.append("| Stop | MAE (seconds) | MAE (minutes) |")
    lines.append("|------|--------------|---------------|")
    for i, (stop, data) in enumerate(metrics['per_stop'].items()):
        lines.append(f"| {i+1} | {data['mae']:.1f} | {data['mae']/60:.2f} |")
    lines.append("")

    lines.append("## Directional Analysis")
    lines.append("")
    lines.append("*Critical for rider experience - overestimation means the bus arrives earlier than predicted, which can cause riders to miss the bus.*")
    lines.append("")
    lines.append(f"- **Overestimate Rate**: {metrics['directional']['overestimate_rate']*100:.1f}% (target: < 20%)")
    lines.append(f"- **Underestimate Rate**: {metrics['directional']['underestimate_rate']*100:.1f}%")
    lines.append(f"- **Overestimate MAE**: {metrics['directional']['overestimate_mae']:.1f} seconds")
    lines.append(f"- **Underestimate MAE**: {metrics['directional']['underestimate_mae']:.1f} seconds")
    lines.append("")

    lines.append("## Accuracy at Thresholds")
    lines.append("")
    lines.append("| Threshold | Accuracy |")
    lines.append("|-----------|----------|")
    for thresh in [30, 60, 90, 120, 180]:
        acc = metrics['accuracy'][f'within_{thresh}s_pct']
        lines.append(f"| {thresh} seconds ({thresh/60:.1f} min) | {acc:.1f}% |")
    lines.append("")

    lines.append("## Error Distribution")
    lines.append("")
    lines.append("| Percentile | Error (seconds) |")
    lines.append("|------------|-----------------|")
    for p in [50, 75, 90, 95, 99]:
        val = metrics['percentiles'][f'p{p}']
        lines.append(f"| P{p} | {val:.1f} |")
    lines.append("")

    with open(output_path, 'w') as f:
        f.write('\n'.join(lines))

    print(f"Report saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Evaluate ETA prediction models',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        '--model-path', type=str, required=True,
        help='Path to model checkpoint'
    )
    parser.add_argument(
        '--data-dir', type=str, required=True,
        help='Directory containing processed test data'
    )
    parser.add_argument(
        '--output', type=str, default=None,
        help='Path to save results JSON'
    )
    parser.add_argument(
        '--report', type=str, default=None,
        help='Path to save markdown report'
    )
    parser.add_argument(
        '--device', type=str, default=None,
        help='Device for inference (auto-detected if not specified)'
    )
    parser.add_argument(
        '--route-filter', type=int, default=None,
        help='Filter to specific route ID (e.g., 100). Must match training filter.'
    )
    parser.add_argument(
        '--detailed', action='store_true',
        help='Show detailed breakdown of worst predictions with all features'
    )
    parser.add_argument(
        '--num-samples', type=int, default=20,
        help='Number of samples to show in detailed mode'
    )

    args = parser.parse_args()

    if args.device is None:
        args.device = 'cuda' if torch.cuda.is_available() else 'cpu'

    metrics = evaluate_model(
        args.model_path,
        args.data_dir,
        args.device,
        args.output,
        args.route_filter,
        args.detailed,
        args.num_samples
    )

    if args.report:
        generate_report(metrics, args.report)


if __name__ == '__main__':
    main()
