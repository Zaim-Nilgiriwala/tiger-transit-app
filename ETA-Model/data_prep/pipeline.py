"""
Main data preparation pipeline orchestrator.

Coordinates all steps of the data preparation process from raw telemetry
and arrivals data to final train/val/test Parquet files.
"""

import json
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import pandas as pd
from tqdm import tqdm

from .config import (
    DATA_PATHS,
    TELEMETRY_FIELDS_KEEP,
    SPLIT_RATIOS,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    CATEGORICAL_COLUMNS,
    CATEGORICAL_DTYPES,
    ID_COLUMNS,
)
from .filters import filter_vehicles, filter_active_trips, verify_filters
from .rolling_features import compute_rolling_features
from .distance_features import compute_distance_features, GTFSDistanceCalculator
from .temporal_features import compute_temporal_features, add_scheduled_baseline
from .weather_features import load_weather_data, join_weather_data
from .historical_stats import compute_historical_stats, save_historical_stats, join_historical_features
from .label_creator import create_labels, build_stop_name_mapping
from .data_quality import (
    check_input_quality,
    check_feature_quality,
    check_label_quality,
    check_final_dataset,
    generate_quality_report,
)


def load_telemetry_file(file_path: Path) -> pd.DataFrame:
    """
    Load a single JSONL telemetry file and extract relevant fields.

    Args:
        file_path: Path to JSONL file

    Returns:
        DataFrame with extracted and renamed fields
    """
    records = []

    with open(file_path, 'r') as f:
        for line in f:
            try:
                data = json.loads(line.strip())
                record = extract_telemetry_fields(data)
                if record:
                    records.append(record)
            except json.JSONDecodeError:
                continue

    return pd.DataFrame(records)


def extract_telemetry_fields(data: dict) -> Optional[dict]:
    """
    Extract and flatten relevant fields from a telemetry packet.

    Args:
        data: Raw telemetry JSON object

    Returns:
        Dictionary with extracted fields, or None if invalid
    """
    record = {}

    # Direct fields
    record['vid'] = data.get('vid', '')
    record['timestamp_ms'] = data.get('t') or data.get('ts', 0)
    record['lat'] = data.get('lt', 0)
    record['lon'] = data.get('ln', 0)
    record['heading'] = data.get('h', 0)
    record['speed_mph'] = data.get('v', 0)
    record['passenger_count'] = data.get('load', 0)
    record['vehicle_capacity'] = data.get('capacity', 0)

    # Service state (nested)
    service_state = data.get('serviceState', {})
    record['route_id'] = service_state.get('rID', 0)
    record['service_status'] = service_state.get('status', 0)
    record['pattern_id'] = service_state.get('patternID', 0)
    record['trip_id'] = service_state.get('tripID', '')
    record['progress_to_next_stop'] = service_state.get('nextStopPercentProgress', 0)

    # Last stop (nested)
    last_stop = data.get('lastStop', {})
    record['last_stop_id'] = last_stop.get('stopID', 0)
    record['last_stop_time_ms'] = last_stop.get('time', 0)
    record['current_delay_sec'] = last_stop.get('onTime', 0)

    # ETA info (nested)
    eta = data.get('eta', {})
    record['target_stop_id'] = eta.get('stopID', 0)

    # Schedule info (nested) - store as-is for later parsing
    schedule = data.get('schedule', {})
    record['schedule_stops'] = schedule.get('stops', [])

    # Skip invalid records
    if not record['vid'] or not record['timestamp_ms']:
        return None

    return record


def load_all_telemetry(telemetry_dir: Path = None, file_pattern: str = '*.jsonl') -> pd.DataFrame:
    """
    Load all telemetry files from a directory.

    Args:
        telemetry_dir: Directory containing JSONL files
        file_pattern: Glob pattern for telemetry files

    Returns:
        Combined DataFrame from all files
    """
    if telemetry_dir is None:
        telemetry_dir = DATA_PATHS['telemetry_dir']

    telemetry_dir = Path(telemetry_dir)
    files = sorted(telemetry_dir.glob(file_pattern))

    if not files:
        print(f"Warning: No telemetry files found in {telemetry_dir}")
        return pd.DataFrame()

    print(f"Loading {len(files)} telemetry files...")

    dfs = []
    for file_path in tqdm(files, desc="Loading telemetry"):
        df = load_telemetry_file(file_path)
        if len(df) > 0:
            dfs.append(df)

    if not dfs:
        return pd.DataFrame()

    combined = pd.concat(dfs, ignore_index=True)
    print(f"Loaded {len(combined):,} telemetry records")

    return combined


