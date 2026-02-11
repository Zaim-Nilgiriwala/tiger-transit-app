"""
Asymmetric Loss Functions for ETA Prediction

Key insight: For riders waiting at a stop, overestimating ETA (predicting bus
arrives later than it actually does) is much worse than underestimating, because:
- Overestimate: Bus arrives EARLY, rider might miss it
- Underestimate: Bus arrives LATE, rider just waits a bit longer

This module implements loss functions that penalize overestimation more heavily.
"""

import torch
import torch.nn as nn


class AsymmetricETALoss(nn.Module):
    """
    Asymmetric loss that penalizes overestimation more than underestimation.

    For a rider at a stop:
    - Prediction: 5 min, Actual: 3 min → Bus came EARLY → Rider might miss it → BAD
    - Prediction: 5 min, Actual: 7 min → Bus came LATE → Rider waits → Less bad

    Math:
    - error = predicted - actual
    - If error > 0 (predicted > actual, bus came early): Apply extra penalty
    - If error < 0 (predicted < actual, bus came late): Normal MSE penalty

    Loss = MSE + alpha * mean(ReLU(predicted - actual)^2)

    Where alpha = (overestimate_penalty - 1) to achieve the desired penalty ratio.
    For 5x penalty: alpha = 4

    Args:
        overestimate_penalty: How many times worse overestimation is (default: 5.0)
        ordering_weight: Weight for ETA ordering constraint (default: 0.1)
        use_huber: Use Huber loss instead of MSE for robustness (default: False)
        huber_delta: Delta parameter for Huber loss (default: 60.0 seconds)
    """

    def __init__(
        self,
        overestimate_penalty: float = 5.0,
        ordering_weight: float = 0.1,
        use_huber: bool = False,
        huber_delta: float = 60.0
    ):
        super().__init__()

        if overestimate_penalty < 1.0:
            raise ValueError("overestimate_penalty must be >= 1.0")

        self.alpha = overestimate_penalty - 1.0  # Extra penalty beyond base loss
        self.ordering_weight = ordering_weight
        self.use_huber = use_huber
        self.huber_delta = huber_delta

        if use_huber:
            self.base_loss = nn.HuberLoss(delta=huber_delta, reduction='none')
        else:
            self.base_loss = nn.MSELoss(reduction='none')

    def forward(
        self,
        predictions: torch.Tensor,
        actuals: torch.Tensor,
        mask: torch.Tensor = None
    ) -> torch.Tensor:
        """
        Compute the asymmetric loss.

        Args:
            predictions: Predicted ETAs, shape (batch, num_stops) or (batch,)
            actuals: Actual ETAs, shape (batch, num_stops) or (batch,)
            mask: Optional mask for valid predictions, shape same as predictions

        Returns:
            Scalar loss value
        """
        # Ensure same shape
        if predictions.shape != actuals.shape:
            raise ValueError(f"Shape mismatch: predictions {predictions.shape} vs actuals {actuals.shape}")

        # Compute base loss (MSE or Huber)
        base = self.base_loss(predictions, actuals)

        # Compute overestimation penalty
        # error = predicted - actual
        # If error > 0, we predicted too high (bus arrives earlier than predicted)
        overestimate = torch.relu(predictions - actuals)

        if self.use_huber:
            # Use Huber for penalty too
            overestimate_penalty = torch.where(
                overestimate < self.huber_delta,
                0.5 * overestimate ** 2,
                self.huber_delta * (overestimate - 0.5 * self.huber_delta)
            )
        else:
            overestimate_penalty = overestimate ** 2

        # Apply mask if provided
        if mask is not None:
            base = base * mask
            overestimate_penalty = overestimate_penalty * mask
            n_valid = mask.sum()
            if n_valid > 0:
                base_mean = base.sum() / n_valid
                penalty_mean = overestimate_penalty.sum() / n_valid
            else:
                base_mean = base.mean()
                penalty_mean = overestimate_penalty.mean()
        else:
            base_mean = base.mean()
            penalty_mean = overestimate_penalty.mean()

        # Combine losses
        total_loss = base_mean + self.alpha * penalty_mean

        # Add ordering constraint for multi-stop predictions
        if predictions.dim() == 2 and predictions.shape[1] >= 2:
            total_loss = total_loss + self.ordering_weight * self._ordering_penalty(predictions)

        return total_loss

    def _ordering_penalty(self, predictions: torch.Tensor) -> torch.Tensor:
        """
        Compute penalty for violating ETA ordering (ETA_1 < ETA_2 < ETA_3).

        Args:
            predictions: Shape (batch, num_stops)

        Returns:
            Scalar penalty value
        """
        penalty = 0.0
        for i in range(predictions.shape[1] - 1):
            # Penalize when ETA_i > ETA_{i+1} (closer stop has higher ETA)
            violation = torch.relu(predictions[:, i] - predictions[:, i + 1])
            penalty = penalty + violation.mean()

        return penalty


