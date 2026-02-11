"""
Neural Network Model Architecture for ETA Prediction

This module defines the ETAPredictor model which predicts arrival times
for the next N stops given current bus telemetry and contextual features.

Key architectural decisions:
1. Vehicle embeddings to learn bus-specific patterns
2. Shared encoder for common feature processing
3. Separate prediction heads for each stop
4. BatchNorm and Dropout for regularization
"""

import torch
import torch.nn as nn
from typing import Optional
from pathlib import Path


class ETAPredictor(nn.Module):
    """
    Multi-output neural network for ETA prediction.

    Architecture:
    ```
    Input Features + Vehicle Embedding
              │
              ▼
    ┌─────────────────────────┐
    │    Shared Encoder       │
    │  (Dense → BN → Dropout) │
    └─────────────────────────┘
              │
      ┌───────┼───────┐
      ▼       ▼       ▼
    [Head1] [Head2] [Head3]
      │       │       │
      ▼       ▼       ▼
    ETA_1   ETA_2   ETA_3
    ```

    Args:
        num_features: Number of input features (excluding vehicle ID)
        num_vehicle_ids: Number of unique vehicles for embedding
        vehicle_embed_dim: Dimension of vehicle embedding
        hidden_dims: Tuple of hidden layer dimensions
        num_stops: Number of stops to predict ETAs for
        dropout: Dropout probability
        use_residual: Use residual connections in encoder
    """

    def __init__(
        self,
        num_features: int,
        num_vehicle_ids: int = 100,
        vehicle_embed_dim: int = 8,
        hidden_dims: tuple = (256, 128, 64),
        num_stops: int = 3,
        dropout: float = 0.2,
        use_residual: bool = False
    ):
        super().__init__()

        self.num_features = num_features
        self.num_vehicle_ids = num_vehicle_ids
        self.vehicle_embed_dim = vehicle_embed_dim
        self.hidden_dims = hidden_dims
        self.num_stops = num_stops
        self.use_residual = use_residual

        # Vehicle embedding layer
        self.vehicle_embedding = nn.Embedding(
            num_embeddings=num_vehicle_ids,
            embedding_dim=vehicle_embed_dim
        )

        # Total input dimension
        total_input = num_features + vehicle_embed_dim

        # Build encoder layers
        self.encoder = self._build_encoder(total_input, hidden_dims, dropout)

        # Per-stop prediction heads
        head_hidden = 32
        self.heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(hidden_dims[-1], head_hidden),
                nn.ReLU(),
                nn.Linear(head_hidden, 1)
            )
            for _ in range(num_stops)
        ])

        # Initialize weights
        self._init_weights()

    def _build_encoder(
        self,
        input_dim: int,
        hidden_dims: tuple,
        dropout: float
    ) -> nn.Module:
        """Build the shared encoder network."""
        layers = []
        prev_dim = input_dim

        for i, hidden_dim in enumerate(hidden_dims):
            layers.append(nn.Linear(prev_dim, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.Dropout(dropout))
            prev_dim = hidden_dim

        return nn.Sequential(*layers)

    def _init_weights(self):
        """Initialize model weights using Xavier initialization."""
        for module in self.modules():
            if isinstance(module, nn.Linear):
                nn.init.xavier_uniform_(module.weight)
                if module.bias is not None:
                    nn.init.zeros_(module.bias)
            elif isinstance(module, nn.Embedding):
                nn.init.normal_(module.weight, mean=0.0, std=0.1)

    def forward(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass through the network.

        Args:
            features: Input features, shape (batch, num_features)
            vehicle_ids: Vehicle ID indices, shape (batch,)

        Returns:
            Predicted ETAs, shape (batch, num_stops)
        """
        # Get vehicle embeddings
        vehicle_embed = self.vehicle_embedding(vehicle_ids)

        # Concatenate features with vehicle embedding
        x = torch.cat([features, vehicle_embed], dim=1)

        # Encode
        encoded = self.encoder(x)

        # Predict each stop
        predictions = []
        for head in self.heads:
            pred = head(encoded)
            predictions.append(pred)

        # Stack predictions: (batch, num_stops)
        return torch.cat(predictions, dim=1)

    def predict(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor,
        log_transform: bool = False
    ) -> dict:
        """
        Make predictions with formatted output.

        Args:
            features: Input features
            vehicle_ids: Vehicle ID indices
            log_transform: If True, model outputs are in log1p space and will
                be inverse-transformed using expm1 to get seconds.

        Returns:
            Dictionary with prediction details
        """
        self.eval()
        with torch.no_grad():
            preds = self.forward(features, vehicle_ids)

            # If model was trained on log1p(ETA), inverse transform to seconds
            if log_transform:
                # expm1(x) = exp(x) - 1, inverse of log1p
                preds = torch.expm1(preds)
                # Clamp to reasonable range (0 to 60 minutes)
                preds = torch.clamp(preds, min=0, max=3600)

        return {
            'eta_seconds': preds.cpu().numpy(),
            'eta_minutes': (preds / 60).cpu().numpy(),
        }

    def get_num_parameters(self) -> int:
        """Get total number of trainable parameters."""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)


class ETAPredictorWithUncertainty(ETAPredictor):
    """
    ETA Predictor that also outputs uncertainty estimates.

    In addition to ETA predictions, outputs a variance estimate
    that can be used for confidence intervals.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Additional heads for variance prediction
        head_hidden = 32
        self.variance_heads = nn.ModuleList([
            nn.Sequential(
                nn.Linear(self.hidden_dims[-1], head_hidden),
                nn.ReLU(),
                nn.Linear(head_hidden, 1),
                nn.Softplus()  # Ensure positive variance
            )
            for _ in range(self.num_stops)
        ])

    def forward(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Forward pass returning both mean and variance.

        Returns:
            Tuple of (mean_predictions, variance_predictions)
        """
        # Get vehicle embeddings
        vehicle_embed = self.vehicle_embedding(vehicle_ids)
        x = torch.cat([features, vehicle_embed], dim=1)

        # Encode
        encoded = self.encoder(x)

        # Predict means
        means = []
        for head in self.heads:
            means.append(head(encoded))
        mean_preds = torch.cat(means, dim=1)

        # Predict variances
        variances = []
        for head in self.variance_heads:
            variances.append(head(encoded))
        var_preds = torch.cat(variances, dim=1)

        return mean_preds, var_preds


class ETAPredictorQuantile(ETAPredictor):
    """
    ETA Predictor with quantile outputs (P50 and P80).

    Instead of predicting a single point estimate, this model predicts
    multiple quantiles which allows for:
    - Median (P50) as the central estimate
    - P80 as a "conservative" estimate (bus arrives by this time 80% of the time)

    Display recommendation: Show P60-P70 to users, as riders hate when
    the bus arrives later than predicted more than when it arrives early.
    """

    def __init__(
        self,
        num_features: int,
        num_vehicle_ids: int = 100,
        vehicle_embed_dim: int = 8,
        hidden_dims: tuple = (256, 128, 64),
        num_stops: int = 3,
        dropout: float = 0.2,
        quantiles: tuple = (0.5, 0.8)
    ):
        super().__init__(
            num_features=num_features,
            num_vehicle_ids=num_vehicle_ids,
            vehicle_embed_dim=vehicle_embed_dim,
            hidden_dims=hidden_dims,
            num_stops=num_stops,
            dropout=dropout
        )
        self.quantiles = quantiles
        self.num_quantiles = len(quantiles)

        # Replace single heads with quantile heads
        # Each stop gets one head per quantile
        head_hidden = 32
        self.quantile_heads = nn.ModuleList([
            nn.ModuleList([
                nn.Sequential(
                    nn.Linear(self.hidden_dims[-1], head_hidden),
                    nn.ReLU(),
                    nn.Linear(head_hidden, 1)
                )
                for _ in quantiles
            ])
            for _ in range(num_stops)
        ])

    def forward(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor
    ) -> torch.Tensor:
        """
        Forward pass returning quantile predictions.

        Args:
            features: Input features, shape (batch, num_features)
            vehicle_ids: Vehicle ID indices, shape (batch,)

        Returns:
            Predictions shape (batch, num_stops, num_quantiles)
            - [:, i, 0] = P50 for stop i
            - [:, i, 1] = P80 for stop i
        """
        # Get vehicle embeddings
        vehicle_embed = self.vehicle_embedding(vehicle_ids)
        x = torch.cat([features, vehicle_embed], dim=1)

        # Encode
        encoded = self.encoder(x)

        # Predict each stop, each quantile
        all_stops = []
        for stop_heads in self.quantile_heads:
            stop_quantiles = [head(encoded) for head in stop_heads]
            all_stops.append(torch.cat(stop_quantiles, dim=1))

        # Stack: (batch, num_stops, num_quantiles)
        return torch.stack(all_stops, dim=1)

    def predict(
        self,
        features: torch.Tensor,
        vehicle_ids: torch.Tensor,
        log_transform: bool = False
    ) -> dict:
        """
        Make predictions with formatted output.

        Args:
            features: Input features
            vehicle_ids: Vehicle ID indices
            log_transform: If True, inverse transform from log space

        Returns:
            Dictionary with quantile predictions
        """
        self.eval()
        with torch.no_grad():
            preds = self.forward(features, vehicle_ids)

            if log_transform:
                preds = torch.expm1(preds)
                preds = torch.clamp(preds, min=0, max=3600)

            # Ensure quantile ordering (P50 <= P80)
            for i in range(preds.shape[1]):
                preds[:, i, :] = torch.sort(preds[:, i, :], dim=1).values

        p50 = preds[:, :, 0].cpu().numpy()
        p80 = preds[:, :, 1].cpu().numpy() if preds.shape[2] > 1 else p50

        return {
            'eta_p50_seconds': p50,
            'eta_p80_seconds': p80,
            'eta_p50_minutes': p50 / 60,
            'eta_p80_minutes': p80 / 60,
            # Recommended display value (P60-P70 estimate)
            'eta_display_seconds': 0.5 * p50 + 0.5 * p80,
            'eta_display_minutes': (0.5 * p50 + 0.5 * p80) / 60,
        }


class LightweightETAPredictor(nn.Module):
    """
    Smaller model variant for faster inference or limited data.

    Useful for:
    - Routes with less training data
    - Real-time inference with latency constraints
    - Initial prototyping
    """

    def __init__(
        self,
        num_features: int,
        hidden_dim: int = 64,
        num_stops: int = 3,
        dropout: float = 0.1
    ):
        super().__init__()

        self.encoder = nn.Sequential(
            nn.Linear(num_features, hidden_dim),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(hidden_dim, hidden_dim // 2),
            nn.ReLU(),
        )

        self.output = nn.Linear(hidden_dim // 2, num_stops)

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        """Forward pass (no vehicle embedding)."""
        encoded = self.encoder(features)
        return self.output(encoded)


def create_model(
    num_features: int,
    num_vehicle_ids: int = 100,
    model_type: str = 'standard',
    **kwargs
) -> nn.Module:
    """
    Factory function to create ETA prediction models.

    Args:
        num_features: Number of input features
        num_vehicle_ids: Number of unique vehicles
        model_type: One of 'standard', 'uncertainty', 'lightweight'
        **kwargs: Additional arguments for model constructor

    Returns:
        Initialized model
    """
    if model_type == 'standard':
        return ETAPredictor(num_features, num_vehicle_ids, **kwargs)
    elif model_type == 'uncertainty':
        return ETAPredictorWithUncertainty(num_features, num_vehicle_ids, **kwargs)
    elif model_type == 'lightweight':
        return LightweightETAPredictor(num_features, **kwargs)
    else:
        raise ValueError(f"Unknown model type: {model_type}")


def save_model(
    model: nn.Module,
    path: str,
    metadata: dict = None
):
    """
    Save model checkpoint with metadata.

    Args:
        model: Model to save
        path: Output path
        metadata: Optional dict with training info
    """
    checkpoint = {
        'model_state_dict': model.state_dict(),
        'model_class': model.__class__.__name__,
    }

    # Save model config
    if hasattr(model, 'num_features'):
        checkpoint['num_features'] = model.num_features
    if hasattr(model, 'num_vehicle_ids'):
        checkpoint['num_vehicle_ids'] = model.num_vehicle_ids
    if hasattr(model, 'hidden_dims'):
        checkpoint['hidden_dims'] = model.hidden_dims
    if hasattr(model, 'num_stops'):
        checkpoint['num_stops'] = model.num_stops

    if metadata:
        checkpoint['metadata'] = metadata

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    torch.save(checkpoint, path)


def load_model(
    path: str,
    device: str = 'cpu',
    num_features: int = None,
    num_vehicle_ids: int = None
) -> nn.Module:
    """
    Load model from checkpoint.

    Args:
        path: Path to checkpoint
        device: Device to load to
        num_features: Override num_features (for compatibility)
        num_vehicle_ids: Override num_vehicle_ids

    Returns:
        Loaded model in eval mode
    """
    checkpoint = torch.load(path, map_location=device)

    # Get model config
    nf = num_features or checkpoint.get('num_features', 32)
    nv = num_vehicle_ids or checkpoint.get('num_vehicle_ids', 100)
    hidden_dims = checkpoint.get('hidden_dims', (256, 128, 64))
    num_stops = checkpoint.get('num_stops', 3)

    # Create model
    model_class = checkpoint.get('model_class', 'ETAPredictor')
    if model_class == 'ETAPredictorWithUncertainty':
        model = ETAPredictorWithUncertainty(
            num_features=nf,
            num_vehicle_ids=nv,
            hidden_dims=hidden_dims,
            num_stops=num_stops
        )
    elif model_class == 'LightweightETAPredictor':
        model = LightweightETAPredictor(num_features=nf, num_stops=num_stops)
    else:
        model = ETAPredictor(
            num_features=nf,
            num_vehicle_ids=nv,
            hidden_dims=hidden_dims,
            num_stops=num_stops
        )

    model.load_state_dict(checkpoint['model_state_dict'])
    model.to(device)
    model.eval()

    return model


if __name__ == '__main__':
    # Test the model
    torch.manual_seed(42)

    num_features = 32
    num_vehicle_ids = 50
    batch_size = 16
    num_stops = 3

    # Create model
    model = ETAPredictor(
        num_features=num_features,
        num_vehicle_ids=num_vehicle_ids,
        num_stops=num_stops
    )

    print(f"Model: {model.__class__.__name__}")
    print(f"Parameters: {model.get_num_parameters():,}")

    # Test forward pass
    features = torch.randn(batch_size, num_features)
    vehicle_ids = torch.randint(0, num_vehicle_ids, (batch_size,))

    predictions = model(features, vehicle_ids)
    print(f"\nInput shape: {features.shape}")
    print(f"Output shape: {predictions.shape}")
    print(f"Sample predictions (seconds): {predictions[0].detach().numpy()}")

    # Test save/load
    save_model(model, '/tmp/test_model.pt', {'test': True})
    loaded = load_model('/tmp/test_model.pt')
    print(f"\nModel loaded successfully")

    # Verify same output
    with torch.no_grad():
        orig_out = model(features, vehicle_ids)
        loaded_out = loaded(features, vehicle_ids)
        diff = (orig_out - loaded_out).abs().max()
        print(f"Max difference after load: {diff.item():.6f}")
