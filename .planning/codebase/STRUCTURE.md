# Codebase Structure

**Analysis Date:** 2026-03-25

## Directory Layout

```
tiger-transit-app/
├── scripts/                  # XGBoost pipeline stage scripts (primary active track)
├── data/
│   └── processed/            # All intermediate and final parquet files
├── gtfs_data/                # GTFS static schedule files (routes, stops, shapes, etc.)
├── models/                   # Trained model artifacts and evaluation outputs
│   ├── evaluation/           # SHAP plots, comparison tables, metrics JSON
│   └── diagnostics/          # Error distribution charts
├── reports/                  # HTML evaluation reports
├── ETA-Model/                # PyTorch neural network track (earlier exploratory work)
│   ├── api/                  # FastAPI inference server
│   ├── src/                  # Core Python ML modules (model, train, preprocess, etc.)
│   ├── data_prep/            # Modular data pipeline package (importable)
│   │   └── output/           # data_prep pipeline parquet outputs
│   ├── config/               # routes.json model registry, training_config.yaml
│   ├── gtfs_data/            # Duplicate GTFS files used by ETA-Model scripts
│   ├── raw_data/             # Raw telemetry JSONL.GZ files (collected by batchCollector)
│   ├── live_data/            # Live CSV data files
│   ├── processed_data_v10/   # PyTorch .npy feature/label arrays (version 10)
│   ├── processed_data_v10_jaunt/
│   ├── processed_data_v11/
│   ├── scripts/              # Standalone validation scripts
│   ├── temporaryFiles/       # Throwaway debug/test scripts (not production)
│   ├── batchCollector.js     # Socket.IO historical data collector
│   ├── processTrainingData.js
│   ├── splitData.js
│   ├── stops.json            # All stop coordinates and metadata
│   ├── CLAUDE.md             # Project overview and key design decisions
│   └── package.json          # Node.js deps (socket.io-client)
├── Code/                     # Reference files preserved from earlier backend
│   ├── etaspot_reference.ts  # Reference implementation for GTFS-RT feed parsing
│   ├── gtfs/                 # Extracted GTFS static files
│   │   └── *.txt
│   ├── gtfs.zip
│   ├── parse_gtfs.py
│   ├── position_update_example.json
│   └── position_updates.jsonl
├── supabase/                 # Supabase local dev configuration
│   ├── migrations/           # SQL migration files (ordered by timestamp prefix)
│   ├── seed.sql
│   └── config.toml
├── .planning/                # GSD planning documents
│   ├── codebase/             # Auto-generated codebase analysis docs
│   ├── milestones/
│   ├── phases/               # Per-phase implementation plans
│   │   ├── 01-data-foundation/
│   │   ├── 02-row-explosion-labels/
│   │   ├── 03-baseline-model/
│   │   ├── 04-differentiator-features/
│   │   ├── 05-advanced-training/
│   │   ├── 06-evaluation-and-analysis/
│   │   ├── 07-baseline-infrastructure/
│   │   ├── 08-training-adaptation/
│   │   └── 09-evaluation-and-comparison/
│   ├── quick/
│   └── research/
├── .claude/                  # Claude project memory
├── analyze_gtfs_fields.py    # Root-level utility script
├── pb file test.py           # Root-level protobuf test script
├── stitch-prompts.md         # Prompt engineering notes
└── assignment2.md            # Assignment notes
```

## Directory Purposes

**`scripts/`:**
- Purpose: All XGBoost pipeline stages run sequentially as standalone scripts
- Contains: One Python script per pipeline step; scripts import shared constants from one another (`from build_features import FEATURE_COLS`)
- Key files:
  - `scripts/parse_telemetry.py` — raw JSONL → `telemetry.parquet`
  - `scripts/parse_arrivals.py` — arrivals CSVs → `arrivals.parquet`
  - `scripts/build_stop_sequences.py` — GTFS stop order per route
  - `scripts/explode_rows.py` — one row per vehicle × upcoming stop
  - `scripts/label_join.py` — `merge_asof` join to produce ground truth
  - `scripts/temporal_split.py` — temporal train/val/test splits
  - `scripts/build_baselines.py` — historical baseline ETAs + residual labels
  - `scripts/build_features.py` — v1 feature set (15 features)
  - `scripts/build_differentiator_features.py` — v2 feature set (43 features)
  - `scripts/train_baseline.py` — XGBoost baseline model
  - `scripts/train_differentiator.py` — XGBoost with v2 features
  - `scripts/train_advanced.py` — residual XGBoost with Optuna tuning
  - `scripts/evaluate.py` — comprehensive evaluation with SHAP

**`data/processed/`:**
- Purpose: All intermediate parquet files between pipeline stages
- Contains: Parquet files produced and consumed by `scripts/` in strict dependency order
- Key files: `telemetry.parquet`, `arrivals.parquet`, `stop_sequences.parquet`, `exploded.parquet`, `labeled.parquet`, `train.parquet`, `val.parquet`, `test.parquet`, `train_featured.parquet`, `train_featured_v2.parquet`, `timepoints.parquet`, `weather.parquet`, `historical_segments.parquet`, `historical_dwells.parquet`

