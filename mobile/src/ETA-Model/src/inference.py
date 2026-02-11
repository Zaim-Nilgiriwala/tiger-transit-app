"""
ETA Inference Module with Sanity Constraints and Smoothing

This module provides a wrapper around the raw model predictions to apply:
1. Clamping to reasonable ETA ranges
2. Monotonicity constraints (ETA should decrease as progress increases)
3. Exponential smoothing to prevent jitter in displayed ETAs

These post-processing steps improve the user experience by preventing
jarring ETA jumps and obviously incorrect predictions.
"""

from typing import Optional
import numpy as np
import torch


class ETAInference:
    """
    Handles inference with sanity constraints and smoothing.

    Wraps a trained model and applies post-processing to ensure
    realistic, smooth ETA predictions.
    """

    def __init__(
        self,
        model,
        smoothing_alpha: float = 0.3,
        min_eta_seconds: float = 0.0,
        max_eta_seconds: float = 3600.0,
        log_transform: bool = False
    ):
        """
        Initialize the inference wrapper.

        Args:
            model: Trained ETAPredictor model
            smoothing_alpha: Weight for new predictions in smoothing (0-1).
                0 = all previous, 1 = all new (no smoothing)
            min_eta_seconds: Minimum allowed ETA
            max_eta_seconds: Maximum allowed ETA (default 60 minutes)
            log_transform: Whether model outputs are in log1p space
        """
        self.model = model
        self.alpha = smoothing_alpha
        self.min_eta = min_eta_seconds
        self.max_eta = max_eta_seconds
        self.log_transform = log_transform

        # Track previous predictions for smoothing
        # Key: vehicle_id, Value: last ETA prediction (per stop)
        self._last_predictions: dict[str, np.ndarray] = {}

        # Track previous progress for monotonicity check
        self._last_progress: dict[str, float] = {}

    def predict(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor,
        vehicle_id_strings: list[str]
    ) -> dict:
        """
        Make predictions with constraints and smoothing.

        Args:
            features: Input features tensor
            vehicle_ids: Vehicle ID indices for model
            vehicle_id_strings: Vehicle ID strings for tracking state

        Returns:
            Dictionary with constrained and smoothed predictions
        """
        # Get raw predictions from model
        self.model.eval()
        with torch.no_grad():
            raw_preds = self.model.forward(features, vehicle_ids)

            # Inverse log transform if needed
            if self.log_transform:
                raw_preds = torch.expm1(raw_preds)

        raw_preds_np = raw_preds.cpu().numpy()

        # Apply constraints and smoothing
        constrained = self._apply_constraints(raw_preds_np, features.cpu().numpy())
        smoothed = self._apply_smoothing(constrained, vehicle_id_strings)

        return {
            'eta_seconds': smoothed,
            'eta_minutes': smoothed / 60,
            'eta_raw_seconds': raw_preds_np,  # Unprocessed for debugging
        }

    def _apply_constraints(
        self,
        predictions: np.ndarray,
        features: np.ndarray
    ) -> np.ndarray:
        """
        Apply sanity constraints to predictions.

        Args:
            predictions: Raw model predictions (batch, num_stops)
            features: Input features (for progress-based constraints)

        Returns:
            Constrained predictions
        """
        constrained = predictions.copy()

        # 1. Clamp to reasonable range
        constrained = np.clip(constrained, self.min_eta, self.max_eta)

        # 2. Ensure ETA ordering (stop 1 < stop 2 < stop 3)
        for i in range(constrained.shape[1] - 1):
            # If ETA for stop i+1 is less than stop i, adjust
            violation_mask = constrained[:, i + 1] < constrained[:, i]
            # Set stop i+1 to be at least stop i + 30 seconds
            constrained[violation_mask, i + 1] = constrained[violation_mask, i] + 30

        # 3. Ensure ETAs are positive
        constrained = np.maximum(constrained, 0)

        return constrained

    def _apply_smoothing(
        self,
        predictions: np.ndarray,
        vehicle_ids: list[str]
    ) -> np.ndarray:
        """
        Apply exponential smoothing to prevent jitter.

        Args:
            predictions: Constrained predictions
            vehicle_ids: Vehicle ID strings for state tracking

        Returns:
            Smoothed predictions
        """
        smoothed = predictions.copy()

        for i, vid in enumerate(vehicle_ids):
            if vid in self._last_predictions:
                prev = self._last_predictions[vid]

                # Apply exponential moving average
                # new_pred = alpha * current + (1 - alpha) * previous
                smoothed[i] = (
                    self.alpha * predictions[i] +
                    (1 - self.alpha) * prev
                )

                # But don't smooth too aggressively on large changes
                # (might indicate stop transition or route change)
                change = np.abs(predictions[i] - prev)
                large_change_mask = change > 60  # More than 1 minute change
                smoothed[i, large_change_mask] = predictions[i, large_change_mask]

            # Update state
            self._last_predictions[vid] = smoothed[i].copy()

        return smoothed

    def apply_monotonicity_constraint(
        self,
        current_eta: float,
        previous_eta: float,
        current_progress: float,
        previous_progress: float,
        max_increase_seconds: float = 30.0
    ) -> float:
        """
        Apply monotonicity constraint: ETA should generally decrease.

        Args:
            current_eta: Current prediction
            previous_eta: Previous prediction
            current_progress: Current route progress (0-1)
            previous_progress: Previous route progress
            max_increase_seconds: Maximum allowed ETA increase

        Returns:
            Constrained ETA
        """
        # If progress increased, ETA should decrease (or stay similar)
        if current_progress > previous_progress:
            # ETA increased unexpectedly
            if current_eta > previous_eta + max_increase_seconds:
                # Cap the increase
                return previous_eta + max_increase_seconds

        return current_eta

    def reset_vehicle_state(self, vehicle_id: Optional[str] = None):
        """
        Reset tracking state for a vehicle or all vehicles.

        Call this when:
        - Vehicle starts a new trip
        - Vehicle changes routes
        - System restarts

        Args:
            vehicle_id: Specific vehicle to reset, or None for all
        """
        if vehicle_id is not None:
            self._last_predictions.pop(vehicle_id, None)
            self._last_progress.pop(vehicle_id, None)
        else:
            self._last_predictions.clear()
            self._last_progress.clear()

    def get_confidence_interval(
        self,
        p50: np.ndarray,
        p80: np.ndarray,
        confidence_level: float = 0.8
    ) -> tuple:
        """
        Compute confidence interval from quantile predictions.

        Args:
            p50: Median (P50) predictions
            p80: 80th percentile predictions
            confidence_level: Desired confidence level

        Returns:
            Tuple of (lower_bound, upper_bound) arrays
        """
        # Simple symmetric interval around P50 using P80-P50 spread
        spread = p80 - p50

        # Scale spread based on confidence level
        # P80 corresponds to ~0.84 of normal distribution
        # Approximate scaling for other confidence levels
        if confidence_level <= 0.5:
            scale = 0.0
        elif confidence_level <= 0.8:
            scale = (confidence_level - 0.5) / 0.3
        else:
            scale = 1.0 + (confidence_level - 0.8) / 0.2

        lower = p50 - spread * scale * 0.5
        upper = p50 + spread * scale

        # Ensure lower bound is positive
        lower = np.maximum(lower, 0)

        return lower, upper


