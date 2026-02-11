# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a PyTorch-based ETA (Estimated Time of Arrival) prediction system for Tiger Transit buses at Auburn University. The system predicts arrival times for the next 3 stops using neural networks trained on historical GPS telemetry data from ETA SPOT.

## Common Commands

### Training
```bash
# Train a model from processed data
python src/train.py --data-dir ./processed_data_v6 --output-dir ./models --route-id 24

# Train with custom hyperparameters
python src/train.py --data-dir ./processed_data_v6 --output-dir ./models --epochs 100 --batch-size 256 --learning-rate 0.001 --hidden-dims 256 128 64

# Generate training data from raw telemetry, then train
python src/train.py --generate-data --telemetry-dir ./raw_data --gtfs-dir ./gtfs_data --data-dir ./processed_data --output-dir ./models
```

### Evaluation
```bash
# Evaluate a trained model
python src/evaluate.py --model-path ./models/route_24/best_model.pt --data-dir ./processed_data_v6

# Generate markdown report
python src/evaluate.py --model-path ./models/route_24/best_model.pt --data-dir ./processed_data_v6 --report evaluation_report.md
```

### Data Collection
```bash
# Collect historical data from ETA SPOT IRM API
node batchCollector.js
```
Edit `CONFIG` in `batchCollector.js` to set date range, service hours, and playback speed.

### API Server
```bash
# Run prediction API server
uvicorn api.server:app --host 0.0.0.0 --port 8000

# Development mode with auto-reload
uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
```

### Dependencies
```bash
pip install torch numpy pandas scikit-learn pyyaml tqdm
pip install fastapi uvicorn pydantic  # For API server
npm install socket.io-client  # For data collection
```

## Architecture

### Data Pipeline
```
ETA SPOT API → batchCollector.js → raw_data/*.jsonl
                                        ↓
                              src/preprocess.py + src/features.py
                                        ↓
                              processed_data/features.npy, labels.npy
                                        ↓
                              src/train.py → models/route_{id}/best_model.pt
                                        ↓
                              api/server.py → /api/eta/predict
```

### Model Architecture (src/model.py)
- **ETAPredictor**: Multi-output network predicting ETAs for next 3 stops
  - Vehicle embedding layer (learns bus-specific patterns)
  - Shared encoder (Dense → BatchNorm → Dropout)
  - Separate prediction heads for each stop
- **ETAPredictorWithUncertainty**: Adds variance prediction for confidence intervals
- **LightweightETAPredictor**: Smaller variant for real-time inference

### Loss Function (src/loss.py)
- **AsymmetricETALoss**: 5x penalty for overestimation (critical because overestimation = bus arrives earlier than predicted = rider misses bus)
- Includes ordering constraint enforcing ETA_1 < ETA_2 < ETA_3

### Feature Groups (src/features.py)
| Group | Features |
|-------|----------|
| Core | route_distance_stop{1,2,3}, speed, heading (sin/cos), load, progress, delay, scheduled_eta |
| Temporal | time_of_day (cyclical), day_of_week (one-hot), is_rush_hour, is_class_change |
| Historical | segment_time_mean/std, boarding_rates, dwell_time, vehicle_speed_avg |
| Weather | precipitation_mm, is_raining, temperature_c |
| Context | is_game_day, hours_to_kickoff |

### Distance Calculation (src/distance.py)
- Uses GTFS `shape_dist_traveled` for actual road distance along routes
- Falls back to Haversine for straight-line distance when route data unavailable

## Key Files

| File | Purpose |
|------|---------|
| `src/train.py` | Training script with CLI, early stopping, LR scheduling |
| `src/model.py` | Neural network definitions |
| `src/loss.py` | Asymmetric loss penalizing overestimation |
| `src/features.py` | Feature extraction from telemetry |
| `src/dataset.py` | PyTorch Dataset and DataLoader creation |
| `src/preprocess.py` | Raw data preprocessing and normalization |
| `src/evaluate.py` | Model evaluation with comprehensive metrics |
| `src/distance.py` | GTFS-based route distance calculation |
| `api/server.py` | FastAPI prediction endpoint |
| `batchCollector.js` | Historical data collection from ETA SPOT |
| `config/routes.json` | Model registry for route-specific models |
| `stops.json` | Stop coordinates and metadata |
| `gtfs_data/` | GTFS schedule files (shapes, trips, stop_times, etc.) |

## Data Formats

### Raw Telemetry (JSONL)
```json
{"t": 1700000000000, "vid": "jAUnt 1", "lat": 32.605, "lon": -85.485, "heading": 90, "speed": 15, "load": 5, "routeId": 24, "patternId": 1234, "lastStopId": 181, "nextStopId": 152}
```

### Processed Data
- `features.npy`: Shape (n_samples, n_features) - normalized feature vectors
- `labels.npy`: Shape (n_samples, 3) - actual ETAs in seconds for next 3 stops
- `vehicle_ids.npy`: Shape (n_samples,) - integer vehicle IDs for embedding lookup

## Key Design Decisions

1. **Asymmetric Loss**: 5x penalty for overestimation because bus arriving early = rider misses bus (worse than bus arriving late = rider waits)

2. **Multi-stop Prediction**: Predicts next 3 stops simultaneously with ordering constraint

3. **Vehicle Embeddings**: Learns bus-specific patterns (some buses may be consistently slower/faster)

4. **Per-route Models**: Separate model trained for each route to capture route-specific characteristics

5. **Cyclical Time Encoding**: Uses sin/cos encoding for time of day to handle midnight wraparound