**`gtfs_data/`:**
- Purpose: GTFS static schedule files for the primary `scripts/` pipeline
- Contains: Standard GTFS CSV files: `routes.txt`, `stops.txt`, `trips.txt`, `stop_times.txt`, `shapes.txt`, `calendar.txt`, `calendar_dates.txt`, `agency.txt`, etc.

**`models/`:**
- Purpose: All trained model artifacts and evaluation outputs
- Contains: XGBoost `.ubj` model files, `*_metrics.json` reports, SHAP `.png` charts
- Key files: `baseline_v1.ubj`, `differentiator_v1.ubj`, `tuned_v1.ubj`, `v1_1_residual.ubj`, `models/evaluation/eval_report.md`, `models/diagnostics/baseline_error_dist.png`
- Generated: Yes (not committed)

**`ETA-Model/src/`:**
- Purpose: Core Python modules for the PyTorch track
- Contains: One module per concern; all importable by `api/server.py` and `train.py`
- Key files:
  - `ETA-Model/src/model.py` — `ETAPredictor`, `ETAPredictorWithUncertainty`, `ETAPredictorQuantile`, `LightweightETAPredictor`; `create_model()`, `save_model()`, `load_model()` factory/IO functions
  - `ETA-Model/src/train.py` — `Trainer` class, `EarlyStopping` class, CLI
  - `ETA-Model/src/preprocess.py` — `NormalizationParams` dataclass, `extract_features_for_prediction()`
  - `ETA-Model/src/features.py` — feature group extraction
  - `ETA-Model/src/loss.py` — `AsymmetricETALoss`
  - `ETA-Model/src/dataset.py` — PyTorch `Dataset`, `create_data_loaders()`
  - `ETA-Model/src/evaluate.py` — metrics computation
  - `ETA-Model/src/distance.py` — GTFS route distance + Haversine fallback
  - `ETA-Model/src/inference.py` — batch inference utilities

**`ETA-Model/data_prep/`:**
- Purpose: Modular, importable data pipeline package for the older GBDT-focused ETA-Model track
- Contains: Python package with `__init__.py`; each module has a single public compute function
- Key files: `pipeline.py` (orchestrator), `config.py` (all constants), `filters.py`, `rolling_features.py`, `distance_features.py`, `temporal_features.py`, `weather_features.py`, `historical_stats.py`, `label_creator.py`, `data_quality.py`

**`ETA-Model/api/`:**
- Purpose: FastAPI prediction server
- Contains: `server.py` only — all logic in one file; CORS enabled for `*`
- Endpoints: `GET /api/health`, `GET /api/routes`, `POST /api/eta/predict`, `POST /api/models/reload`, `GET /api/stops/{stop_id}`

**`ETA-Model/config/`:**
- Purpose: Model registry and training configuration
- Contains: `routes.json` (array of `{id, name, modelFile, lastTrained}`), `training_config.yaml`, `vehicle_mapping.json`, per-route normalization params (`norm_route_{id}.json`)

**`ETA-Model/raw_data/`:**
- Purpose: Raw historical telemetry storage from batchCollector
- Contains: `raw_data_YYYY-MM-DD.jsonl.gz` files, one per collection day; also arrivals CSVs
- Generated: Yes (not committed)

**`supabase/migrations/`:**
- Purpose: Database schema versioning via timestamped SQL files
- Contains:
  - `20260319024944_create_schema.sql` — creates `gtfs`, `position_updates`, `trip_updates` schemas
  - `20260319025850_position_updates_table.sql` — `position_updates.position_updates` table
  - `20260323023315_create_gtfs_calendar.sql` — `gtfs.calendar` table
- Naming: `{YYYYMMDDHHMMSS}_{description}.sql`

**`Code/`:**
- Purpose: Reference artifacts preserved from an earlier backend implementation before it was deleted
- Contains: `etaspot_reference.ts` (working GTFS-RT protobuf parsing logic), raw GTFS zip + extracted files, test scripts for protobuf parsing and database pushing
- Note: Not active code; serves as reference when rebuilding the Supabase ingestion service

## Key File Locations

**Entry Points:**
- `ETA-Model/batchCollector.js`: Data collection (Socket.IO to ETA SPOT IRM)
- `ETA-Model/api/server.py`: Inference API server
- `scripts/parse_telemetry.py`: First stage of XGBoost pipeline
- `ETA-Model/src/train.py`: PyTorch model training

**Configuration:**
- `ETA-Model/config/routes.json`: Model registry
- `ETA-Model/data_prep/config.py`: All pipeline constants (feature lists, quality thresholds, split ratios)
- `supabase/config.toml`: Supabase local dev config (project: `Senior_Design`, schemas exposed via API)
- `ETA-Model/CLAUDE.md`: Authoritative architecture and command reference