class WeightedAsymmetricLoss(nn.Module):
    """
    Asymmetric loss with per-stop weights.

    Allows different penalty weights for different stops (e.g., penalize
    errors more heavily for the immediate next stop).
    """

    def __init__(
        self,
        overestimate_penalty: float = 5.0,
        stop_weights: list[float] = None,
        ordering_weight: float = 0.1
    ):
        super().__init__()
        self.alpha = overestimate_penalty - 1.0
        self.stop_weights = stop_weights or [1.0]
        self.ordering_weight = ordering_weight

    def forward(
        self,
        predictions: torch.Tensor,
        actuals: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute weighted asymmetric loss.

        Args:
            predictions: Shape (batch, num_stops)
            actuals: Shape (batch, num_stops)

        Returns:
            Scalar loss value
        """
        num_stops = predictions.shape[1]
        weights = self.stop_weights[:num_stops]

        # Pad weights if needed
        while len(weights) < num_stops:
            weights.append(weights[-1])

        weights = torch.tensor(weights, device=predictions.device)

        # Compute per-stop losses
        errors = predictions - actuals
        base_loss = errors ** 2

        # Overestimate penalty
        overestimate = torch.relu(errors) ** 2
        combined = base_loss + self.alpha * overestimate

        # Apply weights
        weighted = combined * weights.unsqueeze(0)
        total_loss = weighted.mean()

        # Ordering constraint
        if num_stops >= 2:
            ordering = 0.0
            for i in range(num_stops - 1):
                violation = torch.relu(predictions[:, i] - predictions[:, i + 1])
                ordering = ordering + violation.mean()
            total_loss = total_loss + self.ordering_weight * ordering

        return total_loss


class QuantileLoss(nn.Module):
    """
    Quantile (pinball) loss for asymmetric prediction intervals.

    Instead of predicting point estimates, this loss encourages predictions
    at a specific quantile. For example, quantile=0.8 means the prediction
    should be greater than actual 80% of the time.

    This is another way to achieve conservative predictions that favor
    overestimation (predicting later arrival times).
    """

    def __init__(self, quantile: float = 0.8, ordering_weight: float = 0.1):
        """
        Args:
            quantile: Target quantile (0.5 = median, 0.8 = 80th percentile)
            ordering_weight: Weight for ordering constraint
        """
        super().__init__()
        if not 0 < quantile < 1:
            raise ValueError("quantile must be in (0, 1)")
        self.quantile = quantile
        self.ordering_weight = ordering_weight

    def forward(
        self,
        predictions: torch.Tensor,
        actuals: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute quantile loss.

        Args:
            predictions: Predicted ETAs
            actuals: Actual ETAs

        Returns:
            Scalar loss value
        """
        errors = actuals - predictions  # Note: reversed from MSE

        # Pinball loss
        loss = torch.where(
            errors >= 0,
            self.quantile * errors,
            (self.quantile - 1) * errors
        )

        total_loss = loss.mean()

        # Ordering constraint
        if predictions.dim() == 2 and predictions.shape[1] >= 2:
            for i in range(predictions.shape[1] - 1):
                violation = torch.relu(predictions[:, i] - predictions[:, i + 1])
                total_loss = total_loss + self.ordering_weight * violation.mean()

        return total_loss


class MultiQuantileLoss(nn.Module):
    """
    Multi-quantile (pinball) loss for training quantile regression models.

    This loss trains the model to predict at specific quantiles (e.g., P50, P80).
    For each quantile q:
    - If actual > predicted: penalize by q * error
    - If actual < predicted: penalize by (1-q) * error

    This results in:
    - q=0.5: Symmetric loss (median)
    - q=0.8: Asymmetric, model learns to predict 80th percentile

    Combined with ETAPredictorQuantile, this enables the app to show:
    - P50 as "expected" arrival time
    - P80 as "arrive by" time for trip planning

    Args:
        quantiles: Tuple of quantiles to predict (default: (0.5, 0.8))
        ordering_weight: Weight for ordering constraint (default: 0.1)
    """

    def __init__(
        self,
        quantiles: tuple = (0.5, 0.8),
        ordering_weight: float = 0.1
    ):
        super().__init__()
        self.quantiles = quantiles
        self.ordering_weight = ordering_weight

    def forward(
        self,
        predictions: torch.Tensor,
        actuals: torch.Tensor
    ) -> torch.Tensor:
        """
        Compute multi-quantile loss.

        Args:
            predictions: Shape (batch, num_stops, num_quantiles)
            actuals: Shape (batch, num_stops)

        Returns:
            Scalar loss value
        """
        total_loss = torch.tensor(0.0, device=predictions.device)
        n_quantiles = len(self.quantiles)

        for q_idx, q in enumerate(self.quantiles):
            # Get predictions for this quantile
            preds = predictions[:, :, q_idx]

            # Pinball loss
            errors = actuals - preds
            loss = torch.where(
                errors >= 0,
                q * errors,
                (q - 1) * errors
            )
            total_loss = total_loss + loss.mean()

        # Normalize by number of quantiles
        total_loss = total_loss / n_quantiles

        # Add ordering constraint within each stop (P50 < P80)
        for i in range(predictions.shape[1]):  # For each stop
            for q_idx in range(n_quantiles - 1):
                # Penalize when lower quantile > higher quantile
                violation = torch.relu(
                    predictions[:, i, q_idx] - predictions[:, i, q_idx + 1]
                )
                total_loss = total_loss + self.ordering_weight * violation.mean()

        # Add ordering constraint across stops (ETA_1 < ETA_2 < ETA_3)
        for i in range(predictions.shape[1] - 1):
            for q_idx in range(n_quantiles):
                violation = torch.relu(
                    predictions[:, i, q_idx] - predictions[:, i + 1, q_idx]
                )
                total_loss = total_loss + self.ordering_weight * violation.mean()

        return total_loss


class LogSpaceAsymmetricLoss(nn.Module):
    """
    Asymmetric loss operating in log-space for improved long-ETA accuracy.

    When training on log1p(eta_seconds), this loss function operates in
    log-space where errors on long ETAs (300-900s) contribute more equally
    to the loss compared to short ETAs.

    This addresses the common underestimation bias on long ETAs where
    MSE naturally weights short ETAs more heavily (since their absolute
    error magnitudes are smaller).

    Args:
        overestimate_penalty: How many times worse overestimation is (default: 5.0)
        ordering_weight: Weight for ETA ordering constraint (default: 0.1)
    """

    def __init__(
        self,
        overestimate_penalty: float = 5.0,
        ordering_weight: float = 0.1
    ):
        super().__init__()
        if overestimate_penalty < 1.0:
            raise ValueError("overestimate_penalty must be >= 1.0")

        self.alpha = overestimate_penalty - 1.0
        self.ordering_weight = ordering_weight

    def forward(
        self,
        predictions: torch.Tensor,
        targets: torch.Tensor,
        mask: torch.Tensor = None
    ) -> torch.Tensor:
        """
        Compute the log-space asymmetric loss.

        Args:
            predictions: Predicted log1p(ETAs), shape (batch, num_stops) or (batch,)
            targets: Target log1p(ETAs), shape same as predictions
            mask: Optional mask for valid predictions

        Returns:
            Scalar loss value
        """
        # Both predictions and targets are in log1p space
        errors = predictions - targets
        abs_errors = errors.abs()

        # Base loss (MSE in log space)
        base_loss = errors ** 2

        # Asymmetric penalty for overestimation (predicted > actual in log space)
        overestimate_penalty = torch.relu(errors) ** 2

        # Apply mask if provided
        if mask is not None:
            base_loss = base_loss * mask
            overestimate_penalty = overestimate_penalty * mask
            n_valid = mask.sum()
            if n_valid > 0:
                base_mean = base_loss.sum() / n_valid
                penalty_mean = overestimate_penalty.sum() / n_valid
            else:
                base_mean = base_loss.mean()
                penalty_mean = overestimate_penalty.mean()
        else:
            base_mean = base_loss.mean()
            penalty_mean = overestimate_penalty.mean()

        total_loss = base_mean + self.alpha * penalty_mean

        # Add ordering constraint for multi-stop predictions
        if predictions.dim() == 2 and predictions.shape[1] >= 2:
            ordering_penalty = 0.0
            for i in range(predictions.shape[1] - 1):
                # In log space, ordering still applies: log(ETA_1) < log(ETA_2)
                violation = torch.relu(predictions[:, i] - predictions[:, i + 1])
                ordering_penalty = ordering_penalty + violation.mean()
            total_loss = total_loss + self.ordering_weight * ordering_penalty

        return total_loss


def create_loss_function(
    loss_type: str = 'asymmetric',
    **kwargs
) -> nn.Module:
    """
    Factory function to create loss functions.

    Args:
        loss_type: One of 'asymmetric', 'log_asymmetric', 'multi_quantile', 'weighted', 'quantile', 'mse'
        **kwargs: Additional arguments passed to loss constructor

    Returns:
        Loss function module

    Example:
        # Standard asymmetric loss (for raw ETA values in seconds)
        loss_fn = create_loss_function('asymmetric', overestimate_penalty=5.0)

        # Log-space asymmetric loss (for log1p-transformed ETA values)
        loss_fn = create_loss_function('log_asymmetric', overestimate_penalty=7.0)

        # Multi-quantile loss (for ETAPredictorQuantile model)
        loss_fn = create_loss_function('multi_quantile', quantiles=(0.5, 0.8))
    """
    if loss_type == 'asymmetric':
        return AsymmetricETALoss(**kwargs)
    elif loss_type == 'log_asymmetric':
        return LogSpaceAsymmetricLoss(**kwargs)
    elif loss_type == 'multi_quantile':
        return MultiQuantileLoss(**kwargs)
    elif loss_type == 'weighted':
        return WeightedAsymmetricLoss(**kwargs)
    elif loss_type == 'quantile':
        return QuantileLoss(**kwargs)
    elif loss_type == 'mse':
        return nn.MSELoss()
    else:
        raise ValueError(f"Unknown loss type: {loss_type}")


if __name__ == '__main__':
    # Test the loss functions
    torch.manual_seed(42)

    # Create sample data
    batch_size = 32
    num_stops = 3

    # Predictions and actuals in seconds
    predictions = torch.randn(batch_size, num_stops) * 60 + 300  # ~5 min ± 1 min
    actuals = torch.randn(batch_size, num_stops) * 60 + 300

    print("Testing AsymmetricETALoss:")
    loss_fn = AsymmetricETALoss(overestimate_penalty=5.0)
    loss = loss_fn(predictions, actuals)
    print(f"  Loss: {loss.item():.4f}")

    # Compare with MSE
    mse_loss = nn.MSELoss()(predictions, actuals)
    print(f"  MSE Loss: {mse_loss.item():.4f}")
    print(f"  Ratio: {loss.item() / mse_loss.item():.2f}x")

    # Test with scenarios
    print("\nScenario testing:")

    # Overestimate scenario: predicted > actual (bus arrives early)
    pred_over = torch.tensor([[300.0, 400.0, 500.0]])  # Predicted 5, 6.7, 8.3 min
    actual_over = torch.tensor([[200.0, 300.0, 400.0]])  # Actual 3.3, 5, 6.7 min
    loss_over = loss_fn(pred_over, actual_over)
    print(f"  Overestimate (bad): {loss_over.item():.4f}")

    # Underestimate scenario: predicted < actual (bus arrives late)
    pred_under = torch.tensor([[200.0, 300.0, 400.0]])  # Predicted 3.3, 5, 6.7 min
    actual_under = torch.tensor([[300.0, 400.0, 500.0]])  # Actual 5, 6.7, 8.3 min
    loss_under = loss_fn(pred_under, actual_under)
    print(f"  Underestimate (less bad): {loss_under.item():.4f}")

    print(f"  Overestimate is {loss_over.item() / loss_under.item():.1f}x worse (target: ~5x)")
