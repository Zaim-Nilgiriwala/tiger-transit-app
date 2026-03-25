# Architecture

**Analysis Date:** 2026-03-25

## Pattern Overview

**Overall:** Multi-pipeline ML training system with a separate inference API

The project is a Tiger Transit (Auburn University bus system) ETA prediction system. It contains two parallel development tracks:
1. A PyTorch neural-network approach (`ETA-Model/`) — an earlier, more exploratory track
2. An XGBoost gradient-boosted tree approach (`scripts/`) — the primary active development track, organized as a sequential ETL + train + evaluate pipeline

Both tracks share the same raw data sources and target the same prediction task (time-to-arrival in seconds). The XGBoost track is the current focus per `.planning/phases/` structure.

A Supabase PostgreSQL backend (`supabase/`) stores GTFS-RT live vehicle data intended for a mobile app.

**Key Characteristics:**
- No single entrypoint; each script is a standalone CLI stage run in sequence
- Data flows through disk (parquet files in `data/processed/`) between pipeline stages
- All ML training is offline; inference is served via a FastAPI server (`ETA-Model/api/server.py`)
- GTFS static schedule data is used across both tracks for stop/route geometry
- Raw telemetry collected from ETA SPOT IRM API via Socket.IO replay (`ETA-Model/batchCollector.js`)

## Layers

**Raw Data Ingestion:**
- Purpose: Pull historical GPS telemetry from ETA SPOT's IRM (Instant Replay Manager) and arrivals CSVs from the transit agency
- Location: `ETA-Model/batchCollector.js` (telemetry), `scripts/parse_telemetry.py`, `scripts/parse_arrivals.py`
- Contains: Socket.IO client connecting to `https://auburn.etaspot.com`; CSV parsing utilities
- Output: `ETA-Model/raw_data/*.jsonl.gz` (compressed JSONL), `data/processed/telemetry.parquet`, `data/processed/arrivals.parquet`

**Data Transformation / Feature Engineering:**
- Purpose: Convert raw position pings and schedule data into ML-ready feature rows with ground truth labels
- Location: `scripts/` (XGBoost track), `ETA-Model/data_prep/` (older GBDT pipeline), `ETA-Model/src/preprocess.py` (PyTorch track)
- Contains: Row explosion (one row per vehicle × upcoming stop), label joining via `merge_asof`, feature computation, train/val/test temporal splits
- Key scripts in order:
  1. `scripts/build_stop_sequences.py` → `data/processed/stop_sequences.parquet`
  2. `scripts/parse_telemetry.py` → `data/processed/telemetry.parquet`
  3. `scripts/parse_arrivals.py` → `data/processed/arrivals.parquet`
  4. `scripts/explode_rows.py` → `data/processed/exploded.parquet`
  5. `scripts/label_join.py` → `data/processed/labeled.parquet`
  6. `scripts/temporal_split.py` → `data/processed/{train,val,test}.parquet`
  7. `scripts/build_features.py` → `data/processed/{train,val,test}_featured.parquet`
  8. `scripts/build_baselines.py` → augments splits with `baseline_eta`, `residual` columns
  9. `scripts/build_differentiator_features.py` → `data/processed/{train,val,test}_featured_v2.parquet`

**Model Training:**
- Purpose: Train XGBoost or PyTorch models on processed feature data
- Location: `scripts/train_baseline.py`, `scripts/train_differentiator.py`, `scripts/train_advanced.py`, `ETA-Model/src/train.py`
- Contains: XGBoost DMatrix creation, Optuna hyperparameter tuning, early stopping, model serialization
- Output: `models/baseline_v1.ubj`, `models/differentiator_v1.ubj`, `models/v1_1_residual.ubj`

**Model Evaluation:**
- Purpose: Compute metrics sliced by route, time-of-day, stops-away; produce SHAP explainability plots
- Location: `scripts/evaluate.py`, `scripts/eval_baseline.py`, `scripts/eval_prorated.py`, `scripts/evaluate_v1_1.py`
- Output: `models/evaluation/`, `reports/v1_1_evaluation.html`

