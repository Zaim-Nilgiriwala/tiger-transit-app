# Technology Stack

**Analysis Date:** 2026-03-25

## Languages

**Primary:**
- Python 3.10+ - ML pipeline, data processing scripts, API server
- TypeScript - GTFS-RT protobuf ingestion service reference (`Code/etaspot_reference.ts`), weather data fetcher (`ETA-Model/getWeatherData.ts`)
- JavaScript (ESM) - Historical data collection scripts (`ETA-Model/batchCollector.js`, `ETA-Model/processTrainingData.js`, `ETA-Model/splitData.js`)
- SQL - Supabase database schema and migrations (`supabase/migrations/`)

**Secondary:**
- YAML - Model training configuration (`ETA-Model/config/training_config.yaml`)

## Runtime

**Environment:**
- Node.js (ESM modules) - for data collection scripts; `"type": "module"` in `ETA-Model/package.json`
- Python 3.10 (confirmed by `__pycache__` filenames using cpython-310)
- Deno 2 - Supabase Edge Runtime (`supabase/config.toml` sets `deno_version = 2`)

**Package Manager:**
- npm - for Node.js dependencies; lockfile present at `ETA-Model/package-lock.json`
- pip - for Python dependencies; requirements at `ETA-Model/temporaryFiles/requirements.txt`

## Frameworks

**API Server (ETA Model):**
- FastAPI - REST prediction endpoints; `ETA-Model/api/server.py`
- Uvicorn - ASGI server; `uvicorn api.server:app --host 0.0.0.0 --port 8000`

**ML Training:**
- PyTorch `>=2.0.0` - Neural network ETA model (`ETA-Model/src/model.py`, `ETA-Model/src/train.py`)
- XGBoost - Gradient boosting baseline and residual models (`scripts/train_baseline.py`, `scripts/train_advanced.py`)
- Optuna - Hyperparameter tuning with SQLite persistence (`scripts/train_advanced.py`, `scripts/run_optuna_batches.py`)
- scikit-learn - TimeSeriesSplit CV, preprocessing (`scripts/train_advanced.py`)

**Database:**
- Supabase (PostgreSQL 17) - Transit data storage; local dev at port 54321

**Build/Dev:**
- None detected - no Webpack, Vite, or similar bundler

## Key Dependencies

**Critical (Python ML):**
- `torch>=2.0.0` - Neural network training; GPU support via CUDA 11.8 or 12.1
- `xgboost` - Primary production model for ETA prediction
- `optuna` - Hyperparameter search using SQLite storage at `models/optuna_study.db`
- `numpy>=1.24.0` - Feature vectors; `.npy` binary arrays for training data
- `pandas>=2.0.0` - Data pipeline throughout; parquet I/O
- `scikit-learn>=1.3.0` - Cross-validation
- `scipy` - Statistical analysis in evaluation scripts (`scripts/evaluate_v1_1.py`)
- `matplotlib` - Training plots, SHAP summary charts
- `pyyaml>=6.0` - Training config parsing
- `tqdm>=4.65.0` - Training progress bars
- `pyarrow` - Parquet read/write (`scripts/explode_rows.py` uses `pyarrow.parquet`)
- `supabase` (Python client) - Database writes in `Code/pushing_data_to_db_test.py`
- `google-transit` / `gtfs-realtime-pb2` - Protobuf parsing in `Code/simplepbtest.py`
- `fastapi`, `uvicorn`, `pydantic` - API server in `ETA-Model/api/server.py`

**Critical (Node.js):**
- `socket.io-client ^4.8.3` - Connects to ETA SPOT IRM (Instant Replay Manager) websocket for historical data collection; `ETA-Model/package.json`
- `gtfs-realtime-bindings` - Protobuf decoding in `Code/etaspot_reference.ts`

**TypeScript (weather fetcher):**
- `openmeteo` (via `fetchWeatherApi`) - Fetches historical weather from Open-Meteo API; `ETA-Model/getWeatherData.ts`

## Configuration

**Environment:**
- Supabase local dev configured in `supabase/config.toml`; project_id = `Senior_Design`
- Supabase API at `http://127.0.0.1:54321`, DB at port 54322, Studio at 54323
- Auth JWT expiry: 3600s; email signup enabled; anonymous sign-ins disabled
- ML training configured in `ETA-Model/config/training_config.yaml`

**Build:**
- No build step for Python scripts - run directly with `python scripts/<name>.py`
- Node.js scripts run as ESM: `node ETA-Model/batchCollector.js`
- FastAPI server: `uvicorn api.server:app --host 0.0.0.0 --port 8000`
- Supabase local dev: `supabase start` (uses Docker internally)

**Key env vars (from supabase config.toml - names only):**
- `OPENAI_API_KEY` - Supabase Studio AI features
- `SUPABASE_AUTH_SMS_TWILIO_AUTH_TOKEN` - SMS OTP (disabled)
- `SUPABASE_AUTH_EXTERNAL_APPLE_SECRET` - Apple OAuth (disabled)
- `S3_HOST`, `S3_REGION`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` - Experimental S3/OrioleDB (disabled)

## Platform Requirements

**Development:**
- Windows (confirmed: `venv\Scripts\activate` in requirements comments, `monitor_collector.ps1` PowerShell script, `num_workers: 0` for Windows in training config)
- Docker Desktop required for Supabase local development
- Python 3.10+
- Node.js with ESM support

**Production:**
- PostgreSQL 17 (Supabase hosted or self-hosted)
- Python runtime for FastAPI prediction server
- CUDA-capable GPU recommended for PyTorch model training (optional)

---

*Stack analysis: 2026-03-25*
