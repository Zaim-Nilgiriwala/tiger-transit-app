"""
Training Script for ETA Prediction Models

CLI interface for training per-route ETA prediction models with:
- Asymmetric loss (5x penalty for overestimation)
- Early stopping on validation MAE
- Learning rate scheduling
- Model checkpointing

Usage:
    python train.py --data-dir ./processed_data --output-dir ./models
    python train.py --route-id 24 --epochs 100 --batch-size 256
"""

import argparse
import json
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

import numpy as np
import torch
import torch.nn as nn
from torch.optim import Adam
from torch.optim.lr_scheduler import ReduceLROnPlateau

from model import ETAPredictor, ETAPredictorWithUncertainty, save_model
from loss import AsymmetricETALoss, create_loss_function
from dataset import create_data_loaders, create_data_loaders_from_arrays, generate_training_data


class EarlyStopping:
    """Early stopping to prevent overfitting."""

    def __init__(self, patience: int = 15, min_delta: float = 0.1):
        """
        Args:
            patience: Number of epochs to wait for improvement
            min_delta: Minimum change to qualify as improvement
        """
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_score = None
        self.should_stop = False

    def __call__(self, val_score: float) -> bool:
        """Check if training should stop."""
        if self.best_score is None:
            self.best_score = val_score
            return False

        if val_score < self.best_score - self.min_delta:
            self.best_score = val_score
            self.counter = 0
        else:
            self.counter += 1
            if self.counter >= self.patience:
                self.should_stop = True

        return self.should_stop