**Inference API:**
- Purpose: Serve real-time ETA predictions from trained PyTorch models
- Location: `ETA-Model/api/server.py`
- Contains: FastAPI app with CORS middleware; loads per-route models at startup; `/api/eta/predict` POST endpoint
- Depends on: `ETA-Model/src/model.py`, `ETA-Model/src/preprocess.py`, `ETA-Model/config/routes.json`

**Live Data Backend (Supabase):**
- Purpose: Store GTFS-RT position updates and GTFS static schedule data for mobile app consumption
- Location: `supabase/`
- Contains: PostgreSQL schemas (`gtfs`, `position_updates`, `trip_updates`); migration SQL files
- Reference for ingestion logic: `Code/etaspot_reference.ts`

## Data Flow

**XGBoost Training Pipeline (Primary):**

1. `ETA-Model/batchCollector.js` replays historical data from ETA SPOT IRM API → writes `ETA-Model/raw_data/*.jsonl.gz`
2. `scripts/parse_telemetry.py` reads JSONL files from `mobile/src/ETA-Model/raw_data/`, normalizes column names, filters excluded routes → writes `data/processed/telemetry.parquet`
3. `scripts/parse_arrivals.py` reads arrivals CSVs, joins with `stops.json` and `gtfs_data/routes.txt` for ID mapping → writes `data/processed/arrivals.parquet`
4. `scripts/explode_rows.py` downsamples to ~60s intervals, explodes rows (one per vehicle × upcoming stop, up to 8 stops ahead) → writes `data/processed/exploded.parquet`
5. `scripts/label_join.py` `merge_asof` joins exploded rows with actual arrivals (2h tolerance) → computes `time_to_arrival_seconds` ground truth → writes `data/processed/labeled.parquet`
6. `scripts/temporal_split.py` splits by calendar date (Train: Nov 6 – Nov 29, Val: Dec 1 – Dec 6, Test: Dec 8 – Dec 18, gaps discarded) → writes `data/processed/{train,val,test}.parquet`
7. `scripts/build_baselines.py` computes historical stop-to-stop averages and 4D tiered fallback baseline ETAs → augments split parquets with `baseline_eta` and `residual` columns
8. `scripts/build_differentiator_features.py` adds GPS-derived rolling speed features, historical segment/dwell aggregates, timepoint adherence → writes `*_featured_v2.parquet`
9. `scripts/train_advanced.py` trains XGBoost on residuals (actual - baseline_eta) using Optuna tuning → saves `models/v1_1_residual.ubj`
10. `scripts/evaluate.py` evaluates model on test set with sliced metrics and SHAP plots → writes `models/evaluation/`

**PyTorch Inference Flow:**

1. `ETA-Model/api/server.py` receives POST `/api/eta/predict` with vehicle position + next 3 stop IDs
2. `ETA-Model/src/preprocess.py:extract_features_for_prediction()` extracts and normalizes features
3. Per-route `ETAPredictor` model forward pass returns ETA seconds for 3 stops
4. Response formatted as `PredictionResponse` with `StopPrediction` objects

**State Management:**
- No runtime state between pipeline stages; all intermediate data written to parquet on disk
- API server holds loaded models and normalization params in module-level dicts (`models`, `norm_params`, `stops`, `routes_config`)

## Key Abstractions

**ETAPredictor / MultiStopETAPredictor:**
- Purpose: PyTorch neural network predicting ETAs for next N stops simultaneously
- Examples: `ETA-Model/src/model.py`
- Pattern: Vehicle embedding + shared encoder (Dense → BatchNorm → Dropout) + per-stop prediction heads. Variants: `ETAPredictorWithUncertainty`, `ETAPredictorQuantile`, `LightweightETAPredictor`. Factory via `create_model()`, serialized via `save_model()`/`load_model()`.

