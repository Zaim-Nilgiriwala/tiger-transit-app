"""
FastAPI Server for ETA Prediction

Endpoints:
    POST /api/eta/predict - Predict ETAs for next 3 stops
    POST /api/models/reload - Hot-reload models
    GET /api/routes - List available routes
    GET /api/health - Health check

Usage:
    uvicorn api.server:app --host 0.0.0.0 --port 8000
"""

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Literal, Optional

import torch
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Add paths for imports
BASE_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BASE_DIR / 'src'))

from model import MultiStopETAPredictor, load_model
from preprocess import (
    extract_features_for_prediction,
    load_stops,
    load_normalization_params,
    NormalizationParams,
    NUM_FEATURES,
)

# Configuration
MODELS_DIR = BASE_DIR / 'models'
CONFIG_DIR = BASE_DIR / 'config'
STOPS_FILE = BASE_DIR / 'stops.json'

# Initialize FastAPI app
app = FastAPI(
    title="Tiger Transit ETA Prediction API",
    description="Per-route neural network models for predicting bus ETAs",
    version="1.0.0",
)

# Enable CORS for mobile app
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state
models: dict[int, MultiStopETAPredictor] = {}
norm_params: dict[int, NormalizationParams] = {}
stops: dict = {}
routes_config: dict = {}


# Request/Response models
class PredictionRequest(BaseModel):
    routeId: int = Field(..., description="Route ID")
    lat: float = Field(..., description="Bus latitude")
    lon: float = Field(..., description="Bus longitude")
    heading: float = Field(..., ge=0, le=360, description="Bus heading (0-360)")
    speed: float = Field(..., ge=0, description="Bus speed")
    load: int = Field(0, ge=0, description="Passenger count")
    progress: float = Field(0.0, ge=0, le=1, description="Route progress (0-1)")
    timestamp: Optional[int] = Field(None, description="Timestamp in ms (defaults to now)")
    nextStopIds: list[str] = Field(..., min_length=3, max_length=3, description="Next 3 stop IDs")


class StopPrediction(BaseModel):
    stopId: str
    etaSeconds: int
    etaMinutes: float


class PredictionResponse(BaseModel):
    routeId: int
    vehiclePosition: dict
    predictions: list[StopPrediction]
    modelVersion: str
    timestamp: int


class RouteInfo(BaseModel):
    id: int
    name: str
    modelFile: str
    lastTrained: str
    isLoaded: bool


class HealthResponse(BaseModel):
    status: str
    modelsLoaded: int
    stopsLoaded: int
    timestamp: str


# Startup event
@app.on_event("startup")
async def startup_event():
    """Load models and configuration on startup."""
    global models, norm_params, stops, routes_config

    print("Loading ETA prediction models...")

    # Load stops
    if STOPS_FILE.exists():
        stops = load_stops(str(STOPS_FILE))
        print(f"Loaded {len(stops)} stops")
    else:
        print(f"WARNING: Stops file not found at {STOPS_FILE}")

    # Load routes config
    routes_config_path = CONFIG_DIR / 'routes.json'
    if routes_config_path.exists():
        with open(routes_config_path, 'r') as f:
            routes_config = json.load(f)
        print(f"Loaded routes config with {len(routes_config.get('routes', []))} routes")
    else:
        routes_config = {'routes': [], 'defaultModel': 'fallback.pt'}
        print("No routes config found, starting with empty registry")

    # Load models
    for route in routes_config.get('routes', []):
        route_id = route['id']
        model_file = route.get('modelFile', f'route_{route_id}.pt')
        model_path = MODELS_DIR / model_file

        if model_path.exists():
            try:
                models[route_id] = load_model(str(model_path), NUM_FEATURES)
                print(f"  Loaded model for route {route_id}")

                # Load normalization params
                norm_path = CONFIG_DIR / f'norm_route_{route_id}.json'
                if norm_path.exists():
                    norm_params[route_id] = load_normalization_params(str(norm_path))
            except Exception as e:
                print(f"  ERROR loading route {route_id}: {e}")
        else:
            print(f"  WARNING: Model file not found for route {route_id}: {model_path}")

    print(f"Startup complete. {len(models)} models loaded.")


# Endpoints
@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(
        status="healthy",
        modelsLoaded=len(models),
        stopsLoaded=len(stops),
        timestamp=datetime.now().isoformat(),
    )


@app.get("/api/routes", response_model=list[RouteInfo])
async def list_routes():
    """List all available routes and their model status."""
    result = []
    for route in routes_config.get('routes', []):
        result.append(RouteInfo(
            id=route['id'],
            name=route.get('name', f"Route {route['id']}"),
            modelFile=route.get('modelFile', f"route_{route['id']}.pt"),
            lastTrained=route.get('lastTrained', 'unknown'),
            isLoaded=route['id'] in models,
        ))
    return result


