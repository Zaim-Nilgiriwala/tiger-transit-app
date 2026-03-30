"""
Comprehensive data quality checks for the data preparation pipeline.

Validates input data, feature calculations, label creation, and generates
quality reports.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

from .config import (
    DATA_PATHS,
    QUALITY_THRESHOLDS,
    ROLLING_WINDOWS,
    FEATURE_COLUMNS,
    TARGET_COLUMN,
    EXCLUDED_VEHICLE_PREFIXES,
)


def check_input_quality(
    telemetry_df: pd.DataFrame,
    arrivals_df: pd.DataFrame = None,
    weather_df: pd.DataFrame = None
) -> Dict[str, Any]:
    """
    Run quality checks on input data before processing.

    Args:
        telemetry_df: Raw telemetry DataFrame
        arrivals_df: Arrivals DataFrame (optional)
        weather_df: Weather DataFrame (optional)

    Returns:
        Dictionary with quality check results
    """
    report = {}

    # Telemetry checks
    report['telemetry'] = {}
    report['telemetry']['total_records'] = len(telemetry_df)

    if 'timestamp_ms' in telemetry_df.columns:
        timestamps = pd.to_datetime(telemetry_df['timestamp_ms'], unit='ms')
        report['telemetry']['date_range_start'] = str(timestamps.min())
        report['telemetry']['date_range_end'] = str(timestamps.max())

    if 'vid' in telemetry_df.columns:
        report['telemetry']['unique_vehicles'] = telemetry_df['vid'].nunique()
        report['telemetry']['vehicles_list'] = sorted(telemetry_df['vid'].unique().tolist())

        # Count excluded vehicles
        pattern = '|'.join(EXCLUDED_VEHICLE_PREFIXES)
        excluded_mask = telemetry_df['vid'].str.contains(pattern, case=False, na=False)
        report['telemetry']['excluded_vehicles_count'] = excluded_mask.sum()
        report['telemetry']['excluded_vehicles_pct'] = excluded_mask.mean() * 100

    # Check for required columns
    required_cols = ['vid', 'timestamp_ms', 'lat', 'lon', 'speed_mph']
    report['telemetry']['missing_required_cols'] = [
        c for c in required_cols if c not in telemetry_df.columns
    ]

    # Arrivals checks
    if arrivals_df is not None and len(arrivals_df) > 0:
        report['arrivals'] = {}
        report['arrivals']['total_records'] = len(arrivals_df)

        if 'DATE' in arrivals_df.columns:
            report['arrivals']['date_range_start'] = arrivals_df['DATE'].min()
            report['arrivals']['date_range_end'] = arrivals_df['DATE'].max()

        if 'Vehicle ID' in arrivals_df.columns:
            report['arrivals']['unique_vehicles'] = arrivals_df['Vehicle ID'].nunique()

        if 'Station' in arrivals_df.columns:
            report['arrivals']['unique_stops'] = arrivals_df['Station'].nunique()

    # Weather checks
    if weather_df is not None and len(weather_df) > 0:
        report['weather'] = {}
        report['weather']['total_hours'] = len(weather_df)

        if 'time' in weather_df.columns or 'hour' in weather_df.columns:
            time_col = 'hour' if 'hour' in weather_df.columns else 'time'
            report['weather']['date_range_start'] = str(weather_df[time_col].min())
            report['weather']['date_range_end'] = str(weather_df[time_col].max())

    return report


def verify_filters(
    df_before: pd.DataFrame,
    df_after: pd.DataFrame,
    vid_column: str = 'vid'
) -> Dict[str, Any]:
    """
    Verify jAUnt and Shuttle exclusion worked correctly.

    Args:
        df_before: DataFrame before filtering
        df_after: DataFrame after filtering
        vid_column: Name of vehicle ID column

    Returns:
        Dictionary with verification results

    Raises:
        AssertionError: If excluded vehicles are still present
    """
    pattern = '|'.join(EXCLUDED_VEHICLE_PREFIXES)

    # Count excluded vehicles before and after
    excluded_before = df_before[df_before[vid_column].str.contains(pattern, case=False, na=False)]
    excluded_after = df_after[df_after[vid_column].str.contains(pattern, case=False, na=False)]

    # This must be zero
    if len(excluded_after) > 0:
        remaining = excluded_after[vid_column].unique().tolist()
        raise AssertionError(
            f"Filter FAILED: {len(excluded_after)} records with excluded vehicles still present.\n"
            f"Vehicles: {remaining[:10]}"
        )

    return {
        'records_before_filter': len(df_before),
        'records_after_filter': len(df_after),
        'excluded_count': len(excluded_before),
        'exclusion_rate': len(excluded_before) / len(df_before) * 100 if len(df_before) > 0 else 0,
        'filter_passed': True,
    }


def check_feature_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check quality of computed features.

    Args:
        df: DataFrame with computed features

    Returns:
        Dictionary with feature quality metrics
    """
    report = {}

    # Missing values per feature
    missing_counts = df.isnull().sum()
    missing_rates = df.isnull().mean() * 100

    report['missing_by_feature'] = {
        col: int(count) for col, count in missing_counts.items() if count > 0
    }
    report['missing_rate_by_feature'] = {
        col: float(rate) for col, rate in missing_rates.items() if rate > 0
    }

    # Feature statistics for numeric columns
    numeric_cols = df.select_dtypes(include=[np.number]).columns
    stats = df[numeric_cols].describe()
    report['feature_stats'] = stats.to_dict()

    # Specific range checks
    report['range_checks'] = {}

    # Speed checks
    if 'speed_mph' in df.columns:
        speed = df['speed_mph']
        out_of_range = (speed < 0) | (speed > 80)
        report['range_checks']['speed_out_of_range_count'] = int(out_of_range.sum())
        report['range_checks']['speed_out_of_range_rate'] = float(out_of_range.mean() * 100)

    # Lat/Lon checks
    thresholds = QUALITY_THRESHOLDS
    if 'lat' in df.columns:
        lat = df['lat']
        out_of_range = (lat < thresholds['lat_min']) | (lat > thresholds['lat_max'])
        report['range_checks']['lat_out_of_range_count'] = int(out_of_range.sum())

    if 'lon' in df.columns:
        lon = df['lon']
        out_of_range = (lon < thresholds['lon_min']) | (lon > thresholds['lon_max'])
        report['range_checks']['lon_out_of_range_count'] = int(out_of_range.sum())

    # Progress check
    if 'progress_to_next_stop' in df.columns:
        progress = df['progress_to_next_stop']
        out_of_range = (progress < -1) | (progress > 1)
        report['range_checks']['progress_out_of_range_count'] = int(out_of_range.sum())

    # Rolling feature checks
    report['rolling_checks'] = {}
    for window in ROLLING_WINDOWS:
        col = f'speed_avg_{window}s'
        if col in df.columns:
            report['rolling_checks'][f'{col}_nulls'] = int(df[col].isnull().sum())
            report['rolling_checks'][f'{col}_negative'] = int((df[col] < 0).sum())

        col = f'distance_traveled_{window}s'
        if col in df.columns:
            report['rolling_checks'][f'{col}_negative'] = int((df[col] < 0).sum())

    return report