class Trainer:
    """Handles the training loop for ETA prediction models."""

    def __init__(
        self,
        model: nn.Module,
        train_loader,
        val_loader,
        loss_fn: nn.Module,
        learning_rate: float = 0.001,
        device: str = 'cpu',
        grad_clip: float = 1.0,
        debug: bool = False
    ):
        self.model = model.to(device)
        self.train_loader = train_loader
        self.val_loader = val_loader
        self.loss_fn = loss_fn
        self.device = device
        self.grad_clip = grad_clip
        self.debug = debug

        self.optimizer = Adam(model.parameters(), lr=learning_rate)
        self.scheduler = ReduceLROnPlateau(
            self.optimizer, mode='min', factor=0.5, patience=5, verbose=True
        )

        self.train_losses = []
        self.val_losses = []
        self.val_maes = []

        if self.debug:
            print("\n" + "="*60)
            print("DEBUG MODE ENABLED")
            print("="*60)
            print(f"Model: {model.__class__.__name__}")
            print(f"Parameters: {sum(p.numel() for p in model.parameters()):,}")
            print(f"Training batches: {len(train_loader)}")
            print(f"Validation batches: {len(val_loader)}")
            print(f"Batch size: {train_loader.batch_size}")
            print(f"Learning rate: {learning_rate}")
            print(f"Gradient clipping: {grad_clip}")
            print("="*60 + "\n")

    def train_epoch(self) -> float:
        """Train for one epoch."""
        self.model.train()
        total_loss = 0.0
        n_batches = 0
        batch_losses = []

        for batch_idx, (features, labels, vehicle_ids) in enumerate(self.train_loader):
            features = features.to(self.device)
            labels = labels.to(self.device)
            vehicle_ids = vehicle_ids.to(self.device)

            self.optimizer.zero_grad()

            predictions = self.model(features, vehicle_ids)
            loss = self.loss_fn(predictions, labels)

            loss.backward()

            # Gradient clipping
            if self.grad_clip > 0:
                grad_norm = nn.utils.clip_grad_norm_(self.model.parameters(), self.grad_clip)
            else:
                grad_norm = 0.0

            self.optimizer.step()

            batch_loss = loss.item()
            total_loss += batch_loss
            batch_losses.append(batch_loss)
            n_batches += 1

            # Debug output every 10 batches
            if self.debug and batch_idx % 10 == 0:
                # Compute prediction stats
                with torch.no_grad():
                    pred_mean = predictions.mean().item()
                    pred_std = predictions.std().item()
                    label_mean = labels.mean().item()
                    errors = predictions - labels
                    underest_pct = (errors < 0).float().mean().item() * 100

                print(f"  Batch {batch_idx:4d}/{len(self.train_loader)} | "
                      f"Loss: {batch_loss:.4f} | "
                      f"Grad: {grad_norm:.4f} | "
                      f"Pred: {pred_mean:.1f}±{pred_std:.1f}s | "
                      f"Actual: {label_mean:.1f}s | "
                      f"Under: {underest_pct:.0f}%")

        if self.debug:
            import numpy as np
            print(f"  Epoch summary: Loss min={min(batch_losses):.4f} max={max(batch_losses):.4f} "
                  f"std={np.std(batch_losses):.4f}")

        return total_loss / n_batches

    def validate(self) -> tuple[float, float]:
        """Validate the model."""
        self.model.eval()
        total_loss = 0.0
        total_mae = 0.0
        n_batches = 0
        n_samples = 0
        all_errors = []

        with torch.no_grad():
            for features, labels, vehicle_ids in self.val_loader:
                features = features.to(self.device)
                labels = labels.to(self.device)
                vehicle_ids = vehicle_ids.to(self.device)

                predictions = self.model(features, vehicle_ids)
                loss = self.loss_fn(predictions, labels)

                # MAE in seconds
                mae = torch.abs(predictions - labels).mean()
                errors = (predictions - labels).cpu().numpy()
                all_errors.append(errors)

                total_loss += loss.item()
                total_mae += mae.item() * features.shape[0]
                n_batches += 1
                n_samples += features.shape[0]

        avg_loss = total_loss / n_batches
        avg_mae = total_mae / n_samples

        if self.debug:
            import numpy as np
            all_errors = np.concatenate(all_errors, axis=0)
            underest_pct = (all_errors < 0).mean() * 100
            overest_pct = (all_errors > 0).mean() * 100
            within_60 = (np.abs(all_errors) < 60).mean() * 100
            within_120 = (np.abs(all_errors) < 120).mean() * 100
            per_stop_mae = np.abs(all_errors).mean(axis=0)
            print(f"  Validation: Under={underest_pct:.1f}% Over={overest_pct:.1f}% | "
                  f"<60s={within_60:.1f}% <120s={within_120:.1f}%")
            print(f"  Per-stop MAE: " + " | ".join([f"Stop{i+1}={mae:.1f}s" for i, mae in enumerate(per_stop_mae)]))

        return avg_loss, avg_mae

    def fit(
        self,
        epochs: int,
        early_stopping: EarlyStopping = None,
        checkpoint_dir: str = None,
        verbose: bool = True
    ) -> dict:
        """
        Train the model for multiple epochs.

        Args:
            epochs: Number of epochs to train
            early_stopping: EarlyStopping callback
            checkpoint_dir: Directory to save checkpoints
            verbose: Whether to print progress

        Returns:
            Dictionary with training history and final metrics
        """
        best_val_mae = float('inf')
        best_epoch = 0

        if checkpoint_dir:
            Path(checkpoint_dir).mkdir(parents=True, exist_ok=True)

        for epoch in range(epochs):
            start_time = time.time()

            # Train
            train_loss = self.train_epoch()

            # Validate
            val_loss, val_mae = self.validate()

            # Update learning rate
            self.scheduler.step(val_mae)

            # Record history
            self.train_losses.append(train_loss)
            self.val_losses.append(val_loss)
            self.val_maes.append(val_mae)

            epoch_time = time.time() - start_time

            if verbose:
                print(f"Epoch {epoch+1}/{epochs} ({epoch_time:.1f}s) - "
                      f"Train Loss: {train_loss:.4f} - "
                      f"Val Loss: {val_loss:.4f} - "
                      f"Val MAE: {val_mae:.1f}s")

            # Save best model
            if val_mae < best_val_mae:
                best_val_mae = val_mae
                best_epoch = epoch

                if checkpoint_dir:
                    save_model(
                        self.model,
                        f"{checkpoint_dir}/best_model.pt",
                        metadata={
                            'epoch': epoch,
                            'val_mae': val_mae,
                            'val_loss': val_loss,
                            'train_loss': train_loss
                        }
                    )

            # Early stopping
            if early_stopping and early_stopping(val_mae):
                if verbose:
                    print(f"\nEarly stopping at epoch {epoch+1}")
                break

        return {
            'best_val_mae': best_val_mae,
            'best_epoch': best_epoch,
            'final_train_loss': self.train_losses[-1],
            'final_val_loss': self.val_losses[-1],
            'final_val_mae': self.val_maes[-1],
            'train_losses': self.train_losses,
            'val_losses': self.val_losses,
            'val_maes': self.val_maes,
            'epochs_trained': len(self.train_losses)
        }