**NormalizationParams:**
- Purpose: Per-route feature normalization stored alongside model checkpoints
- Examples: `ETA-Model/src/preprocess.py`
- Pattern: Dataclass with `to_dict()`/`from_dict()` serialization; JSON files at `ETA-Model/config/norm_route_{id}.json`

**AsymmetricETALoss:**
- Purpose: 5x penalty for overestimation (bus arrives earlier than predicted = rider misses bus)
- Examples: `ETA-Model/src/loss.py`
- Pattern: Custom `nn.Module` wrapping MSE with asymmetric weighting + ordering constraint (ETA_1 < ETA_2 < ETA_3)

**Data Preparation Pipeline (GBDT track):**
- Purpose: Modular, importable pipeline for the older GBDT-focused data prep
- Examples: `ETA-Model/data_prep/pipeline.py` orchestrates `filters.py`, `rolling_features.py`, `distance_features.py`, `temporal_features.py`, `weather_features.py`, `historical_stats.py`, `label_creator.py`
- Pattern: Each submodule has a single public function (`compute_*`, `load_*`, `join_*`)

**FEATURE_COLS / FEATURE_COLS_V2:**
- Purpose: Canonical feature lists imported by train, evaluate, and build scripts
- Examples: `scripts/build_features.py` (15 features v1), `scripts/build_differentiator_features.py` (43 features v2)
- Pattern: Module-level constants; scripts import them to ensure training and inference use identical feature sets

## Entry Points

**Data Collection:**
- Location: `ETA-Model/batchCollector.js`
- Triggers: Manual execution; `CONFIG` block at top of file sets date range
- Responsibilities: Socket.IO connection to ETA SPOT IRM; replays historical vehicle positions at configurable speed; writes compressed JSONL per day

**XGBoost Pipeline Stage Scripts:**
- Location: `scripts/*.py` — each is a standalone CLI script
- Triggers: Manual sequential execution following pipeline order
- Responsibilities: Each script reads from `data/processed/` and writes back to `data/processed/` or `models/`

**PyTorch Training:**
- Location: `ETA-Model/src/train.py`
- Triggers: `python src/train.py --data-dir ./processed_data --output-dir ./models`
- Responsibilities: Loads processed `.npy` arrays, builds DataLoaders, runs training loop with early stopping and LR scheduling, saves `.pt` checkpoint

**Inference API:**
- Location: `ETA-Model/api/server.py`
- Triggers: `uvicorn api.server:app --host 0.0.0.0 --port 8000`
- Responsibilities: Loads all route models at startup from `ETA-Model/config/routes.json`; serves predictions; supports hot-reload via `/api/models/reload`

**Supabase Migrations:**
- Location: `supabase/migrations/*.sql`
- Triggers: `supabase db push` or `supabase migration up`
- Responsibilities: Schema creation for `gtfs`, `position_updates`, `trip_updates` schemas

## Error Handling

**Strategy:** Script-level; errors propagate as Python exceptions and halt the pipeline stage. No cross-stage recovery.

**Patterns:**
- FastAPI endpoints raise `HTTPException` with 404/400 status codes for missing models or unknown stops
- Training scripts print warnings and continue when optional files (e.g., normalization params) are missing
- `batchCollector.js` has a per-day safety timeout (`maxTimeout: 4200000ms`) to prevent hangs
- Quality threshold checks in `ETA-Model/data_prep/data_quality.py` log violations but do not halt by default

## Cross-Cutting Concerns

**Logging:** `print()` statements throughout pipeline scripts; no structured logging framework
**Validation:** Data quality checks in `ETA-Model/data_prep/data_quality.py`; `QUALITY_THRESHOLDS` constants in `ETA-Model/data_prep/config.py`; geographic bounding box filter for Auburn, AL (lat 32.5–32.7, lon -85.6 to -85.4)
**Authentication:** ETA SPOT IRM access uses a hardcoded session cookie in `ETA-Model/batchCollector.js`; Supabase anonymous role granted usage on `position_updates` schema

---

*Architecture analysis: 2026-03-25*
