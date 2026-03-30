# GBDT ETA Model - Data Preparation Pipeline

## Overview

This pipeline transforms raw telemetry JSONL files and arrivals CSVs into training-ready Parquet datasets for a Gradient Boosted Decision Tree (GBDT) model that predicts **time until bus arrival at a stop** (in seconds).

## Architecture

```
live_data/*.jsonl (raw telemetry)
raw_data/Arrivals*.csv (ground truth)
raw_data/weather_data.csv (hourly weather)
gtfs_data/ (route shapes)
stops.json (stop ID/name mapping)
        │
        ▼
┌──────────────────────────────┐
│  data_prep/pipeline.py       │
│  (orchestrator)              │
│                              │
│  Step 1: Load JSONL          │  ← pipeline.load_all_telemetry()
│  Step 2: Input quality check │  ← data_quality.check_input_quality()
│  Step 3: Filter vehicles     │  ← filters.filter_vehicles() + filter_active_trips()
│  Step 4: Historical stats    │  ← historical_stats.compute_historical_stats()
│  Step 5: Core transforms     │  ← heading → sin/cos
│  Step 6: Rolling features    │  ← rolling_features.compute_rolling_features()
│  Step 7: Distance features   │  ← distance_features.compute_distance_features()
│  Step 8: Temporal features   │  ← temporal_features.compute_temporal_features()
│  Step 9: Weather + history   │  ← weather_features + historical_stats join
│  Label: Join with arrivals   │  ← label_creator.create_labels()
│  Split: Time-based 70/15/15  │
│  Save: Parquet + metadata    │
└──────────────────────────────┘
        │
        ▼
data_prep/output/
  ├── train.parquet
  ├── val.parquet
  ├── test.parquet
  ├── metadata.json
  ├── historical_stats.json
  └── quality_report.md
```

## Module Reference

| Module | Purpose |
|--------|---------|
| `config.py` | All constants: file paths, feature lists, thresholds, split ratios, vehicle exclusion list |
| `filters.py` | Excludes jAUnt/Shuttle vehicles, filters to active trips (status 7/71), removes NIS patterns |
| `rolling_features.py` | Rolling window stats (30s–300s): speed avg/std/min/max, distance traveled, heading change |
| `distance_features.py` | GTFS route distance (miles), Haversine fallback (meters), stops remaining count |
| `temporal_features.py` | Hour, day of week, cyclical time encoding, rush hour/class change flags, minutes since last stop |
| `weather_features.py` | Loads hourly weather CSV, joins on truncated hour, adds temperature/precipitation/is_raining |
| `historical_stats.py` | Pre-computes from arrivals: segment travel times, stop dwell times, vehicle speed factors |
| `label_creator.py` | Matches telemetry to next arrival at target stop → `time_to_arrival_sec` (0–3600s) |
| `data_quality.py` | Input checks, filter verification, feature/label quality, markdown report generation |
| `pipeline.py` | `DataPipeline` class orchestrating all steps end-to-end |
| `run_pipeline.py` | CLI entry point with argparse |

## Features Produced (~52 total)

### Core Features (8)
`lat`, `lon`, `speed_mph`, `heading_sin`, `heading_cos`, `passenger_count`, `progress_to_next_stop`, `current_delay_sec`

### Rolling Window Features (36 = 6 metrics × 6 windows)
For each window in [30s, 60s, 90s, 120s, 180s, 300s]:
- `speed_avg_{W}s`, `speed_std_{W}s`, `speed_max_{W}s`, `speed_min_{W}s`
- `distance_traveled_{W}s`, `heading_change_{W}s`

### Distance Features (3)
`route_distance_to_stop_miles`, `haversine_distance_to_stop_m`, `stops_remaining`

### Temporal Features (9)
`hour_of_day`, `minute_of_hour`, `time_of_day_sin`, `time_of_day_cos`, `day_of_week`, `is_weekend`, `is_rush_hour`, `is_class_change`, `minutes_since_last_stop`

### Historical Features (4)
`segment_avg_travel_time_sec`, `segment_std_travel_time_sec`, `stop_avg_dwell_time_sec`, `vehicle_speed_factor`

### Weather Features (4)
`temperature_c`, `precipitation_mm`, `precipitation_probability`, `is_raining`

### Baseline (1)
`scheduled_time_to_stop_sec`

### Route (1, categorical)
`route_id`

### Target
`time_to_arrival_sec` — ground truth from arrivals data

## Vehicle Filtering

Only numbered buses (e.g., `21-120`, `21-117`) are kept. These are excluded:
- Any vehicle ID containing `jAUnt` (demand-response service)
- Any vehicle ID containing `Shuttle` (different operating characteristics)

## GBDT-Specific Design Choices

- **No normalization** — GBDT splits on raw values; normalization adds no benefit
- **NaN values preserved** — LightGBM/XGBoost handle missing values natively
- **Categorical columns typed** — `hour_of_day`, `day_of_week`, `route_id` stored as int8/int16
- **Float32 precision** — All continuous features stored as float32 (saves ~50% disk)

## Input Files Required

| File | Location | Purpose |
|------|----------|---------|
| `live_data/*.jsonl` | Telemetry JSONL files | Bus GPS/status packets |
| `raw_data/Arrivals*.csv` | Arrivals CSVs (skip row 1 header) | Ground truth stop arrivals |
| `raw_data/weather_data.csv` | Hourly weather | Temperature, precipitation |
| `stops.json` | Project root | Stop ID ↔ Name mapping |
| `gtfs_data/shapes.txt` | GTFS directory | Route geometry for distances |
| `gtfs_data/trips.txt` | GTFS directory | Trip → shape mapping |
| `gtfs_data/stop_times.txt` | GTFS directory | Stop distances along route |

## Usage

```bash
# From the ETA-Model directory:
python -m data_prep.run_pipeline

# Custom paths:
python -m data_prep.run_pipeline --telemetry-dir ./live_data --output-dir ./my_output

# Disable progress bars (for logging):
python -m data_prep.run_pipeline --no-progress
```

### CLI Options

| Flag | Default | Description |
|------|---------|-------------|
| `--telemetry-dir` | `live_data/` | Directory with JSONL telemetry files |
| `--output-dir` | `data_prep/output/` | Where to write Parquet files |
| `--gtfs-dir` | `gtfs_data/` | GTFS data directory |
| `--weather-file` | `raw_data/weather_data.csv` | Hourly weather CSV |
| `--arrivals-files` | Both CSVs in `raw_data/` | Space-separated list of arrivals CSVs |
| `--no-progress` | False | Disable tqdm progress bars |

## Quality Report

After running, check `data_prep/output/quality_report.md` for:
- Input data coverage (records, vehicles, date ranges)
- Filter verification (confirms jAUnt/Shuttle excluded)
- Feature range checks (speed, lat/lon, progress)
- Label distribution (buckets: 0–60s, 60–300s, 300–600s, etc.)
- Missing value analysis per feature

### Quality Thresholds (pipeline warns if violated)

| Check | Threshold |
|-------|-----------|
| Join success rate (telemetry → arrivals) | > 50% |
| Label missing rate | < 30% |
| Negative labels | = 0 |
| Excluded vehicles in output | = 0 |
| Weather missing rate | < 5% |
| Speed out of range (0–80 mph) | < 1% |