def train_model(
    data_dir: str,
    output_dir: str,
    route_id: Optional[str] = None,
    route_filter: Optional[int] = None,
    epochs: int = 100,
    batch_size: int = 256,
    learning_rate: float = 0.001,
    hidden_dims: tuple = (256, 128, 64),
    dropout: float = 0.2,
    overestimate_penalty: float = 5.0,
    patience: int = 15,
    device: str = None,
    model_type: str = 'standard',
    debug: bool = False
) -> dict:
    """
    Train an ETA prediction model.

    Args:
        data_dir: Directory containing processed training data
        output_dir: Directory to save trained model
        route_id: Route identifier (for naming)
        route_filter: Filter data to only this route ID (e.g., 100 for route 100)
        epochs: Number of training epochs
        batch_size: Batch size
        learning_rate: Initial learning rate
        hidden_dims: Hidden layer dimensions
        dropout: Dropout probability
        overestimate_penalty: Penalty multiplier for overestimation
        patience: Early stopping patience
        device: Device to train on (auto-detected if None)
        model_type: 'standard' or 'uncertainty'
        debug: Enable detailed debug output

    Returns:
        Dictionary with training results
    """
    # Auto-detect device
    if device is None:
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"Using device: {device}")

    data_path = Path(data_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Load data
    print("Loading training data...")
    features_path = data_path / 'features.npy'
    labels_path = data_path / 'labels.npy'
    vehicle_ids_path = data_path / 'vehicle_ids.npy'

    if not features_path.exists():
        raise FileNotFoundError(f"Features not found at {features_path}")

    # Load raw arrays for potential filtering
    features = np.load(features_path)
    labels = np.load(labels_path)
    vehicle_ids = np.load(vehicle_ids_path)

    # Filter by route if requested
    # Route ID is stored in feature column 27, normalized as routeId/300
    if route_filter is not None:
        ROUTE_FEATURE_IDX = 27  # Index of routeId feature
        expected_value = route_filter / 300.0
        tolerance = 0.5 / 300.0  # Allow for small floating point differences

        route_mask = np.abs(features[:, ROUTE_FEATURE_IDX] - expected_value) < tolerance
        n_before = len(features)

        features = features[route_mask]
        labels = labels[route_mask]
        vehicle_ids = vehicle_ids[route_mask]

        n_after = len(features)
        print(f"Filtered to route {route_filter}: {n_after:,} samples ({n_after/n_before*100:.1f}% of {n_before:,})")

        if n_after == 0:
            # Reload original to show available routes
            original_features = np.load(features_path)
            unique_routes = np.unique(np.round(original_features[:, ROUTE_FEATURE_IDX] * 300).astype(int))
            raise ValueError(f"No samples found for route {route_filter}. Available routes: {list(unique_routes[:20])}...")

    # Create data loaders from arrays directly
    # Use fixed seed for reproducible train/val/test split (matches evaluate.py)
    np.random.seed(42)
    train_loader, val_loader, test_loader, data_stats = create_data_loaders_from_arrays(
        features, labels, vehicle_ids,
        batch_size=batch_size,
        train_split=0.8,
        val_split=0.1
    )

    print(f"Training samples: {data_stats['n_train']}")
    print(f"Validation samples: {data_stats['n_val']}")
    print(f"Test samples: {data_stats['n_test']}")
    print(f"Number of features: {data_stats['n_features']}")
    print(f"Number of stops: {data_stats['n_stops']}")

    if debug:
        # Load raw data for analysis
        features = np.load(features_path)
        labels = np.load(labels_path)
        print("\n" + "="*60)
        print("DATA ANALYSIS")
        print("="*60)
        print(f"Label stats (ETA in seconds):")
        print(f"  Mean: {labels.mean():.1f}s  Std: {labels.std():.1f}s")
        print(f"  Min: {labels.min():.1f}s  Max: {labels.max():.1f}s")
        print(f"  Median: {np.median(labels):.1f}s")
        print(f"\nLabel distribution:")
        for threshold in [60, 120, 180, 300, 600]:
            pct = (labels < threshold).mean() * 100
            print(f"  <{threshold}s: {pct:.1f}%")
        print(f"\nFeature stats (first 10):")
        for i in range(min(10, features.shape[1])):
            print(f"  F{i:02d}: mean={features[:,i].mean():.3f} std={features[:,i].std():.3f} "
                  f"min={features[:,i].min():.3f} max={features[:,i].max():.3f}")
        print("="*60 + "\n")

    # Load vehicle mapping
    vehicle_mapping_path = data_path / 'vehicle_mapping.json'
    if vehicle_mapping_path.exists():
        with open(vehicle_mapping_path) as f:
            vehicle_mapping = json.load(f)
        num_vehicles = len(vehicle_mapping)
    else:
        num_vehicles = 100  # Default

    # Ensure num_vehicles is large enough for all vehicle IDs in data
    max_vehicle_id = int(vehicle_ids.max())
    if max_vehicle_id >= num_vehicles:
        print(f"Warning: Max vehicle ID ({max_vehicle_id}) >= vehicle mapping size ({num_vehicles})")
        print(f"  Expanding embedding table to {max_vehicle_id + 1}")
        num_vehicles = max_vehicle_id + 1

    # Create model
    print("\nCreating model...")
    if model_type == 'uncertainty':
        model = ETAPredictorWithUncertainty(
            num_features=data_stats['n_features'],
            num_vehicle_ids=num_vehicles,
            hidden_dims=hidden_dims,
            num_stops=data_stats['n_stops'],
            dropout=dropout
        )
    else:
        model = ETAPredictor(
            num_features=data_stats['n_features'],
            num_vehicle_ids=num_vehicles,
            hidden_dims=hidden_dims,
            num_stops=data_stats['n_stops'],
            dropout=dropout
        )

    print(f"Model parameters: {model.get_num_parameters():,}")

    # Create loss function
    loss_fn = AsymmetricETALoss(
        overestimate_penalty=overestimate_penalty,
        ordering_weight=0.1
    )

    # Create trainer
    trainer = Trainer(
        model=model,
        train_loader=train_loader,
        val_loader=val_loader,
        loss_fn=loss_fn,
        learning_rate=learning_rate,
        device=device,
        debug=debug
    )

    # Train
    print(f"\nTraining for up to {epochs} epochs...")
    early_stopping = EarlyStopping(patience=patience)

    route_name = f"route_{route_id}" if route_id else "model"
    checkpoint_dir = output_path / route_name

    results = trainer.fit(
        epochs=epochs,
        early_stopping=early_stopping,
        checkpoint_dir=str(checkpoint_dir)
    )

    # Evaluate on test set
    print("\nEvaluating on test set...")
    test_metrics = evaluate_model(model, test_loader, device)
    results['test_metrics'] = test_metrics

    print(f"\nTest Results:")
    print(f"  Overall MAE: {test_metrics['overall_mae']:.1f} seconds")
    for i, mae in enumerate(test_metrics['per_stop_mae']):
        print(f"  Stop {i+1} MAE: {mae:.1f} seconds")
    print(f"  Overestimate Rate: {test_metrics['overestimate_rate']*100:.1f}%")
    print(f"  Within 1 min: {test_metrics['within_60s']*100:.1f}%")
    print(f"  Within 2 min: {test_metrics['within_120s']*100:.1f}%")

    # Save final results
    results_path = checkpoint_dir / 'training_results.json'
    with open(results_path, 'w') as f:
        # Convert numpy arrays to lists for JSON serialization
        serializable_results = {
            k: v if not isinstance(v, np.ndarray) else v.tolist()
            for k, v in results.items()
        }
        json.dump(serializable_results, f, indent=2)

    # Save normalization stats
    norm_stats_path = checkpoint_dir / 'normalization_stats.json'
    with open(norm_stats_path, 'w') as f:
        json.dump({
            'means': data_stats['means'],
            'stds': data_stats['stds']
        }, f, indent=2)

    print(f"\nModel saved to: {checkpoint_dir}")
    print(f"Best validation MAE: {results['best_val_mae']:.1f} seconds (epoch {results['best_epoch']+1})")

    return results


def evaluate_model(
    model: nn.Module,
    data_loader,
    device: str
) -> dict:
    """
    Evaluate model on a dataset.

    Returns:
        Dictionary with evaluation metrics
    """
    model.eval()
    model.to(device)

    all_predictions = []
    all_actuals = []

    with torch.no_grad():
        for features, labels, vehicle_ids in data_loader:
            features = features.to(device)
            vehicle_ids = vehicle_ids.to(device)

            predictions = model(features, vehicle_ids)

            all_predictions.append(predictions.cpu().numpy())
            all_actuals.append(labels.numpy())

    predictions = np.concatenate(all_predictions, axis=0)
    actuals = np.concatenate(all_actuals, axis=0)

    # Compute metrics
    errors = predictions - actuals
    abs_errors = np.abs(errors)

    # Overall metrics
    overall_mae = abs_errors.mean()

    # Per-stop MAE
    per_stop_mae = abs_errors.mean(axis=0).tolist()

    # Overestimate rate (predicted > actual, bus arrives early)
    overestimate_rate = (errors > 0).mean()

    # Underestimate rate
    underestimate_rate = (errors < 0).mean()

    # Accuracy thresholds
    within_60s = (abs_errors < 60).mean()
    within_120s = (abs_errors < 120).mean()
    within_180s = (abs_errors < 180).mean()

    # Overestimate-specific MAE
    overestimate_mask = errors > 0
    overestimate_mae = abs_errors[overestimate_mask].mean() if overestimate_mask.any() else 0

    # Underestimate-specific MAE
    underestimate_mask = errors < 0
    underestimate_mae = abs_errors[underestimate_mask].mean() if underestimate_mask.any() else 0

    return {
        'overall_mae': float(overall_mae),
        'per_stop_mae': per_stop_mae,
        'overestimate_rate': float(overestimate_rate),
        'underestimate_rate': float(underestimate_rate),
        'overestimate_mae': float(overestimate_mae),
        'underestimate_mae': float(underestimate_mae),
        'within_60s': float(within_60s),
        'within_120s': float(within_120s),
        'within_180s': float(within_180s),
        'n_samples': len(predictions)
    }


def main():
    parser = argparse.ArgumentParser(
        description='Train ETA prediction models',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Data arguments
    parser.add_argument(
        '--data-dir', type=str, required=True,
        help='Directory containing processed training data'
    )
    parser.add_argument(
        '--output-dir', type=str, default='./models',
        help='Directory to save trained models'
    )
    parser.add_argument(
        '--route-id', type=str, default=None,
        help='Route identifier for naming'
    )
    parser.add_argument(
        '--route-filter', type=int, default=None,
        help='Filter data to only this route ID (e.g., 100 for route 100)'
    )

    # Training arguments
    parser.add_argument(
        '--epochs', type=int, default=100,
        help='Maximum number of training epochs'
    )
    parser.add_argument(
        '--batch-size', type=int, default=256,
        help='Training batch size'
    )
    parser.add_argument(
        '--learning-rate', type=float, default=0.001,
        help='Initial learning rate'
    )
    parser.add_argument(
        '--patience', type=int, default=15,
        help='Early stopping patience'
    )

    # Model arguments
    parser.add_argument(
        '--hidden-dims', type=int, nargs='+', default=[256, 128, 64],
        help='Hidden layer dimensions'
    )
    parser.add_argument(
        '--dropout', type=float, default=0.2,
        help='Dropout probability'
    )
    parser.add_argument(
        '--model-type', type=str, default='standard',
        choices=['standard', 'uncertainty'],
        help='Model type to train'
    )

    # Loss arguments
    parser.add_argument(
        '--overestimate-penalty', type=float, default=5.0,
        help='Penalty multiplier for overestimation (bus arrives earlier than predicted)'
    )

    # Device arguments
    parser.add_argument(
        '--device', type=str, default=None,
        help='Device to train on (auto-detected if not specified)'
    )
    parser.add_argument(
        '--debug', action='store_true',
        help='Enable debug mode with detailed output (per-batch loss, gradients, etc.)'
    )

    # Generate data arguments
    parser.add_argument(
        '--generate-data', action='store_true',
        help='Generate training data from raw telemetry files'
    )
    parser.add_argument(
        '--telemetry-dir', type=str, default=None,
        help='Directory containing raw JSONL telemetry files'
    )
    parser.add_argument(
        '--gtfs-dir', type=str, default=None,
        help='Directory containing GTFS data'
    )

    args = parser.parse_args()

    # Generate data if requested
    if args.generate_data:
        if not args.telemetry_dir or not args.gtfs_dir:
            parser.error("--generate-data requires --telemetry-dir and --gtfs-dir")

        print("Generating training data...")
        from glob import glob

        telemetry_files = glob(f"{args.telemetry_dir}/*.jsonl")
        if not telemetry_files:
            print(f"No JSONL files found in {args.telemetry_dir}")
            sys.exit(1)

        generate_training_data(
            telemetry_files=telemetry_files,
            gtfs_dir=args.gtfs_dir,
            output_dir=args.data_dir
        )

    # Train model
    train_model(
        data_dir=args.data_dir,
        output_dir=args.output_dir,
        route_id=args.route_id,
        route_filter=args.route_filter,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        hidden_dims=tuple(args.hidden_dims),
        dropout=args.dropout,
        overestimate_penalty=args.overestimate_penalty,
        patience=args.patience,
        device=args.device,
        model_type=args.model_type,
        debug=args.debug
    )


if __name__ == '__main__':
    main()