def batch_inference(
    model,
    features: np.ndarray,
    vehicle_ids: np.ndarray,
    device: str = 'cpu',
    log_transform: bool = False,
    batch_size: int = 512
) -> np.ndarray:
    """
    Run batch inference on a dataset.

    Args:
        model: Trained model
        features: Feature array (n_samples, n_features)
        vehicle_ids: Vehicle ID array (n_samples,)
        device: Device for inference
        log_transform: Whether to apply inverse log transform
        batch_size: Batch size for inference

    Returns:
        Predictions array (n_samples, num_stops)
    """
    model.eval()
    model.to(device)

    all_predictions = []

    for i in range(0, len(features), batch_size):
        batch_features = torch.tensor(
            features[i:i + batch_size],
            dtype=torch.float32
        ).to(device)

        batch_vehicle_ids = torch.tensor(
            vehicle_ids[i:i + batch_size],
            dtype=torch.long
        ).to(device)

        with torch.no_grad():
            preds = model(batch_features, batch_vehicle_ids)

            if log_transform:
                preds = torch.expm1(preds)
                preds = torch.clamp(preds, min=0, max=3600)

            all_predictions.append(preds.cpu().numpy())

    return np.concatenate(all_predictions, axis=0)


if __name__ == '__main__':
    # Test the inference module
    import torch.nn as nn

    # Create a simple mock model for testing
    class MockModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.fc = nn.Linear(10, 3)
            self.vehicle_embedding = nn.Embedding(10, 4)

        def forward(self, features, vehicle_ids):
            return torch.abs(self.fc(features)) * 100 + 60  # Random ETAs 60-160s

    model = MockModel()
    inference = ETAInference(model, smoothing_alpha=0.5)

    # Test predictions
    features = torch.randn(5, 10)
    vehicle_ids = torch.tensor([0, 1, 2, 3, 4])
    vehicle_strings = ['bus1', 'bus2', 'bus3', 'bus4', 'bus5']

    result = inference.predict(features, vehicle_ids, vehicle_strings)
    print("First prediction:")
    print(f"  ETA seconds: {result['eta_seconds']}")

    # Second prediction (should be smoothed)
    result2 = inference.predict(features, vehicle_ids, vehicle_strings)
    print("\nSecond prediction (smoothed):")
    print(f"  ETA seconds: {result2['eta_seconds']}")

    print("\nConstraints applied successfully!")