**Core ML Logic:**
- `ETA-Model/src/model.py`: All PyTorch model classes and factory functions
- `ETA-Model/src/loss.py`: Asymmetric loss function
- `scripts/build_differentiator_features.py`: Feature set v2 constants (`FEATURE_COLS_V2`, `CATEGORICAL_COLS_V2`)
- `scripts/build_features.py`: Feature set v1 constants (`FEATURE_COLS`, `CATEGORICAL_COLS`, `TARGET_COL`)
- `scripts/train_advanced.py`: Current best model training pipeline

**Reference/Documentation:**
- `ETA-Model/CLAUDE.md`: Project overview, data pipeline diagram, key design decisions
- `Code/etaspot_reference.ts`: GTFS-RT feed URLs, data model interface definitions, parsing logic
- `ETA-Model/stops.json`: All stop IDs, names, and coordinates

**Testing:**
- `reports/v1_1_evaluation.html`: Generated evaluation report for current best model

## Naming Conventions

**Files:**
- Pipeline scripts: `verb_noun.py` style (e.g., `parse_telemetry.py`, `build_features.py`, `train_baseline.py`, `label_join.py`)
- Parquet intermediates: `{noun}.parquet` for raw stages, `{split}_featured.parquet` / `{split}_featured_v2.parquet` for feature-enriched splits
- XGBoost models: `{name}_v{N}.ubj`
- PyTorch models: `route_{id}/best_model.pt`
- Supabase migrations: `{timestamp}_{description}.sql`
- JSONL raw data: `raw_data_YYYY-MM-DD.jsonl.gz`

**Python Modules:**
- snake_case for all module names and function names
- Module-level constants in SCREAMING_SNAKE_CASE
- Classes in PascalCase (e.g., `ETAPredictor`, `NormalizationParams`, `EarlyStopping`)

**Directories:**
- Versioned processed data: `processed_data_v{N}/` in `ETA-Model/`
- Evaluation outputs: `models/evaluation/`
- Diagnostic outputs: `models/diagnostics/`

## Where to Add New Code

**New XGBoost pipeline stage:**
- Script: `scripts/{verb}_{noun}.py`
- Reads from: `data/processed/` parquets
- Writes to: `data/processed/` parquets
- Import shared feature constants from: `scripts/build_differentiator_features.py` (v2) or `scripts/build_features.py` (v1)
- Follow existing docstring format: module-level docstring with Input/Output/Usage sections

**New feature column:**
- Add to `FEATURE_COLS_V2` / `CATEGORICAL_COLS_V2` in `scripts/build_differentiator_features.py`
- Compute the column in `build_differentiator_features.py` before the output write
- Update `FEATURE_COLUMNS` in `ETA-Model/data_prep/config.py` if also using the data_prep pipeline

**New Supabase table:**
- Migration file: `supabase/migrations/{timestamp}_{description}.sql`
- Add schema to `schemas` list in `supabase/config.toml` if in a new schema

**New PyTorch model variant:**
- Class: add to `ETA-Model/src/model.py`, subclass `ETAPredictor`
- Register in `create_model()` factory and `load_model()` dispatch in same file
- Add model type string to `ETA-Model/config/routes.json` route entry

**New inference endpoint:**
- Add to `ETA-Model/api/server.py`
- Define Pydantic request/response models at top of file
- Load any new data requirements in `startup_event()`

**Utility / analysis scripts:**
- Exploratory or one-off: place at repo root (e.g., `analyze_gtfs_fields.py`)
- Reusable pipeline utilities: place in `scripts/`
- Debugging / throwaway: place in `ETA-Model/temporaryFiles/` (not production)

## Special Directories

**`ETA-Model/raw_data/`:**
- Purpose: Historical GPS telemetry collected by batchCollector, one file per day
- Generated: Yes
- Committed: No (large binary files, listed in `.gitignore`)

**`ETA-Model/processed_data_v{N}/`:**
- Purpose: Versioned numpy arrays for PyTorch training (`features.npy`, `labels.npy`, `vehicle_ids.npy`, `normalization_stats.json`)
- Generated: Yes (by PyTorch preprocessing pipeline)
- Committed: No

**`data/processed/`:**
- Purpose: All intermediate and final parquet files for XGBoost pipeline
- Generated: Yes (by `scripts/` pipeline)
- Committed: No

**`models/`:**
- Purpose: Trained model artifacts
- Generated: Yes
- Committed: No

**`ETA-Model/temporaryFiles/`:**
- Purpose: Debug, test, and throwaway scripts used during development
- Generated: No (manually created)
- Committed: Historically yes, but considered non-production code

**`.planning/`:**
- Purpose: GSD planning system — phase plans, milestones, codebase analysis docs
- Generated: Partially (by GSD commands)
- Committed: Yes

---

*Structure analysis: 2026-03-25*