def check_label_quality(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Check quality of created labels.

    Args:
        df: DataFrame with time_to_arrival_sec column

    Returns:
        Dictionary with label quality metrics
    """
    report = {}

    if TARGET_COLUMN not in df.columns:
        return {'error': f'{TARGET_COLUMN} column not found'}

    labels = df[TARGET_COLUMN]

    # Label coverage
    report['label_count'] = int(labels.notna().sum())
    report['label_missing'] = int(labels.isna().sum())
    report['label_missing_rate'] = float(labels.isna().mean() * 100)

    # Range statistics
    valid_labels = labels.dropna()
    if len(valid_labels) > 0:
        report['label_min'] = float(valid_labels.min())
        report['label_max'] = float(valid_labels.max())
        report['label_mean'] = float(valid_labels.mean())
        report['label_median'] = float(valid_labels.median())
        report['label_std'] = float(valid_labels.std())

        # Outlier detection
        report['labels_negative'] = int((valid_labels < 0).sum())
        report['labels_over_1hour'] = int((valid_labels > 3600).sum())
        report['labels_over_30min'] = int((valid_labels > 1800).sum())

        # Distribution buckets
        report['distribution'] = {
            '0-60s': int(((valid_labels >= 0) & (valid_labels < 60)).sum()),
            '60-300s': int(((valid_labels >= 60) & (valid_labels < 300)).sum()),
            '300-600s': int(((valid_labels >= 300) & (valid_labels < 600)).sum()),
            '600-1800s': int(((valid_labels >= 600) & (valid_labels < 1800)).sum()),
            '1800-3600s': int(((valid_labels >= 1800) & (valid_labels <= 3600)).sum()),
        }

    return report


def check_final_dataset(df: pd.DataFrame) -> Dict[str, Any]:
    """
    Comprehensive check of the final dataset before saving.

    Args:
        df: Final DataFrame ready for export

    Returns:
        Dictionary with overall quality metrics
    """
    report = {}

    report['total_records'] = len(df)
    report['total_features'] = len(df.columns) - 1  # Exclude target

    # Label presence
    if TARGET_COLUMN in df.columns:
        report['labeled_records'] = int(df[TARGET_COLUMN].notna().sum())
        report['label_coverage'] = float(df[TARGET_COLUMN].notna().mean() * 100)

    # Feature completeness
    feature_cols = [c for c in df.columns if c != TARGET_COLUMN and c not in ['row_id', 'vid', 'timestamp_ms', 'target_stop_id']]
    complete_rows = df[feature_cols].notna().all(axis=1).sum()
    report['complete_feature_rows'] = int(complete_rows)
    report['feature_completeness_rate'] = float(complete_rows / len(df) * 100) if len(df) > 0 else 0

    # Check all expected features are present
    expected_features = set(FEATURE_COLUMNS)
    actual_features = set(df.columns)
    report['missing_expected_features'] = list(expected_features - actual_features)
    report['extra_features'] = list(actual_features - expected_features - {TARGET_COLUMN, 'row_id', 'vid', 'timestamp_ms', 'target_stop_id'})

    # Vehicle coverage
    if 'vid' in df.columns:
        report['unique_vehicles'] = df['vid'].nunique()

    # Route coverage
    if 'route_id' in df.columns:
        report['unique_routes'] = df['route_id'].nunique()
        report['records_by_route'] = df['route_id'].value_counts().to_dict()

    return report


def generate_quality_report(all_checks: Dict[str, Any], output_file: Path = None) -> str:
    """
    Generate comprehensive quality report as markdown.

    Args:
        all_checks: Dictionary with all quality check results
        output_file: Optional path to save report

    Returns:
        Markdown-formatted quality report string
    """
    report = []
    report.append("# Data Quality Report")
    report.append(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Summary
    report.append("\n## Summary")
    if 'final' in all_checks:
        final = all_checks['final']
        report.append(f"- Total records: {final.get('total_records', 'N/A'):,}")
        report.append(f"- Labeled records: {final.get('labeled_records', 'N/A'):,}")
        report.append(f"- Label coverage: {final.get('label_coverage', 0):.1f}%")
        report.append(f"- Feature completeness: {final.get('feature_completeness_rate', 0):.1f}%")

    # Warnings
    report.append("\n## Warnings")
    warnings_found = False

    if 'labels' in all_checks:
        labels = all_checks['labels']
        if labels.get('labels_negative', 0) > 0:
            report.append(f"- WARNING: {labels['labels_negative']} negative labels found")
            warnings_found = True
        if labels.get('label_missing_rate', 0) > QUALITY_THRESHOLDS['max_label_missing_rate']:
            report.append(f"- WARNING: Label missing rate ({labels['label_missing_rate']:.1f}%) exceeds threshold ({QUALITY_THRESHOLDS['max_label_missing_rate']}%)")
            warnings_found = True

    if 'features' in all_checks:
        features = all_checks['features']
        range_checks = features.get('range_checks', {})
        if range_checks.get('speed_out_of_range_rate', 0) > QUALITY_THRESHOLDS['max_speed_out_of_range_rate']:
            report.append(f"- WARNING: Speed out of range rate ({range_checks['speed_out_of_range_rate']:.1f}%) exceeds threshold")
            warnings_found = True

    if 'final' in all_checks:
        final = all_checks['final']
        if final.get('missing_expected_features'):
            report.append(f"- WARNING: Missing expected features: {final['missing_expected_features']}")
            warnings_found = True

    if not warnings_found:
        report.append("- No warnings - all quality checks passed")

    # Input data summary
    if 'input' in all_checks:
        report.append("\n## Input Data")
        input_checks = all_checks['input']

        if 'telemetry' in input_checks:
            tel = input_checks['telemetry']
            report.append("\n### Telemetry")
            report.append(f"- Records: {tel.get('total_records', 'N/A'):,}")
            report.append(f"- Vehicles: {tel.get('unique_vehicles', 'N/A')}")
            report.append(f"- Date range: {tel.get('date_range_start', 'N/A')} to {tel.get('date_range_end', 'N/A')}")
            report.append(f"- Excluded vehicles (jAUnt/Shuttle): {tel.get('excluded_vehicles_count', 0):,} ({tel.get('excluded_vehicles_pct', 0):.1f}%)")

        if 'arrivals' in input_checks:
            arr = input_checks['arrivals']
            report.append("\n### Arrivals")
            report.append(f"- Records: {arr.get('total_records', 'N/A'):,}")
            report.append(f"- Vehicles: {arr.get('unique_vehicles', 'N/A')}")
            report.append(f"- Stops: {arr.get('unique_stops', 'N/A')}")

        if 'weather' in input_checks:
            wx = input_checks['weather']
            report.append("\n### Weather")
            report.append(f"- Hours: {wx.get('total_hours', 'N/A')}")
            report.append(f"- Date range: {wx.get('date_range_start', 'N/A')} to {wx.get('date_range_end', 'N/A')}")

    # Label distribution
    if 'labels' in all_checks:
        report.append("\n## Label Statistics")
        labels = all_checks['labels']
        report.append(f"- Total labels: {labels.get('label_count', 0):,}")
        report.append(f"- Missing: {labels.get('label_missing', 0):,} ({labels.get('label_missing_rate', 0):.1f}%)")
        if 'label_mean' in labels:
            report.append(f"- Mean: {labels.get('label_mean', 0):.1f}s")
            report.append(f"- Median: {labels.get('label_median', 0):.1f}s")
            report.append(f"- Std: {labels.get('label_std', 0):.1f}s")
            report.append(f"- Range: {labels.get('label_min', 0):.1f}s - {labels.get('label_max', 0):.1f}s")

        if 'distribution' in labels:
            report.append("\n### Label Distribution")
            for bucket, count in labels['distribution'].items():
                report.append(f"- {bucket}: {count:,}")

    # Feature quality
    if 'features' in all_checks:
        report.append("\n## Feature Quality")
        features = all_checks['features']

        if features.get('missing_by_feature'):
            report.append("\n### Missing Values")
            for feat, count in sorted(features['missing_by_feature'].items(), key=lambda x: -x[1])[:10]:
                rate = features['missing_rate_by_feature'].get(feat, 0)
                report.append(f"- {feat}: {count:,} ({rate:.1f}%)")

    report_str = '\n'.join(report)

    # Save if output file provided
    if output_file:
        output_file = Path(output_file)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(report_str)
        print(f"Quality report saved to {output_file}")

    return report_str