def time_based_split(df: pd.DataFrame, timestamp_col: str = 'timestamp_ms') -> tuple:
    """
    Split data by time into train/val/test sets.

    Args:
        df: DataFrame to split
        timestamp_col: Name of timestamp column

    Returns:
        Tuple of (train_df, val_df, test_df)
    """
    # Sort by timestamp
    df = df.sort_values(timestamp_col)

    n = len(df)
    train_end = int(n * SPLIT_RATIOS['train'])
    val_end = train_end + int(n * SPLIT_RATIOS['val'])

    train_df = df.iloc[:train_end].copy()
    val_df = df.iloc[train_end:val_end].copy()
    test_df = df.iloc[val_end:].copy()

    return train_df, val_df, test_df


def optimize_dtypes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Optimize data types for efficient storage.

    Args:
        df: DataFrame to optimize

    Returns:
        DataFrame with optimized dtypes
    """
    df = df.copy()

    # Float columns to float32
    for col in df.select_dtypes(include=['float64']).columns:
        df[col] = df[col].astype('float32')

    # Categorical columns to specified types
    for col, dtype in CATEGORICAL_DTYPES.items():
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(dtype)

    # Boolean columns to int8
    for col in df.select_dtypes(include=['bool']).columns:
        df[col] = df[col].astype('int8')

    return df


class DataPipeline:
    """
    Main data preparation pipeline.

    Orchestrates all steps from raw data to final train/val/test splits.
    """

    def __init__(
        self,
        telemetry_dir: Path = None,
        arrivals_files: List[Path] = None,
        weather_file: Path = None,
        output_dir: Path = None,
        gtfs_dir: Path = None,
    ):
        """
        Initialize the pipeline.

        Args:
            telemetry_dir: Directory containing JSONL telemetry files
            arrivals_files: List of arrivals CSV files
            weather_file: Path to weather CSV file
            output_dir: Directory for output files
            gtfs_dir: Directory containing GTFS files
        """
        self.telemetry_dir = telemetry_dir or DATA_PATHS['telemetry_dir']
        self.arrivals_files = arrivals_files or DATA_PATHS['arrivals_files']
        self.weather_file = weather_file or DATA_PATHS['weather_file']
        self.output_dir = output_dir or DATA_PATHS['output_dir']
        self.gtfs_dir = gtfs_dir or DATA_PATHS['gtfs_dir']

        # Ensure output dir exists
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        # Initialize components
        self.gtfs_calculator = None
        self.weather_df = None
        self.historical_stats = None

        # Quality check results
        self.quality_checks = {}

    def run(self, show_progress: bool = True) -> Dict[str, Path]:
        """
        Run the complete pipeline.

        Args:
            show_progress: Whether to show progress bars

        Returns:
            Dictionary with paths to output files
        """
        print("=" * 60)
        print("GBDT ETA Model - Data Preparation Pipeline")
        print("=" * 60)

        # Step 1: Load raw data
        print("\n[Step 1/9] Loading raw telemetry data...")
        df = load_all_telemetry(self.telemetry_dir)

        if df.empty:
            raise ValueError("No telemetry data loaded")

        # Step 2: Check input quality
        print("\n[Step 2/9] Checking input data quality...")
        self.weather_df = load_weather_data(self.weather_file)
        self.quality_checks['input'] = check_input_quality(df, weather_df=self.weather_df)

        # Step 3: Filter vehicles and trips
        print("\n[Step 3/9] Filtering vehicles and trips...")
        df_original = df.copy()
        df = filter_vehicles(df)
        df = filter_active_trips(df)
        self.quality_checks['filters'] = verify_filters(df_original, df)
        print(f"  Filtered: {len(df_original):,} -> {len(df):,} records")

        # Step 4: Compute historical statistics
        print("\n[Step 4/9] Computing historical statistics from arrivals...")
        self.historical_stats = compute_historical_stats(self.arrivals_files)
        save_historical_stats(self.historical_stats)

        # Step 5: Add row IDs and transform heading
        print("\n[Step 5/9] Transforming core features...")
        df['row_id'] = range(len(df))
        df['heading_sin'] = np.sin(np.radians(df['heading']))
        df['heading_cos'] = np.cos(np.radians(df['heading']))

        # Step 6: Compute rolling features
        print("\n[Step 6/9] Computing rolling window features...")
        df = compute_rolling_features(df, show_progress=show_progress)

        # Step 7: Compute distance features
        print("\n[Step 7/9] Computing distance features...")
        self.gtfs_calculator = GTFSDistanceCalculator(self.gtfs_dir)
        df = compute_distance_features(df, self.gtfs_calculator, show_progress=show_progress)

        # Step 8: Compute temporal features
        print("\n[Step 8/9] Computing temporal features...")
        df = compute_temporal_features(df)
        df = add_scheduled_baseline(df)

        # Step 9: Join weather data
        print("\n[Step 9/9] Joining weather and historical data...")
        df = join_weather_data(df, self.weather_df)
        df = join_historical_features(df, self.historical_stats)

        # Check feature quality
        self.quality_checks['features'] = check_feature_quality(df)

        # Create labels
        print("\n[Labeling] Creating ground truth labels from arrivals...")
        df = create_labels(df, self.arrivals_files, show_progress=show_progress)
        self.quality_checks['labels'] = check_label_quality(df)

        # Filter to only labeled records for training
        labeled_df = df[df[TARGET_COLUMN].notna()].copy()
        print(f"  Labeled records: {len(labeled_df):,} of {len(df):,}")

        # Final quality check
        self.quality_checks['final'] = check_final_dataset(labeled_df)

        # Time-based split
        print("\n[Splitting] Creating train/val/test splits...")
        train_df, val_df, test_df = time_based_split(labeled_df)
        print(f"  Train: {len(train_df):,} | Val: {len(val_df):,} | Test: {len(test_df):,}")

        # Optimize dtypes
        print("\n[Optimizing] Optimizing data types...")
        train_df = optimize_dtypes(train_df)
        val_df = optimize_dtypes(val_df)
        test_df = optimize_dtypes(test_df)

        # Save to Parquet
        print("\n[Saving] Writing Parquet files...")
        output_paths = self._save_outputs(train_df, val_df, test_df)

        # Generate quality report
        print("\n[Report] Generating quality report...")
        report = generate_quality_report(
            self.quality_checks,
            output_file=DATA_PATHS['quality_report']
        )

        print("\n" + "=" * 60)
        print("Pipeline completed successfully!")
        print("=" * 60)

        return output_paths

    def _save_outputs(
        self,
        train_df: pd.DataFrame,
        val_df: pd.DataFrame,
        test_df: pd.DataFrame
    ) -> Dict[str, Path]:
        """
        Save train/val/test DataFrames to Parquet.

        Args:
            train_df: Training data
            val_df: Validation data
            test_df: Test data

        Returns:
            Dictionary with paths to output files
        """
        output_dir = Path(self.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Select columns to save (features + target + IDs)
        save_cols = ID_COLUMNS + FEATURE_COLUMNS + [TARGET_COLUMN]
        save_cols = [c for c in save_cols if c in train_df.columns]

        paths = {}

        # Train
        train_path = output_dir / 'train.parquet'
        train_df[save_cols].to_parquet(train_path, index=False)
        paths['train'] = train_path
        print(f"  Saved train: {train_path}")

        # Val
        val_path = output_dir / 'val.parquet'
        val_df[save_cols].to_parquet(val_path, index=False)
        paths['val'] = val_path
        print(f"  Saved val: {val_path}")

        # Test
        test_path = output_dir / 'test.parquet'
        test_df[save_cols].to_parquet(test_path, index=False)
        paths['test'] = test_path
        print(f"  Saved test: {test_path}")

        # Save column info
        meta_path = output_dir / 'metadata.json'
        metadata = {
            'feature_columns': FEATURE_COLUMNS,
            'target_column': TARGET_COLUMN,
            'categorical_columns': CATEGORICAL_COLUMNS,
            'id_columns': ID_COLUMNS,
            'train_records': len(train_df),
            'val_records': len(val_df),
            'test_records': len(test_df),
            'created_at': datetime.now().isoformat(),
        }
        with open(meta_path, 'w') as f:
            json.dump(metadata, f, indent=2)
        paths['metadata'] = meta_path
        print(f"  Saved metadata: {meta_path}")

        return paths
