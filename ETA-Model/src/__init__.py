"""
ETA Prediction Model Training Framework

A neural network training framework for predicting bus arrival times at Tiger Transit stops.

Key Components:
- model.py: ETAPredictor neural network architecture
- loss.py: Asymmetric loss function (5x penalty for overestimation)
- features.py: Feature extraction from telemetry data
- distance.py: Route-based distance calculation using GTFS
- dataset.py: PyTorch Dataset classes for training
- train.py: Training CLI script
- evaluate.py: Model evaluation metrics
"""

from .model import ETAPredictor, ETAPredictorWithUncertainty, create_model, load_model, save_model
from .loss import AsymmetricETALoss, create_loss_function
from .features import FeatureExtractor, FeatureConfig
from .distance import GTFSRouteData, DistanceCalculator
from .dataset import ETADataset, create_data_loaders, generate_training_data

__version__ = '1.0.0'
__all__ = [
    'ETAPredictor',
    'ETAPredictorWithUncertainty',
    'create_model',
    'load_model',
    'save_model',
    'AsymmetricETALoss',
    'create_loss_function',
    'FeatureExtractor',
    'FeatureConfig',
    'GTFSRouteData',
    'DistanceCalculator',
    'ETADataset',
    'create_data_loaders',
    'generate_training_data',
]