@app.post("/api/eta/predict", response_model=PredictionResponse)
async def predict_eta(request: PredictionRequest):
    """
    Predict ETAs for the next 3 stops on a route.

    The model predicts how many seconds until the bus arrives at each
    of the next 3 stops, based on current position, heading, speed, etc.
    """
    route_id = request.routeId

    # Check if model is available
    if route_id not in models:
        available = list(models.keys())
        raise HTTPException(
            status_code=404,
            detail=f"No model available for route {route_id}. Available routes: {available}"
        )

    # Validate stop IDs
    stop_coords = []
    for stop_id in request.nextStopIds:
        if stop_id not in stops:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown stop ID: {stop_id}"
            )
        stop_coords.append((stops[stop_id][0], stops[stop_id][1]))

    # Get timestamp
    timestamp = request.timestamp or int(datetime.now().timestamp() * 1000)

    # Extract features
    route_norm = norm_params.get(route_id)
    features = extract_features_for_prediction(
        lat=request.lat,
        lon=request.lon,
        heading=request.heading,
        speed=request.speed,
        load=request.load,
        progress=request.progress,
        timestamp_ms=timestamp,
        next_stop_coords=stop_coords,
        norm_params=route_norm,
    )

    # Make prediction
    model = models[route_id]
    model.eval()

    with torch.no_grad():
        input_tensor = torch.FloatTensor(features).unsqueeze(0)
        predictions = model(input_tensor)

    # Format response
    stop_predictions = []
    for i, stop_id in enumerate(request.nextStopIds):
        eta_seconds = max(0, int(predictions[0, i].item()))
        stop_predictions.append(StopPrediction(
            stopId=stop_id,
            etaSeconds=eta_seconds,
            etaMinutes=round(eta_seconds / 60.0, 1),
        ))

    return PredictionResponse(
        routeId=route_id,
        vehiclePosition={'lat': request.lat, 'lon': request.lon},
        predictions=stop_predictions,
        modelVersion=routes_config.get('modelVersion', '1.0.0'),
        timestamp=timestamp,
    )


# ─── Batch ETA Prediction (Phase 4+ scaffold) ─────────────────────────


class VehicleInput(BaseModel):
    """Single vehicle position for batch prediction."""
    vehicleId: str = Field(..., description="Vehicle identifier")
    lat: float = Field(..., description="Vehicle latitude")
    lon: float = Field(..., description="Vehicle longitude")
    heading: float = Field(..., ge=0, le=360, description="Vehicle heading (0-360)")
    speed: float = Field(..., ge=0, description="Vehicle speed")


class BatchPredictionRequest(BaseModel):
    """Request body for batch route ETA prediction."""
    routeId: str = Field(..., description="Route ID")
    vehicles: list[VehicleInput] = Field(..., description="Active vehicles on this route")


class StopArrival(BaseModel):
    """Predicted arrival of a specific vehicle at a stop."""
    vehicleId: str
    etaSeconds: int


class StopPredictionBatch(BaseModel):
    """ETA predictions for a single stop across all vehicles."""
    stopId: str
    arrivals: list[StopArrival]


class BatchPredictionResponse(BaseModel):
    """Response body for batch route ETA prediction."""
    routeId: str
    stopPredictions: list[StopPredictionBatch]
    source: Literal["model", "stub"]
    timestamp: int


@app.post("/api/eta/predict-route", response_model=BatchPredictionResponse)
async def predict_route(request: BatchPredictionRequest):
    """
    Batch ETA prediction for all stops on a route.

    Scaffold endpoint for Phase 4+ model integration. Currently returns stub
    responses with empty arrival arrays. When trained per-route models are
    deployed, this endpoint will compute ETAs for every vehicle-stop pair on
    the requested route.

    Request:
        routeId - Route identifier (e.g. "24")
        vehicles - List of active vehicle positions on this route

    Response:
        stopPredictions - For each stop on the route, predicted arrivals
        source - "stub" until model integration is complete, then "model"
        timestamp - Server timestamp (epoch seconds)
    """
    # Load stop sequence for this route (from GTFS data if available)
    # For now, return stub with route's known stops from config
    route_stops = []
    route_id_int = None
    try:
        route_id_int = int(request.routeId)
    except ValueError:
        pass

    # Build stub stop predictions with empty arrivals
    stop_predictions = [
        StopPredictionBatch(stopId=stop_id, arrivals=[])
        for stop_id in route_stops
    ]

    return BatchPredictionResponse(
        routeId=request.routeId,
        stopPredictions=stop_predictions,
        source="stub",
        timestamp=int(datetime.now().timestamp()),
    )


@app.post("/api/models/reload")
async def reload_models():
    """
    Hot-reload models without server restart.

    Re-reads routes.json and loads any new or updated models.
    """
    global models, norm_params, routes_config

    reloaded = []
    errors = []

    # Reload routes config
    routes_config_path = CONFIG_DIR / 'routes.json'
    if routes_config_path.exists():
        with open(routes_config_path, 'r') as f:
            routes_config = json.load(f)

    # Reload models
    for route in routes_config.get('routes', []):
        route_id = route['id']
        model_file = route.get('modelFile', f'route_{route_id}.pt')
        model_path = MODELS_DIR / model_file

        if model_path.exists():
            try:
                models[route_id] = load_model(str(model_path), NUM_FEATURES)
                reloaded.append(route_id)

                # Reload normalization params
                norm_path = CONFIG_DIR / f'norm_route_{route_id}.json'
                if norm_path.exists():
                    norm_params[route_id] = load_normalization_params(str(norm_path))
            except Exception as e:
                errors.append({'route_id': route_id, 'error': str(e)})

    return {
        'status': 'success',
        'reloaded': reloaded,
        'errors': errors,
        'totalModels': len(models),
    }


@app.get("/api/stops/{stop_id}")
async def get_stop_info(stop_id: str):
    """Get information about a specific stop."""
    if stop_id not in stops:
        raise HTTPException(status_code=404, detail=f"Stop not found: {stop_id}")

    lat, lon, name = stops[stop_id]
    return {
        'id': stop_id,
        'name': name,
        'lat': lat,
        'lon': lon,
    }


# Run with: uvicorn api.server:app --reload --host 0.0.0.0 --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
